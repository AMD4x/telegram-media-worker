# Workflow Reference

This document describes the behavior of each workflow.

## Capability matrix

| Capability | `remote-media.yml` | `youtube-video-local-api.yml` | `tiktok-direct-local-api.yml` | `facebook-long-video-local-api.yml` | `torrent-document-local-api.yml` |
|---|:---:|:---:|:---:|:---:|:---:|
| Manual `workflow_dispatch` | Yes | Yes | Yes | Yes | Yes |
| Video output | Yes | Yes | Yes | Yes | No |
| Document output | Yes | No | No | No | Yes |
| `document_mode=zip` | Yes | No | No | No | No |
| `document_mode=original` | Yes | No | No | No | No |
| Split large ZIP into parts | Yes | No | No | No | No |
| Split large documents into parts | Yes | No | No | No | Yes |
| Torrent file listing | No | No | No | No | Yes |
| Selected torrent indexes | No | No | No | No | Yes |
| Progress message edits | Yes | Yes | Yes | Yes | Yes |
| Public Bot API | Yes, for small files | No | No | No | Yes, for small documents |
| Local Bot API | Yes, when needed | Yes | Yes | Yes | Yes |
| YouTube cookies | Yes | Yes | No | No | No |
| Facebook cookies | Yes | No | No | Yes | No |
| TikTok third-party resolver | No | No | Yes | No | No |
| Telegram/iPhone video preparation | Yes | Yes | Yes, simpler codec/audio check | Yes | No |
| Size-fit recompression | Yes | No | No | No | No |

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

### Safety behavior

The workflow masks torrent URLs, selected indexes, file paths, hashes, sizes, Telegram secrets, and raw response details from GitHub logs where possible. File names and sizes are intentionally shown only in the Telegram `list` message so the admin can choose indexes.

### Notes

This workflow is intended for controlled/admin use. Bot integrations should validate access before allowing magnet or `.torrent` dispatch.

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

## Shared limitations

- No workflow currently exposes `workflow_call`.
- Dedicated workflows do not support document output.
- Dedicated workflows duplicate helper logic instead of sharing common scripts.
- The generic workflow handles more cases but is larger and more complex.
- Platform extraction depends on upstream websites and `yt-dlp` behavior.
- Torrent delivery is document-only and does not perform media conversion or Telegram/iPhone video compatibility preparation.
- Torrent split parts are raw binary chunks, not ZIP/RAR archives; users must join all parts in order to restore the original file.
- Torrent file availability depends on peers, trackers, DHT behavior, and GitHub Actions runtime limits.
