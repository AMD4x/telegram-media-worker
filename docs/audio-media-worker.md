# Audio Media Worker

## Overview

Audio Media Worker is a GitHub Actions workflow for extracting audio from media links, converting it to a selected format, and sending the result to Telegram.

It is intended to run as a standalone worker inside this repository. The workflow can be triggered manually from GitHub Actions and can later be called from another service or bot.

## What it does

The worker supports:

- Extracting audio from supported media URLs.
- Converting video links to audio-only files.
- Sending the final audio file to Telegram.
- Using Telegram Local Bot API for large files when configured.
- Falling back to metadata-based search for platforms that do not expose direct audio streams.

## Files

The feature is implemented in two files:

```text
.github/workflows/audio-media.yml
scripts/audio_media/audio_media_worker.py
```

### Workflow

```text
.github/workflows/audio-media.yml
```

Defines the manual GitHub Actions entry point.

The workflow:

- Runs inside the configured media worker container.
- Loads the Python worker script from the repository.
- Passes workflow inputs and secrets to the worker.
- Masks runtime inputs before running the worker.
- Exposes only minimal safe outputs.

### Worker script

```text
scripts/audio_media/audio_media_worker.py
```

Handles the actual audio job.

The script:

- Detects the source platform.
- Downloads the best available audio stream.
- Resolves fallback sources when direct extraction is not available.
- Converts the media to the requested output format.
- Uploads the result to Telegram.
- Updates Telegram progress messages when progress fields are provided.

## Running the workflow

Open the repository on GitHub, then run:

```text
Actions -> Audio Media To Telegram -> Run workflow
```

## Inputs

### source_url

Media URL to process.

Examples:

```text
https://youtu.be/example
https://open.spotify.com/track/example
https://soundcloud.com/example/example
```

This can be left empty only when `search_query` is provided.

### search_query

Optional manual search query.

When this value is provided, the worker searches YouTube using the given query instead of starting from a URL.

### audio_format

Final output format.

Supported values:

```text
mp3
m4a
raw
voice
```

#### mp3

Converts the result to MP3 and sends it as Telegram audio.

#### m4a

Converts the result to M4A/AAC and sends it as Telegram audio.

#### raw

Keeps the downloaded audio format when possible.

#### voice

Converts the result to OGG/Opus and sends it as a Telegram voice message.

### output_filename

Optional final filename.

When this is empty, the worker tries to create a filename from the source metadata. If metadata is not available, it falls back to a generated name.

### chat_id

Optional Telegram destination chat ID.

The worker resolves the destination in this order:

```text
chat_id input
TELEGRAM_CHAT_ID secret
ADMIN_ID secret
```

### progress_chat_id

Optional Telegram chat ID used for progress updates.

When empty, it falls back to the destination chat ID.

### progress_message_id

Optional Telegram message ID to edit for progress updates.

When empty, the worker creates a new progress message when possible.

### reply_to_message_id

Optional Telegram message ID to reply to when sending the final audio.

### dispatch_key

Optional external dispatch identifier.

It can be used by callers to track a request, but it is not required for manual runs.

## Required secrets

### TELEGRAM_TOKEN

Telegram bot token.

Required.

### TELEGRAM_CHAT_ID

Default Telegram destination chat ID.

Used when `chat_id` is empty.

### ADMIN_ID

Fallback Telegram destination chat ID.

Used when both `chat_id` and `TELEGRAM_CHAT_ID` are empty.

### TELEGRAM_API_ID

Telegram API ID.

Required only when the worker needs to use the local Telegram Bot API for large uploads.

### TELEGRAM_API_HASH

Telegram API hash.

Required only when the worker needs to use the local Telegram Bot API for large uploads.

### YOUTUBE_COOKIES_TXT

Optional YouTube cookies file content.

Useful for age-restricted, region-restricted, or authenticated YouTube requests.

### FACEBOOK_COOKIES_TXT

Optional Facebook cookies file content.

Useful when Facebook extraction requires cookies.

## Runtime environment

The workflow runs inside:

```text
ghcr.io/amd4x/tg-video-worker:latest
```

The container is expected to provide:

```text
python3
yt-dlp
ffmpeg
ffprobe
curl
```

For large Telegram uploads, it should also provide:

```text
telegram-bot-api
```

## Processing flow

A normal run follows this flow:

```text
Prepare runtime
Detect source platform
Download best audio stream
Resolve fallback source if needed
Convert or preserve audio format
Upload to Telegram
Finalize progress message
Set workflow outputs
```

## Direct extraction

For sources supported directly by `yt-dlp`, the worker downloads the best available audio stream using:

```text
bestaudio/best
```

After that, it converts the downloaded file according to the selected `audio_format`.

This path is commonly used for YouTube, SoundCloud, and other sources supported by `yt-dlp`.

## Video to audio

Video URLs are supported as long as `yt-dlp` can extract media from the URL.

The worker keeps only the audio stream. For converted formats, FFmpeg is called with video disabled:

```text
-vn
```

## Spotify and metadata fallback

Some platforms, such as Spotify, do not provide a direct downloadable audio stream.

When direct extraction fails, the worker uses metadata from the source page and searches for an equivalent public audio result.

For Spotify links, the worker prefers the page title metadata because it often includes a better track name and featured artist information.

Fallback search order:

```text
ytsearch1:{query} "Topic"
ytmsearch1:{query} official audio
```

This is meant to prefer topic or official audio results when possible.

## Arabic titles

Arabic music titles can be harder to resolve because search results may include unrelated videos with similar names.

For Spotify fallback, the worker prefers the Spotify page `<title>` before other metadata sources. This usually gives a more complete search query, especially when the track includes a featured artist.

Example query shape:

```text
Track Name (feat. Artist)
```

## Telegram uploads

The worker supports two upload paths.

### Public Bot API

Used when the final file is within the public Telegram Bot API upload limit.

The current public limit used by the worker is:

```text
50 MB
```

### Local Bot API

Used when the final file is larger than the public limit.

The current local safety limit used by the worker is:

```text
2 GB
```

When local upload is needed, the worker starts a local Telegram Bot API server inside the job container.

## Filenames

The worker tries to keep a readable final filename based on source metadata.

For the actual multipart upload, the worker uses a temporary safe upload filename. This avoids upload problems caused by Unicode characters or special characters in file paths.

When possible, the original source-derived title is still sent as the Telegram audio title.

## Progress updates

When progress fields are provided, the worker updates Telegram with job progress.

Possible stages include:

```text
Preparing
Detecting
Downloading
Resolving
Searching
Converting
Uploading
Finalizing
Completed
Failed
```

GitHub logs only show compact progress markers, for example:

```text
AUDIO_WORKER: PROGRESS_PERCENT=68
AUDIO_WORKER: PROGRESS_STATUS=Converting
AUDIO_WORKER: completed
```

## Workflow outputs

The workflow exposes the following outputs:

```text
ok
audio_format
send_mode
```

These outputs are intentionally small and safe to consume from another workflow or external dispatcher.

## Limitations

Metadata fallback depends on the source metadata and the search results returned by YouTube.

For platforms that do not expose direct audio streams, the worker does not download audio from the original platform. Instead, it resolves an equivalent public audio source when possible.

This behavior is expected for platforms such as Spotify.
