"""Repack selected package items into a Telegram-ready ZIP."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import zipfile
import base64
import binascii
import gzip
import re
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any

from common import (
    DEFAULT_SPLIT_PART_MIB,
    TelegramContext,
    add_common_cli,
    build_selection,
    download_file,
    ensure_zip_extension,
    filename_from_url,
    format_bytes,
    guess_kind_from_url,
    html_escape,
    http_head,
    load_rename_map,
    progress_stage,
    read_url_text,
    run_cmd,
    sanitize_filename,
    sanitize_relative_path,
    target_path_for_item,
    telegram_delete_progress,
    telegram_edit_final,
    telegram_send_document,
    telegram_send_message,
    write_json,
)
import importlib.util

_INSPECT_PATH = Path(__file__).with_name("inspect.py")
_INSPECT_SPEC = importlib.util.spec_from_file_location("package_tools_inspect", _INSPECT_PATH)
if _INSPECT_SPEC is None or _INSPECT_SPEC.loader is None:
    raise RuntimeError("Could not load package inspect helpers.")
_INSPECT_MOD = importlib.util.module_from_spec(_INSPECT_SPEC)
_INSPECT_SPEC.loader.exec_module(_INSPECT_MOD)

inspect_archive = _INSPECT_MOD.inspect_archive
inspect_direct_file = _INSPECT_MOD.inspect_direct_file
inspect_directory_listing = _INSPECT_MOD.inspect_directory_listing
inspect_torrent = _INSPECT_MOD.inspect_torrent
inspect_url_list = _INSPECT_MOD.inspect_url_list


def fresh_manifest(source_url: str, work_dir: Path, dispatch_key: str) -> dict[str, Any]:
    head = http_head(source_url) if source_url.startswith(("http://", "https://")) else {}
    kind = guess_kind_from_url(source_url, head)
    if kind in {"zip", "rar", "7z"}:
        items, warnings = inspect_archive(source_url, kind, work_dir / "inspect")
    elif kind == "torrent":
        items, warnings = inspect_torrent(source_url, work_dir / "inspect")
    elif kind == "url_list":
        items, warnings = inspect_url_list(source_url, work_dir / "inspect")
    elif kind == "directory_listing":
        items, warnings = inspect_directory_listing(source_url)
    else:
        items = inspect_direct_file(source_url, head)
        warnings = []
    from common import build_manifest

    return build_manifest(
        source_url,
        kind,
        items,
        dispatch_key=dispatch_key,
        source_meta={
            "content_type": head.get("content_type", ""),
            "size_bytes": int(head.get("size_bytes") or 0),
            "size_text": format_bytes(head.get("size_bytes") or 0),
        },
        warnings=warnings,
    )


def copy_into_stage(src: Path, stage_dir: Path, rel_path: str) -> Path:
    target = stage_dir / sanitize_relative_path(rel_path, fallback=src.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    return target


def extract_zip_selected(archive_path: Path, selected: list[dict[str, Any]], stage_dir: Path, rename_map: dict[str, str]) -> None:
    selected_paths = {str(item.get("path")): item for item in selected}
    with zipfile.ZipFile(archive_path) as zf:
        for info in zf.infolist():
            if info.is_dir() or info.filename not in selected_paths:
                continue
            item = selected_paths[info.filename]
            target_rel = target_path_for_item(item, rename_map)
            target = stage_dir / target_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)


def extract_7z_selected(archive_path: Path, selected: list[dict[str, Any]], stage_dir: Path, rename_map: dict[str, str]) -> None:
    temp_extract = stage_dir.parent / "archive_extract"
    shutil.rmtree(temp_extract, ignore_errors=True)
    temp_extract.mkdir(parents=True, exist_ok=True)
    for item in selected:
        original = str(item.get("path") or "")
        if not original:
            continue
        extracted = temp_extract / original
        try:
            run_cmd(["7z", "x", "-y", f"-o{temp_extract}", str(archive_path), original], check=True)
        except Exception:
            run_cmd(["bsdtar", "-xf", str(archive_path), "-C", str(temp_extract), original], check=True)
        if extracted.exists() and extracted.is_file():
            copy_into_stage(extracted, stage_dir, target_path_for_item(item, rename_map))


def stage_archive(source_url: str, kind: str, selected: list[dict[str, Any]], stage_dir: Path, work_dir: Path, rename_map: dict[str, str]) -> None:
    archive_name = filename_from_url(source_url, f"source.{kind}")
    archive_path = work_dir / sanitize_filename(archive_name, f"source.{kind}")
    download_file(source_url, archive_path)
    if kind == "zip":
        extract_zip_selected(archive_path, selected, stage_dir, rename_map)
    else:
        extract_7z_selected(archive_path, selected, stage_dir, rename_map)


def stage_direct(source_url: str, selected: list[dict[str, Any]], stage_dir: Path, work_dir: Path, rename_map: dict[str, str]) -> None:
    if not selected:
        return
    item = selected[0]
    name = item.get("name") or filename_from_url(source_url, "direct_file.bin")
    src = work_dir / sanitize_filename(str(name), "direct_file.bin")
    download_file(source_url, src)
    copy_into_stage(src, stage_dir, target_path_for_item(item, rename_map))


def stage_url_items(selected: list[dict[str, Any]], stage_dir: Path, work_dir: Path, rename_map: dict[str, str]) -> None:
    for item in selected:
        url = str(item.get("source_url") or "")
        if not url:
            continue
        name = item.get("name") or filename_from_url(url, f"item_{item.get('index', 'x')}.bin")
        src = work_dir / f"url_{item.get('index', 'x')}_{sanitize_filename(str(name), 'item.bin')}"
        download_file(url, src)
        copy_into_stage(src, stage_dir, target_path_for_item(item, rename_map))


def stage_torrent(source_url: str, selected: list[dict[str, Any]], stage_dir: Path, work_dir: Path, rename_map: dict[str, str]) -> None:
    if not selected:
        return

    download_dir = work_dir / "torrent_download"
    download_dir.mkdir(parents=True, exist_ok=True)

    source_lower = source_url.lower().strip()
    torrent_source = source_url

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

    def extract_magnet_trackers(value: str) -> list[str]:
        trackers: list[str] = []

        try:
            parsed = urllib.parse.urlparse(value)
            for key, raw_tracker in urllib.parse.parse_qsl(parsed.query, keep_blank_values=False):
                if key != "tr":
                    continue

                tracker = urllib.parse.unquote(str(raw_tracker or "")).strip()
                if tracker and tracker not in trackers:
                    trackers.append(tracker)
        except Exception:
            return []

        return trackers

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

    def fetch_cached_torrent(info_hash: str) -> Path | None:
        urls = [
            f"https://itorrents.org/torrent/{info_hash}.torrent",
            f"http://itorrents.net/torrent/{info_hash}.torrent",
            f"https://torrage.info/torrent.php?h={info_hash}",
            f"https://btcache.me/torrent/{info_hash}",
        ]

        for pos, cache_url in enumerate(urls, start=1):
            target = work_dir / f"cached-repack-{pos}-{info_hash}.torrent"

            try:
                req = urllib.request.Request(
                    cache_url,
                    headers={
                        "User-Agent": "AMD4x-Package-Repacker/1.0",
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
                torrent_source = str(cached_torrent)

        if torrent_source == source_url:
            metadata_dir = work_dir / "torrent_metadata"
            metadata_dir.mkdir(parents=True, exist_ok=True)

            runner_temp = Path(os.environ.get("RUNNER_TEMP") or "/tmp")
            dht_file = runner_temp / "aria2-dht-package-repack.dat"
            tracker_args = []
            trackers = extract_magnet_trackers(source_url)
            if trackers:
                tracker_args = [f"--bt-tracker={','.join(trackers)}"]

            metadata_cmd = [
                "timeout",
                "240s",
                "aria2c",
                f"--dir={metadata_dir}",
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
                *tracker_args,
                source_url,
            ]

            metadata_result = run_cmd(
                metadata_cmd,
                cwd=work_dir,
                timeout=300,
                check=False,
            )

            torrent_file = find_latest_torrent_file(metadata_dir, work_dir, runner_temp, Path.cwd())

            if not torrent_file:
                raise RuntimeError(
                    "Could not fetch torrent metadata for selected repack. "
                    f"aria2c exit code: {metadata_result.returncode}"
                )

            torrent_source = str(torrent_file)
    else:
        torrent_file = work_dir / sanitize_filename(filename_from_url(source_url, "source.torrent"), "source.torrent")
        download_file(source_url, torrent_file)
        torrent_source = str(torrent_file)

    torrent_indexes = []
    for item in selected:
        torrent_indexes.append(str(item.get("torrent_index") or item.get("index")))

    select_arg = ",".join(torrent_indexes)

    tracker_args = []
    if source_lower.startswith("magnet:?"):
        trackers = extract_magnet_trackers(source_url)
        if trackers:
            tracker_args = [f"--bt-tracker={','.join(trackers)}"]

    cmd = [
        "aria2c",
        "--dir",
        str(download_dir),
        "--seed-time=0",
        "--seed-ratio=0.0",
        "--max-overall-upload-limit=1K",
        "--disable-ipv6=true",
        "--enable-dht=true",
        "--enable-dht6=false",
        "--follow-torrent=mem",
        "--bt-remove-unselected-file=true",
        "--bt-stop-timeout=300",
        "--bt-max-peers=80",
        "--max-connection-per-server=8",
        "--split=8",
        "--min-split-size=1M",
        "--file-allocation=none",
        "--allow-overwrite=true",
        "--auto-file-renaming=false",
        "--summary-interval=30",
        "--console-log-level=warn",
        *tracker_args,
        f"--select-file={select_arg}",
        torrent_source,
    ]

    run_cmd(cmd, timeout=21600, check=True)

    for item in selected:
        original = sanitize_relative_path(
            str(item.get("path") or item.get("name") or ""),
            fallback=f"torrent_{item.get('index')}.bin"
        )

        candidates = [download_dir / original]
        candidates.extend(download_dir.rglob(Path(original).name))

        src = next((path for path in candidates if path.exists() and path.is_file()), None)
        if src:
            copy_into_stage(src, stage_dir, target_path_for_item(item, rename_map))


def make_zip(stage_dir: Path, zip_path: Path) -> tuple[int, int]:
    files = [p for p in stage_dir.rglob("*") if p.is_file()]
    if not files:
        raise RuntimeError("No files were staged for repack.")
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for path in files:
            zf.write(path, path.relative_to(stage_dir).as_posix())
    return len(files), zip_path.stat().st_size


def build_repack_report(manifest: dict[str, Any], selected: list[dict[str, Any]], output_name: str, output_size: int) -> str:
    source = manifest.get("source", {})
    lines = []
    for item in selected[:25]:
        lines.append(f"{item.get('index')}. <code>{html_escape(item.get('path') or item.get('name'))}</code>")
    if len(selected) > 25:
        lines.append(f"… +{len(selected) - 25} more")
    return (
        "📦 <b>Package Repacker</b>\n\n"
        f"🧭 <b>Source Type:</b> <code>{html_escape(source.get('kind', 'unknown'))}</code>\n"
        f"🧩 <b>Included Items:</b> <code>{len(selected)}</code>\n"
        f"📄 <b>Output:</b> <code>{html_escape(output_name)}</code>\n"
        f"📏 <b>Size:</b> <code>{html_escape(format_bytes(output_size))}</code>\n\n"
        "🧩 <b>Included:</b>\n"
        + "\n".join(lines)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Repack selected package items into ZIP")
    add_common_cli(parser)
    parser.add_argument("--keep-indexes", default="")
    parser.add_argument("--delete-indexes", default="")
    parser.add_argument("--rename-map-json", default="")
    parser.add_argument("--output-filename", default="package_output.zip")
    parser.add_argument("--send-manifest", default="false", choices=["true", "false"])
    parser.add_argument("--manifest-out", default="repack-manifest.json")
    parser.add_argument("--split-part-mib", default=str(DEFAULT_SPLIT_PART_MIB))
    parser.add_argument("--send-telegram", default="true", choices=["true", "false"])
    args = parser.parse_args()

    if args.progress_chat_id:
        os.environ["PROGRESS_CHAT_ID"] = args.progress_chat_id
    if args.progress_message_id:
        os.environ["PROGRESS_MESSAGE_ID"] = args.progress_message_id

    ctx = TelegramContext.from_env()
    work_dir = Path(args.work_dir)
    stage_dir = work_dir / "stage"
    shutil.rmtree(stage_dir, ignore_errors=True)
    stage_dir.mkdir(parents=True, exist_ok=True)

    source_url = args.source_url.strip()
    if not source_url:
        raise SystemExit("Missing source_url.")

    progress_stage(ctx, "inspecting", 10, "Inspecting", "Reading_source_manifest")
    manifest = fresh_manifest(source_url, work_dir, args.dispatch_key)
    items = manifest.get("items") or []
    selected = build_selection(items, args.keep_indexes, args.delete_indexes)
    if not selected:
        raise RuntimeError("Selection is empty. Check keep_indexes/delete_indexes.")

    rename_map = load_rename_map(args.rename_map_json)
    kind = manifest.get("source", {}).get("kind", "direct_file")

    progress_stage(ctx, "downloading", 25, "Downloading", f"Downloading_{kind}")
    if kind in {"zip", "rar", "7z"}:
        progress_stage(ctx, "extracting", 45, "Extracting", "Extracting_selected_items")
        stage_archive(source_url, kind, selected, stage_dir, work_dir, rename_map)
    elif kind == "torrent":
        progress_stage(ctx, "downloading", 45, "Downloading", "Downloading_selected_torrent_files")
        stage_torrent(source_url, selected, stage_dir, work_dir, rename_map)
    elif kind in {"url_list", "directory_listing"}:
        progress_stage(ctx, "downloading", 45, "Downloading", "Downloading_selected_link_items")
        stage_url_items(selected, stage_dir, work_dir, rename_map)
    else:
        stage_direct(source_url, selected, stage_dir, work_dir, rename_map)

    output_name = ensure_zip_extension(args.output_filename, "package_output.zip")
    output_path = work_dir / output_name
    progress_stage(ctx, "repacking", 70, "Repacking", "Building_output_zip")
    file_count, output_size = make_zip(stage_dir, output_path)

    repack_manifest = {
        **manifest,
        "repack": {
            "created_at": manifest.get("created_at"),
            "keep_indexes": args.keep_indexes,
            "delete_indexes": args.delete_indexes,
            "rename_map": rename_map,
            "output_filename": output_name,
            "output_size_bytes": output_size,
            "output_size_text": format_bytes(output_size),
            "included_item_count": len(selected),
            "zip_file_count": file_count,
        },
    }
    manifest_out = Path(args.manifest_out)
    write_json(manifest_out, repack_manifest)

    progress_stage(ctx, "uploading", 85, "Uploading", "Sending_repacked_zip")
    if args.send_telegram == "true":
        caption = (
            "📦 <b>Package Repacker</b>\n"
            f"📄 <code>{html_escape(output_name)}</code>\n"
            f"🧩 Items: <code>{len(selected)}</code>\n"
            f"📏 Size: <code>{html_escape(format_bytes(output_size))}</code>"
        )

        telegram_send_document(
            ctx,
            output_path,
            output_name,
            caption,
            split_part_mib=int(args.split_part_mib or DEFAULT_SPLIT_PART_MIB)
        )

        if args.send_manifest == "true":
            telegram_send_document(
                ctx,
                manifest_out,
                "repack-manifest.json",
                "📄 <b>Repack manifest</b>"
            )

        telegram_delete_progress(ctx)

    print(json.dumps(repack_manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        from common import stop_local_bot_api

        stop_local_bot_api()
