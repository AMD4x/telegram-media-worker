#!/usr/bin/env python3
"""Video compression worker for AD4x telegram-media-worker.

The script is intentionally self-contained so the new workflow can stay isolated
from the existing workflows while keeping the same progress-message philosophy.
"""

from __future__ import annotations

import atexit
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

WORK_DIR = Path("work")
PUBLIC_BOT_API_MAX_BYTES = 50_000_000
LOCAL_BOT_API_MAX_BYTES = 2_000_000_000


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def mask(value: str) -> None:
    if value:
        print(f"::add-mask::{value}")


def run_url() -> str:
    server = env("GITHUB_SERVER_URL", "https://github.com")
    repo = env("GITHUB_REPOSITORY", "AD4x/telegram-media-worker")
    run_id = env("GITHUB_RUN_ID", "unknown")
    return f"{server}/{repo}/actions/runs/{run_id}"


def format_bytes(value: int | str | None) -> str:
    try:
        n = max(int(value or 0), 0)
    except Exception:
        n = 0
    units = ["B", "KB", "MB", "GB"]
    if n < 1024:
        return f"{n} B"
    idx = min(int(math.log(max(n, 1), 1024)), len(units) - 1)
    return f"{n / (1024 ** idx):.2f} {units[idx]}"


def progress_bar(percent: int) -> str:
    percent = max(0, min(100, int(percent)))
    filled = percent * 10 // 100
    return "█" * filled + "░" * (10 - filled)


def safe_text(value: str) -> str:
    return html.escape(str(value), quote=False)


def clean_filename(value: str, fallback: str, ext: str) -> str:
    raw = urllib.parse.unquote((value or "").strip()) or fallback
    raw = raw.replace("\\", "/")
    name = os.path.basename(raw)
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = re.sub(r"[\/*?:\"<>|]", "", name)
    name = re.sub(r"\s+", " ", name).strip().strip(".") or fallback

    base, current_ext = os.path.splitext(name)
    if ext and current_ext.lower() != ext.lower():
        if ext.lower() == ".zip":
            name = f"{base or name}.zip"
        elif not current_ext or current_ext.lower() in {".zip", ".bin", ".webm", ".mkv", ".mov", ".m4v"}:
            name = f"{base or name}.mp4"

    base, current_ext = os.path.splitext(name)
    if len(name) > 120:
        base = base[: max(1, 120 - len(current_ext))].rstrip().strip(".")
        name = f"{base or 'video'}{current_ext}"
    return name


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def subprocess_run(args: list[str], *, check: bool = True, capture: bool = False, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    kwargs = {
        "text": True,
        "timeout": timeout,
    }
    if capture:
        kwargs.update({"stdout": subprocess.PIPE, "stderr": subprocess.PIPE})
    result = subprocess.run(args, **kwargs)
    if check and result.returncode != 0:
        stderr = (result.stderr or "").strip() if capture else ""
        raise RuntimeError(stderr or f"Command failed with exit code {result.returncode}: {args[0]}")
    return result


def curl_json(args: list[str], *, timeout: int | None = None) -> dict:
    result = subprocess_run(args, check=False, capture=True, timeout=timeout)
    raw = result.stdout or ""
    try:
        data = json.loads(raw)
    except Exception:
        data = {"ok": False, "description": raw[-500:] or (result.stderr or "curl failed")}
    if result.returncode != 0:
        data.setdefault("ok", False)
        data.setdefault("description", (result.stderr or "curl failed").strip())
    return data


@dataclass
class CompressionSettings:
    level: int
    crf: int
    preset: str
    audio_bitrate: str
    max_height: int
    maxrate: str
    bufsize: str
    level_tag: str


def compression_settings(level_text: str) -> CompressionSettings:
    try:
        level = int(str(level_text).strip())
    except Exception as exc:
        raise ValueError("compression_level must be an integer from 1 to 100.") from exc

    if level < 1 or level > 100:
        raise ValueError("compression_level must be between 1 and 100.")

    if level <= 10:
        return CompressionSettings(level, 18, "medium", "192k", 2160, "12000k", "24000k", "5.1")
    if level <= 30:
        crf = 20 + round((level - 11) * (2 / 19))
        return CompressionSettings(level, crf, "medium", "160k", 1440, "9000k", "18000k", "5.1")
    if level <= 50:
        crf = 23 + round((level - 31) * (3 / 19))
        return CompressionSettings(level, crf, "medium", "128k", 1080, "5500k", "11000k", "4.1")
    if level <= 75:
        crf = 27 + round((level - 51) * (3 / 24))
        return CompressionSettings(level, crf, "fast", "96k", 720, "3000k", "6000k", "4.1")

    crf = 31 + round((level - 76) * (5 / 24))
    preset = "slow" if level >= 90 else "medium"
    return CompressionSettings(level, crf, preset, "64k", 480, "1400k", "2800k", "3.1")


@dataclass
class ProbeInfo:
    width: str = ""
    height: str = ""
    duration: str = ""
    video_codec: str = ""
    audio_codec: str = ""


def probe_value(path: Path, selector: str, entry: str) -> str:
    result = subprocess_run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            selector,
            "-show_entries",
            f"stream={entry}",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=False,
        capture=True,
    )
    return (result.stdout or "").splitlines()[0].strip() if result.stdout else ""


def probe_duration(path: Path) -> str:
    result = subprocess_run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=False,
        capture=True,
    )
    raw = (result.stdout or "").splitlines()[0].strip() if result.stdout else ""
    try:
        return str(max(0, int(float(raw))))
    except Exception:
        return ""


def probe(path: Path) -> ProbeInfo:
    return ProbeInfo(
        width=probe_value(path, "v:0", "width"),
        height=probe_value(path, "v:0", "height"),
        duration=probe_duration(path),
        video_codec=probe_value(path, "v:0", "codec_name"),
        audio_codec=probe_value(path, "a:0", "codec_name"),
    )


class Telegram:
    def __init__(self, token: str, chat_id: str, progress_chat_id: str, progress_message_id: str) -> None:
        self.token = token
        self.chat_id = chat_id
        self.progress_chat_id = progress_chat_id or chat_id
        self.progress_message_id = progress_message_id
        self.local_process: subprocess.Popen[str] | None = None
        self.local_base = f"http://127.0.0.1:8081/bot{token}"
        self.public_base = f"https://api.telegram.org/bot{token}"

    def api_url(self, method: str, *, local: bool = False) -> str:
        return f"{self.local_base if local else self.public_base}/{method}"

    def send_message(self, text: str) -> str:
        if not self.progress_chat_id:
            return ""
        data = curl_json(
            [
                "curl",
                "-sS",
                "--connect-timeout",
                "10",
                "--max-time",
                "20",
                "-X",
                "POST",
                self.api_url("sendMessage"),
                "-d",
                f"chat_id={self.progress_chat_id}",
                "-d",
                "parse_mode=HTML",
                "-d",
                "disable_web_page_preview=true",
                "--data-urlencode",
                f"text={text}",
            ]
        )
        if data.get("ok"):
            return str(((data.get("result") or {}).get("message_id")) or "")
        return ""

    def ensure_progress_message(self) -> None:
        if self.progress_message_id or not self.progress_chat_id:
            return
        initial = self.progress_text(2, "Starting", "Preparing video compression workflow...")
        self.progress_message_id = self.send_message(initial)

    def progress_text(self, percent: int, status: str, detail: str) -> str:
        bar = progress_bar(percent)
        return (
            "🐙 <b>GitHub Remote</b>\n\n"
            f"📊 <code>[{bar}] {percent}%</code>\n"
            f"🧭 <b>Status:</b> {safe_text(status)}\n"
            f"ℹ️ <i>{safe_text(detail)}</i>\n"
            f"🆔 <code>{safe_text(env('GITHUB_RUN_ID', 'unknown'))}</code>\n"
            f"🔗 <a href=\"{safe_text(run_url())}\">Open Run</a>"
        )

    def update_progress(self, percent: int, status: str, detail: str) -> None:
        print(f"PROGRESS_PERCENT={percent}")
        print(f"PROGRESS_STATUS={status}")
        print(f"PROGRESS_DETAIL={detail}")
        if not self.progress_chat_id:
            return
        if not self.progress_message_id:
            self.ensure_progress_message()
        if not self.progress_message_id:
            return
        text = self.progress_text(percent, status, detail)
        curl_json(
            [
                "curl",
                "-sS",
                "--connect-timeout",
                "10",
                "--max-time",
                "20",
                "-X",
                "POST",
                self.api_url("editMessageText"),
                "-d",
                f"chat_id={self.progress_chat_id}",
                "-d",
                f"message_id={self.progress_message_id}",
                "-d",
                "parse_mode=HTML",
                "-d",
                "disable_web_page_preview=true",
                "--data-urlencode",
                f"text={text}",
            ]
        )

    def update_completed(
        self,
        *,
        send_as: str,
        send_method: str,
        message_id: str,
        source_size: int,
        final_size: int,
        settings: CompressionSettings,
        final_file_name: str,
        video_probe: ProbeInfo,
        platform: str,
    ) -> None:
        if not self.progress_chat_id or not self.progress_message_id:
            return
        settings_label = f"CRF {settings.crf} · {settings.preset} · {settings.audio_bitrate} · {settings.max_height}p"
        dimensions = "unknown"
        if video_probe.width and video_probe.height:
            dimensions = f"{video_probe.width}x{video_probe.height}"
        text = (
            "✅ <b>GitHub Video Compress completed.</b>\n\n"
            f"🌐 <b>Platform:</b> <code>{safe_text(platform)}</code>\n"
            "🧭 <b>Path:</b> <code>video-compress</code>\n"
            f"🎚️ <b>Compression:</b> <code>{settings.level}/100</code>\n"
            f"🧱 <b>Settings:</b> <code>{safe_text(settings_label)}</code>\n"
            f"📐 <b>Dimensions:</b> <code>{safe_text(dimensions)}</code>\n"
            f"📄 <b>File:</b> <code>{safe_text(final_file_name)}</code>\n"
            f"📥 <b>Downloaded Size:</b> <code>{format_bytes(source_size)}</code>\n"
            f"📦 <b>Final Size:</b> <code>{format_bytes(final_size)}</code> — OK\n"
            f"🚀 <b>Send Mode:</b> <code>{safe_text(send_as)}</code>\n"
            f"📤 <b>Send Method:</b> <code>{safe_text(send_method)}</code>\n"
        )
        if message_id:
            text += f"🆔 <b>Message ID:</b> <code>{safe_text(message_id)}</code>\n"
        text += f"🔗 <a href=\"{safe_text(run_url())}\">Open Run</a>"
        curl_json(
            [
                "curl",
                "-sS",
                "--connect-timeout",
                "10",
                "--max-time",
                "20",
                "-X",
                "POST",
                self.api_url("editMessageText"),
                "-d",
                f"chat_id={self.progress_chat_id}",
                "-d",
                f"message_id={self.progress_message_id}",
                "-d",
                "parse_mode=HTML",
                "-d",
                "disable_web_page_preview=true",
                "--data-urlencode",
                f"text={text}",
            ]
        )

    def update_failed(self, detail: str) -> None:
        if not self.progress_chat_id or not self.progress_message_id:
            return
        text = self.progress_text(100, "Failed", detail[:280])
        curl_json(
            [
                "curl",
                "-sS",
                "--connect-timeout",
                "10",
                "--max-time",
                "20",
                "-X",
                "POST",
                self.api_url("editMessageText"),
                "-d",
                f"chat_id={self.progress_chat_id}",
                "-d",
                f"message_id={self.progress_message_id}",
                "-d",
                "parse_mode=HTML",
                "-d",
                "disable_web_page_preview=true",
                "--data-urlencode",
                f"text={text}",
            ]
        )

    def start_local_api(self) -> None:
        if self.local_process:
            return
        api_id = env("TELEGRAM_API_ID")
        api_hash = env("TELEGRAM_API_HASH")
        if not api_id or not api_hash:
            raise RuntimeError("TELEGRAM_API_ID and TELEGRAM_API_HASH are required for files above the public Bot API safety limit.")
        if not command_exists("telegram-bot-api"):
            raise RuntimeError("telegram-bot-api binary is missing from the worker image.")

        temp_dir = Path(env("RUNNER_TEMP", tempfile.gettempdir())) / "telegram-bot-api-video-compress"
        temp_dir.mkdir(parents=True, exist_ok=True)
        log_path = temp_dir / "telegram-bot-api.log"
        self.local_process = subprocess.Popen(
            [
                "telegram-bot-api",
                f"--api-id={api_id}",
                f"--api-hash={api_hash}",
                "--local",
                "--http-ip-address=127.0.0.1",
                "--http-port=8081",
                f"--dir={temp_dir}",
            ],
            stdout=log_path.open("w"),
            stderr=subprocess.STDOUT,
            text=True,
        )
        atexit.register(self.stop_local_api)

        for _ in range(90):
            if self.local_process.poll() is not None:
                raise RuntimeError("Local Bot API exited before becoming ready.")
            result = subprocess_run(
                ["curl", "-sS", "--connect-timeout", "1", "--max-time", "2", "-o", "/dev/null", "-w", "%{http_code}", "http://127.0.0.1:8081/"],
                check=False,
                capture=True,
            )
            if (result.stdout or "").strip() not in {"", "000"}:
                return
            time.sleep(1)
        raise RuntimeError("Local Bot API did not become ready.")

    def stop_local_api(self) -> None:
        if self.local_process and self.local_process.poll() is None:
            self.local_process.terminate()
            try:
                self.local_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.local_process.kill()

    def send_file(self, path: Path, *, send_as: str, probe_info: ProbeInfo, reply_to_message_id: str) -> tuple[str, str]:
        size = path.stat().st_size
        use_local = size > PUBLIC_BOT_API_MAX_BYTES
        if use_local:
            self.start_local_api()
        send_method = "Local Bot API" if use_local else "Public Bot API"
        base = self.local_base if use_local else self.public_base

        if send_as == "video":
            args = [
                "curl",
                "-sS",
                "--connect-timeout",
                "20",
                "--max-time",
                "7200",
                "-X",
                "POST",
                f"{base}/sendVideo",
                "-F",
                f"chat_id={self.chat_id}",
                "-F",
                "supports_streaming=true",
                "-F",
                f"video=@{path}",
            ]
            if probe_info.width and probe_info.height:
                args.extend(["-F", f"width={probe_info.width}", "-F", f"height={probe_info.height}"])
            if probe_info.duration:
                args.extend(["-F", f"duration={probe_info.duration}"])
        else:
            args = [
                "curl",
                "-sS",
                "--connect-timeout",
                "20",
                "--max-time",
                "7200",
                "-X",
                "POST",
                f"{base}/sendDocument",
                "-F",
                f"chat_id={self.chat_id}",
                "-F",
                "disable_content_type_detection=true",
                "-F",
                f"document=@{path};filename={path.name};type=application/octet-stream",
            ]

        if reply_to_message_id:
            args.extend(["-F", f"reply_to_message_id={reply_to_message_id}"])

        data = curl_json(args, timeout=7300)
        if not data.get("ok"):
            raise RuntimeError(str(data.get("description") or "Telegram upload failed")[:500])
        message_id = str(((data.get("result") or {}).get("message_id")) or "")
        return send_method, message_id


def detect_platform(url: str) -> tuple[str, str]:
    low = url.lower()
    if "youtube.com" in low or "youtu.be" in low:
        return "youtube", "https://www.youtube.com/"
    if "facebook.com" in low or "fb.watch" in low:
        return "facebook", "https://www.facebook.com/"
    if "instagram.com" in low:
        return "instagram", "https://www.instagram.com/"
    if "tiktok.com" in low:
        return "tiktok", "https://www.tiktok.com/"
    if "twitter.com" in low or "x.com" in low:
        return "x", "https://x.com/"
    if "reddit.com" in low or "redd.it" in low:
        return "reddit", "https://www.reddit.com/"
    return "generic", "https://www.google.com/"


def prepare_cookies(platform: str) -> list[str]:
    secret_name = ""
    if platform == "youtube":
        secret_name = "YOUTUBE_COOKIES_TXT"
    elif platform == "facebook":
        secret_name = "FACEBOOK_COOKIES_TXT"
    if not secret_name or not env(secret_name):
        return []
    cookie_path = Path(env("RUNNER_TEMP", tempfile.gettempdir())) / f"{platform}-cookies.txt"
    cookie_path.write_text(env(secret_name) + "\n", encoding="utf-8")
    return ["--cookies", str(cookie_path)]


def newest_file(paths: Iterable[Path]) -> Path | None:
    existing = [p for p in paths if p.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def download_with_ytdlp(url: str, settings: CompressionSettings, cookies_args: list[str]) -> Path:
    if not command_exists("ffmpeg") or not command_exists("ffprobe"):
        raise RuntimeError("ffmpeg/ffprobe is missing from the worker image.")

    output_template = str(WORK_DIR / "source.%(ext)s")
    fmt = (
        f"bv*[height<={settings.max_height}]+ba/"
        f"bestvideo[height<={settings.max_height}]+bestaudio/"
        f"b[height<={settings.max_height}]/best"
    )
    log_path = Path(env("RUNNER_TEMP", tempfile.gettempdir())) / "yt-dlp-video-compress.log"
    args = [
        sys.executable,
        "-m",
        "yt_dlp",
        *cookies_args,
        "--quiet",
        "--no-warnings",
        "--no-progress",
        "--no-playlist",
        "--no-write-info-json",
        "--no-write-thumbnail",
        "--no-write-description",
        "--no-write-comments",
        "--no-cache-dir",
        "--no-part",
        "--restrict-filenames",
        "--concurrent-fragments",
        "4",
        "-f",
        fmt,
        "--merge-output-format",
        "mp4",
        "-o",
        output_template,
        url,
    ]
    result = subprocess_run(args, check=False, capture=True)
    log_path.write_text((result.stdout or "") + "\n" + (result.stderr or ""), encoding="utf-8", errors="ignore")
    if result.returncode != 0:
        raise RuntimeError("yt-dlp download failed; direct download fallback may be attempted.")

    candidate = newest_file(WORK_DIR.glob("source.*"))
    if not candidate or candidate.stat().st_size <= 0:
        raise RuntimeError("yt-dlp did not create a valid media file.")
    return candidate


def download_direct(url: str, referer: str) -> Path:
    path = WORK_DIR / "source_direct.bin"
    subprocess_run(
        [
            "curl",
            "-sS",
            "-fL",
            "--connect-timeout",
            "20",
            "--max-time",
            "21600",
            "--max-redirs",
            "10",
            "--retry",
            "2",
            "--retry-delay",
            "2",
            "--user-agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "--referer",
            referer,
            "-H",
            "Accept-Language: en-US,en;q=0.9",
            "-o",
            str(path),
            url,
        ]
    )
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError("Direct download did not create a valid file.")
    return path


def transcode(input_file: Path, output_file: Path, settings: CompressionSettings) -> None:
    vf = (
        f"scale=w='if(gt(ih,{settings.max_height}),-2,trunc(iw/2)*2)':"
        f"h='if(gt(ih,{settings.max_height}),{settings.max_height},trunc(ih/2)*2)':"
        "flags=bicubic,setsar=1,format=yuv420p"
    )
    log_path = Path(env("RUNNER_TEMP", tempfile.gettempdir())) / "ffmpeg-video-compress.log"
    args = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_file),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-map_metadata",
        "-1",
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        settings.preset,
        "-crf",
        str(settings.crf),
        "-maxrate",
        settings.maxrate,
        "-bufsize",
        settings.bufsize,
        "-profile:v",
        "main",
        "-level",
        settings.level_tag,
        "-tag:v",
        "avc1",
        "-c:a",
        "aac",
        "-b:a",
        settings.audio_bitrate,
        "-ar",
        "44100",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(output_file),
    ]
    result = subprocess_run(args, check=False, capture=True)
    log_path.write_text((result.stdout or "") + "\n" + (result.stderr or ""), encoding="utf-8", errors="ignore")
    if result.returncode != 0:
        raise RuntimeError("ffmpeg compression failed. Check the workflow log for ffmpeg-video-compress.log details.")
    if not output_file.is_file() or output_file.stat().st_size <= 0:
        raise RuntimeError("Compressed output is missing or empty.")


def package_zip(mp4_file: Path, requested_name: str) -> Path:
    zip_name = clean_filename(requested_name, "compressed-video.zip", ".zip")
    zip_path = WORK_DIR / zip_name
    inner_base = os.path.splitext(zip_name)[0] or "compressed-video"
    inner_name = clean_filename(f"{inner_base}.mp4", "compressed-video.mp4", ".mp4")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        zf.write(mp4_file, arcname=inner_name)
    if not zip_path.is_file() or zip_path.stat().st_size <= 0:
        raise RuntimeError("ZIP packaging failed.")
    return zip_path


def write_outputs(values: dict[str, str | int]) -> None:
    output_path = env("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as f:
        for key, value in values.items():
            safe_value = str(value).replace("\n", " ").replace("\r", " ")
            f.write(f"{key}={safe_value}\n")


def validate_runtime() -> None:
    missing = [name for name in ("curl", "ffmpeg", "ffprobe") if not command_exists(name)]
    if missing:
        raise RuntimeError("Missing required runtime tools: " + ", ".join(missing))
    try:
        subprocess_run([sys.executable, "-m", "yt_dlp", "--version"], check=True, capture=True)
    except Exception as exc:
        raise RuntimeError("yt-dlp is missing from the worker image.") from exc


def main() -> int:
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    media_url = env("MEDIA_URL_INPUT")
    send_as = env("SEND_AS_INPUT", "video").lower()
    if send_as not in {"video", "document", "zip"}:
        send_as = "video"
    requested_name = env("OUTPUT_FILENAME_INPUT")
    dispatch_key = env("DISPATCH_KEY", "manual")
    reply_to_message_id = env("REPLY_TO_MESSAGE_ID")

    telegram_token = env("TELEGRAM_TOKEN")
    target_chat_id = env("CHAT_ID_INPUT") or env("TELEGRAM_CHAT_ID") or env("ADMIN_ID")
    progress_chat_id = env("PROGRESS_CHAT_ID") or target_chat_id
    progress_message_id = env("PROGRESS_MESSAGE_ID")

    for value in (media_url, requested_name, dispatch_key, telegram_token, target_chat_id, progress_chat_id, progress_message_id, reply_to_message_id, env("TELEGRAM_API_ID"), env("TELEGRAM_API_HASH")):
        mask(value)

    settings = compression_settings(env("COMPRESSION_LEVEL_INPUT", "50"))

    if not media_url:
        raise RuntimeError("Missing media_url input.")
    if not telegram_token:
        raise RuntimeError("Missing TELEGRAM_TOKEN secret.")
    if not target_chat_id:
        raise RuntimeError("Missing destination chat id. Set chat_id input, TELEGRAM_CHAT_ID, or ADMIN_ID.")

    telegram = Telegram(telegram_token, target_chat_id, progress_chat_id, progress_message_id)

    try:
        validate_runtime()
        telegram.ensure_progress_message()
        telegram.update_progress(8, "Preparing", "Preparing video compression worker...")

        platform, referer = detect_platform(media_url)
        cookies_args = prepare_cookies(platform)
        print(f"PLATFORM={platform}")
        print(f"SEND_AS={send_as}")
        print(f"DISPATCH_KEY={dispatch_key}")
        print(f"COMPRESSION_LEVEL={settings.level}")
        print(f"COMPRESSION_CRF={settings.crf}")
        print(f"COMPRESSION_PRESET={settings.preset}")
        print(f"COMPRESSION_AUDIO_BITRATE={settings.audio_bitrate}")
        print(f"COMPRESSION_MAX_HEIGHT={settings.max_height}")

        telegram.update_progress(25, "Downloading", "Downloading source media...")
        try:
            source_file = download_with_ytdlp(media_url, settings, cookies_args)
        except Exception as first_error:
            print(f"YTDLP_DOWNLOAD_FAILED={str(first_error)[:180]}")
            source_file = download_direct(media_url, referer)

        source_size = source_file.stat().st_size
        print(f"SOURCE_SIZE_BYTES={source_size}")

        input_probe = probe(source_file)
        if not input_probe.video_codec:
            raise RuntimeError("Downloaded file does not contain a readable video stream.")

        telegram.update_progress(55, "Compressing", "Compressing video with ffmpeg...")
        compressed_name = clean_filename(requested_name, "compressed-video.mp4", ".mp4")
        compressed_path = WORK_DIR / compressed_name
        transcode(source_file, compressed_path, settings)
        video_probe = probe(compressed_path)
        if video_probe.video_codec != "h264":
            raise RuntimeError("Compressed output is not H.264 video.")

        final_send_as = send_as
        final_path = compressed_path
        if send_as == "zip":
            telegram.update_progress(70, "Packaging", "Packaging compressed video as ZIP...")
            final_path = package_zip(compressed_path, requested_name)
            final_send_as = "document"
        elif send_as == "document":
            telegram.update_progress(70, "Packaging", "Preparing compressed video as document...")
            final_send_as = "document"
        else:
            telegram.update_progress(70, "Packaging", "Preparing streamable Telegram video...")
            final_send_as = "video"

        final_size = final_path.stat().st_size
        if final_size > LOCAL_BOT_API_MAX_BYTES:
            raise RuntimeError("Final file is larger than the Telegram Local Bot API safety limit used by this workflow.")

        telegram.update_progress(84, "Uploading", "Uploading final output to Telegram...")
        send_method, message_id = telegram.send_file(final_path, send_as=final_send_as, probe_info=video_probe, reply_to_message_id=reply_to_message_id)

        telegram.update_progress(96, "Completed", "Final output uploaded successfully.")
        telegram.update_completed(
            send_as=send_as,
            send_method=send_method,
            message_id=message_id,
            source_size=source_size,
            final_size=final_size,
            settings=settings,
            final_file_name=final_path.name,
            video_probe=video_probe,
            platform=platform,
        )

        write_outputs(
            {
                "final_file_name": final_path.name,
                "final_size_bytes": final_size,
                "send_as": send_as,
                "send_method": send_method,
                "telegram_message_id": message_id,
                "compression_level": settings.level,
                "crf": settings.crf,
                "preset": settings.preset,
                "audio_bitrate": settings.audio_bitrate,
                "max_height": settings.max_height,
                "dispatch_key": dispatch_key,
            }
        )

        print("OK: Video compression output was sent successfully.")
        return 0
    except Exception as exc:
        detail = str(exc) or "Video compression failed."
        print(f"ERROR: {detail}", file=sys.stderr)
        try:
            telegram.update_failed(detail)
        except Exception:
            pass
        return 1
    finally:
        telegram.stop_local_api()


if __name__ == "__main__":
    raise SystemExit(main())
