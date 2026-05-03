from __future__ import annotations

import argparse
import html
import json
import math
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import urllib.request
import urllib.error

DIRECT_TELEGRAM_MAX_BYTES = 50_000_000
LOCAL_BOT_API_MAX_BYTES = 2_000_000_000
DEFAULT_SPLIT_PART_MIB = 1900
SAFE_MAX_NAME = 120


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default) or default


def telegram_chat_id() -> str:
    return env("TELEGRAM_CHAT_ID") or env("ADMIN_ID")


def github_run_url() -> str:
    server = env("GITHUB_SERVER_URL", "https://github.com")
    repo = env("GITHUB_REPOSITORY", "AD4x/telegram-media-worker")
    run_id = env("GITHUB_RUN_ID", "unknown")
    return f"{server}/{repo}/actions/runs/{run_id}"


def html_escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=False)


def format_bytes(size: int | float | None) -> str:
    try:
        n = max(int(size or 0), 0)
    except Exception:
        n = 0
    units = ["B", "KB", "MB", "GB", "TB"]
    if n < 1024:
        return f"{n} B"
    idx = min(int(math.log(max(n, 1), 1024)), len(units) - 1)
    value = n / (1024**idx)
    return f"{value:.2f} {units[idx]}"


def progress_bar(percent: int, length: int = 10) -> str:
    try:
        pct = max(0, min(100, int(percent)))
    except Exception:
        pct = 0
    filled = pct * length // 100
    return "█" * filled + "░" * (length - filled)


def sanitize_filename(value: str, fallback: str = "package_output.bin", max_len: int = SAFE_MAX_NAME) -> str:
    raw = urllib.parse.unquote((value or "").replace("\\", "/")).strip()
    name = os.path.basename(raw)
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = re.sub(r"[\\/*?:\"<>|;]", "", name)
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    if not name:
        name = fallback
    if len(name) > max_len:
        base, ext = os.path.splitext(name)
        base = base[: max(1, max_len - len(ext))].rstrip().strip(".")
        name = f"{base or 'package'}{ext}"
    return name or fallback


def sanitize_relative_path(value: str, fallback: str = "item.bin") -> str:
    raw = urllib.parse.unquote((value or "").replace("\\", "/"))
    parts: list[str] = []
    for part in raw.split("/"):
        part = sanitize_filename(part, "")
        if not part or part in {".", ".."}:
            continue
        parts.append(part)
    safe = "/".join(parts).strip("/")
    return safe or sanitize_filename(fallback, "item.bin")


def filename_from_url(url: str, fallback: str = "download.bin") -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        name = urllib.parse.unquote(parsed.path.rsplit("/", 1)[-1])
    except Exception:
        name = ""
    return sanitize_filename(name, fallback)


def ensure_zip_extension(value: str, fallback: str = "package_output.zip") -> str:
    name = sanitize_filename(value, fallback)
    base, ext = os.path.splitext(name)
    if ext.lower() != ".zip":
        name = f"{base or 'package_output'}.zip"
    return sanitize_filename(name, fallback)


def safe_url_for_log(url: str) -> str:
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "magnet":
        return "magnet:?xt=<masked>"
    netloc = parsed.netloc
    path = parsed.path
    if len(path) > 80:
        path = path[:77] + "..."
    return urllib.parse.urlunparse((parsed.scheme, netloc, path, "", "", ""))


def run_cmd(cmd: list[str], *, cwd: str | Path | None = None, timeout: int | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Package command timed out.") from None
    except OSError as exc:
        raise RuntimeError("Package command could not be executed.") from None

    if check and result.returncode != 0:
        raise RuntimeError(f"Package command failed with exit code {result.returncode}.")
    return result


def http_head(url: str, timeout: int = 25) -> dict[str, Any]:
    headers = {
        "User-Agent": "Mozilla/5.0 package-inspector-repacker",
        "Accept": "*/*",
    }
    result: dict[str, Any] = {"ok": False, "status": 0, "headers": {}, "size_bytes": 0, "content_type": ""}
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers=headers)
        if method == "GET":
            req.add_header("Range", "bytes=0-0")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                hdrs = {k.lower(): v for k, v in resp.headers.items()}
                result.update({"ok": True, "status": getattr(resp, "status", 200), "headers": hdrs})
                content_range = hdrs.get("content-range") or hdrs.get("Content-Range") or ""
                range_match = re.search(r"/(\d+)\s*$", content_range)

                if range_match:
                    result["size_bytes"] = int(range_match.group(1))
                else:
                    length = hdrs.get("content-length") or hdrs.get("Content-Length")
                    if length and str(length).isdigit():
                        result["size_bytes"] = int(length)
                result["content_type"] = (hdrs.get("content-type") or "").split(";", 1)[0].strip()
                cd = hdrs.get("content-disposition") or ""
                if cd:
                    result["filename"] = filename_from_content_disposition(cd)
                return result
        except Exception as exc:
            result["error"] = str(exc)
            continue
    return result


def filename_from_content_disposition(value: str) -> str:
    match = re.search(r"filename\*\s*=\s*[^']*''([^;]+)", value, re.I)
    if match:
        return sanitize_filename(urllib.parse.unquote(match.group(1)))
    match = re.search(r'filename\s*=\s*"([^"]+)"', value, re.I)
    if match:
        return sanitize_filename(match.group(1))
    match = re.search(r"filename\s*=\s*([^;]+)", value, re.I)
    if match:
        return sanitize_filename(match.group(1).strip())
    return ""


def download_file(url: str, dest: Path, *, timeout: int = 21600) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0 package-inspector-repacker", "Accept": "*/*"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp, dest.open("wb") as fh:
        shutil.copyfileobj(resp, fh, length=1024 * 1024)
    if not dest.exists() or dest.stat().st_size <= 0:
        raise RuntimeError("Downloaded file is empty.")
    return dest


def read_url_text(url: str, limit_bytes: int = 4_000_000, timeout: int = 40) -> str:
    headers = {"User-Agent": "Mozilla/5.0 package-inspector-repacker", "Accept": "text/plain,text/html,*/*"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read(limit_bytes + 1)
    if len(data) > limit_bytes:
        data = data[:limit_bytes]
    return data.decode("utf-8", errors="replace")


def extract_urls_from_text(text: str, base_url: str = "") -> list[str]:
    found: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.search(r"(magnet:\?[^\s]+|https?://[^\s'\"<>]+)", line)
        if match:
            found.append(match.group(1).strip())
    if not found and "<a" in text.lower():
        for href in re.findall(r"href\s*=\s*['\"]([^'\"]+)['\"]", text, flags=re.I):
            href = html.unescape(href).strip()
            if not href or href.startswith(("#", "?", "mailto:", "javascript:")):
                continue
            url = urllib.parse.urljoin(base_url, href)
            if url.rstrip("/") == base_url.rstrip("/"):
                continue
            found.append(url)
    cleaned: list[str] = []
    seen: set[str] = set()
    for url in found:
        if url in seen:
            continue
        seen.add(url)
        cleaned.append(url)
    return cleaned


def guess_kind_from_url(url: str, head: dict[str, Any] | None = None) -> str:
    low = url.lower().strip()
    content_type = ((head or {}).get("content_type") or "").lower()
    parsed = urllib.parse.urlparse(low)
    path = parsed.path
    if low.startswith("magnet:?"):
        return "torrent"
    if path.endswith(".torrent"):
        return "torrent"
    if path.endswith(".zip"):
        return "zip"
    if path.endswith(".rar"):
        return "rar"
    if path.endswith(".7z"):
        return "7z"
    if path.endswith((".txt", ".list", ".m3u", ".m3u8")) and "html" not in content_type:
        return "url_list"
    if "text/html" in content_type or low.endswith("/"):
        return "directory_listing"
    return "direct_file"


def item_from_path(index: int, path: str, size_bytes: int = 0, *, kind: str = "file", source_url: str = "") -> dict[str, Any]:
    safe_path = path.replace("\\", "/").strip("/") or f"item_{index}"
    return {
        "index": index,
        "path": safe_path,
        "name": os.path.basename(safe_path) or safe_path,
        "size_bytes": int(size_bytes or 0),
        "size_text": format_bytes(size_bytes or 0),
        "kind": kind,
        "source_url": source_url,
        "selected_by_default": True,
    }


def parse_indexes(value: str, max_index: int) -> set[int]:
    value = (value or "").strip()
    if not value:
        return set()
    selected: set[int] = set()
    for chunk in re.split(r"[,\s]+", value):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            a, b = chunk.split("-", 1)
            if a.strip().isdigit() and b.strip().isdigit():
                start, end = int(a), int(b)
                if start > end:
                    start, end = end, start
                for idx in range(start, end + 1):
                    if 1 <= idx <= max_index:
                        selected.add(idx)
            continue
        if chunk.isdigit():
            idx = int(chunk)
            if 1 <= idx <= max_index:
                selected.add(idx)
    return selected


def build_selection(items: list[dict[str, Any]], keep_indexes: str = "", delete_indexes: str = "") -> list[dict[str, Any]]:
    max_index = len(items)
    keep = parse_indexes(keep_indexes, max_index)
    delete = parse_indexes(delete_indexes, max_index)
    if keep:
        chosen = [item for item in items if int(item.get("index", 0)) in keep]
    else:
        chosen = [item for item in items if int(item.get("index", 0)) not in delete]
    return chosen


def load_rename_map(raw: str) -> dict[str, str]:
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"rename_map_json is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("rename_map_json must be a JSON object.")
    result: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        clean_value = sanitize_relative_path(value, fallback=os.path.basename(key) or "item.bin")
        if clean_value:
            result[key] = clean_value
    return result


def target_path_for_item(item: dict[str, Any], rename_map: dict[str, str]) -> str:
    path = str(item.get("path") or item.get("name") or f"item_{item.get('index', 0)}")
    name = str(item.get("name") or os.path.basename(path) or path)
    for key in (path, name, f"{item.get('index')}"):
        if key in rename_map:
            return sanitize_relative_path(rename_map[key], fallback=name)
    return sanitize_relative_path(path, fallback=name)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class TelegramContext:
    def __init__(
        self,
        token: str,
        chat_id: str,
        progress_chat_id: str = "",
        progress_message_id: str = "",
    ):
        self.token = token
        self.chat_id = chat_id
        self.progress_chat_id = progress_chat_id
        self.progress_message_id = progress_message_id

    @classmethod
    def from_env(cls) -> "TelegramContext":
        return cls(
            token=env("TELEGRAM_TOKEN"),
            chat_id=telegram_chat_id(),
            progress_chat_id=env("PROGRESS_CHAT_ID"),
            progress_message_id=env("PROGRESS_MESSAGE_ID"),
        )

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)


def curl_form(url: str, fields: dict[str, str], files: dict[str, tuple[Path, str]] | None = None, timeout: int = 21600) -> tuple[int, str]:
    cmd = ["curl", "--ipv4", "-sS", "--connect-timeout", "20", "--max-time", str(timeout), "-w", "\n%{http_code}", "-X", "POST", url]
    for key, value in fields.items():
        cmd.extend(["-F", f"{key}={value}"])
    for key, (path, filename) in (files or {}).items():
        cmd.extend(["-F", f"{key}=@{path};filename={filename}"])
    result = run_cmd(cmd, check=False)
    output = result.stdout or ""
    if "\n" in output:
        body, code = output.rsplit("\n", 1)
    else:
        body, code = output, "000"
    try:
        return int(code.strip()) if code.strip().isdigit() else 0, body
    except Exception:
        return 0, body


def telegram_edit_progress(ctx: TelegramContext, percent: int, label: str, detail: str) -> None:
    if not (ctx.token and ctx.progress_chat_id and ctx.progress_message_id):
        return
    text = (
        "🐙 <b>GitHub Remote</b>\n\n"
        f"📊 <code>[{progress_bar(percent)}] {max(0, min(100, int(percent)))}%</code>\n"
        f"🧭 <b>Status:</b> {html_escape(label)}\n"
        f"ℹ️ <i>{html_escape(str(detail).replace('_', ' '))}</i>\n"
        f"🆔 <code>{html_escape(env('GITHUB_RUN_ID', 'unknown'))}</code>\n"
        f"🔗 <a href=\"{html_escape(github_run_url())}\">Open Run</a>"
    )
    curl_form(
        f"https://api.telegram.org/bot{ctx.token}/editMessageText",
        {
            "chat_id": ctx.progress_chat_id,
            "message_id": ctx.progress_message_id,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
            "text": text,
        },
        timeout=20,
    )


def progress_stage(ctx: TelegramContext, stage: str, percent: int, label: str, detail: str) -> None:
    print(f"PROGRESS_STAGE={stage}")
    print(f"PROGRESS_PERCENT={percent}")
    print(f"PROGRESS_LABEL={label}")
    print(f"PROGRESS_DETAIL={detail}")
    telegram_edit_progress(ctx, percent, label, detail)


def telegram_send_message(ctx: TelegramContext, text: str) -> bool:
    if not ctx.configured:
        print("TELEGRAM_MESSAGE_SKIPPED=missing_credentials")
        return False
    code, body = curl_form(
        f"https://api.telegram.org/bot{ctx.token}/sendMessage",
        {
            "chat_id": ctx.chat_id,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
            "text": text,
        },
        timeout=30,
    )
    ok = 200 <= code <= 299 and '"ok":true' in body
    print(f"TELEGRAM_SEND_MESSAGE_HTTP={code}")
    return ok


def telegram_edit_final(ctx: TelegramContext, title: str, body: str, *, status: str = "Completed") -> None:
    if not (ctx.token and ctx.progress_chat_id and ctx.progress_message_id):
        return
    text = (
        f"{title}\n\n"
        f"{body}\n"
        f"🧭 <b>Status:</b> {html_escape(status)}\n"
        f"🆔 <code>{html_escape(env('GITHUB_RUN_ID', 'unknown'))}</code>\n"
        f"🔗 <a href=\"{html_escape(github_run_url())}\">Open Run</a>"
    )
    curl_form(
        f"https://api.telegram.org/bot{ctx.token}/editMessageText",
        {
            "chat_id": ctx.progress_chat_id,
            "message_id": ctx.progress_message_id,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
            "text": text,
        },
        timeout=30,
    )

def telegram_delete_progress(ctx: TelegramContext) -> None:
    if not (ctx.token and ctx.progress_chat_id and ctx.progress_message_id):
        return

    curl_form(
        f"https://api.telegram.org/bot{ctx.token}/deleteMessage",
        {
            "chat_id": ctx.progress_chat_id,
            "message_id": ctx.progress_message_id,
        },
        timeout=20,
    )

def start_local_bot_api(ctx: TelegramContext) -> str:
    if not shutil.which("telegram-bot-api"):
        raise RuntimeError("telegram-bot-api is missing from the worker image.")
    api_id = env("TELEGRAM_API_ID")
    api_hash = env("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        raise RuntimeError("Large upload requires TELEGRAM_API_ID and TELEGRAM_API_HASH secrets.")
    work_dir = Path(env("RUNNER_TEMP", "/tmp")) / "telegram-bot-api-package"
    work_dir.mkdir(parents=True, exist_ok=True)
    log_path = work_dir / "telegram-bot-api.log"
    port = 8081
    cmd = [
        "telegram-bot-api",
        f"--api-id={api_id}",
        f"--api-hash={api_hash}",
        "--local",
        "--http-ip-address=127.0.0.1",
        f"--http-port={port}",
        f"--dir={work_dir}",
    ]
    log = log_path.open("ab")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(90):
        if proc.poll() is not None:
            raise RuntimeError("Local Bot API exited before becoming ready.")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                os.environ["PACKAGE_LOCAL_BOT_API_PID"] = str(proc.pid)
                return f"http://127.0.0.1:{port}/bot{ctx.token}"
        time.sleep(1)
    raise RuntimeError("Local Bot API did not become ready.")


def stop_local_bot_api() -> None:
    pid = env("PACKAGE_LOCAL_BOT_API_PID")
    if pid.isdigit():
        try:
            os.kill(int(pid), 15)
        except Exception:
            pass


def telegram_send_document(ctx: TelegramContext, path: Path, display_name: str, caption: str, *, split_part_mib: int = DEFAULT_SPLIT_PART_MIB) -> bool:
    if not ctx.configured:
        print("TELEGRAM_DOCUMENT_SKIPPED=missing_credentials")
        return False
    if not path.exists() or path.stat().st_size <= 0:
        raise RuntimeError("Cannot send missing or empty document.")
    size = path.stat().st_size
    display = sanitize_filename(display_name, path.name)
    if size > LOCAL_BOT_API_MAX_BYTES:
        return telegram_send_split_document(ctx, path, display, caption, split_part_mib=split_part_mib)
    if size <= DIRECT_TELEGRAM_MAX_BYTES:
        api_base = f"https://api.telegram.org/bot{ctx.token}"
        send_mode = "public"
    else:
        api_base = start_local_bot_api(ctx)
        send_mode = "local"
    code, body = curl_form(
        f"{api_base}/sendDocument",
        {"chat_id": ctx.chat_id, "parse_mode": "HTML", "caption": caption},
        {"document": (path, display)},
        timeout=21600,
    )
    ok = 200 <= code <= 299 and '"ok":true' in body
    print(f"TELEGRAM_DOCUMENT_HTTP={code}")
    print(f"TELEGRAM_DOCUMENT_SEND_MODE={send_mode}")
    return ok


def telegram_send_split_document(ctx: TelegramContext, path: Path, display_name: str, caption: str, *, split_part_mib: int = DEFAULT_SPLIT_PART_MIB) -> bool:
    split_part_mib = max(64, min(int(split_part_mib or DEFAULT_SPLIT_PART_MIB), DEFAULT_SPLIT_PART_MIB))
    part_bytes = split_part_mib * 1024 * 1024
    total = path.stat().st_size
    count = (total + part_bytes - 1) // part_bytes
    notice = (
        "📦 <b>Large GitHub Document</b>\n\n"
        f"The file is larger than Telegram single-file limit, so it will be sent in <b>{count} parts</b>.\n\n"
        f"📥 <b>Total Size:</b> <code>{html_escape(format_bytes(total))}</code>\n"
        "ℹ️ <i>Download all parts, then join them in order to restore the original ZIP.</i>"
    )
    telegram_send_message(ctx, notice)
    api_base = start_local_bot_api(ctx)
    ok_all = True
    with path.open("rb") as src:
        for index in range(1, count + 1):
            part_name = sanitize_filename(f"{display_name}.part{index:03d}", f"package.part{index:03d}")
            part_path = Path(env("RUNNER_TEMP", "/tmp")) / part_name
            with part_path.open("wb") as dst:
                remaining = part_bytes
                while remaining > 0:
                    chunk = src.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    dst.write(chunk)
                    remaining -= len(chunk)
            part_caption = f"{caption}\n🧩 Part {index}/{count}\n📦 {html_escape(format_bytes(part_path.stat().st_size))} / {html_escape(format_bytes(total))}"
            code, body = curl_form(
                f"{api_base}/sendDocument",
                {"chat_id": ctx.chat_id, "parse_mode": "HTML", "caption": part_caption},
                {"document": (part_path, part_name)},
                timeout=21600,
            )
            ok = 200 <= code <= 299 and '"ok":true' in body
            print(f"TELEGRAM_SPLIT_PART_HTTP={code}")
            ok_all = ok_all and ok
            part_path.unlink(missing_ok=True)
            if not ok:
                break
    return ok_all


def manifest_caption(manifest: dict[str, Any]) -> str:
    mid = manifest.get("manifest_id") or manifest.get("dispatch_key") or "manual"
    kind = manifest.get("source", {}).get("kind", "unknown")
    count = len(manifest.get("items") or [])
    return (
        "📄 <b>Package manifest</b>\n"
        f"🧩 Items: <code>{count}</code>\n"
        f"📦 Kind: <code>{html_escape(kind)}</code>\n"
        f"🆔 <code>{html_escape(mid)}</code>"
    )


def compact_items_for_telegram(items: list[dict[str, Any]], limit: int = 30) -> str:
    lines: list[str] = []
    for item in items[:limit]:
        idx = item.get("index", "?")
        path = html_escape(item.get("path") or item.get("name") or "item")
        size = html_escape(item.get("size_text") or format_bytes(item.get("size_bytes") or 0))
        lines.append(f"{idx}. <code>{path}</code> — <code>{size}</code>")
    if len(items) > limit:
        lines.append(f"… +{len(items) - limit} more items in manifest.json")
    return "\n".join(lines) if lines else "No items found."


def build_manifest(source_url: str, kind: str, items: list[dict[str, Any]], *, dispatch_key: str = "manual", source_meta: dict[str, Any] | None = None, warnings: list[str] | None = None) -> dict[str, Any]:
    total_bytes = sum(int(item.get("size_bytes") or 0) for item in items)
    manifest_id = f"pkg-{dispatch_key or 'manual'}-{int(time.time())}"
    return {
        "schema_version": 1,
        "feature": "package-inspector-repacker",
        "manifest_id": manifest_id,
        "created_at": utc_now_iso(),
        "dispatch_key": dispatch_key or "manual",
        "source": {
            "url": source_url,
            "kind": kind,
            "safe_log_url": safe_url_for_log(source_url),
            **(source_meta or {}),
        },
        "summary": {
            "item_count": len(items),
            "total_size_bytes": total_bytes,
            "total_size_text": format_bytes(total_bytes),
        },
        "items": items,
        "warnings": warnings or [],
        "bot_binding": {
            "index_base": 1,
            "display_key": "path",
            "keep_indexes_format": "1,2,4-6",
            "delete_indexes_format": "2,3",
            "rename_map_key": "path",
            "repack_workflow": "package-repack.yml",
            "required_repack_inputs": ["source_url", "keep_indexes", "delete_indexes", "rename_map_json", "output_filename", "dispatch_key"],
        },
    }


def add_common_cli(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--dispatch-key", default="manual")
    parser.add_argument("--progress-chat-id", default="")
    parser.add_argument("--progress-message-id", default="")
    parser.add_argument("--work-dir", default="work/package")
