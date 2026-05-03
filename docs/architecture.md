# Architecture

This document explains how Telegram Media Worker is structured and how a request moves through the system.

## High-level model

Telegram Media Worker is a GitHub Actions based job runner. A Telegram bot or a human starts a workflow. The workflow downloads or prepares media inside a GitHub-hosted job container, then sends the final result to Telegram.

The repository does not need a permanent media-processing server. GitHub Actions provides the temporary compute environment, while the bot remains the controller.

## Main components

| Component | Role |
|---|---|
| GitHub Actions workflow | Main execution unit. Each workflow is a remote worker. |
| `ghcr.io/ad4x/tg-video-worker:latest` | Container image used by workflows. It must contain the runtime tools. |
| `yt-dlp` | Extracts and downloads media from supported platforms. |
| `ffmpeg` | Converts, remuxes, normalizes, compresses, or prepares media. |
| `ffprobe` | Reads codecs, dimensions, duration, streams, and metadata. |
| `curl` | Calls Telegram APIs, downloads direct files, probes headers, and talks to third-party APIs. |
| Python snippets | Used for filename sanitization, ZIP creation, bitrate calculations, response parsing, and HTML escaping. |
| Telegram Public Bot API | Sends smaller files directly through `https://api.telegram.org`. |
| Telegram Local Bot API | Sends larger files through a local `telegram-bot-api --local` server. |
| Package manifest store | Temporary `.package_manifests/<dispatch_key>.enc` files used by bot-side Package Browser integration. |

## Request lifecycle

1. A caller provides `media_url` and optional runtime inputs.
2. The workflow validates required inputs and secrets.
3. Sensitive values are masked in GitHub Actions logs.
4. The workflow detects the platform or validates that the URL matches the dedicated workflow.
5. The workflow prepares cookies when the target platform supports repository cookie secrets.
6. The workflow downloads the media/file.
7. The workflow prepares the output:
   - video normalization,
   - fast remux,
   - safe transcode,
   - size fitting,
   - document wrapping,
   - or ZIP splitting.
8. The workflow chooses the Telegram upload API.
9. The workflow sends the final result to Telegram.
10. If progress inputs exist, the workflow edits the existing progress message throughout the run.

## Progress update model

Workflows can accept:

```text
progress_chat_id
progress_message_id
```

When both are present, the workflow edits the existing Telegram message with:

- stage/status label,
- progress percentage,
- progress bar,
- GitHub run ID,
- GitHub Actions run URL,
- final media summary when available.

If either value is missing, the workflow still runs but silently skips progress edits.

## Sensitive data handling

The workflows use `::add-mask::` for sensitive runtime values such as:

- source URL,
- normalized URL,
- video ID,
- output filename,
- Telegram token,
- Telegram chat ID,
- Telegram progress chat/message IDs,
- Telegram API ID/hash,
- some computed file sizes and file paths.

The generic workflow also includes a safe log-printing helper that replaces URLs, IDs, and sizes before printing selected logs.

Important: masking helps, but raw logs should still be treated as private because external tool output can change.

## Telegram upload architecture

There are two Telegram upload paths:

### Public Bot API

Used for smaller files. It sends directly to:

```text
https://api.telegram.org/bot<TOKEN>
```

This path is simpler and does not require `TELEGRAM_API_ID` or `TELEGRAM_API_HASH`.

### Local Bot API

Used by all dedicated platform workflows and by `remote-media.yml`, `package-repack.yml`, or `video-compress.yml` when large files need it.

The workflow starts:

```text
telegram-bot-api \
  --api-id="$TELEGRAM_API_ID" \
  --api-hash="$TELEGRAM_API_HASH" \
  --local \
  --http-ip-address=127.0.0.1 \
  --http-port=8081
```

Then it sends to:

```text
http://127.0.0.1:8081/bot<TOKEN>
```

The workflow waits for the local server to respond before upload. If it does not become ready, the run fails.

## Size constants used by remote workflows

`remote-media.yml` and `video-compress.yml` use these effective size constants where applicable:

| Constant | Value | Meaning |
|---|:---:|---|
| `DIRECT_TELEGRAM_MAX_BYTES` | `50,000,000` | Small-file threshold for Public Bot API. |
| `LOCAL_BOT_API_MAX_BYTES` | `2,000,000,000` | Effective Local Bot API upload ceiling used by workflows. |
| `DOCUMENT_SPLIT_PART_BYTES` | `1,850,000,000` | Target size for split ZIP parts. |
| `TELEGRAM_TARGET_MAX_BYTES` | `1,950,000,000` | Target size used by the generic workflow when compressing video to fit below the Local Bot API limit. |
| `YTDLP_MAX_FILESIZE` | `2000M` | Download cap used for non-document `yt-dlp` video downloads in the generic workflow. |
| `PUBLIC_BOT_API_MAX_BYTES` | `50,000,000` | Public Bot API threshold used by `video-compress.yml` before Local Bot API is selected. |

## Video preparation architecture

Video preparation depends on workflow.

### Generic workflow

`remote-media.yml` normalizes media to a Telegram-friendly MP4 using `ffmpeg`:

- H.264 video through `libx264`,
- AAC audio,
- `yuv420p` pixel format,
- square sample aspect ratio via `setsar=1`,
- dimensions capped to fit within 1920 px on the longer side,
- `+faststart`.

If the final file is too large for Local Bot API, the workflow calculates a target video bitrate from duration, target file size, and audio bitrate. It then tries lower candidate heights in this order:

```text
2160 1440 1080 720 480 360
```

Audio is copied during size-fit attempts when possible.

### YouTube and Facebook dedicated workflows

These workflows first test whether the downloaded file is already safe for Telegram/iPhone playback. A file is considered safe only when it satisfies conditions such as:

- H.264 video,
- AAC or absent audio,
- `yuv420p`,
- acceptable sample aspect ratio,
- width and height not greater than 1920,
- H.264 level not greater than 4.2.

If safe, the workflow performs a fast remux with metadata stripped, `avc1` video tag, and `+faststart`.

If not safe, the workflow transcodes with:

- `libx264`,
- `profile:v main`,
- `level 4.1`,
- AAC audio,
- `yuv420p`,
- `+faststart`,
- capped dimensions.

### TikTok dedicated workflow

TikTok uses a simpler compatibility check:

- video codec must be H.264,
- audio codec must be AAC,
- both audio and video streams must exist.

It tries to avoid unnecessary re-encoding, but if a candidate is not compatible and can be used as a source, it may transcode to Telegram-compatible MP4.

### Video Compress workflow

`video-compress.yml` always creates a new compressed MP4 using `ffmpeg` and settings derived from `compression_level`:

- H.264 video through `libx264`,
- AAC audio,
- `yuv420p` pixel format,
- `avc1` video tag,
- `+faststart`,
- max-height cap based on compression strength,
- optional ZIP wrapper when `send_as=zip`.

It is isolated in `scripts/video_compress/video_compress_worker.py` and does not call existing workflow scripts.

## Document architecture

`remote-media.yml` supports document mode through `document_mode`. `video-compress.yml` also supports `send_as=document`, but it does not use `document_mode`; it sends the compressed MP4 as a Telegram document.

In `remote-media.yml`, `send_as=document` enables two modes:

| Mode | Behavior |
|:---:|---|
| `document_mode=original` | Send the downloaded file as a document after validation. |
| `document_mode=zip` | Wrap the downloaded file in a ZIP before sending. |

The generic workflow can also:

- detect filenames from URLs,
- detect filenames from `Content-Disposition` headers,
- sanitize requested and inferred filenames,
- reject empty downloads,
- reject HTML pages accidentally downloaded as files,
- create ZIP files using Python `zipfile` with `ZIP_STORED`,
- split very large ZIP files into ordered parts,
- send a Telegram notice before split parts explaining how to join them.

## Package Inspector / Repacker architecture

Package Inspector and Package Repacker are a two-step package workflow family.

`package-inspect.yml` reads `source_url`, detects or stages the source, builds a manifest with stable item indexes, and encrypts that manifest into `.package_manifests/<dispatch_key>.enc` using `PACKAGE_MANIFEST_KEY`. The bot reads the encrypted manifest, decrypts it locally, then should delete the `.enc` file from the repository after a successful read.

`package-repack.yml` receives `source_url`, selected indexes, optional delete indexes, optional `rename_map_json`, and `output_filename`. It stages only the selected items, applies internal path renames, creates the output ZIP, and sends it to Telegram. Large ZIP output can use Local Bot API or split delivery according to the same Telegram-size constraints used by package tools.

Package Inspector / Repacker is split between GitHub Actions and the Telegram bot. GitHub Actions performs inspection, encrypted manifest storage, staging, ZIP creation, splitting, and Telegram delivery. The Telegram bot owns the Package Browser state: current folder, selected indexes, output ZIP name, rename map, and newest-renamed-first ordering. When the admin renames several files in a long list, the bot keeps the most recently renamed item at the top of the current list, then keeps other renamed items before unchanged items. The workflow still receives only the final selected indexes and `rename_map_json`.

## Platform detection in the generic workflow

The generic workflow detects:

| URL pattern | Platform label | Referer |
|---|---|---|
| `youtube.com`, `youtu.be` | `youtube` | `https://www.youtube.com/` |
| `facebook.com`, `fb.watch` | `facebook` | `https://www.facebook.com/` |
| `instagram.com` | `instagram` | `https://www.instagram.com/` |
| `tiktok.com`, `vm.tiktok.com`, `vt.tiktok.com` | `tiktok` | `https://www.tiktok.com/` |
| `twitter.com`, `x.com` | `x` | `https://x.com/` |
| `reddit.com`, `redd.it` | `reddit` | `https://www.reddit.com/` |
| Anything else | `generic` | `https://www.google.com/` |

For YouTube URLs, the workflow may normalize Shorts, `youtu.be`, and `watch?v=` forms to a canonical watch URL.

## Container requirements

The configured image should provide:

- Bash,
- Python 3,
- `yt-dlp` importable as `python3 -m yt_dlp`,
- `ffmpeg`,
- `ffprobe`,
- `curl`,
- `telegram-bot-api`,
- `deno` where the workflow checks it.

If any required tool is missing, the affected workflow exits with an explicit error.
