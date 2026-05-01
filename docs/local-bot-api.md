# Telegram Local Bot API Notes

Some workflows start Telegram Bot API in local mode inside the GitHub Actions job container.

This is useful for large uploads and for direct interaction with a local endpoint during the workflow run.

## Required secrets

```text
TELEGRAM_TOKEN
TELEGRAM_CHAT_ID
TELEGRAM_API_ID
TELEGRAM_API_HASH
```

## Typical local endpoint

The workflow usually talks to a local endpoint similar to:

```text
http://127.0.0.1:8081/bot<TELEGRAM_TOKEN>/sendVideo
```

or another Telegram method supported by the workflow.

## Operational notes

- The Local Bot API process is temporary.
- It only lives for the duration of the GitHub Actions job.
- It should be stopped or cleaned up when the job exits.
- If it does not become ready, the workflow should fail clearly.

## Compatibility goals

Local Bot API workflows often prepare media for Telegram/iPhone compatibility by using:

- MP4 output.
- H.264 video.
- AAC audio.
- `+faststart`.
- Safe remux when possible.
- Transcode fallback when needed.
