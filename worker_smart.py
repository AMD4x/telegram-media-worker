#!/usr/bin/env python3
"""
Smart GitHub Remote worker.

This file is intentionally self-contained so the workflow can run it from the
Docker image without checking out the repository.
"""
from __future__ import annotations

import html
import json
import mimetypes
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yt_dlp
except Exception as exc:  # pragma: no cover
    yt_dlp = None
    YTDLP_IMPORT_ERROR = exc
else:
    YTDLP_IMPORT_ERROR = None

WORK_DIR = Path("work")
WORK_DIR.mkdir(parents=True, exist_ok=True)

DIRECT_TELEGRAM_MAX_BYTES = 50_000_000
LOCAL_BOT_API_MAX_BYTES = 2_000_000_000
TELEGRAM_TARGET_MAX_BYTES = 1_950_000_000
DIRECT_URL_SEND_TIMEOUT = 45
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

LOCAL_BOT_API_PROC: subprocess.Popen | None = None
LOCAL_BOT_API_STARTED = False
DOWNLOAD_SIZE_BYTES_FINAL = 0
INPUT_VIDEO_CODEC_FINAL = "unknown"
OUTPUT_VIDEO_CODEC_FINAL = "unknown"
FINAL_SIZE_STATUS = "OK"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


SOURCE_URL = env("MEDIA_URL_INPUT")
MAX_HEIGHT_RAW = env("MAX_HEIGHT_INPUT", "auto") or "auto"
REMOTE_MODE = env("REMOTE_MODE_INPUT", "auto_best") or "auto_best"
SEND_AS = env("SEND_AS_INPUT", "video") or "video"
OUTPUT_FILENAME = env("OUTPUT_FILENAME_INPUT", "")
TELEGRAM_TOKEN = env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")
PROGRESS_CHAT_ID = env("PROGRESS_CHAT_ID")
PROGRESS_MESSAGE_ID = env("PROGRESS_MESSAGE_ID")
TELEGRAM_API_ID = env("TELEGRAM_API_ID")
TELEGRAM_API_HASH = env("TELEGRAM_API_HASH")
GITHUB_RUN_URL = f"{env('GITHUB_SERVER_URL')}/{env('GITHUB_REPOSITORY')}/actions/runs/{env('GITHUB_RUN_ID')}"


def log(key: str, value: str = "1") -> None:
    print(f"{key}={value}", flush=True)


def mask(value: str | int | None) -> None:
    if value is not None and str(value):
        print(f"::add-mask::{value}", flush=True)


def progress_bar(percent: int, length: int = 10) -> str:
    percent = max(0, min(100, int(percent)))
    filled = percent * length // 100
    return "█" * filled + "░" * (length - filled)


def telegram_escape(value: str) -> str:
    return html.escape(str(value), quote=False)


def edit_progress(percent: int, label: str, detail: str) -> None:
    log("PROGRESS_STAGE", re.sub(r"\s+", "_", label.lower()))
    log("PROGRESS_PERCENT", str(percent))
    log("PROGRESS_LABEL", label)
    log("PROGRESS_DETAIL", detail.replace(" ", "_"))

    if not (TELEGRAM_TOKEN and PROGRESS_CHAT_ID and PROGRESS_MESSAGE_ID):
        return

    bar = progress_bar(percent)
    text = (
        "🐙 <b>GitHub Remote</b>\n\n"
        f"📊 <code>[{bar}] {percent}%</code>\n"
        f"🧭 <b>Status:</b> {telegram_escape(label)}\n"
        f"ℹ️ <i>{telegram_escape(detail)}</i>\n"
        f"🧩 <b>Mode:</b> <code>{telegram_escape(REMOTE_MODE)}</code>\n"
        f"🎚️ <b>Target:</b> <code>{telegram_escape(MAX_HEIGHT_RAW)}</code>\n"
        f"🆔 <code>{telegram_escape(env('GITHUB_RUN_ID'))}</code>\n"
        f"🔗 <a href=\"{telegram_escape(GITHUB_RUN_URL)}\">Open Run</a>"
    )

    run_curl(
        [
            "curl", "-sS", "--connect-timeout", "10", "--max-time", "20",
            "-X", "POST", f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText",
            "-F", f"chat_id={PROGRESS_CHAT_ID}",
            "-F", f"message_id={PROGRESS_MESSAGE_ID}",
            "-F", "parse_mode=HTML",
            "-F", "disable_web_page_preview=true",
            "-F", f"text={text}",
        ],
        check=False,
        quiet=True,
    )


def format_bytes(num: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    n = float(max(0, int(num)))
    idx = 0
    while n >= 1024 and idx < len(units) - 1:
        n /= 1024
        idx += 1
    if idx == 0:
        return f"{int(n)} B"
    return f"{n:.2f} {units[idx]}"


def run_curl(args: list[str], *, check: bool = True, quiet: bool = False) -> subprocess.CompletedProcess:
    if quiet:
        return subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=check)
    return subprocess.run(args, check=check)


def run_capture(args: list[str], *, check: bool = False, timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=check, timeout=timeout)


def max_height_num() -> int | None:
    if str(MAX_HEIGHT_RAW).lower() == "auto":
        return None
    try:
        value = int(MAX_HEIGHT_RAW)
    except Exception:
        return None
    return value if value > 0 else None


def candidate_heights() -> list[int]:
    standard_heights = [4320, 2160, 1440, 1080, 720, 480, 360, 240, 144]
    cap = max_height_num()

    if cap is None:
        return standard_heights

    heights = []

    # في Manual قد تكون الجودة المختارة غير قياسيّة مثل 1920 أو 1280 أو 1024.
    # لذلك يجب تجربة الرقم المختار نفسه أوّلًا.
    if cap >= 144:
        heights.append(cap)

    for h in standard_heights:
        if h <= cap and h not in heights:
            heights.append(h)

    return heights


def origin_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/"
    return "https://www.google.com/"


def platform_name(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    if "youtube" in host or "youtu.be" in host:
        return "youtube"
    if "facebook" in host or "fb.watch" in host:
        return "facebook"
    if "tiktok" in host:
        return "tiktok"
    if "instagram" in host:
        return "instagram"
    if "x.com" in host or "twitter" in host:
        return "x"
    if "reddit" in host or "redd.it" in host:
        return "reddit"
    return "generic"


PLATFORM = platform_name(SOURCE_URL)
REFERER_URL = origin_from_url(SOURCE_URL)


@dataclass
class Candidate:
    url: str
    source: str
    headers: dict[str, str] = field(default_factory=dict)
    height: int = 0
    score: int = 0


def default_headers(url: str | None = None) -> dict[str, str]:
    referer = origin_from_url(url or SOURCE_URL)
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referer,
    }


def fetch_text(url: str, timeout: int = 30) -> tuple[str, str]:
    request = urllib.request.Request(url, headers=default_headers(url))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        final_url = response.geturl()
        content_type = response.headers.get("content-type", "")
        data = response.read(5_000_000)
    text = data.decode("utf-8", errors="replace")
    return text, final_url or url


def unescape_url(value: str) -> str:
    value = html.unescape(value)
    value = value.replace("\\/", "/")
    value = value.replace("\\u0026", "&")
    value = value.replace("&amp;", "&")
    try:
        value = urllib.parse.unquote(value)
    except Exception:
        pass
    return value.strip()


def is_media_url(url: str) -> bool:
    lower = url.lower()
    if lower.startswith("blob:") or lower.startswith("data:"):
        return False
    return any(token in lower for token in (".mp4", ".m4v", ".mov", ".m3u8", "mime=video", "video_mp4", "video"))


def guess_height_from_url(url: str) -> int:
    patterns = [
        r"(?<!\d)(2160|1440|1080|720|480|360)p(?!\d)",
        r"(?<!\d)(2160|1440|1080|720|480|360)[xX](?:\d+)",
        r"(?:height|h)=([0-9]{3,4})",
    ]
    for pat in patterns:
        m = re.search(pat, url, re.I)
        if m:
            try:
                h = int(m.group(1))
            except Exception:
                continue
            if 144 <= h <= 4320:
                return h
    return 0


def score_candidate(candidate: Candidate) -> int:
    lower = candidate.url.lower()
    score = 0
    if ".mp4" in lower:
        score += 80
    if any(x in lower for x in ("playable", "progressive", "browser_native", "playaddr", "contenturl", "videourl")):
        score += 30
    if ".m3u8" in lower:
        score += 10
    if "watermark" in lower or "download" in lower:
        score -= 15
    if candidate.height:
        score += min(candidate.height // 20, 120)
    return score


def add_candidate(rows: dict[str, Candidate], raw_url: str, source: str, base_url: str) -> None:
    url = unescape_url(str(raw_url or ""))
    if not url:
        return
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = urllib.parse.urljoin(base_url, url)
    if not url.startswith(("http://", "https://")):
        return
    if not is_media_url(url):
        return
    parsed = urllib.parse.urlparse(url)
    cleaned = urllib.parse.urlunparse(parsed._replace(fragment=""))
    if cleaned in rows:
        return
    height = guess_height_from_url(cleaned)
    cap = max_height_num()
    if cap is not None and height and height > cap:
        return
    cand = Candidate(cleaned, source=source, headers=default_headers(base_url), height=height)
    cand.score = score_candidate(cand)
    rows[cleaned] = cand


def extract_candidates_from_text(text: str, base_url: str) -> list[Candidate]:
    rows: dict[str, Candidate] = {}

    for match in re.finditer(r"https?:\\?/\\?/[^\"'<>\\\s]+", text):
        add_candidate(rows, match.group(0), "url-regex", base_url)

    for match in re.finditer(r"(?:src|content|href)=[\"']([^\"']+)[\"']", text, re.I):
        add_candidate(rows, match.group(1), "html-attr", base_url)

    key_pat = re.compile(
        r"(?:playable_url|browser_native_hd_url|browser_native_sd_url|progressive_url|playAddr|play_addr|contentUrl|videoUrl|playUrl|url|src)" 
        r"[\"']?\s*[:=]\s*[\"']([^\"']+)[\"']",
        re.I,
    )
    for match in key_pat.finditer(text):
        add_candidate(rows, match.group(1), "json-key", base_url)

    candidates = list(rows.values())
    candidates.sort(key=lambda c: (c.score, c.height), reverse=True)
    return candidates[:12]


def discover_direct_candidates() -> list[Candidate]:
    edit_progress(22, "Discovering", "Looking for direct media candidates")
    try:
        text, final_url = fetch_text(SOURCE_URL)
    except Exception as exc:
        log("DIRECT_DISCOVERY_FAILED", type(exc).__name__)
        return []
    mask(final_url)
    candidates = extract_candidates_from_text(text, final_url)
    log("DIRECT_CANDIDATES_COUNT", str(len(candidates)))
    return candidates


def telegram_api_base_for_size(size_bytes: int) -> tuple[str, str]:
    if size_bytes <= DIRECT_TELEGRAM_MAX_BYTES:
        return f"https://api.telegram.org/bot{TELEGRAM_TOKEN}", "public"
    start_local_bot_api_server()
    return f"http://127.0.0.1:8081/bot{TELEGRAM_TOKEN}", "local"


def try_telegram_url_send(candidate: Candidate) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    if ".mp4" not in candidate.url.lower():
        return False

    edit_progress(30, "Trying URL send", "Asking Telegram to fetch the direct URL")
    response_file = WORK_DIR / "telegram-url-send.json"
    args = [
        "curl", "-sS", "--connect-timeout", "10", "--max-time", str(DIRECT_URL_SEND_TIMEOUT),
        "-o", str(response_file), "-w", "%{http_code}",
        "-X", "POST", f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVideo",
        "-F", f"chat_id={TELEGRAM_CHAT_ID}",
        "-F", "supports_streaming=true",
        "-F", f"video={candidate.url}",
    ]
    proc = run_capture(args, timeout=DIRECT_URL_SEND_TIMEOUT + 10)
    http_code = proc.stdout.strip()
    log("TELEGRAM_URL_SEND_HTTP_CODE", http_code or "000")
    try:
        ok = '"ok":true' in response_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        ok = False
    if ok and http_code.startswith("2"):
        edit_progress(98, "Completed", "Telegram accepted the direct URL")
        log("FINAL_RESULT", "success_url_send")
        return True
    return False


def download_candidate(candidate: Candidate, index: int) -> Path | None:
    edit_progress(38, "Downloading", "Downloading direct media inside GitHub")
    suffix = ".mp4" if ".mp4" in candidate.url.lower() else ".bin"
    out = WORK_DIR / f"direct-{index}{suffix}"
    args = [
        "curl", "-fL", "--connect-timeout", "20", "--max-time", "21600",
        "--retry", "2", "--retry-delay", "2",
        "-A", USER_AGENT,
        "-H", f"Referer: {candidate.headers.get('Referer', REFERER_URL)}",
        "-o", str(out), candidate.url,
    ]
    proc = run_capture(args)
    if proc.returncode != 0 or not out.exists() or out.stat().st_size <= 0:
        log("DIRECT_DOWNLOAD_FAILED", str(index))
        try:
            out.unlink()
        except FileNotFoundError:
            pass
        return None
    mask(out.stat().st_size)
    log("DIRECT_DOWNLOAD_SUCCESS", str(index))
    return out


def ffprobe_json(path: Path) -> dict[str, Any]:
    proc = run_capture([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-print_format", "json", str(path)
    ])
    if proc.returncode != 0:
        return {}
    try:
        return json.loads(proc.stdout or "{}")
    except Exception:
        return {}


def probe_summary(path: Path) -> dict[str, Any]:
    data = ffprobe_json(path)
    streams = data.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    a = next((s for s in streams if s.get("codec_type") == "audio"), {})
    fmt = data.get("format") or {}
    return {
        "format": str(fmt.get("format_name") or ""),
        "duration": float(fmt.get("duration") or 0) if str(fmt.get("duration") or "").replace('.', '', 1).isdigit() else 0,
        "vcodec": str(v.get("codec_name") or ""),
        "acodec": str(a.get("codec_name") or ""),
        "pix_fmt": str(v.get("pix_fmt") or ""),
        "height": int(v.get("height") or 0),
        "width": int(v.get("width") or 0),
    }


def is_video_safe_for_telegram(summary: dict[str, Any]) -> bool:
    fmt = summary.get("format", "")
    vcodec = summary.get("vcodec", "")
    acodec = summary.get("acodec", "")
    return (
        "mp4" in fmt or "mov" in fmt
    ) and vcodec == "h264" and (not acodec or acodec == "aac") and summary.get("height", 0) > 0


def remux_copy(input_path: Path) -> Path | None:
    output = input_path.with_suffix(".remux.mp4")
    output.unlink(missing_ok=True)
    edit_progress(58, "Remuxing", "Trying fast copy remux")
    proc = run_capture([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(input_path), "-map", "0:v:0", "-map", "0:a:0?",
        "-c", "copy", "-movflags", "+faststart", str(output)
    ])
    if proc.returncode == 0 and output.exists() and output.stat().st_size > 0:
        return output
    output.unlink(missing_ok=True)
    return None


def encode_safe(input_path: Path, target_height: int | None = None) -> Path | None:
    output = input_path.with_suffix(".safe.mp4")
    output.unlink(missing_ok=True)
    edit_progress(66, "Encoding", "Encoding safe H.264/AAC fallback")
    vf = "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p"
    if target_height:
        vf = f"scale=-2:{target_height}:force_original_aspect_ratio=decrease,format=yuv420p"
    proc = run_capture([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(input_path), "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart", str(output)
    ])
    if proc.returncode == 0 and output.exists() and output.stat().st_size > 0:
        return output
    output.unlink(missing_ok=True)
    return None


def prepare_video_file(input_path: Path, label: str) -> tuple[Path, dict[str, Any]] | None:
    global INPUT_VIDEO_CODEC_FINAL, OUTPUT_VIDEO_CODEC_FINAL, DOWNLOAD_SIZE_BYTES_FINAL
    DOWNLOAD_SIZE_BYTES_FINAL = input_path.stat().st_size
    summary = probe_summary(input_path)
    INPUT_VIDEO_CODEC_FINAL = summary.get("vcodec") or "unknown"
    log("PROBE_VIDEO_CODEC", INPUT_VIDEO_CODEC_FINAL)
    log("PROBE_AUDIO_CODEC", summary.get("acodec") or "none")
    log("PROBE_HEIGHT", str(summary.get("height") or 0))

    if is_video_safe_for_telegram(summary):
        OUTPUT_VIDEO_CODEC_FINAL = summary.get("vcodec") or "h264"
        return input_path, summary

    remuxed = remux_copy(input_path)
    if remuxed:
        summary2 = probe_summary(remuxed)
        if is_video_safe_for_telegram(summary2):
            OUTPUT_VIDEO_CODEC_FINAL = summary2.get("vcodec") or "h264"
            return remuxed, summary2

    target = summary.get("height") or max_height_num()
    if max_height_num() and target and target > max_height_num():
        target = max_height_num()
    encoded = encode_safe(input_path, int(target or 0) or None)
    if encoded:
        summary3 = probe_summary(encoded)
        if summary3.get("vcodec"):
            OUTPUT_VIDEO_CODEC_FINAL = summary3.get("vcodec") or "h264"
            return encoded, summary3
    return None


def start_local_bot_api_server() -> None:
    global LOCAL_BOT_API_PROC, LOCAL_BOT_API_STARTED
    if LOCAL_BOT_API_STARTED:
        return
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        raise RuntimeError("Missing TELEGRAM_API_ID/TELEGRAM_API_HASH for Local Bot API")
    if not shutil.which("telegram-bot-api"):
        raise RuntimeError("telegram-bot-api is missing")
    api_dir = WORK_DIR / "telegram-bot-api"
    api_dir.mkdir(exist_ok=True)
    log_file = WORK_DIR / "telegram-bot-api.log"
    edit_progress(82, "Starting sender", "Starting Local Bot API")
    LOCAL_BOT_API_PROC = subprocess.Popen([
        "telegram-bot-api", f"--api-id={TELEGRAM_API_ID}", f"--api-hash={TELEGRAM_API_HASH}",
        "--local", "--http-ip-address=127.0.0.1", "--http-port=8081", f"--dir={api_dir}",
    ], stdout=log_file.open("w"), stderr=subprocess.STDOUT)
    for _ in range(30):
        proc = run_capture(["curl", "-sS", f"http://127.0.0.1:8081/bot{TELEGRAM_TOKEN}/getMe"])
        if proc.returncode == 0 and '"ok":true' in proc.stdout:
            LOCAL_BOT_API_STARTED = True
            return
        time.sleep(1)
    raise RuntimeError("Local Bot API did not become ready")


def send_file_to_telegram(path: Path, summary: dict[str, Any], attempt_label: str, as_document: bool = False) -> bool:
    size = path.stat().st_size
    api_base, send_mode = telegram_api_base_for_size(size)
    edit_progress(90, "Ready", "Sending file to Telegram")
    response_file = WORK_DIR / "telegram-send-response.json"
    method = "sendDocument" if as_document else "sendVideo"
    field = "document" if as_document else "video"
    args = [
        "curl", "-sS", "--connect-timeout", "20", "--max-time", "7200",
        "-o", str(response_file), "-w", "%{http_code}",
        "-X", "POST", f"{api_base}/{method}",
        "-F", f"chat_id={TELEGRAM_CHAT_ID}",
        "-F", f"{field}=@{path}",
    ]
    if not as_document:
        args.extend(["-F", "supports_streaming=true"])
    proc = run_capture(args)
    http_code = proc.stdout.strip()
    log("TELEGRAM_SEND_MODE", send_mode)
    log("TELEGRAM_HTTP_CODE", http_code or "000")
    try:
        ok = '"ok":true' in response_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        ok = False
    if ok and http_code.startswith("2"):
        final_text = (
            "✅ <b>GitHub Remote completed</b>\n\n"
            f"🌐 <b>Platform:</b> <code>{telegram_escape(PLATFORM)}</code>\n"
            f"🎚️ <b>Quality:</b> <code>{telegram_escape(str(summary.get('height') or MAX_HEIGHT_RAW))} / {telegram_escape(MAX_HEIGHT_RAW)}</code>\n"
            f"📥 <b>Final Size:</b> <code>{telegram_escape(format_bytes(size))}</code>\n"
            f"🎬 <b>Codec:</b> <code>{telegram_escape(INPUT_VIDEO_CODEC_FINAL)} → {telegram_escape(OUTPUT_VIDEO_CODEC_FINAL)}</code>\n"
            f"🚀 <b>Send Mode:</b> <code>{telegram_escape(send_mode)}</code>\n"
            f"🆔 <code>{telegram_escape(env('GITHUB_RUN_ID'))}</code>\n"
            f"🔗 <a href=\"{telegram_escape(GITHUB_RUN_URL)}\">Open Run</a>"
        )
        edit_message(final_text)
        log("FINAL_RESULT", "success_file_send")
        return True
    if not as_document and send_mode == "local":
        edit_progress(94, "Fallback send", "Video send failed; trying document fallback")
        return send_file_to_telegram(path, summary, attempt_label, as_document=True)
    return False


def edit_message(text: str) -> None:
    if not (TELEGRAM_TOKEN and PROGRESS_CHAT_ID and PROGRESS_MESSAGE_ID):
        return
    run_curl([
        "curl", "-sS", "--connect-timeout", "10", "--max-time", "20",
        "-X", "POST", f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText",
        "-F", f"chat_id={PROGRESS_CHAT_ID}",
        "-F", f"message_id={PROGRESS_MESSAGE_ID}",
        "-F", "parse_mode=HTML",
        "-F", "disable_web_page_preview=true",
        "-F", f"text={text}",
    ], check=False, quiet=True)


def write_cookie_file() -> Path | None:
    if PLATFORM == "youtube":
        raw = env("YOUTUBE_COOKIES_TXT")
        name = "youtube-cookies.txt"
    elif PLATFORM == "facebook":
        raw = env("FACEBOOK_COOKIES_TXT")
        name = "facebook-cookies.txt"
    else:
        raw = ""
        name = "site-cookies.txt"
    if not raw:
        return None
    path = WORK_DIR / name
    path.write_text(raw.replace("\r\n", "\n"), encoding="utf-8")
    path.chmod(0o600)
    return path


def ytdlp_common_opts(download: bool) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "geo_bypass": True,
        "socket_timeout": 10,
        "retries": 1,
        "fragment_retries": 1,
        "concurrent_fragment_downloads": 4,
        "http_headers": {
            "User-Agent": USER_AGENT,
            "Referer": REFERER_URL,
            "Accept-Language": "en-US,en;q=0.9",
        },
    }
    cookie_file = write_cookie_file()
    if cookie_file:
        opts["cookiefile"] = str(cookie_file)
    if download:
        opts.update({
            "outtmpl": str(WORK_DIR / "ytdlp-video.%(ext)s"),
            "merge_output_format": "mp4",
            "remux_video": "mp4",
            "max_filesize": LOCAL_BOT_API_MAX_BYTES,
        })
    return opts


def scan_formats() -> list[int]:
    if yt_dlp is None:
        raise RuntimeError(f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}")

    edit_progress(25, "Scanning", "Scanning actually downloadable GitHub Remote qualities")

    with yt_dlp.YoutubeDL(ytdlp_common_opts(False)) as ydl:
        info = ydl.extract_info(SOURCE_URL, download=False)

    formats = info.get("formats") or []
    cap = max_height_num()

    video_heights_with_audio: set[int] = set()
    video_only_heights: set[int] = set()
    audio_available = False

    for fmt in formats:
        height = fmt.get("height")
        vcodec = str(fmt.get("vcodec") or "none").lower()
        acodec = str(fmt.get("acodec") or "none").lower()
        ext = str(fmt.get("ext") or "").lower()
        url = str(fmt.get("url") or "").strip()
        protocol = str(fmt.get("protocol") or "").lower()

        if not url:
            continue

        # صيغة صوت قابلة للمرافقة مع video-only
        if vcodec == "none" and acodec != "none":
            if ext in {"m4a", "mp4", "webm"} or "m3u8" in protocol or "http" in protocol:
                audio_available = True
            continue

        if vcodec == "none" or not height:
            continue

        try:
            height = int(height)
        except Exception:
            continue

        if height < 144:
            continue

        if cap is not None and height > cap:
            continue

        # لا نعرض إلّا صيغًا قابلة فعليًّا للتنزيل عبر المسار الحالي.
        is_http_like = "http" in protocol or "m3u8" in protocol or url.startswith(("http://", "https://"))
        if not is_http_like:
            continue

        has_audio = acodec != "none"

        # صيغة muxed جاهزة: فيديو + صوت في نفس الفورمات.
        if has_audio:
            video_heights_with_audio.add(height)
            continue

        # صيغة video-only: لا نعرضها إلّا إذا كان هناك صوت منفصل متاح للدمج.
        video_only_heights.add(height)

    heights: set[int] = set(video_heights_with_audio)

    if audio_available:
        heights.update(video_only_heights)

    result = sorted(heights, reverse=True)

    if not result:
        payload = {
            "ok": False,
            "heights": [],
            "title": info.get("title") or "Media",
            "reason": "No actually downloadable video qualities were detected",
        }
        print("SMART_FORMATS_JSON=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)
        edit_progress(100, "Scan completed", "No actually downloadable qualities were detected")
        return []

    payload = {
        "ok": True,
        "heights": result,
        "title": info.get("title") or "Media",
    }
    print("SMART_FORMATS_JSON=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)
    edit_progress(100, "Scan completed", "Available qualities are ready")
    return result


def format_selector_for_height(height: int | None) -> str:
    if height is None:
        return (
            "bv*[ext=mp4][vcodec^=avc1]+ba[ext=m4a]/"
            "b[ext=mp4]/bv*+ba/best"
        )

    # Manual quality يجب أن يحاول الجودة المطلوبة نفسها فقط داخل هذه المحاولة.
    # الهبوط للأقل يتم خارجيًّا في run_ytdlp_fallback عبر candidate_heights().
    return (
        f"bv*[ext=mp4][vcodec^=avc1][height={height}]+ba[ext=m4a]/"
        f"b[ext=mp4][height={height}]/"
        f"bv*[height={height}]+ba/"
        f"best[height={height}]"
    )


def ytdlp_download_for_height(height: int | None) -> Path | None:
    if yt_dlp is None:
        raise RuntimeError(f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}")
    label = "auto" if height is None else str(height)
    edit_progress(42, "Downloading", f"yt-dlp fallback is trying {label}")
    opts = ytdlp_common_opts(True)
    opts["format"] = format_selector_for_height(height)
    opts["format_sort"] = ["vcodec:avc1", "acodec:m4a", "ext:mp4", "res", "fps", "br"]
    before = set(WORK_DIR.glob("ytdlp-video.*"))
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            ydl.extract_info(SOURCE_URL, download=True)
        except Exception as exc:
            log("YTDLP_DOWNLOAD_FAILED", type(exc).__name__)
            return None
    after = [p for p in WORK_DIR.glob("ytdlp-video.*") if p not in before or p.exists()]
    after = [p for p in after if p.is_file() and p.stat().st_size > 0]
    if not after:
        return None
    after.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return after[0]


def process_and_send(path: Path, attempt_label: str) -> bool:
    prepared = prepare_video_file(path, attempt_label)
    if not prepared:
        return False
    final_path, summary = prepared
    size = final_path.stat().st_size
    if size > LOCAL_BOT_API_MAX_BYTES:
        log("FILE_TOO_LARGE_FOR_LOCAL_BOT_API", "1")
        return False
    return send_file_to_telegram(final_path, summary, attempt_label)


def run_direct_path() -> bool:
    candidates = discover_direct_candidates()
    if not candidates:
        return False
    for idx, candidate in enumerate(candidates, start=1):
        log("DIRECT_CANDIDATE_SOURCE", candidate.source)
        log("DIRECT_CANDIDATE_HEIGHT", str(candidate.height or 0))
        if try_telegram_url_send(candidate):
            return True
        downloaded = download_candidate(candidate, idx)
        if not downloaded:
            continue
        if process_and_send(downloaded, f"direct-{idx}"):
            return True
    return False


def run_ytdlp_fallback() -> bool:
    edit_progress(34, "Fallback", "Direct path failed; switching to yt-dlp")
    if REMOTE_MODE == "manual_quality" and max_height_num() is not None:
        heights = candidate_heights()
    else:
        heights = [None] + candidate_heights()
    for h in heights:
        path = ytdlp_download_for_height(h)
        if not path:
            continue
        if process_and_send(path, "ytdlp-auto" if h is None else f"ytdlp-{h}"):
            return True
    return False


def cleanup() -> None:
    global LOCAL_BOT_API_PROC
    if LOCAL_BOT_API_PROC and LOCAL_BOT_API_PROC.poll() is None:
        try:
            LOCAL_BOT_API_PROC.send_signal(signal.SIGTERM)
            LOCAL_BOT_API_PROC.wait(timeout=5)
        except Exception:
            try:
                LOCAL_BOT_API_PROC.kill()
            except Exception:
                pass


def main() -> int:
    try:
        if not SOURCE_URL:
            raise RuntimeError("Missing MEDIA_URL_INPUT")
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            raise RuntimeError("Missing Telegram secrets")
        mask(SOURCE_URL)
        mask(TELEGRAM_TOKEN)
        mask(TELEGRAM_CHAT_ID)
        mask(PROGRESS_CHAT_ID)
        mask(PROGRESS_MESSAGE_ID)
        log("SMART_WORKER", "1")
        log("REMOTE_MODE", REMOTE_MODE)
        log("MAX_HEIGHT", MAX_HEIGHT_RAW)
        log("PLATFORM", PLATFORM)
        edit_progress(10, "Preparing", "Preparing smart GitHub worker")

        if REMOTE_MODE == "scan_formats":
            scan_formats()
            return 0

        if run_direct_path():
            return 0
        if run_ytdlp_fallback():
            return 0
        edit_progress(100, "Failed", "All GitHub Remote smart paths failed")
        log("FINAL_RESULT", "failed_all_paths")
        return 1
    except Exception as exc:
        log("SMART_WORKER_ERROR", type(exc).__name__)
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        edit_progress(100, "Failed", f"Smart worker failed: {type(exc).__name__}")
        return 1
    finally:
        cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
