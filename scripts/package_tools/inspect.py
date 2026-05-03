from __future__ import annotations

import argparse
import os
import re
import zipfile
import base64
import binascii
import gzip
import urllib.request
from pathlib import Path
from typing import Any

from common import (
    TelegramContext,
    add_common_cli,
    build_manifest,
    compact_items_for_telegram,
    download_file,
    extract_urls_from_text,
    filename_from_url,
    format_bytes,
    guess_kind_from_url,
    html_escape,
    http_head,
    item_from_path,
    progress_stage,
    read_url_text,
    run_cmd,
    safe_url_for_log,
    sanitize_filename,
    telegram_edit_final,
    telegram_send_message,
    write_json,
)


def list_zip(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            items.append(item_from_path(len(items) + 1, info.filename, int(info.file_size or 0), kind="archive_member"))
    return items


def parse_7z_listing(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    block: dict[str, str] = {}

    def flush() -> None:
        if not block:
            return
        path = block.get("Path", "").strip()
        folder = block.get("Folder", "-").strip() == "+"
        if path and not folder and path not in {"Name", "----------"}:
            size = 0
            raw_size = block.get("Size", "0").strip()
            if raw_size.isdigit():
                size = int(raw_size)
            items.append(item_from_path(len(items) + 1, path, size, kind="archive_member"))

    for line in text.splitlines():
        if not line.strip():
            flush()
            block = {}
            continue
        if " = " in line:
            key, value = line.split(" = ", 1)
            block[key.strip()] = value.strip()
    flush()
    return items


def list_with_7z(path: Path) -> list[dict[str, Any]]:
    result = run_cmd(["7z", "l", "-slt", str(path)], check=True)
    return parse_7z_listing(result.stdout)


def list_with_bsdtar(path: Path) -> list[dict[str, Any]]:
    result = run_cmd(["bsdtar", "-tvf", str(path)], check=True)
    items: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        parts = line.split(None, 8)
        if len(parts) < 9:
            continue
        mode = parts[0]
        if mode.startswith("d"):
            continue
        size = int(parts[4]) if parts[4].isdigit() else 0
        item_path = parts[8].strip()
        if item_path:
            items.append(item_from_path(len(items) + 1, item_path, size, kind="archive_member"))
    return items


def parse_aria2_show_files(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        match = re.match(r"^\s*(\d+)\|(.+)$", line)
        if match:
            path = match.group(2).strip()
            if path and not path.lower().startswith("path/"):
                current = item_from_path(int(match.group(1)), path, 0, kind="torrent_file")
                items.append(current)
            continue
        size_match = re.match(r"^\s*\|\s*([0-9.]+)\s*([KMGT]?i?B|[KMGT]?B)\s*$", line, re.I)
        if current and size_match:
            current["size_text"] = f"{size_match.group(1)} {size_match.group(2)}"
    for pos, item in enumerate(items, start=1):
        item["torrent_index"] = int(item.get("index") or pos)
        item["index"] = pos
    return items

def _bdecode(data: bytes, pos: int = 0) -> tuple[Any, int]:
    if pos >= len(data):
        raise ValueError("Unexpected end of bencode data.")

    token = data[pos:pos + 1]

    if token == b"i":
        end = data.index(b"e", pos)
        return int(data[pos + 1:end]), end + 1

    if token == b"l":
        pos += 1
        result = []
        while data[pos:pos + 1] != b"e":
            value, pos = _bdecode(data, pos)
            result.append(value)
        return result, pos + 1

    if token == b"d":
        pos += 1
        result = {}
        while data[pos:pos + 1] != b"e":
            key, pos = _bdecode(data, pos)
            value, pos = _bdecode(data, pos)
            result[key] = value
        return result, pos + 1

    if token.isdigit():
        colon = data.index(b":", pos)
        length = int(data[pos:colon])
        start = colon + 1
        end = start + length
        return data[start:end], end

    raise ValueError(f"Invalid bencode token at position {pos}.")


def _torrent_text(value: Any) -> str:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.decode("latin-1", errors="replace")

    return str(value or "")


def _torrent_dict_get(data: dict, *keys: bytes) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return None


def parse_torrent_metadata_file(torrent_file: Path) -> list[dict[str, Any]]:
    raw = torrent_file.read_bytes()
    decoded, _pos = _bdecode(raw, 0)

    if not isinstance(decoded, dict):
        return []

    info = decoded.get(b"info")
    if not isinstance(info, dict):
        return []

    root_name = _torrent_text(
        _torrent_dict_get(info, b"name.utf-8", b"name")
    ).strip() or "torrent"

    items: list[dict[str, Any]] = []

    files = info.get(b"files")
    if isinstance(files, list):
        for torrent_index, file_entry in enumerate(files, start=1):
            if not isinstance(file_entry, dict):
                continue

            size = int(file_entry.get(b"length") or 0)
            path_parts = _torrent_dict_get(file_entry, b"path.utf-8", b"path")

            if not isinstance(path_parts, list):
                continue

            rel_parts = []
            for part in path_parts:
                clean_part = _torrent_text(part).strip()
                if clean_part:
                    rel_parts.append(clean_part)

            if not rel_parts:
                continue

            item_path = "/".join([root_name, *rel_parts]).strip("/")
            item = item_from_path(len(items) + 1, item_path, size, kind="torrent_file")
            item["torrent_index"] = torrent_index
            items.append(item)

        return items

    size = int(info.get(b"length") or 0)
    item = item_from_path(1, root_name, size, kind="torrent_file")
    item["torrent_index"] = 1
    return [item]

def inspect_torrent(source_url: str, work_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    work_dir.mkdir(parents=True, exist_ok=True)

    source_lower = source_url.lower().strip()

    def extract_btih(value: str) -> str | None:
        match = re.search(r"urn:btih:([A-Za-z0-9]+)", value, re.I)
        if not match:
            return None

        raw = match.group(1).strip()

        if re.fullmatch(r"[A-Fa-f0-9]{40}", raw):
            return raw.upper()

        if re.fullmatch(r"[A-Za-z2-7]{32}", raw):
            try:
                return base64.b32decode(raw.upper()).hex().upper()
            except (binascii.Error, ValueError):
                return None

        return None

    def find_latest_torrent_file(*roots: Path) -> Path | None:
        candidates: list[Path] = []

        for root in roots:
            try:
                if root and root.exists():
                    candidates.extend(
                        path for path in root.rglob("*.torrent")
                        if path.is_file() and path.stat().st_size > 0
                    )
            except Exception:
                continue

        if not candidates:
            return None

        return sorted(
            candidates,
            key=lambda path: path.stat().st_mtime if path.exists() else 0,
            reverse=True,
        )[0]

    def list_torrent_file(torrent_file: Path) -> list[dict[str, Any]]:
        try:
            items = parse_torrent_metadata_file(torrent_file)
            if items:
                return items
        except Exception as exc:
            warnings.append(f"Direct torrent metadata parser failed: {exc}")

        show_result = run_cmd(
            [
                "aria2c",
                "-S",
                str(torrent_file),
            ],
            cwd=work_dir,
            timeout=120,
            check=False,
        )
        return parse_aria2_show_files(show_result.stdout or "")

    def fetch_cached_torrent(info_hash: str) -> Path | None:
        urls = [
            f"https://itorrents.org/torrent/{info_hash}.torrent",
            f"http://itorrents.net/torrent/{info_hash}.torrent",
            f"https://torrage.info/torrent.php?h={info_hash}",
            f"https://btcache.me/torrent/{info_hash}",
        ]

        for pos, cache_url in enumerate(urls, start=1):
            target = work_dir / f"cached-{pos}-{info_hash}.torrent"

            try:
                req = urllib.request.Request(
                    cache_url,
                    headers={
                        "User-Agent": "AMD4x-Package-Inspector/1.0",
                        "Accept": "application/x-bittorrent,*/*",
                        "Accept-Encoding": "gzip",
                    },
                )

                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = resp.read()
                    encoding = str(resp.headers.get("Content-Encoding") or "").lower()

                if encoding == "gzip" or data.startswith(b"\x1f\x8b"):
                    try:
                        data = gzip.decompress(data)
                    except Exception:
                        pass

                if not data.startswith(b"d") or b"4:info" not in data[:2000000]:
                    continue

                target.write_bytes(data)

                if target.exists() and target.stat().st_size > 0:
                    return target

            except Exception:
                continue

        return None

    if source_lower.startswith("magnet:?"):
        info_hash = extract_btih(source_url)

        if info_hash:
            cached_torrent = fetch_cached_torrent(info_hash)
            if cached_torrent:
                items = list_torrent_file(cached_torrent)
                if items:
                    return items, warnings

                warnings.append("Torrent cache returned metadata, but aria2c -S did not return a parsable file list.")

        runner_temp = Path(os.environ.get("RUNNER_TEMP") or "/tmp")
        dht_file = runner_temp / "aria2-dht-package-inspect.dat"

        metadata_cmd = [
            "timeout",
            "240s",
            "aria2c",
            f"--dir={work_dir}",
            "--bt-metadata-only=true",
            "--bt-save-metadata=true",
            "--seed-time=0",
            "--seed-ratio=0.0",
            "--max-overall-upload-limit=1K",
            "--disable-ipv6=true",
            "--enable-dht=true",
            "--enable-dht6=false",
            f"--dht-file-path={dht_file}",
            "--bt-stop-timeout=180",
            "--summary-interval=0",
            "--console-log-level=warn",
            source_url,
        ]

        metadata_result = run_cmd(
            metadata_cmd,
            cwd=work_dir,
            timeout=300,
            check=False,
        )

        torrent_file = find_latest_torrent_file(work_dir, runner_temp, Path.cwd())

        if torrent_file:
            items = list_torrent_file(torrent_file)
            if not items:
                warnings.append("Torrent metadata was fetched, but aria2c -S did not return a parsable file list.")
            return items, warnings

        items = parse_aria2_show_files((metadata_result.stdout or "") + "\n" + (metadata_result.stderr or ""))

        if not items:
            warnings.append(
                "Could not fetch torrent metadata from this magnet link. "
                "Tried torrent metadata cache first, then aria2 DHT/tracker metadata fetch, "
                "but no parsable .torrent metadata was available."
            )

        return items, warnings

    torrent_file = work_dir / sanitize_filename(filename_from_url(source_url, "source.torrent"), "source.torrent")
    download_file(source_url, torrent_file)

    items = list_torrent_file(torrent_file)

    if not items:
        warnings.append("Could not parse torrent file list from aria2c -S output.")

    return items, warnings


def inspect_url_list(source_url: str, work_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    text = source_url if "\n" in source_url else read_url_text(source_url)
    urls = extract_urls_from_text(text, source_url if source_url.startswith("http") else "")
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    for url in urls:
        head = http_head(url)
        name = head.get("filename") or filename_from_url(url, f"url_item_{len(items) + 1}.bin")
        size = int(head.get("size_bytes") or 0)
        item = item_from_path(len(items) + 1, name, size, kind="url_item", source_url=url)
        item["content_type"] = head.get("content_type", "")
        items.append(item)
    if not items:
        warnings.append("No URLs were found in the supplied list.")
    return items, warnings


def inspect_directory_listing(source_url: str) -> tuple[list[dict[str, Any]], list[str]]:
    text = read_url_text(source_url)
    urls = extract_urls_from_text(text, source_url)
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    for url in urls:
        parsed_path = os.path.basename(url.split("?", 1)[0].rstrip("/"))
        if not parsed_path or url.endswith("/"):
            continue
        head = http_head(url)
        name = head.get("filename") or filename_from_url(url, f"listing_item_{len(items) + 1}.bin")
        size = int(head.get("size_bytes") or 0)
        item = item_from_path(len(items) + 1, name, size, kind="directory_item", source_url=url)
        item["content_type"] = head.get("content_type", "")
        items.append(item)
    if not items:
        warnings.append("Directory listing parsing is best-effort and no downloadable file links were found.")
    return items, warnings


def inspect_direct_file(source_url: str, head: dict[str, Any]) -> list[dict[str, Any]]:
    name = head.get("filename") or filename_from_url(source_url, "direct_file.bin")
    size = int(head.get("size_bytes") or 0)
    item = item_from_path(1, name, size, kind="direct_file", source_url=source_url)
    item["content_type"] = head.get("content_type", "") or mimetype_from_name(name)
    return [item]


def mimetype_from_name(name: str) -> str:
    import mimetypes

    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def inspect_archive(source_url: str, kind: str, work_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    archive_name = filename_from_url(source_url, f"source.{kind}")
    archive_path = work_dir / sanitize_filename(archive_name, f"source.{kind}")
    download_file(source_url, archive_path)
    if kind == "zip":
        items = list_zip(archive_path)
    else:
        try:
            items = list_with_7z(archive_path)
        except Exception as exc_7z:
            try:
                items = list_with_bsdtar(archive_path)
                warnings.append(f"7z listing failed, but bsdtar listed this {kind.upper()} archive.")
            except Exception as exc_bsdtar:
                items = []
                warnings.append(f"Could not list this {kind.upper()} archive with 7z or bsdtar: {exc_7z}; {exc_bsdtar}")
    return items, warnings


def build_report(manifest: dict[str, Any]) -> str:
    source = manifest.get("source", {})
    items = manifest.get("items") or []
    warnings = manifest.get("warnings") or []
    warning_text = ""
    if warnings:
        warning_text = "\n\n⚠️ <b>Notes:</b>\n" + "\n".join(f"- {html_escape(w)}" for w in warnings[:5])
    return (
        "📦 <b>Package Inspector</b>\n\n"
        "🔗 <b>Source:</b>\n"
        f"<code>{html_escape(source.get('safe_log_url') or safe_url_for_log(source.get('url', '')))}</code>\n\n"
        f"🧭 <b>Type:</b> <code>{html_escape(source.get('kind', 'unknown'))}</code>\n"
        f"🧩 <b>Items:</b> <code>{len(items)}</code>\n"
        f"📏 <b>Total:</b> <code>{html_escape(manifest.get('summary', {}).get('total_size_text', 'Unknown'))}</code>\n\n"
        "🧩 <b>Item list:</b>\n"
        f"{compact_items_for_telegram(items)}"
        f"{warning_text}\n\n"
       "📄 <b>Package Browser:</b> Ready."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect package-like source and create manifest.json")
    add_common_cli(parser)
    parser.add_argument("--manifest-out", default="manifest.json")
    parser.add_argument("--send-telegram", default="true", choices=["true", "false"])
    args = parser.parse_args()

    if args.progress_chat_id:
        os.environ["PROGRESS_CHAT_ID"] = args.progress_chat_id
    if args.progress_message_id:
        os.environ["PROGRESS_MESSAGE_ID"] = args.progress_message_id

    ctx = TelegramContext.from_env()
    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    progress_stage(ctx, "inspecting", 10, "Inspecting", "Preparing_package_inspection")
    source_url = args.source_url.strip()
    if not source_url:
        raise SystemExit("Missing source_url.")

    head = http_head(source_url) if source_url.startswith(("http://", "https://")) else {}
    kind = guess_kind_from_url(source_url, head)
    source_meta = {
        "content_type": head.get("content_type", ""),
        "size_bytes": int(head.get("size_bytes") or 0),
        "size_text": format_bytes(head.get("size_bytes") or 0),
    }

    progress_stage(ctx, "listing", 25, "Listing", f"Detected_{kind}")
    warnings: list[str] = []

    if kind in {"zip", "rar", "7z"}:
        items, warnings = inspect_archive(source_url, kind, work_dir)
    elif kind == "torrent":
        items, warnings = inspect_torrent(source_url, work_dir)
    elif kind == "url_list":
        items, warnings = inspect_url_list(source_url, work_dir)
    elif kind == "directory_listing":
        items, warnings = inspect_directory_listing(source_url)
    else:
        items = inspect_direct_file(source_url, head)

    progress_stage(ctx, "manifest", 70, "Building", "Building_manifest_json")
    manifest = build_manifest(
        source_url,
        kind,
        items,
        dispatch_key=args.dispatch_key,
        source_meta=source_meta,
        warnings=warnings,
    )
    out = Path(args.manifest_out)
    write_json(out, manifest)

    progress_stage(ctx, "uploading", 85, "Uploading", "Sending_manifest_report")
    report = build_report(manifest)
    if args.send_telegram == "true":
        telegram_send_message(ctx, report)
        telegram_edit_final(
            ctx,
            "✅ <b>GitHub Remote</b>",
            "📦 <b>Package Inspector completed</b>\n",
        )
    print("PACKAGE_INSPECT_COMPLETED")
    progress_stage(ctx, "completed", 100, "Completed", "Package_inspection_completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
