# Telegram Media Worker

GitHub Actions powered remote media worker for Telegram bots.

This repository runs temporary media jobs on GitHub-hosted runners, prepares the final media when needed, and sends the result to Telegram. It is designed for Telegram bots that need remote downloading, media conversion, document delivery, progress updates, or large-file upload behavior without keeping a permanent server online.

## What it does

- Downloads media or direct file URLs through GitHub Actions.
- Sends media to Telegram as video or document, depending on workflow support.
- Supports progress updates by editing an existing Telegram message.
- Uses `yt-dlp`, `ffmpeg`, `ffprobe`, `curl`, Python helpers, and Telegram Bot API / Telegram Local Bot API.
- Supports a generic `remote-media.yml` workflow plus dedicated Local Bot API workflows for YouTube, TikTok, and Facebook.
- Can be started manually from GitHub Actions or programmatically from a Telegram bot through `workflow_dispatch`.
- Masks sensitive inputs in GitHub Actions logs where possible.
- Prepares Telegram/iPhone-compatible video output when the selected workflow includes compatibility preparation.
- Supports large Telegram uploads through Local Bot API when configured.
- Supports document ZIP mode and split ZIP parts in the generic workflow.

## Why this exists

Small home servers, Raspberry Pi bots, and lightweight Telegram bot hosts are good controllers, but they are not always ideal for long media extraction, conversion, and upload tasks. This worker lets the bot delegate heavy work to an isolated GitHub Actions run, update the user with progress, then deliver the final Telegram message.

## Current workflow family

| Workflow | Main purpose | Output type | Telegram sender | Document mode | Notes |
|---|---|---:|---|---:|---|
| `.github/workflows/remote-media.yml` | Generic remote media/file worker | Video or document | Public Bot API for small files, Local Bot API for larger files when needed | Yes | Broadest workflow. Detects several platforms and direct downloadable files. |
| `.github/workflows/youtube-video-local-api.yml` | YouTube video sender | Video only | Local Bot API | No | YouTube-focused path with Telegram/iPhone compatibility preparation. |
| `.github/workflows/tiktok-direct-local-api.yml` | TikTok direct video sender | Video only | Local Bot API | No | Tries direct TikTok resolver first, then `yt-dlp` fallbacks, while requiring audio and Telegram-compatible video. |
| `.github/workflows/facebook-long-video-local-api.yml` | Facebook long-video sender | Video only | Local Bot API | No | Facebook-focused path with optional cookies and Telegram/iPhone compatibility preparation. |

## Quick routing guide

| Source URL / requested output | Recommended workflow |
|---|---|
| Direct downloadable file to Telegram as a document | `remote-media.yml` with `send_as=document` |
| Any URL that should be zipped before sending | `remote-media.yml` with `send_as=document` and `document_mode=zip` |
| Generic platform video | `remote-media.yml` with `send_as=video` |
| YouTube video | `youtube-video-local-api.yml` for video-only output; `remote-media.yml` for document mode |
| TikTok video | `tiktok-direct-local-api.yml` for video-only output; `remote-media.yml` for document mode |
| Facebook video | `facebook-long-video-local-api.yml` for video-only output; `remote-media.yml` for document mode |
| Instagram, X/Twitter, Reddit | `remote-media.yml` only; no dedicated workflow currently exists |

## Required secrets

Create secrets in:

```text
Repository Settings -> Secrets and variables -> Actions -> Repository secrets
```

| Secret | Required by | Purpose |
|---|---|---|
| `TELEGRAM_TOKEN` | All workflows that send progress or final Telegram messages | Telegram bot token from BotFather. |
| `TELEGRAM_CHAT_ID` | All final-send workflows | Destination chat, group, or channel ID. |
| `TELEGRAM_API_ID` | Local Bot API workflows and large uploads through `remote-media.yml` | Telegram API ID used by `telegram-bot-api --local`. |
| `TELEGRAM_API_HASH` | Local Bot API workflows and large uploads through `remote-media.yml` | Telegram API hash used by `telegram-bot-api --local`. |
| `YOUTUBE_COOKIES_TXT` | Optional for YouTube paths | Netscape-format cookies for restricted, account-sensitive, age-gated, or region-gated YouTube media. |
| `FACEBOOK_COOKIES_TXT` | Optional for Facebook paths | Netscape-format cookies for restricted or account-sensitive Facebook media. |

See:

- [`secrets.example.md`](secrets.example.md)
- [`docs/telegram-secrets.md`](docs/telegram-secrets.md)
- [`docs/security-and-privacy.md`](docs/security-and-privacy.md)

## Manual usage from GitHub

1. Open the repository on GitHub.
2. Go to **Actions**.
3. Choose the workflow.
4. Click **Run workflow**.
5. Fill the inputs.
6. Start the run.
7. Watch GitHub logs or the Telegram progress message.

## Common workflow inputs

| Input | Used by | Meaning |
|---|---|---|
| `media_url` | All workflows | Source media/file URL. |
| `max_height` | `remote-media.yml`, YouTube, TikTok | Requested maximum video height. `remote-media.yml` exposes fixed choices. Dedicated workflows accept a string and normalize invalid values to `auto`. |
| `send_as` | Fully used only by `remote-media.yml` | `video` or `document`. Dedicated platform workflows keep it only as an ignored compatibility input. |
| `output_filename` | Fully used only by document-capable paths | Requested output document/ZIP filename. Dedicated platform workflows keep it only as an ignored compatibility input. |
| `document_mode` | `remote-media.yml` only | `zip` or `original`. Invalid values fall back to `zip`. |
| `progress_chat_id` | Workflows with progress updates | Chat ID containing the progress message to edit. |
| `progress_message_id` | Workflows with progress updates | Telegram message ID to edit. |
| `dispatch_key` | Caller tracking | Optional task identifier used by a bot to match a run to a user request. |

## Important capability rules

- `remote-media.yml` is currently the only workflow with real `document_mode` support.
- Dedicated platform workflows always send videos through `sendVideo`.
- In dedicated platform workflows, `send_as` and `output_filename` are compatibility inputs only and are not used to change behavior.
- Large uploads require `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` because the worker must start Telegram Local Bot API.
- Direct public Bot API uploads are used for smaller files where possible.
- The generic workflow can create ZIP documents and split oversized ZIPs into Telegram-safe parts.
- TikTok support may depend on a third-party direct resolver and/or `yt-dlp`; platform behavior can change without repository changes.

## Workflow details

Detailed behavior is documented in:

- [`docs/workflows.md`](docs/workflows.md)
- [`docs/architecture.md`](docs/architecture.md)
- [`docs/supported-platforms.md`](docs/supported-platforms.md)
- [`docs/usage-from-bot.md`](docs/usage-from-bot.md)
- [`docs/troubleshooting.md`](docs/troubleshooting.md)

## Security notes

Never put bot tokens, cookies, private URLs, personal media links, chat IDs, message IDs, or raw workflow logs in public issues, screenshots, README examples, workflow files, or comments.

The workflows mask sensitive inputs where possible, but masking is not a substitute for careful log handling. Treat raw workflow logs as private.

## Project status

The repository currently contains four workflow families:

- Generic remote media/file worker.
- YouTube Local Bot API video worker.
- TikTok Direct Local Bot API video worker.
- Facebook Long Video Local Bot API video worker.

Known limitations:

- There is no `workflow_call` interface yet.
- Platform workflows duplicate progress and compatibility helper logic.
- Dedicated platform workflows do not support `document_mode`.
- Instagram, X/Twitter, and Reddit are handled only by the generic workflow and have no dedicated cookie path.
- TikTok extraction depends on external platform behavior and may require fallback paths.

## License

MIT License. See [`LICENSE`](LICENSE).
