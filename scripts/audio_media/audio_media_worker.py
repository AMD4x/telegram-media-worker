#!/usr/bin/env python3
"""Audio media worker for AMD4x telegram-media-worker."""

from __future__ import annotations

import atexit
from datetime import datetime, timezone
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
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

WORK_DIR = Path("work")
PUBLIC_BOT_API_MAX_BYTES = 50_000_000
LOCAL_BOT_API_MAX_BYTES = 2_000_000_000
MAX_SEARCH_QUERY_CHARS = 180
SAFE_PRINT_PREFIX = "AUDIO_WORKER"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def mask(value: object) -> None:
    if value is None:
        return
    text = str(value)
    if not text:
        return
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        item = line.strip()
        if item:
            print(f"::add-mask::{item}")


def mask_many(values: Iterable[object]) -> None:
    for value in values:
        mask(value)


def safe_log(message: str) -> None:
    message = re.sub(r"[^A-Za-z0-9 _.,:=+/@-]", "_", str(message))
    print(f"{SAFE_PRINT_PREFIX}: {message[:220]}")


def run_url() -> str:
    server = env("GITHUB_SERVER_URL", "https://github.com")
    repo = env("GITHUB_REPOSITORY", "AMD4x/telegram-media-worker")
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


def safe_text(value: object) -> str:
    return html.escape(str(value), quote=False)


def default_output_base(platform: str) -> str:
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Africa/Cairo"))
    except Exception:
        now = datetime.now(timezone.utc)

    clean_platform = re.sub(r"[^A-Za-z0-9_-]+", "-", (platform or "generic").lower())
    clean_platform = clean_platform.strip("-") or "generic"
    return f"{clean_platform}-audio-{now:%Y%m%d-%H%M%S}"


def clean_filename(value: str, fallback: str, ext: str | None = None) -> str:
    raw = urllib.parse.unquote((value or "").strip()) or fallback
    raw = raw.replace("\\", "/")
    name = os.path.basename(raw)
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = re.sub(r"[\/*?:\"<>|]", "", name)
    name = re.sub(r"\s+", " ", name).strip().strip(".") or fallback

    if ext:
        base, current_ext = os.path.splitext(name)
        if current_ext.lower() != ext.lower():
            name = f"{base or name}{ext}"

    base, current_ext = os.path.splitext(name)
    if len(name) > 120:
        base = base[: max(1, 120 - len(current_ext))].rstrip().strip(".")
        name = f"{base or 'audio'}{current_ext}"
    return name or fallback


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def subprocess_run(
    args: list[str],
    *,
    check: bool = True,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {args[0]}")
    return result


def curl_json(args: list[str], *, timeout: int | None = None) -> dict:
    result = subprocess_run(args, check=False, timeout=timeout)
    raw = result.stdout or ""
    try:
        data = json.loads(raw)
    except Exception:
        data = {"ok": False, "description": "Telegram API response could not be parsed."}
    if result.returncode != 0:
        data.setdefault("ok", False)
        data.setdefault("description", "curl command failed.")
    return data


@dataclass
class ProbeInfo:
    duration: str = ""
    title: str = ""
    artist: str = ""


@dataclass
class SourcePlan:
    source: str
    source_mode: str
    platform: str
    referer: str
    metadata_query: str = ""


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
    )
    raw = (result.stdout or "").splitlines()[0].strip() if result.stdout else ""
    try:
        return str(max(0, int(float(raw))))
    except Exception:
        return ""


def probe(path: Path) -> ProbeInfo:
    return ProbeInfo(duration=probe_duration(path))


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
            ],
        )
        if data.get("ok"):
            return str(((data.get("result") or {}).get("message_id")) or "")
        return ""

    def ensure_progress_message(self) -> None:
        if self.progress_message_id or not self.progress_chat_id:
            return
        self.progress_message_id = self.send_message(self.progress_text(2, "Preparing", "Preparing audio worker"))

    def update_progress(self, percent: int, status: str, detail: str) -> None:
        safe_log(f"PROGRESS_PERCENT={percent}")
        safe_log(f"PROGRESS_STATUS={status}")
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
            ],
        )

    def update_completed(
        self,
        *,
        platform: str,
        source_mode: str,
        audio_format: str,
        send_method: str,
        message_id: str,
        final_size: int,
        duration: str,
    ) -> None:
        if not self.progress_chat_id or not self.progress_message_id:
            return
        duration_line = duration or "unknown"
        text = (
            "✅ <b>GitHub Audio completed.</b>\n\n"
            f"🌐 <b>Platform:</b> <code>{safe_text(platform)}</code>\n"
            "🧭 <b>Path:</b> <code>audio-media</code>\n"
            f"🎧 <b>Source Mode:</b> <code>{safe_text(source_mode)}</code>\n"
            f"🎚️ <b>Format:</b> <code>{safe_text(audio_format)}</code>\n"
            f"⏱️ <b>Duration:</b> <code>{safe_text(duration_line)}</code>\n"
            f"📦 <b>Final Size:</b> <code>{format_bytes(final_size)}</code> — OK\n"
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
            ],
        )

    def update_failed(self, detail: str) -> None:
        if not self.progress_chat_id or not self.progress_message_id:
            return
        text = self.progress_text(100, "Failed", detail[:240])
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
            ],
        )

    def start_local_api(self) -> None:
        if self.local_process:
            return
        api_id = env("TELEGRAM_API_ID")
        api_hash = env("TELEGRAM_API_HASH")
        if not api_id or not api_hash:
            raise RuntimeError("Local Bot API credentials are required for this file size.")
        if not command_exists("telegram-bot-api"):
            raise RuntimeError("telegram-bot-api binary is missing from the worker image.")

        temp_dir = Path(env("RUNNER_TEMP", tempfile.gettempdir())) / "telegram-bot-api-audio-media"
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
                [
                    "curl",
                    "-sS",
                    "--connect-timeout",
                    "1",
                    "--max-time",
                    "2",
                    "-o",
                    "/dev/null",
                    "-w",
                    "%{http_code}",
                    "http://127.0.0.1:8081/",
                ],
                check=False,
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

    def send_audio_file(
        self,
        path: Path,
        *,
        audio_format: str,
        probe_info: ProbeInfo,
        reply_to_message_id: str,
    ) -> tuple[str, str]:
        size = path.stat().st_size
        use_local = size > PUBLIC_BOT_API_MAX_BYTES
        if use_local:
            self.start_local_api()
        send_method = "Local Bot API" if use_local else "Public Bot API"
        base = self.local_base if use_local else self.public_base

        if audio_format == "voice":
            method = "sendVoice"
            media_field = f"voice=@{path};filename={path.name};type=audio/ogg"
        else:
            method = "sendAudio"
            media_field = f"audio=@{path};filename={path.name}"

        args = [
            "curl",
            "-sS",
            "--connect-timeout",
            "20",
            "--max-time",
            "7200",
            "-X",
            "POST",
            f"{base}/{method}",
            "-F",
            f"chat_id={self.chat_id}",
            "-F",
            media_field,
        ]
        if audio_format != "voice":
            args.extend(["-F", f"title={path.stem}"])
        if probe_info.duration:
            args.extend(["-F", f"duration={probe_info.duration}"])
        if reply_to_message_id:
            args.extend(["-F", f"reply_to_message_id={reply_to_message_id}"])

        data = curl_json(args, timeout=7300)
        if not data.get("ok"):
            description = str(data.get("description") or "Telegram upload failed.").strip()
            description = re.sub(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b", "[redacted-token]", description)
            raise RuntimeError(f"Telegram upload failed: {description[:220]}")
        message_id = str(((data.get("result") or {}).get("message_id")) or "")
        return send_method, message_id


def detect_platform(value: str) -> tuple[str, str]:
    host = ""
    try:
        host = urllib.parse.urlparse(value).netloc.lower()
    except Exception:
        host = ""

    if "youtube.com" in host or "youtu.be" in host or "music.youtube.com" in host:
        return "youtube", "https://www.youtube.com/"
    if "spotify.com" in host or "spotify.link" in host or "spoti.fi" in host:
        return "spotify", "https://open.spotify.com/"
    if "anghami.com" in host:
        return "anghami", "https://www.anghami.com/"
    if "soundcloud.com" in host:
        return "soundcloud", "https://soundcloud.com/"
    if "bandcamp.com" in host:
        return "bandcamp", "https://bandcamp.com/"
    if "deezer.com" in host:
        return "deezer", "https://www.deezer.com/"
    if "music.apple.com" in host:
        return "apple-music", "https://music.apple.com/"
    if "tidal.com" in host:
        return "tidal", "https://tidal.com/"
    if "qobuz.com" in host:
        return "qobuz", "https://www.qobuz.com/"
    if "music.amazon." in host or "amazon." in host:
        return "amazon-music", "https://music.amazon.com/"
    if "audiomack.com" in host:
        return "audiomack", "https://audiomack.com/"
    if "mixcloud.com" in host:
        return "mixcloud", "https://www.mixcloud.com/"
    if "hearthis.at" in host:
        return "hearthis", "https://hearthis.at/"
    if "reverbnation.com" in host:
        return "reverbnation", "https://www.reverbnation.com/"
    if "facebook.com" in host or "fb.watch" in host:
        return "facebook", "https://www.facebook.com/"
    if "instagram.com" in host:
        return "instagram", "https://www.instagram.com/"
    if "tiktok.com" in host:
        return "tiktok", "https://www.tiktok.com/"
    if "twitter.com" in host or "x.com" in host:
        return "x", "https://x.com/"
    if "reddit.com" in host or "redd.it" in host:
        return "reddit", "https://www.reddit.com/"
    return "generic", "https://www.google.com/"


def prepare_cookies(platform: str) -> list[str]:
    secret_name = ""
    if platform in {"youtube"}:
        secret_name = "YOUTUBE_COOKIES_TXT"
    elif platform in {"facebook"}:
        secret_name = "FACEBOOK_COOKIES_TXT"

    cookies_text = env(secret_name) if secret_name else ""
    if not secret_name or not cookies_text:
        return []

    cookie_path = Path(env("RUNNER_TEMP", tempfile.gettempdir())) / f"{platform}-cookies.txt"
    cookie_path.write_text(cookies_text + "\n", encoding="utf-8")
    cookie_path.chmod(0o600)
    return ["--cookies", str(cookie_path)]


def ytdlp_base_args(cookies_args: list[str]) -> list[str]:
    return [
        sys.executable,
        "-m",
        "yt_dlp",
        *cookies_args,
        "--quiet",
        "--no-warnings",
        "--no-progress",
        "--no-playlist",
        "--no-cache-dir",
        "--no-part",
        "--restrict-filenames",
        "--concurrent-fragments",
        "4",
    ]


def metadata_query_from_info(info: dict) -> str:
    fields: list[str] = []
    for key in ("artist", "creator", "uploader", "channel"):
        value = str(info.get(key) or "").strip()
        if value and value.lower() not in {"unknown", "none"}:
            fields.append(value)
            break
    for key in ("track", "title", "alt_title"):
        value = str(info.get(key) or "").strip()
        if value and value.lower() not in {"unknown", "none"}:
            fields.append(value)
            break
    query = " ".join(dict.fromkeys(fields)).strip()
    if not query:
        title = str(info.get("fulltitle") or info.get("title") or "").strip()
        query = title
    query = re.sub(r"\s+", " ", query).strip()
    return query[:MAX_SEARCH_QUERY_CHARS]


def normalize_metadata_query(value: str) -> str:
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"^Listen to\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*[-–]\s*song and lyrics by\s*", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*[-–]\s*song by\s*", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*[-–]\s*Single by\s*", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*[-–]\s*EP by\s*", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*\|\s*Spotify\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+on\s+Spotify\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:MAX_SEARCH_QUERY_CHARS]


def metadata_query_from_spotify_oembed(source_url: str) -> str:
    platform, _referer = detect_platform(source_url)
    if platform != "spotify":
        return ""

    endpoint = "https://open.spotify.com/oembed?url=" + urllib.parse.quote(source_url, safe="")
    result = subprocess_run(
        [
            "curl",
            "-sS",
            "-L",
            "--connect-timeout",
            "10",
            "--max-time",
            "20",
            "--user-agent",
            "Mozilla/5.0",
            endpoint,
        ],
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        return ""

    try:
        data = json.loads(result.stdout or "{}")
    except Exception:
        return ""

    title = normalize_metadata_query(str(data.get("title") or ""))
    author = normalize_metadata_query(str(data.get("author_name") or ""))

    if author and author.lower() != "spotify" and author.lower() not in title.lower():
        return f"{author} {title}".strip()[:MAX_SEARCH_QUERY_CHARS]

    return ""


def metadata_query_from_webpage_title(source_url: str) -> str:
    result = subprocess_run(
        [
            "curl",
            "-sS",
            "-L",
            "--connect-timeout",
            "10",
            "--max-time",
            "20",
            "--user-agent",
            "Mozilla/5.0",
            "-H",
            "Accept-Language: en-US,en;q=0.9",
            source_url,
        ],
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        return ""

    page = result.stdout or ""
    candidates: list[str] = []

    patterns = [
        r'<meta[^>]+(?:property|name)=["\'](?:og:title|twitter:title)["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:title|twitter:title)["\']',
        r"<title[^>]*>(.*?)</title>",
    ]

    for pattern in patterns:
        match = re.search(pattern, page, flags=re.IGNORECASE | re.DOTALL)
        if match:
            candidates.append(match.group(1))

    for candidate in candidates:
        query = normalize_metadata_query(candidate)
        if query:
            return query

    return ""


def media_name_from_info(info: dict) -> str:
    artist = str(info.get("artist") or info.get("creator") or info.get("uploader") or "").strip()
    title = str(info.get("track") or info.get("title") or info.get("fulltitle") or "").strip()

    if artist and title and artist.lower() not in title.lower():
        value = f"{artist} - {title}"
    else:
        value = title or artist

    value = re.sub(r"\s+", " ", value).strip()
    return value[:120]


def extract_metadata_query(source_url: str, cookies_args: list[str]) -> str:
    args = [
        *ytdlp_base_args(cookies_args),
        "--skip-download",
        "--dump-single-json",
        source_url,
    ]
    result = subprocess_run(args, check=False, timeout=180)

    if result.returncode == 0:
        try:
            info = json.loads(result.stdout or "{}")
        except Exception:
            info = {}

        query = metadata_query_from_info(info)
        if query:
            return query

    platform, _referer = detect_platform(source_url)
    if platform == "spotify":
        fallbacks = (metadata_query_from_webpage_title, metadata_query_from_spotify_oembed)
    else:
        fallbacks = (metadata_query_from_spotify_oembed, metadata_query_from_webpage_title)

    for fallback in fallbacks:
        query = fallback(source_url)
        if query:
            return query

    return ""


def extract_source_name(source_url: str, cookies_args: list[str]) -> str:
    args = [
        *ytdlp_base_args(cookies_args),
        "--skip-download",
        "--dump-single-json",
        source_url,
    ]
    result = subprocess_run(args, check=False, timeout=180)
    if result.returncode != 0:
        return ""

    try:
        info = json.loads(result.stdout or "{}")
    except Exception:
        return ""

    return media_name_from_info(info)


def youtube_search_base_args(cookies_args: list[str]) -> list[str]:
    return [arg for arg in ytdlp_base_args(cookies_args) if arg != "--no-playlist"]


def youtube_entry_url(entry: dict) -> str:
    webpage_url = str(entry.get("webpage_url") or entry.get("original_url") or "").strip()
    if webpage_url:
        return webpage_url

    video_id = str(entry.get("id") or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{6,}", video_id):
        return f"https://www.youtube.com/watch?v={video_id}"

    return ""


def youtube_search_first_url(search_source: str, cookies_args: list[str]) -> str:
    result = subprocess_run(
        [
            *youtube_search_base_args(cookies_args),
            "--skip-download",
            "--dump-single-json",
            search_source,
        ],
        check=False,
        timeout=180,
    )
    if result.returncode != 0:
        return ""

    try:
        data = json.loads(result.stdout or "{}")
    except Exception:
        return ""

    entries = data.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict):
                url = youtube_entry_url(entry)
                if url:
                    return url
        return ""

    if isinstance(data, dict):
        return youtube_entry_url(data)

    return ""


def select_youtube_search_source(query: str, cookies_args: list[str]) -> str:
    clean_query = normalize_metadata_query(query)
    if len(clean_query) < 3:
        return ""

    search_sources = [
        f'ytsearch1:{clean_query} "Topic"',
        f"ytmsearch1:{clean_query} official audio",
    ]

    for search_source in search_sources:
        url = youtube_search_first_url(search_source, cookies_args)
        if url:
            return url

    return ""


def is_search_source(value: str) -> bool:
    return value.startswith("ytsearch") or value.startswith("ytsearchdate")


def newest_file(paths: Iterable[Path]) -> Path | None:
    existing = [p for p in paths if p.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def download_best_audio(source: str, cookies_args: list[str], output_prefix: str) -> Path:
    output_template = str(WORK_DIR / f"{output_prefix}.%(ext)s")
    args = [
        *ytdlp_base_args(cookies_args),
        "-f",
        "bestaudio/best",
        "--extract-audio",
        "-o",
        output_template,
        source,
    ]
    result = subprocess_run(args, check=False, timeout=21600)
    if result.returncode != 0:
        raise RuntimeError("Audio extraction failed.")
    candidate = newest_file(WORK_DIR.glob(f"{output_prefix}.*"))
    if not candidate or candidate.stat().st_size <= 0:
        raise RuntimeError("Audio extraction produced no output.")
    return candidate


def convert_audio(input_file: Path, output_file: Path, audio_format: str) -> Path:
    if audio_format == "raw":
        if input_file.name != output_file.name:
            shutil.copy2(input_file, output_file)
        return output_file

    if audio_format == "mp3":
        args = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(input_file),
            "-vn",
            "-map_metadata",
            "-1",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "192k",
            str(output_file),
        ]
    elif audio_format == "m4a":
        args = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(input_file),
            "-vn",
            "-map_metadata",
            "-1",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_file),
        ]
    elif audio_format == "voice":
        args = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(input_file),
            "-vn",
            "-map_metadata",
            "-1",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-c:a",
            "libopus",
            "-b:a",
            "48k",
            "-vbr",
            "on",
            str(output_file),
        ]
    else:
        raise RuntimeError("Unsupported audio format.")

    result = subprocess_run(args, check=False, timeout=21600)
    if result.returncode != 0:
        raise RuntimeError("Audio conversion failed.")
    if not output_file.is_file() or output_file.stat().st_size <= 0:
        raise RuntimeError("Audio conversion produced no output.")
    return output_file


def extension_for_format(audio_format: str, raw_source: Path | None = None) -> str:
    if audio_format == "mp3":
        return ".mp3"
    if audio_format == "m4a":
        return ".m4a"
    if audio_format == "voice":
        return ".ogg"
    if raw_source:
        suffix = raw_source.suffix.lower()
        if suffix:
            return suffix
    return ".audio"


def build_source_plan(source_url: str, search_query: str) -> SourcePlan:
    if search_query:
        clean_query = re.sub(r"\s+", " ", search_query).strip()[:MAX_SEARCH_QUERY_CHARS]
        return SourcePlan(
            source=f"ytsearch1:{clean_query}",
            source_mode="search",
            platform="youtube-search",
            referer="https://www.youtube.com/",
            metadata_query=clean_query,
        )

    platform, referer = detect_platform(source_url)
    return SourcePlan(
        source=source_url,
        source_mode="direct",
        platform=platform,
        referer=referer,
    )


def resolve_with_fallback(plan: SourcePlan, cookies_args: list[str], telegram: Telegram) -> tuple[Path, SourcePlan]:
    telegram.update_progress(35, "Downloading", "Extracting best audio stream")
    try:
        return download_best_audio(plan.source, cookies_args, "source_audio"), plan
    except Exception:
        if plan.source_mode == "search":
            raise

    telegram.update_progress(42, "Resolving", "Building metadata search fallback")
    query = extract_metadata_query(plan.source, cookies_args)
    if not query:
        raise RuntimeError("Direct audio extraction failed and metadata fallback was unavailable.")

    fallback_cookies = prepare_cookies("youtube")

    telegram.update_progress(48, "Searching", "Selecting best fallback audio match")
    fallback_source = select_youtube_search_source(query, fallback_cookies)
    if not fallback_source:
        raise RuntimeError("No confident fallback audio match was found.")

    fallback_plan = SourcePlan(
        source=fallback_source,
        source_mode="metadata-search",
        platform=f"{plan.platform}-via-youtube",
        referer="https://www.youtube.com/",
        metadata_query=query,
    )

    return download_best_audio(fallback_plan.source, fallback_cookies, "source_audio_fallback"), fallback_plan


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
        raise RuntimeError("Missing required runtime tools.")
    result = subprocess_run([sys.executable, "-m", "yt_dlp", "--version"], check=False)
    if result.returncode != 0:
        raise RuntimeError("yt-dlp is missing from the worker image.")


def main() -> int:
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    source_url = env("SOURCE_URL_INPUT")
    search_query = env("SEARCH_QUERY_INPUT")
    audio_format = env("AUDIO_FORMAT_INPUT", "mp3").lower()
    output_filename = env("OUTPUT_FILENAME_INPUT")
    dispatch_key = env("DISPATCH_KEY", "manual")
    reply_to_message_id = env("REPLY_TO_MESSAGE_ID")

    if audio_format not in {"mp3", "m4a", "raw", "voice"}:
        audio_format = "mp3"

    telegram_token = env("TELEGRAM_TOKEN")
    target_chat_id = env("CHAT_ID_INPUT") or env("TELEGRAM_CHAT_ID") or env("ADMIN_ID")
    progress_chat_id = env("PROGRESS_CHAT_ID") or target_chat_id
    progress_message_id = env("PROGRESS_MESSAGE_ID")

    mask_many(
        [
            telegram_token,
            target_chat_id,
            progress_chat_id,
            progress_message_id,
            env("TELEGRAM_API_ID"),
            env("TELEGRAM_API_HASH"),
            env("YOUTUBE_COOKIES_TXT"),
            env("FACEBOOK_COOKIES_TXT"),
        ]
    )

    if not source_url and not search_query:
        raise RuntimeError("Missing source_url or search_query input.")
    if not telegram_token:
        raise RuntimeError("Missing TELEGRAM_TOKEN secret.")
    if not target_chat_id:
        raise RuntimeError("Missing destination chat id.")

    telegram = Telegram(telegram_token, target_chat_id, progress_chat_id, progress_message_id)

    final_file: Path | None = None
    final_probe = ProbeInfo()
    final_plan = SourcePlan("", "unknown", "unknown", "")
    send_method = ""
    message_id = ""

    try:
        validate_runtime()
        telegram.ensure_progress_message()
        telegram.update_progress(8, "Preparing", "Preparing audio worker")
        safe_log("runtime_ready")

        plan = build_source_plan(source_url, search_query)
        final_plan = plan

        telegram.update_progress(18, "Detecting", "Detecting source platform")
        cookies_args = prepare_cookies(plan.platform)

        source_file, final_plan = resolve_with_fallback(plan, cookies_args, telegram)

        telegram.update_progress(68, "Converting", "Preparing final audio output")
        ext = extension_for_format(audio_format, source_file)
        source_name = extract_source_name(
            final_plan.source,
            prepare_cookies("youtube") if final_plan.source_mode == "metadata-search" else cookies_args,
        )
        fallback_base = source_name or default_output_base(final_plan.platform)
        fallback_name = f"{fallback_base}{ext}"
        final_name = clean_filename(output_filename, fallback_name, ext if audio_format != "raw" else None)
        final_file = WORK_DIR / final_name

        convert_audio(source_file, final_file, audio_format)
        final_probe = probe(final_file)

        size = final_file.stat().st_size
        if size > LOCAL_BOT_API_MAX_BYTES:
            raise RuntimeError("Final audio file exceeds Telegram Local Bot API safety limit.")

        telegram.update_progress(82, "Uploading", "Uploading final audio to Telegram")
        send_method, message_id = telegram.send_audio_file(
            final_file,
            audio_format=audio_format,
            probe_info=final_probe,
            reply_to_message_id=reply_to_message_id,
        )

        telegram.update_progress(96, "Finalizing", "Finalizing Telegram delivery")
        telegram.update_completed(
            platform=final_plan.platform,
            source_mode=final_plan.source_mode,
            audio_format=audio_format,
            send_method=send_method,
            message_id=message_id,
            final_size=size,
            duration=final_probe.duration,
        )

        write_outputs(
            {
                "ok": "true",
                "audio_format": audio_format,
                "send_mode": "voice" if audio_format == "voice" else "audio",
            }
        )
        safe_log("completed")
        return 0
    except Exception as exc:
        detail = str(exc) or "Audio worker failed."
        telegram.update_failed(detail)
        write_outputs(
            {
                "ok": "false",
                "audio_format": audio_format,
                "send_mode": "voice" if audio_format == "voice" else "audio",
            }
        )
        safe_log("failed")
        print(f"ERROR: {safe_text(detail)[:240]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
