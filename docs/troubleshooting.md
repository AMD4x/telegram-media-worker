# Troubleshooting

This document lists common failures and the most likely causes.

## `media_url input is missing`

The caller did not pass `media_url`, or the workflow could not read it from the event payload.

Check:

- the JSON body sent to GitHub,
- the workflow input name,
- that the bot is dispatching the intended workflow.

## `Missing TELEGRAM_TOKEN secret` / `TELEGRAM_TOKEN secret is missing`

Add `TELEGRAM_TOKEN` to repository Actions secrets.

The token must be a valid bot token created through BotFather.

## `Missing TELEGRAM_CHAT_ID secret` / `TELEGRAM_CHAT_ID secret is missing`

Add `TELEGRAM_CHAT_ID` to repository Actions secrets.

Check that the bot can send to this chat, group, or channel.

## `TELEGRAM_API_ID secret is missing` or `TELEGRAM_API_HASH secret is missing`

Local Bot API requires both secrets.

These are required by:

- `youtube-video-local-api.yml`,
- `tiktok-direct-local-api.yml`,
- `facebook-long-video-local-api.yml`,
- `remote-media.yml` when it needs Local Bot API for large uploads.

## `Large Telegram upload requires TELEGRAM_API_ID and TELEGRAM_API_HASH secrets`

The generic workflow selected Local Bot API because the file exceeded the Public Bot API threshold. Add the Local Bot API secrets or use a smaller output.

## `Local Bot API did not become ready`

Possible causes:

- invalid `TELEGRAM_API_ID`,
- invalid `TELEGRAM_API_HASH`,
- `telegram-bot-api` missing from the worker image,
- process crashed at startup,
- local port did not become reachable,
- container image/runtime issue.

Check sanitized logs and the Local Bot API startup section. Do not share raw logs publicly.

## `telegram-bot-api is missing from worker image`

The container image does not contain `telegram-bot-api`.

Rebuild or update `ghcr.io/amd4x/tg-video-worker:latest`.

## `yt-dlp is missing from worker image`

The container image does not contain `yt-dlp`, or Python cannot import it.

Rebuild/update the image and verify:

```text
python3 -m yt_dlp --version
```

## `ffmpeg is missing from worker image`

The container image does not contain `ffmpeg`.

Rebuild/update the image and verify:

```text
ffmpeg -version
```

## `ffprobe is missing from worker image`

The container image does not contain `ffprobe`.

`ffprobe` is needed for stream, codec, dimension, duration, and bitrate checks.

## YouTube fails or asks for sign-in

Try:

- adding or refreshing `YOUTUBE_COOKIES_TXT`,
- exporting cookies in Netscape format,
- verifying the URL from the same browser account,
- reducing requested height,
- trying the generic workflow if the dedicated workflow fails,
- updating the worker image so `yt-dlp` is current.

## Facebook fails to parse or extract

Try:

- adding or refreshing `FACEBOOK_COOKIES_TXT`,
- testing whether the URL is accessible from the cookie account,
- using the canonical Facebook video URL if available,
- updating `yt-dlp`,
- trying `remote-media.yml` if the dedicated path fails.

## TikTok fails

The TikTok workflow uses multiple strategies, including a third-party direct resolver and `yt-dlp` fallbacks.

Possible causes:

- `tikwm.com` failed or changed response format,
- TikTok blocked the request,
- `yt-dlp` extractor changed or broke,
- no clean video+audio candidate was available,
- the candidate did not contain AAC audio and H.264 video,
- Telegram rejected the upload.

Try:

- re-running later,
- testing the URL manually,
- updating `yt-dlp`,
- trying the generic workflow,
- using a different URL form.

## `No clean playable TikTok candidate was downloaded`

The workflow could not produce a final file with both video and audio that also passed compatibility checks.

Common causes:

- no audio stream,
- no video stream,
- unsupported codec,
- resolver failure,
- `yt-dlp` failure,
- source platform restriction.

## Video sends as a file or does not play inline

Possible causes:

- unsupported video codec,
- unsupported audio codec,
- missing audio stream,
- incompatible container,
- missing `+faststart`,
- bad sample aspect ratio,
- dimensions or H.264 level not ideal for Telegram/iPhone.

Use a workflow that prepares Telegram/iPhone-compatible MP4 output.

## `Prepared TikTok file is not Telegram video compatible`

The final TikTok file did not satisfy the TikTok workflow's compatibility check:

- H.264 video,
- AAC audio,
- video stream present,
- audio stream present.

Try updating the worker image or using another route.

## `File is larger than 2000MB Local Bot API limit`

The final media/document exceeds the workflow's Local Bot API ceiling.

Options:

- lower `max_height`,
- use `remote-media.yml` document ZIP mode,
- allow split ZIP parts for documents,
- reduce source quality,
- add size-fit behavior to the dedicated workflow if needed.

## I received split parts and cannot open them on Windows

Split files such as `.part001`, `.part002`, `.001`, and `.002` are ordered binary parts. They are not standalone media files and should not be extracted as ZIP/RAR archives.

Fixes:

- download every part,
- keep all parts in the same folder,
- join them in order with `copy /b`,
- or install the optional Windows helper in `tools/windows/amd4x-merge/` and right-click the first part.

AMD4x Merge is only a local restore helper. It does not change workflow execution or Telegram upload limits.

## Direct document download produces HTML

The generic workflow rejects HTML pages in document mode. This usually means the URL is not a direct downloadable file.

Try:

- a direct file link,
- a signed download URL,
- a URL that does not require a web session,
- platform video mode instead of document direct mode.

## Output filename ignored

`output_filename` is fully meaningful only in `remote-media.yml` document-capable paths.

It is an ignored compatibility input in dedicated YouTube, TikTok, and Facebook workflows.

## `send_as=document` does not work in a dedicated workflow

This is expected. Dedicated workflows send video only.

Use `remote-media.yml` for document output.

## `PACKAGE_MANIFEST_KEY_MISSING=1`

`package-inspect.yml` could not encrypt the package manifest because `PACKAGE_MANIFEST_KEY` is missing.

Add the same long random `PACKAGE_MANIFEST_KEY` value to GitHub repository secrets and to the bot environment that decrypts package manifests.

## Package Inspector completed but the bot did not receive a manifest

Check:

- `PACKAGE_MANIFEST_KEY` matches between GitHub and the bot,
- `.package_manifests/<dispatch_key>.enc` was created,
- the bot token used for GitHub API can read repository contents,
- the bot deletes the `.enc` file only after successful decrypt/read,
- the bot does not print manifest contents into public logs.

## Package Inspector / Repacker renamed file is not at the top

This is Package Browser bot-side UI behavior. Keep a rename-priority list in the bot state, move an original manifest path to the newest position after each rename, sort newest renamed items first, and remove the path when the rename is reset.

## Progress message does not update

Check:

- `progress_chat_id` is present,
- `progress_message_id` is present,
- the message was created by the same bot,
- the bot still has permission,
- the target chat exists,
- `TELEGRAM_TOKEN` is valid,
- Telegram did not reject the edit.

## Telegram returns non-ok response

Check:

- bot permissions,
- chat ID,
- file size,
- file type,
- Telegram API response description in private logs,
- whether the Local Bot API endpoint is running.

Do not paste raw response logs publicly if they include private data.

## Public bug report checklist

When opening a public issue, include only sanitized information:

- workflow name,
- platform name,
- requested quality,
- send mode,
- document mode if used,
- whether cookies were enabled: yes/no,
- high-level error message,
- whether Local Bot API was used.

Do not include:

- bot token,
- cookies,
- chat IDs,
- message IDs,
- private URLs,
- full raw workflow logs,
- personal media links.

## `video-compress.yml` output is larger than the source

This can happen with low compression levels such as `21` or `30`, especially when the source is already very small or heavily compressed.

Try:

- `compression_level=50` for balanced output,
- `compression_level=75` for strong compression,
- `compression_level=100` for the smallest practical output.

## `send_as=document` still shows a video preview

`video-compress.yml` sends document mode through `sendDocument` with content-type detection disabled. Some Telegram clients may still show a preview for MP4 files.

For a guaranteed file-wrapper experience, use:

```text
send_as=zip
```

## `compression_level must be between 1 and 100`

The workflow expects an integer from `1` to `100`. It treats the value as compression strength, not quality.
