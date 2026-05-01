# Usage From a Telegram Bot

A bot can use this repository as a remote media worker by triggering GitHub Actions workflows.

## Suggested flow

1. User sends a media URL to the bot.
2. Bot validates the URL and detects the platform.
3. Bot sends a temporary progress message to Telegram.
4. Bot triggers the relevant GitHub workflow through `workflow_dispatch`.
5. Bot passes:

```text
media_url
max_height
send_as
output_filename
document_mode
progress_chat_id
progress_message_id
dispatch_key
```

6. Workflow updates the progress message while running.
7. Workflow sends the final media to Telegram.
8. Bot polls the GitHub run if it wants additional status or cancellation support.

## Suggested workflow routing

| URL type | Suggested route |
|---|---|
| YouTube video | YouTube Local Bot API workflow if available. |
| TikTok video | TikTok Direct workflow if available. |
| Facebook long video | Facebook Long workflow if available. |
| Generic media URL | Generic remote-media workflow. |
| Direct downloadable file | Generic document mode. |

## Dispatch key

Use a unique `dispatch_key` per request. This helps the bot match a GitHub workflow run to a user task.

Example:

```text
chatid-messageid-randomsuffix
```

## Cancellation

The bot can provide a Cancel button and call GitHub Actions cancel-run API for the matched run.

## Reliability notes

- Always handle GitHub API timeouts.
- Do not block the bot event loop while polling.
- Poll at a reasonable interval.
- Keep a fallback path if GitHub Actions is unavailable.
- Sanitize user URLs before placing anything into logs.
