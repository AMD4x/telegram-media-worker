# Workflow Reference

This document describes the behavior of each workflow.

## Capability matrix

| Capability | `remote-media.yml` | `youtube-video-local-api.yml` | `tiktok-direct-local-api.yml` | `facebook-long-video-local-api.yml` | `torrent-document-local-api.yml` | `package-inspect.yml` | `package-repack.yml` | `video-compress.yml` |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Manual `workflow_dispatch` | yes | yes | yes | yes | yes | yes | yes | yes |
| Video output | yes | yes | yes | yes | no | no | no | yes |
| Document output | yes | no | no | no | yes | optional report | ZIP document | yes |
| ZIP output | yes | no | no | no | no | no | yes | yes |
| `document_mode=zip` | yes | no | no | no | no | no | no | no |
| `document_mode=original` | yes | no | no | no | no | no | no | no |
| Split large ZIP into parts | yes | no | no | no | no | no | yes | no |
| Split large documents into parts | yes | no | no | no | yes | no | yes | no |
| Torrent file listing | no | no | no | no | yes | manifest only | via selected source | no |
| Selected torrent indexes | no | no | no | no | yes | no | yes | no |
| Package manifest generation | no | no | no | no | no | yes | no | no |
| Package item rename map | no | no | no | no | no | no | yes | no |
| Progress message edits | yes | yes | yes | yes | yes | yes | yes | yes |
| Public Bot API | small files | no | no | no | small documents | optional report | small ZIPs | small files |
| Local Bot API | when needed | yes | yes | yes | yes | no | when needed | when needed |
| YouTube cookies | yes | yes | no | no | no | no | no | yes |
| Facebook cookies | yes | no | no | yes | no | no | no | yes |
| TikTok third-party resolver | no | no | yes | no | no | no | no | no |
| Telegram/iPhone video preparation | yes | yes | codec/audio check | yes | no | no | no | yes |
| Size-fit recompression | yes | no | no | no | no | no | no | no |
| User-selected compression strength | no | no | no | no | no | no | no | yes |

## `remote-media.yml`

### Purpose

Generic worker for:

- platform media URLs,
- direct downloadable file URLs,
- video output,
- document output,
- ZIP document output,
- oversized document splitting,
- public or local Telegram upload selection.

### Inputs

| Input | Required | Default | Accepted values / behavior |
|---|:---:|---|---|
| `media_url` | Yes | none | Source media or file URL. |
| `max_height` | Yes | `auto` | `auto`, `2160`, `1440`, `1080`, `720`, `480`, `360`. |
| `send_as` | Yes | `video` | `video` or `document`; invalid values become `video`. |
| `output_filename` | No | empty | Used mostly by document/ZIP output. Sanitized before use. |
| `document_mode` | No | `zip` | `zip` or `original`; invalid values become `zip`. Ignored unless `send_as=document`. |
| `progress_chat_id` | No | empty | Progress message chat ID. |
| `progress_message_id` | No | empty | Progress message ID. |
| `dispatch_key` | No | empty | Caller tracking key. |

### Core stages

1. Prepare workspace.
2. Normalize `send_as` and `document_mode`.
3. Define Telegram and file-size limits.
4. Validate URL and Telegram secrets.
5. Mask sensitive values.
6. Detect platform and referer.
7. Prepare platform cookies when available.
8. Build candidate video heights.
9. Try direct-document download if `send_as=document`.
10. Download with `yt-dlp` when needed.
11. Normalize video or prepare document.
12. Check file size.
13. Compress video to fit when necessary.
14. Start Local Bot API only if needed.
15. Send video/document/split document parts.
16. Update final Telegram progress summary.

### Platform detection

The generic workflow detects:

- YouTube,
- Facebook,
- Instagram,
- TikTok,
- X/Twitter,
- Reddit,
- generic/direct URLs.

Only YouTube and Facebook have dedicated cookie secret handling in this workflow.

### Video mode

When `send_as=video`, the workflow uses `yt-dlp` with a maximum file size for non-document downloads, tries quality candidates based on `max_height`, prepares the media with `ffmpeg`, checks size, and sends through Telegram.

Output preparation includes:

- MP4-compatible output,
- H.264 video,
- AAC audio,
- `yuv420p`,
- square sample aspect ratio,
- `+faststart`,
- max dimension handling,
- size-fit compression when the file is above the Local Bot API limit.

### Document mode

When `send_as=document`, the workflow first attempts to treat the URL as a direct downloadable file.

It performs:

- optional `HEAD` request,
- filename inference from URL path,
- filename inference from `Content-Disposition`,
- direct `curl` download,
- empty-file rejection,
- HTML-page rejection,
- filename sanitization,
- document send preparation.

If direct document download fails, the workflow can fall back to platform/media download behavior depending on the path.

### `document_mode=original`

Sends the downloaded file as a Telegram document after validation.

### `document_mode=zip`

Creates a ZIP file around the downloaded document/media using Python `zipfile` with stored compression. The ZIP filename and inner filename are sanitized. If the ZIP exceeds the split threshold, it is split into ordered parts.

### Split ZIP behavior

If a ZIP is larger than the configured split size, the workflow:

1. Splits the ZIP into ordered files using `.001`, `.002`, etc.
2. Writes a manifest of part paths.
3. Validates every part exists and fits the Local Bot API limit.
4. Sends a Telegram notice explaining that multiple parts must be joined.
5. Sends each part with `sendDocument`.
6. Updates the progress summary.

### Optional Windows restore helper for split ZIP parts

When split ZIP parts such as `.001`, `.002`, and `.003` are downloaded on Windows, users can optionally install:

```text
tools/windows/amd4x-merge/install.reg
```

AMD4x Merge adds a Windows Explorer context-menu action for joining ordered split parts locally. This is only a user-side restore helper and does not affect the workflow runtime.

### Telegram send-mode selection

- Files at or below the public threshold can use Public Bot API.
- Larger files require Local Bot API.
- Local Bot API requires `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`.

### Retry behavior

The generic workflow includes document-send retry handling for retryable Telegram states such as:

- `429`,
- network timeout / `000`,
- `408`,
- `500`,
- `502`,
- `503`,
- `504`.

For `429`, it tries to honor `retry_after` from Telegram when present, within a bounded wait window.


## `torrent-document-local-api.yml`

### Purpose

Admin-oriented torrent document workflow for:

- magnet links,
- direct `.torrent` URLs,
- listing torrent contents before download,
- downloading selected torrent file indexes,
- downloading all torrent files when explicitly requested,
- sending small files through Telegram Public Bot API when possible,
- sending larger files through Telegram Local Bot API,
- splitting oversized documents into ordered Telegram-safe raw binary parts.

### Inputs

| Input | Required | Default | Accepted values / behavior |
|---|:---:|---|---|
| `torrent_url` | Yes | none | Magnet link or direct `.torrent` URL. |
| `file_mode` | No | `list` | `list`, `selected`, or `all`. Invalid values fall back to `list`. |
| `selected_files` | Required for `selected` | empty | File indexes such as `1`, `1,2`, `3-5`, or `1-3,5`. |
| `split_part_mib` | No | `1900` | Split size in MiB. Values are clamped to a safe range. |
| `progress_chat_id` | No | empty | Progress message chat ID. |
| `progress_message_id` | No | empty | Progress message ID. |
| `dispatch_key` | No | `manual` | Caller tracking key; masked in logs and not exposed in the run name. |

### Modes

#### `file_mode=list`

Fetches torrent metadata and sends a Telegram message listing torrent files grouped by folder. No torrent content is downloaded.

#### `file_mode=selected`

Downloads and sends only the selected file indexes. Ranges such as `3-5` are expanded before dispatching to `aria2c`, and the final send manifest is built only from the selected indexes.

#### `file_mode=all`

Downloads and sends all torrent files.

### Upload behavior

The workflow sends files as Telegram documents. Small documents are sent through Telegram Public Bot API when possible. Larger documents use Telegram Local Bot API. If a selected file is larger than the workflow single-file threshold, it is split into ordered raw binary parts and each part is sent as a Telegram document.

### Split part restore behavior

Oversized torrent documents are split into raw binary parts named like:

```text
filename.ext.part001
filename.ext.part002
```

These parts are not ZIP/RAR archives and should not be extracted with archive tools. Download all parts, keep them in order, then join them to restore the original file.

On Windows Command Prompt:

```cmd
copy /b "filename.ext.part001"+"filename.ext.part002" "filename.ext"
```

On Linux/macOS:

```bash
cat *.part??? > filename.ext
```

Optional Windows helper:

```text
tools/windows/amd4x-merge/
```

AMD4x Merge can be used from the Windows right-click menu to join ordered split parts such as `.part001` and `.001`. It is a local restore helper only; it does not change torrent workflow behavior, upload limits, secrets, or inputs.

### Safety behavior

The workflow masks torrent URLs, selected indexes, file paths, hashes, sizes, Telegram secrets, and raw response details from GitHub logs where possible. File names and sizes are intentionally shown only in the Telegram `list` message so the admin can choose indexes.

### Notes

This workflow is intended for controlled/admin use. Bot integrations should validate access before allowing magnet or `.torrent` dispatch.


## `package-inspect.yml`

### Purpose

Package source inspector used by bot-side Package Browser integrations. It reads a package-like source, creates a manifest of items and stable indexes, encrypts the manifest, and stores it temporarily in `.package_manifests/<dispatch_key>.enc` for the bot to read.

### Inputs

| Input | Required | Default | Behavior |
|:---:|:---:|:---:|---|
| `source_url` | yes | - | Archive, direct file, torrent, magnet, directory listing, or URL list to inspect. |
| `progress_chat_id` | no | empty | Progress-message chat. |
| `progress_message_id` | no | empty | Existing progress message to edit. |
| `dispatch_key` | no | `manual` | Bot-side tracking key and encrypted-manifest filename seed. |
| `send_telegram` | no | `true` | Sends a compact Telegram inspection report when enabled. |

### Manifest behavior

- Builds a `manifest.json` with stable 1-based item indexes.
- Encrypts the manifest using `PACKAGE_MANIFEST_KEY`.
- Publishes only the encrypted `.enc` manifest under `.package_manifests/`.
- Prints only generic completion markers such as `PACKAGE_INSPECT_COMPLETED` and `MANIFEST_STORE_OK=1`.

### Bot behavior

The bot should decrypt the `.enc` manifest, show Package Browser, then delete the encrypted manifest after a successful read. Package Inspector / Repacker bot integrations can keep the newest renamed file at the top of long Package Browser lists by storing rename priority in bot-side state.

## `package-repack.yml`

### Purpose

Package item repacker used after `package-inspect.yml`. It rebuilds a ZIP from selected manifest indexes, optional delete indexes, and optional internal rename mappings, then sends the output ZIP to Telegram.

### Inputs

| Input | Required | Default | Behavior |
|:---:|:---:|:---:|---|
| `source_url` | yes | - | Same original source URL used by Package Inspector. |
| `keep_indexes` | no | empty | Manifest indexes to include, e.g. `1`, `1,2`, or `3-5`. |
| `delete_indexes` | no | empty | Manifest indexes to exclude when `keep_indexes` is empty. |
| `rename_map_json` | no | empty | JSON mapping of original manifest paths to new relative ZIP paths. |
| `output_filename` | no | `package_output.zip` | Final ZIP filename. `.zip` is normalized by the worker. |
| `split_part_mib` | no | `1900` | Split size in MiB for oversized ZIP output. |
| `progress_chat_id` | no | empty | Progress-message chat. |
| `progress_message_id` | no | empty | Existing progress message to edit. |
| `dispatch_key` | no | `manual` | Bot-side tracking key. |
| `send_telegram` | no | `true` | Sends output ZIP to Telegram when enabled. |

### Rename behavior

`rename_map_json` is the only rename data consumed by the workflow. Bot-side Package Browser ordering is not sent to GitHub; it only keeps the newest renamed item visible at the top of long lists before the final repack request.

### Upload behavior

The output is a ZIP document. Small ZIP output can use Public Bot API. Larger ZIPs or split ZIP parts can use Telegram Local Bot API when `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` are configured.

## `youtube-video-local-api.yml`

### Purpose

YouTube-specific video-only workflow that downloads a YouTube URL, prepares a Telegram/iPhone-compatible MP4, and sends it through Telegram Local Bot API.

### Inputs

| Input | Behavior |
|---|---|
| `media_url` | Required. Must match YouTube, YouTube short links, or music YouTube domains. |
| `max_height` | Optional. Invalid values become `auto`; `auto` maps to 2160. |
| `send_as` | Ignored compatibility input. |
| `output_filename` | Ignored compatibility input. |
| `progress_chat_id` | Optional progress target. |
| `progress_message_id` | Optional progress target. |
| `dispatch_key` | Optional tracking key; default `manual`. |

### Required secrets

- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `YOUTUBE_COOKIES_TXT` optional

### Download behavior

Uses `yt-dlp` with:

- no playlist,
- no thumbnails/comments/descriptions/info JSON,
- no cache,
- restricted filenames,
- YouTube extractor args `youtube:player_client=web_safari,web`,
- format selector preferring MP4/H.264 video and M4A/AAC audio under target height,
- merge output as MP4.

### Compatibility behavior

After download, the workflow checks if the file is safe for fast copy/remux:

- H.264 video,
- AAC or no audio,
- `yuv420p`,
- sample aspect ratio `1:1` or `0:1`,
- width and height not above 1920,
- H.264 level not above 4.2.

If safe, it remuxes with `-c copy`, `-tag:v avc1`, strips metadata, and applies `+faststart`.

If not safe, it transcodes to a safe MP4 using `libx264`, AAC audio, `yuv420p`, capped dimensions, `profile:v main`, `level 4.1`, and `+faststart`.

### Upload behavior

Always starts Telegram Local Bot API and sends through `sendVideo` at:

```text
http://127.0.0.1:8081/bot<TOKEN>/sendVideo
```

It includes `supports_streaming=true` and width/height when available.

### Size behavior

Fails if the final prepared file is empty or larger than `2,000,000,000` bytes.

## `tiktok-direct-local-api.yml`

### Purpose

TikTok-specific video-only workflow focused on getting a clean playable TikTok video with audio and sending it through Telegram Local Bot API.

### Inputs

| Input | Behavior |
|---|---|
| `media_url` | Required. Must match TikTok URL forms. |
| `max_height` | Optional. Invalid values become `auto`. |
| `send_as` | Declared as compatibility input but not used in the run environment. |
| `output_filename` | Declared as compatibility input but not used in the run environment. |
| `progress_chat_id` | Optional progress target. |
| `progress_message_id` | Optional progress target. |
| `dispatch_key` | Declared as an input but not used in the run environment. |

### Required secrets

- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`

### Download strategy

The workflow tries multiple candidates:

1. `tikwm.com` API direct resolver.
2. `yt-dlp` with audio-safe format selector.
3. `yt-dlp` sorted by audio/resolution/fps/bitrate.
4. `yt-dlp` best audio fallback.
5. Transcode fallback if a previously downloaded incompatible candidate can be converted.

### Third-party resolver note

The first TikTok path calls:

```text
https://www.tikwm.com/api/
```

This is an external resolver, not part of GitHub, Telegram, or `yt-dlp`. It can fail, change behavior, rate-limit, or disappear. The workflow has fallbacks, but this dependency should be documented for users.

### Compatibility behavior

A candidate must have:

- video stream,
- audio stream,
- H.264 video,
- AAC audio.

If a candidate has video and audio but incompatible codecs, the workflow may save it as a transcode source and later convert it to Telegram-compatible MP4.

### Remux/transcode behavior

- Compatible candidates are remuxed to MP4 with `+faststart`.
- Incompatible fallback candidates may be transcoded to H.264/AAC MP4.
- The final prepared file must still pass the compatibility check before upload.

### Upload behavior

Always uses Telegram Local Bot API and sends with `sendVideo` plus `supports_streaming=true`.

### Size behavior

Fails if the final file is empty or larger than `2,000,000,000` bytes.

## `facebook-long-video-local-api.yml`

### Purpose

Facebook-specific video-only workflow for long videos, using Local Bot API and compatibility preparation.

### Inputs

| Input | Behavior |
|---|---|
| `media_url` | Required. Must match Facebook or `fb.watch`. |
| `max_height` | Ignored compatibility input. |
| `send_as` | Ignored compatibility input. |
| `output_filename` | Ignored compatibility input. |
| `progress_chat_id` | Optional progress target. |
| `progress_message_id` | Optional progress target. |
| `dispatch_key` | Optional tracking key; default `manual`. |

### Required secrets

- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `FACEBOOK_COOKIES_TXT` optional

### Download behavior

Uses `yt-dlp` with:

- optional Facebook cookies,
- no playlist,
- no thumbnails/comments/descriptions/info JSON,
- no cache,
- restricted filenames,
- sort expression `res,fps,tbr,filesize`,
- format selector preferring MP4/H.264 video and M4A/AAC audio,
- merge output as MP4.

### Compatibility behavior

Uses the same fast-remux / safe-transcode logic as the YouTube workflow:

- H.264,
- AAC or absent audio,
- `yuv420p`,
- acceptable sample aspect ratio,
- dimensions not above 1920,
- H.264 level not above 4.2.

Safe files are remuxed; unsafe files are transcoded.

### Upload behavior

Always starts Telegram Local Bot API and sends through `sendVideo` with `supports_streaming=true` and dimensions when available.

### Size behavior

Fails if the prepared file is empty or larger than `2,000,000,000` bytes.

## `video-compress.yml`

### Purpose

Independent remote video-compression workflow. It downloads a source video, compresses it with `ffmpeg`, normalizes it to Telegram/mobile-friendly MP4, then sends it as a video, document, or ZIP-wrapped document.

### Inputs

| Input | Required | Default | Behavior |
|:---:|:---:|:---:|---|
| `media_url` | yes | - | Source video URL. |
| `compression_level` | yes | `50` | Compression strength from `1` to `100`; higher means stronger compression and smaller output. |
| `send_as` | yes | `video` | `video`, `document`, or `zip`; invalid values become `video`. |
| `output_filename` | no | auto | Optional output filename. Empty value creates `platform-YYYYMMDD-HHMMSS.mp4` or `.zip`. |
| `chat_id` | no | secret fallback | Final Telegram destination. |
| `progress_chat_id` | no | final chat | Progress-message chat. |
| `progress_message_id` | no | auto-create | Existing progress message to edit. |
| `reply_to_message_id` | no | empty | Optional Telegram message id to reply to when sending the final output. |
| `dispatch_key` | no | `manual` | Bot-side tracking key used in the run name. Not exported as a job output. |

### Output behavior

| `send_as` | Telegram method | Final file |
|:---:|:---:|:---:|
| `video` | `sendVideo` | `.mp4` |
| `document` | `sendDocument` | `.mp4` |
| `zip` | `sendDocument` | `.zip` |

### Compression behavior

The workflow converts `compression_level` into CRF, preset, audio bitrate, max height, maxrate, and bufsize. The final MP4 uses H.264/AAC, `yuv420p`, `avc1`, and `+faststart`.

Low compression levels such as `21` or `30` prioritize quality and can make already heavily compressed source videos larger. Higher values such as `75` and `100` are intended for smaller output.

### Naming behavior

When `output_filename` is empty, the workflow uses platform and Cairo time:

```text
platform-YYYYMMDD-HHMMSS.mp4
platform-YYYYMMDD-HHMMSS.zip
```

When `output_filename` is provided, the extension is normalized to `.mp4` for `video`/`document` and `.zip` for `zip`.

## Shared limitations

- No workflow currently exposes `workflow_call`.
- Dedicated YouTube, TikTok, and Facebook workflows do not support document output.
- `video-compress.yml` supports `video`, `document`, and `zip` output modes, but it does not support `document_mode`.
- Dedicated workflows duplicate helper logic instead of sharing common scripts.
- The generic workflow handles more cases but is larger and more complex.
- Platform extraction depends on upstream websites and `yt-dlp` behavior.
- Torrent delivery is document-only and does not perform media conversion or Telegram/iPhone video compatibility preparation.
- Package Inspector / Repacker is ZIP/document-oriented and does not perform media conversion or Telegram/iPhone video compatibility preparation.
- Package Browser ordering for renamed items is bot-side state inside the Package Inspector / Repacker integration and is not a workflow input.
- Torrent split parts are raw binary chunks, not ZIP/RAR archives; users must join all parts in order to restore the original file.
- Torrent file availability depends on peers, trackers, DHT behavior, and GitHub Actions runtime limits.
