# Telegram Media Worker

GitHub Actions powered remote media worker for Telegram bots.

This repository runs temporary media jobs on GitHub-hosted runners, then sends the final media to Telegram. It is designed for bots that need remote download, conversion, trimming, or large-file upload behavior without keeping a permanent server online.

## What it does

- Downloads media URLs through GitHub Actions.
- Sends videos or documents to Telegram.
- Supports progress updates back to an existing Telegram message.
- Uses `yt-dlp`, `ffmpeg`, and Telegram Bot API / Local Bot API workflows.
- Supports platform-oriented workflows for YouTube, TikTok, Facebook, and a generic remote-media path.
- Can be called manually from GitHub or programmatically from a Telegram bot.

## Why this exists

Small home servers and Raspberry Pi bots are excellent controllers, but they are not always the best place to perform long media downloads, conversion, and upload work. This worker lets the bot trigger an isolated GitHub Actions run, monitor progress, and receive the final result.

## Current workflow family

The repository currently contains workflow-based workers such as:

| Workflow | Purpose |
|---|---|
| `remote-media.yml` | Generic remote media download/send path with video/document modes. |
| `youtube-video-local-api.yml` | YouTube-focused Local Bot API video sender. |
| `tiktok-direct-local-api.yml` | TikTok-focused direct video sender through Local Bot API. |
| `facebook-long-video-local-api.yml` | Facebook long-video path through Local Bot API. |

## Required secrets

At minimum, most workflows need:

| Secret | Required | Purpose |
|---|:---:|---|
| `TELEGRAM_TOKEN` | Yes | Telegram bot token. |
| `TELEGRAM_CHAT_ID` | Yes | Destination chat ID. |
| `TELEGRAM_API_ID` | Required for Local Bot API workflows | Telegram API ID. |
| `TELEGRAM_API_HASH` | Required for Local Bot API workflows | Telegram API hash. |
| `YOUTUBE_COOKIES_TXT` | Optional / recommended for restricted YouTube videos | Netscape-format YouTube cookies. |
| `FACEBOOK_COOKIES_TXT` | Optional / recommended for Facebook videos | Netscape-format Facebook cookies. |

See [`secrets.example.md`](secrets.example.md) and [`docs/telegram-secrets.md`](docs/telegram-secrets.md).

## Manual usage from GitHub

1. Open the repository on GitHub.
2. Go to **Actions**.
3. Choose the workflow you want to run.
4. Click **Run workflow**.
5. Fill the required inputs.
6. Start the run and follow the logs or Telegram progress message.

Typical inputs include:

| Input | Meaning |
|---|---|
| `media_url` | The source media URL. |
| `max_height` | Maximum video height, such as `720`, `1080`, or `auto`. |
| `send_as` | `video` or `document`, depending on workflow support. |
| `output_filename` | Optional output document filename. |
| `document_mode` | Usually `zip` or `original` in document-capable workflows. |
| `progress_chat_id` | Optional chat ID where a progress message should be edited. |
| `progress_message_id` | Optional Telegram message ID to edit during progress. |
| `dispatch_key` | Optional tracking key supplied by the caller bot. |

## Programmatic usage from a bot

A Telegram bot can trigger a workflow through the GitHub REST API using `workflow_dispatch`. The bot should provide the workflow inputs, poll the workflow run, and update the user-facing Telegram message.

Recommended bot-side responsibilities:

- Validate the URL before dispatching.
- Choose the correct workflow.
- Send a placeholder Telegram message first.
- Pass `progress_chat_id` and `progress_message_id` to the workflow.
- Poll the GitHub run status.
- Cancel the run if the user presses a cancel button.

See [`docs/usage-from-bot.md`](docs/usage-from-bot.md).

## Supported platforms

Support depends on the selected workflow and the current behavior of the source platform. See [`docs/supported-platforms.md`](docs/supported-platforms.md).

## Security notes

Never put bot tokens, cookies, private URLs, or personal media links inside issues, discussions, README examples, workflow files, or public logs.

Use GitHub repository secrets only. See [`SECURITY.md`](SECURITY.md).

## Troubleshooting

Common failures usually come from one of these areas:

- Missing Telegram secrets.
- Invalid cookies or expired cookies.
- Source platform extraction changes.
- Telegram upload limits.
- Incompatible codecs requiring conversion.
- Local Bot API not starting correctly.

See [`docs/troubleshooting.md`](docs/troubleshooting.md).

## Project status

All four workflow families are working and functionally complete. The Docker image rebuilds automatically when yt-dlp or Deno release updates.

Known limitations include duplicated progress helpers across platform workflows, no `workflow_call` interface, and no `document_mode` support in dedicated platform workflows. Instagram, X/Twitter, and Reddit fall through to the generic remote-media path without dedicated cookie support.

Possible future additions are tracked in [`ROADMAP.md`](ROADMAP.md).
See [`ROADMAP.md`](ROADMAP.md).

## License

MIT License. See [`LICENSE`](LICENSE).
