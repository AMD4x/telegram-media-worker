# Usage From a Telegram Bot

A Telegram bot can use this repository as a remote media worker by triggering GitHub Actions workflows with `workflow_dispatch`.

## Recommended bot flow

1. Receive a user URL.
2. Validate the URL syntax and reject unsupported schemes.
3. Detect the platform or requested send mode.
4. Choose a workflow.
5. Send a placeholder Telegram message to the user.
6. Trigger the GitHub workflow.
7. Pass `progress_chat_id` and `progress_message_id` so the workflow can edit the placeholder message.
8. Store a task record that maps the user request to `dispatch_key`.
9. Poll GitHub Actions for run status.
10. Offer cancellation by canceling the matching GitHub Actions run.
11. Let the workflow send the final media/document to Telegram.
12. Clean up the bot-side task record.

## Workflow routing

| User request | Recommended route |
|---|---|
| YouTube as playable video | `youtube-video-local-api.yml` |
| YouTube as document/ZIP | `remote-media.yml` |
| TikTok as playable video | `tiktok-direct-local-api.yml` |
| TikTok as document/ZIP | `remote-media.yml` |
| Facebook long video as playable video | `facebook-long-video-local-api.yml` |
| Facebook as document/ZIP | `remote-media.yml` |
| Direct file URL as Telegram document | `remote-media.yml` |
| Unknown platform video | `remote-media.yml` |
| Instagram/X/Reddit | `remote-media.yml` |

## Inputs to send

### Generic video request

```json
{
  "ref": "main",
  "inputs": {
    "media_url": "https://example.com/video",
    "max_height": "720",
    "send_as": "video",
    "progress_chat_id": "123456789",
    "progress_message_id": "55",
    "dispatch_key": "123456789-55-abcd"
  }
}
```

### Generic document ZIP request

```json
{
  "ref": "main",
  "inputs": {
    "media_url": "https://example.com/file.pdf",
    "max_height": "auto",
    "send_as": "document",
    "document_mode": "zip",
    "output_filename": "download.zip",
    "progress_chat_id": "123456789",
    "progress_message_id": "56",
    "dispatch_key": "123456789-56-abcd"
  }
}
```

### YouTube video request

```json
{
  "ref": "main",
  "inputs": {
    "media_url": "https://www.youtube.com/watch?v=VIDEO_ID",
    "max_height": "1080",
    "progress_chat_id": "123456789",
    "progress_message_id": "57",
    "dispatch_key": "123456789-57-abcd"
  }
}
```

### TikTok video request

```json
{
  "ref": "main",
  "inputs": {
    "media_url": "https://www.tiktok.com/@user/video/123",
    "max_height": "auto",
    "progress_chat_id": "123456789",
    "progress_message_id": "58",
    "dispatch_key": "123456789-58-abcd"
  }
}
```

### Facebook long video request

```json
{
  "ref": "main",
  "inputs": {
    "media_url": "https://www.facebook.com/watch/?v=123",
    "progress_chat_id": "123456789",
    "progress_message_id": "59",
    "dispatch_key": "123456789-59-abcd"
  }
}
```

## Dispatch endpoint

Use GitHub REST API:

```text
POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches
```

Examples of `workflow_id`:

```text
remote-media.yml
youtube-video-local-api.yml
tiktok-direct-local-api.yml
facebook-long-video-local-api.yml
```

## `dispatch_key`

Use a unique key per task. Recommended format:

```text
<chat_id>-<message_id>-<random_suffix>
```

The workflows include the key in `run-name`, which helps the bot match a run to a user task.

## Finding the matching run

After dispatching, GitHub's dispatch endpoint does not directly return the run ID. The bot should:

1. record the dispatch time,
2. list recent workflow runs for that workflow,
3. match by branch, event type, created time, and `dispatch_key` in the run name,
4. store the run ID.

## Progress message requirements

The progress message can be edited only if:

- the same bot created the message,
- `progress_chat_id` is correct,
- `progress_message_id` is correct,
- the message still exists,
- the bot has permission to edit it.

If progress inputs are missing or invalid, the workflows continue without progress updates.

## Cancellation

A bot-side Cancel button can call GitHub Actions cancel-run API for the stored run ID.

Bot-side cancellation should also update the Telegram progress message so the user knows the request was canceled.

## Choosing `send_as`

Use `send_as=document` only with `remote-media.yml`.

Dedicated workflows ignore `send_as`; sending `document` to them will not turn the result into a document.

## Choosing `document_mode`

Use only with `remote-media.yml`.

| Mode | User-facing behavior |
|---|---|
| `original` | Send the downloaded file directly as a document. |
| `zip` | Put the file inside a ZIP, then send it. If too large, the ZIP may be sent in split parts. |

## Bot-side validation recommendations

Reject or sanitize before dispatch:

- empty URL,
- non-HTTP/HTTPS schemes,
- extremely long input,
- known malicious or unsupported domains,
- local/private network URLs if the bot accepts arbitrary links,
- suspicious output filenames,
- attempts to place secrets in filenames or URLs.

## Bot-side reliability recommendations

- Do not block the bot event loop while polling.
- Poll at a reasonable interval.
- Persist task state so restarts do not lose active runs.
- Handle GitHub API rate limits.
- Provide a timeout to the user.
- Keep a fallback message for workflow failure.
- Avoid echoing raw GitHub logs to users.
- Never expose repository secrets, cookies, private URLs, or full workflow logs.
