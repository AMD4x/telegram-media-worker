# Telegram Secrets Guide

This repository uses Telegram-related secrets to send media after a GitHub Actions worker finishes processing.

Create secrets in:

```text
Repository Settings -> Secrets and variables -> Actions -> Repository secrets
```

## `TELEGRAM_TOKEN`

Telegram bot token created through BotFather.

Required by all workflows that send Telegram progress updates or final media.

Example placeholder:

```text
TELEGRAM_TOKEN=123456789:REPLACE_WITH_YOUR_BOT_TOKEN
```

Never commit a real token.

## `TELEGRAM_CHAT_ID`

Destination chat ID used for the final media message.

This can be:

- private chat ID,
- group ID,
- supergroup ID,
- channel ID.

The bot must have permission to send messages to the destination.

## `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`

Telegram API credentials used by Telegram Local Bot API.

Required by:

- `youtube-video-local-api.yml`,
- `tiktok-direct-local-api.yml`,
- `facebook-long-video-local-api.yml`,
- `remote-media.yml` when a file is too large for Public Bot API and Local Bot API is needed.
- `video-compress.yml` when the compressed output is too large for Public Bot API and Local Bot API is needed.
- `package-repack.yml` when the output ZIP or split ZIP parts require Telegram Local Bot API.

The workflows start Local Bot API with:

```text
telegram-bot-api --local --http-ip-address=127.0.0.1 --http-port=8081
```

## Progress message inputs

These are runtime workflow inputs, not repository secrets:

```text
progress_chat_id
progress_message_id
```

They let the workflow edit an existing Telegram message while the job runs.

The progress message must have been sent by the same bot.

## Package manifest encryption

### `PACKAGE_MANIFEST_KEY`

Required when a bot uses Package Inspector / Repacker and reads the generated `package-inspect.yml` manifest from `.package_manifests/`.

The workflow encrypts `manifest.json` into `.package_manifests/<dispatch_key>.enc`. The bot must use the same key to decrypt the manifest, then delete the `.enc` file after successful read.

Use a long random value and keep it only in repository secrets and the bot environment.

## Platform cookies

### `YOUTUBE_COOKIES_TXT`

Optional but recommended for:

- restricted YouTube videos,
- age-gated videos,
- region-gated videos,
- account-sensitive videos,
- videos that ask for sign-in.

### `FACEBOOK_COOKIES_TXT`

Optional but recommended for:

- account-sensitive Facebook videos,
- restricted Facebook videos,
- videos not visible publicly.

## Cookie format

Use Netscape HTTP Cookie File format.

The value normally starts with:

```text
# Netscape HTTP Cookie File
```

## Rotation

Rotate secrets if:

- they appear in logs,
- they appear in screenshots,
- they are pasted into an issue,
- a collaborator should no longer have access,
- cookies stop working,
- the bot token is suspected compromised.

## Minimal setup

For small generic uploads and small `video-compress.yml` outputs:

```text
TELEGRAM_TOKEN
TELEGRAM_CHAT_ID
```

For dedicated Local Bot API workflows and large uploads:

```text
TELEGRAM_TOKEN
TELEGRAM_CHAT_ID
TELEGRAM_API_ID
TELEGRAM_API_HASH
```

For restricted platform content, add cookies as needed.

For Package Inspector bot integration, also add:

```text
PACKAGE_MANIFEST_KEY
```
