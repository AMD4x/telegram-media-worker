# Video Compress To Telegram

`video-compress.yml` is an independent GitHub Actions workflow for compressing a source video on GitHub-hosted runners, then sending the compressed result to Telegram as a streamable video, a document, or a ZIP-wrapped document.

It is designed for manual GitHub Actions runs and for `workflow_dispatch` calls from a lightweight Telegram bot controller such as Raspberry Pi.

## Files

```text
.github/workflows/video-compress.yml
scripts/video_compress/video_compress_worker.py
docs/video-compress.md
```

The feature is intentionally isolated from the existing workflows. No existing workflow or script has to be modified to run it.

## Required secret

| Secret | Purpose |
|:---:|---|
| `TELEGRAM_TOKEN` | Telegram bot token used for progress updates and final upload. |

## Destination chat fallback

The final destination chat is resolved in this order:

1. `chat_id` workflow input
2. `TELEGRAM_CHAT_ID` repository secret
3. `ADMIN_ID` repository secret

This keeps the workflow compatible with manual GitHub usage and bot-driven usage.

## Optional secrets

| Secret | Purpose |
|:---:|---|
| `TELEGRAM_CHAT_ID` | Default destination chat when `chat_id` input is empty. |
| `ADMIN_ID` | Secondary destination fallback when `chat_id` and `TELEGRAM_CHAT_ID` are empty. |
| `TELEGRAM_API_ID` | Starts Telegram Local Bot API for files above the Public Bot API safety limit. |
| `TELEGRAM_API_HASH` | Used with `TELEGRAM_API_ID` for Local Bot API. |
| `YOUTUBE_COOKIES_TXT` | Optional Netscape cookies for YouTube downloads. |
| `FACEBOOK_COOKIES_TXT` | Optional Netscape cookies for Facebook downloads. |

## Inputs

| Input | Required | Default | Meaning |
|:---:|:---:|:---:|---|
| `media_url` | yes | - | Source video URL. |
| `compression_level` | yes | `50` | Compression strength from `1` to `100`. Higher means stronger compression and smaller output. |
| `send_as` | yes | `video` | `video`, `document`, or `zip`. |
| `output_filename` | no | auto | Optional output name. `.mp4` or `.zip` is normalized automatically. |
| `chat_id` | no | secret fallback | Final Telegram destination chat. |
| `progress_chat_id` | no | final chat | Chat containing the progress message. |
| `progress_message_id` | no | auto-create | Existing Telegram message to edit. If empty, the workflow creates a progress message when it has a chat id. |
| `reply_to_message_id` | no | empty | Optional Telegram message id to reply to when sending the final output. |
| `dispatch_key` | no | `manual` | Caller tracking key for bot-side run matching. |

## Compression levels

`compression_level` is compression strength, not quality. A higher number means stronger compression, smaller output, and lower visual quality. A lower number means lighter compression and higher visual quality.

| Level | Meaning | Internal behavior |
|:---:|---|---|
| `1` | Highest quality / least compression | CRF 18, 2160p cap, 192k audio. |
| `10` | Very high quality / light compression | CRF 18, 2160p cap, 192k audio. |
| `30` | High quality | CRF about 22, 1440p cap, 160k audio. |
| `50` | Balanced | CRF about 26, 1080p cap, 128k audio. |
| `75` | Strong compression / smaller size | CRF about 30, 720p cap, 96k audio. |
| `100` | Maximum compression / smallest practical size | CRF about 36, 480p cap, 64k audio. |

The produced video is normalized to MP4/H.264/AAC with `yuv420p`, `avc1`, and `+faststart` for Telegram and mobile compatibility.

## Telegram output modes

| `send_as` | Telegram method | Final container | Notes |
|:---:|:---:|:---:|---|
| `video` | `sendVideo` | `.mp4` | Sends a streamable Telegram video with `supports_streaming=true`. |
| `document` | `sendDocument` | `.mp4` | Sends the compressed MP4 as a document with content-type detection disabled. |
| `zip` | `sendDocument` | `.zip` | Wraps the compressed MP4 in a ZIP document. |

The ZIP uses `ZIP_STORED` intentionally. It is for wrapping, naming, and delivery behavior, not for meaningful MP4 compression.

## Default file names

If `output_filename` is empty, the workflow creates a platform-aware name using Cairo time:

```text
platform-YYYYMMDD-HHMMSS.mp4
platform-YYYYMMDD-HHMMSS.zip
```

Examples:

```text
instagram-20260503-231455.mp4
facebook-20260503-231455.zip
```

If `output_filename` is provided, the workflow normalizes the extension:

| Mode | Missing or wrong extension becomes |
|:---:|:---:|
| `video` | `.mp4` |
| `document` | `.mp4` |
| `zip` | `.zip` |

## Progress message style

The workflow keeps the same compact GitHub Remote style:

```text
🐙 GitHub Remote

📊 [█████░░░░░] 55%
🧭 Status: Compressing
ℹ️ Compressing video with ffmpeg...
🆔 <GitHub run id>
🔗 Open Run
```

Main stages:

```text
Preparing
Downloading
Compressing
Packaging
Uploading
Completed
```

Completion summary example:

```text
✅ GitHub Video Compress completed.

🌐 Platform: instagram
🧭 Path: video-compress
🎚️ Compression: 50/100
🧱 Settings: CRF 26 · medium · 128k · 1080p
📐 Dimensions: 720x1280
📄 File: instagram-20260503-231455.mp4
📥 Downloaded Size: 12.50 MB
📦 Final Size: 4.20 MB — OK
🚀 Send Mode: video
📤 Send Method: Public Bot API
🆔 Message ID: 12345
🔗 Open Run
```

## Manual GitHub test

1. Push the workflow, worker script, and this document to the repository.
2. Open GitHub Actions.
3. Select `Video Compress To Telegram`.
4. Click `Run workflow`.
5. Fill:
   - `media_url`: a public video URL.
   - `compression_level`: start with `50`.
   - `send_as`: start with `video`.
   - `output_filename`: leave empty for the automatic platform/time name, or enter a custom name such as `test-compressed.mp4`.
6. Run again with `compression_level=30` to compare higher quality.
7. Run again with `compression_level=75` to compare smaller output.
8. Test `send_as=document`.
9. Test `send_as=zip` with both empty and custom `output_filename`.

## Bot-side `workflow_dispatch` payload example

```json
{
  "ref": "main",
  "inputs": {
    "media_url": "https://example.com/video.mp4",
    "compression_level": "50",
    "send_as": "video",
    "output_filename": "",
    "chat_id": "6445942442",
    "progress_chat_id": "6445942442",
    "progress_message_id": "12345",
    "reply_to_message_id": "",
    "dispatch_key": "vc_6445942442_20260503_001"
  }
}
```

Endpoint:

```text
POST /repos/AD4x/telegram-media-worker/actions/workflows/video-compress.yml/dispatches
```

Use the same GitHub token permission model already used by the bot for existing `workflow_dispatch` calls.

## Operational notes

- This workflow does not use Playwright, Chromium, or a browser runtime.
- The worker masks Telegram credentials, chat IDs, dispatch keys, media URLs, and multiline cookies where possible.
- `dispatch_key` is used for run matching, but it is not exported as a job output.
- Compression can make very small or already heavily compressed videos larger at low compression levels such as `21` or `30`.
- For the smallest practical output, use a high level such as `75` or `100`.
