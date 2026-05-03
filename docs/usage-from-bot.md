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
| Compress a video before Telegram delivery | `video-compress.yml` |
| Instagram/X/Reddit | `remote-media.yml` or `video-compress.yml` when compression is required |
| Magnet link or direct `.torrent` URL | `torrent-document-local-api.yml` |
| Inspect and repack archive/package source | `package-inspect.yml`, then `package-repack.yml` |

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

### Video compression request

```json
{
  "ref": "main",
  "inputs": {
    "media_url": "https://example.com/video.mp4",
    "compression_level": "75",
    "send_as": "zip",
    "output_filename": "",
    "chat_id": "123456789",
    "progress_chat_id": "123456789",
    "progress_message_id": "62",
    "reply_to_message_id": "",
    "dispatch_key": "123456789-62-abcd"
  }
}
```

`output_filename` can be left empty. In that case, `video-compress.yml` creates a default name such as `instagram-20260503-231455.mp4` or `facebook-20260503-231455.zip`.


### Torrent list request

```json
{
  "ref": "main",
  "inputs": {
    "torrent_url": "magnet:?xt=urn:btih:...",
    "file_mode": "list",
    "progress_chat_id": "123456789",
    "progress_message_id": "60",
    "dispatch_key": "123456789-60-abcd"
  }
}
```

### Torrent selected files request

```json
{
  "ref": "main",
  "inputs": {
    "torrent_url": "magnet:?xt=urn:btih:...",
    "file_mode": "selected",
    "selected_files": "1,2",
    "split_part_mib": "1900",
    "progress_chat_id": "123456789",
    "progress_message_id": "61",
    "dispatch_key": "123456789-61-abcd"
  }
}
```

### Package inspect request

```json
{
  "ref": "main",
  "inputs": {
    "source_url": "https://example.com/archive.zip",
    "progress_chat_id": "123456789",
    "progress_message_id": "63",
    "dispatch_key": "123456789-63-pkg",
    "send_telegram": "false"
  }
}
```

The bot should read `.package_manifests/<dispatch_key>.enc`, decrypt it with `PACKAGE_MANIFEST_KEY`, build the Package Browser UI, then delete the encrypted manifest after successful read.

### Package repack request

```json
{
  "ref": "main",
  "inputs": {
    "source_url": "https://example.com/archive.zip",
    "keep_indexes": "1,2,5-7",
    "delete_indexes": "",
    "rename_map_json": "{\"folder/old.pdf\":\"folder/new.pdf\"}",
    "output_filename": "package_output.zip",
    "split_part_mib": "1900",
    "progress_chat_id": "123456789",
    "progress_message_id": "64",
    "dispatch_key": "123456789-64-repack",
    "send_telegram": "true"
  }
}
```

### Package Inspector / Repacker browser ordering

After `package-inspect.yml` returns the encrypted manifest, the bot displays Package Browser. For long Package Browser lists, keep rename ordering in bot-side state:

1. When a selected file is renamed, add its original manifest path to a rename-priority list.
2. If the same file is renamed again, move it to the newest position.
3. Sort the current folder with the newest renamed file first, then older renamed files, then unchanged files.
4. When a file rename is reset, remove that original path from the priority list.

This Package Browser UI priority does not need to be sent to GitHub. `package-repack.yml` only needs selected indexes and the final `rename_map_json`.

### Joining split torrent parts on Windows

Large torrent documents may arrive as ordered raw binary parts such as:

```text
video.mp4.part001
video.mp4.part002
```

These files are not ZIP/RAR archives. Put all parts in the same folder and join them from Command Prompt:

```cmd
copy /b "video.mp4.part001"+"video.mp4.part002" "video.mp4"
```

For many parts, include every part in order:

```cmd
copy /b "video.mp4.part001"+"video.mp4.part002"+"video.mp4.part003" "video.mp4"
```

#### Optional Windows helper

Windows users can also install the optional AMD4x Merge context-menu helper:

```text
tools/windows/amd4x-merge/install.reg
```

After installing it, put all split parts in the same folder, right-click the first part only, such as `.part001` or `.001`, then choose:

```text
[</> AMD4x Merge </>]
```

To remove the helper later, run:

```text
tools/windows/amd4x-merge/uninstall.reg
```

AMD4x Merge is a local Windows restore helper only. It does not change workflow execution, Telegram upload behavior, secrets, or workflow inputs.

### Joining split torrent parts on Linux or macOS

If all parts are in the same folder and use the `.part001`, `.part002` pattern:

```bash
cat *.part??? > video.mp4
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
video-compress.yml
torrent-document-local-api.yml
package-inspect.yml
package-repack.yml
```

## `dispatch_key`

Use a unique key per task. Recommended format:

```text
<chat_id>-<message_id>-<random_suffix>
```

Most workflows include the key in `run-name`, which helps the bot match a run to a user task.

`torrent-document-local-api.yml` intentionally does not expose `dispatch_key` in `run-name`. Bot integrations should match torrent runs by workflow file, dispatch time, branch, event type, and recent run ordering, while keeping `dispatch_key` private.

Package workflows use `dispatch_key` for bot correlation and encrypted manifest naming. Keep it unique per Package Inspector task so `.package_manifests/<dispatch_key>.enc` does not collide with another active request.

## Finding the matching run

After dispatching, GitHub's dispatch endpoint does not directly return the run ID. The bot should:

1. record the dispatch time,
2. list recent workflow runs for that workflow,
3. match by branch, event type, created time, and `dispatch_key` in the run name when available,
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

Use `send_as=document` with `remote-media.yml` for document delivery and with `video-compress.yml` for compressed MP4 document delivery.

Use `send_as=zip` only with `video-compress.yml` or the ZIP path in `remote-media.yml` document mode.

Dedicated YouTube, TikTok, and Facebook video workflows ignore `send_as`; sending `document` to them will not turn the result into a document.

## Choosing `document_mode`

Use only with `remote-media.yml`.

| Mode | User-facing behavior |
|---|---|
| `original` | Send the downloaded file directly as a document. |
| `zip` | Put the file inside a ZIP, then send it. If too large, the ZIP may be sent in split parts. |

## Bot-side validation recommendations

Reject or sanitize before dispatch:

- empty URL,
- non-HTTP/HTTPS schemes, except `magnet:` for the admin-only torrent path,
- extremely long input,
- known malicious or unsupported domains,
- local/private network URLs if the bot accepts arbitrary links,
- suspicious output filenames,
- attempts to place secrets in filenames or URLs,
- torrent requests from non-admin users,
- package inspect/repack requests from non-admin users,
- package rename paths that escape the ZIP root or use suspicious relative paths.

For torrent split deliveries, the bot should tell the user that `.part001`, `.part002`, etc. are raw binary chunks and must be joined in order, not extracted as archives.

## Bot-side reliability recommendations

- Do not block the bot event loop while polling.
- Poll at a reasonable interval.
- Persist task state so restarts do not lose active runs.
- Handle GitHub API rate limits.
- Provide a timeout to the user.
- Keep a fallback message for workflow failure.
- Avoid echoing raw GitHub logs to users.
- Never expose repository secrets, cookies, private URLs, or full workflow logs.
