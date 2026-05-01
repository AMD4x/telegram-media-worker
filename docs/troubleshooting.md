# Troubleshooting

## `TELEGRAM_TOKEN secret is missing`

Add `TELEGRAM_TOKEN` to repository Actions secrets.

## `TELEGRAM_CHAT_ID secret is missing`

Add `TELEGRAM_CHAT_ID` to repository Actions secrets.

## `TELEGRAM_API_ID secret is missing` or `TELEGRAM_API_HASH secret is missing`

Local Bot API workflows need Telegram API credentials.

Add both values as repository Actions secrets.

## Local Bot API did not become ready

Possible causes:

- Invalid `TELEGRAM_API_ID` or `TELEGRAM_API_HASH`.
- Worker image missing `telegram-bot-api`.
- Port conflict inside the job container.
- Telegram Local Bot API startup failure.

Check the workflow logs, but avoid sharing raw logs publicly if they contain private inputs.

## `yt-dlp is missing from worker image`

The worker image does not contain yt-dlp or Python cannot import it.

Rebuild or update the image used by the workflow.

## `ffmpeg is missing from worker image`

The worker image does not contain ffmpeg.

Rebuild or update the image used by the workflow.

## YouTube asks for sign-in or fails to extract

Try adding or refreshing `YOUTUBE_COOKIES_TXT` in Netscape cookie format.

Also verify that the URL is accessible from a normal browser session using the same account.

## Facebook fails to parse or extract media

Try adding or refreshing `FACEBOOK_COOKIES_TXT` in Netscape cookie format.

Facebook extraction can be sensitive to account state, URL form, and platform-side changes.

## Video uploads as a file instead of a playable video

Possible causes:

- Unsupported codec.
- Missing audio stream.
- Incompatible container.
- Dimensions or bitrate unsuitable for Telegram/iPhone playback.

Use a workflow that prepares Telegram/iPhone-compatible MP4 output.

## File is too large

Telegram upload behavior depends on whether the workflow uses the public Bot API or Local Bot API.

Use document mode or a Local Bot API workflow for larger files when supported.

## Progress message does not update

Check:

- `progress_chat_id` is correct.
- `progress_message_id` is correct.
- The bot can edit that message.
- The message was originally sent by the same bot.
- The workflow has `TELEGRAM_TOKEN` available.

## Public bug report checklist

When opening a public issue, include:

- Workflow name.
- Platform name, not a private URL.
- Sanitized error message.
- Whether cookies were enabled: yes/no.
- Requested quality.
- Send mode: video/document.

Do not include tokens, cookies, private media URLs, or full raw logs.
