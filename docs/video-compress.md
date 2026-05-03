# Video Compress To Telegram

`video-compress.yml` is an independent GitHub Actions workflow for compressing a video remotely on GitHub-hosted runners, then sending the compressed output to Telegram as a streamable video, a document, or a ZIP-wrapped document.

The workflow is designed for later `workflow_dispatch` calls from a Telegram bot running on a lightweight controller such as Raspberry Pi.

## Files

```text
.github/workflows/video-compress.yml
scripts/video_compress/video_compress_worker.py
docs/video-compress.md
```

No existing workflow or script is required to be modified.

## Required secret

| Secret | Purpose |
|---|---|
| `TELEGRAM_TOKEN` | Telegram bot token used for progress updates and final upload. |

## Destination chat fallback

The final destination chat is resolved in this order:

1. `chat_id` workflow input
2. `TELEGRAM_CHAT_ID` repository secret
3. `ADMIN_ID` repository secret

This keeps the workflow compatible with the current repository style while also supporting an `ADMIN_ID`-based setup.

## Optional secrets

| Secret | Purpose |
|---|---|
| `TELEGRAM_API_ID` | Starts Telegram Local Bot API for files above the public Bot API safety limit. |
| `TELEGRAM_API_HASH` | Used with `TELEGRAM_API_ID` for Local Bot API. |
| `YOUTUBE_COOKIES_TXT` | Optional Netscape cookies for YouTube downloads. |
| `FACEBOOK_COOKIES_TXT` | Optional Netscape cookies for Facebook downloads. |

## Inputs

| Input | Required | Default | Meaning |
|---|---:|---|---|
| `media_url` | Yes | - | Source video URL. |
| `compression_level` | Yes | `50` | Compression strength from 1 to 100. Higher means smaller output and lower quality. |
| `send_as` | Yes | `video` | `video`, `document`, or `zip`. |
| `output_filename` | No | auto | Optional output name. `.mp4` or `.zip` is normalized automatically. |
| `chat_id` | No | secret fallback | Final Telegram destination chat. |
| `progress_chat_id` | No | final chat | Chat containing the progress message. |
| `progress_message_id` | No | auto-create | Existing Telegram message to edit. If empty, the workflow creates a progress message when it has a chat id. |
| `reply_to_message_id` | No | empty | Optional Telegram message id to reply to when sending the final output. |
| `dispatch_key` | No | `manual` | Caller tracking key for bot-side matching. |

## Compression levels

`compression_level` is not quality. It is compression strength:

| Level | Meaning | Internal behavior |
|---:|---|---|
| `1` | Highest quality / least compression | CRF 18, 2160p cap, 192k audio. |
| `10` | Very high quality / light compression | CRF 18, 2160p cap, 192k audio. |
| `30` | High quality | CRF about 22, 1440p cap, 160k audio. |
| `50` | Balanced | CRF about 26, 1080p cap, 128k audio. |
| `75` | Strong compression / smaller size | CRF about 30, 720p cap, 96k audio. |
| `100` | Maximum compression / smallest practical size | CRF about 36, 480p cap, 64k audio. |

The produced video is normalized to MP4/H.264/AAC with `yuv420p`, `avc1`, and `+faststart` for Telegram and mobile compatibility.

## Telegram output modes

### `send_as=video`

Sends the compressed MP4 through `sendVideo` with `supports_streaming=true`.

### `send_as=document`

Sends the compressed MP4 through `sendDocument`.

### `send_as=zip`

Wraps the compressed MP4 in a `.zip` file and sends it through `sendDocument`.

The ZIP uses `ZIP_STORED` intentionally. It is for wrapping, naming, and delivery behavior, not for meaningful MP4 compression.

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

Completion summary:

```text
✅ GitHub Video Compress completed.

🌐 Platform: generic
🧭 Path: video-compress
🎚️ Compression: 50/100
🧱 Settings: CRF 26 · medium · 128k · 1080p
📐 Dimensions: 1920x1080
📄 File: compressed-video.mp4
📥 Downloaded Size: 120.50 MB
📦 Final Size: 38.20 MB — OK
🚀 Send Mode: video
📤 Send Method: Public Bot API
🆔 Message ID: 12345
🔗 Open Run
```

## Manual GitHub test

1. Push the three new files to the repository.
2. Open GitHub Actions.
3. Select `Video Compress To Telegram`.
4. Click `Run workflow`.
5. Fill:
   - `media_url`: a public video URL.
   - `compression_level`: start with `50`.
   - `send_as`: start with `video`.
   - `output_filename`: optional, for example `test-compressed.mp4`.
6. Run again with `compression_level=30` to compare higher quality.
7. Run again with `compression_level=75` to compare smaller output.
8. Test `send_as=document`.
9. Test `send_as=zip` with `output_filename=test-compressed.zip`.

## Bot-side `workflow_dispatch` payload example

```json
{
  "ref": "main",
  "inputs": {
    "media_url": "https://example.com/video.mp4",
    "compression_level": "50",
    "send_as": "video",
    "output_filename": "compressed-video.mp4",
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
