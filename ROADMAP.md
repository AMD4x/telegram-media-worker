# Roadmap

## Current state

The project is functionally complete. All six workflow families are working.
The Docker image rebuilds automatically when yt-dlp or Deno release updates.

## Known limitations

- progress_bar(), update_progress(), and update_completed() are duplicated
  inline across the three dedicated platform workflows. This is intentional
  for now to keep each workflow fully self-contained.

- Instagram, X/Twitter, and Reddit fall through to the generic remote-media
  path, or to video-compress.yml when compression is requested. Cookie
  support for these platforms is not wired in.

- The TikTok workflow includes a tikwm.com fallback path. This is a
  third-party service and may stop working without notice.

- Dedicated platform workflows do not support document_mode. The
  generic remote-media workflow handles document and ZIP output, while
  video-compress.yml has its own video/document/zip output modes.

- AMD4x Merge is an optional user-side Windows restore helper only. It
  does not change workflow behavior, upload limits, secrets, or inputs.

- All workflows are trigger-only via workflow_dispatch. There is no
  workflow_call interface for composability.

## Possible future additions

These are not scheduled. They are here only to record known gaps.

- Add INSTAGRAM_COOKIES_TXT and X_COOKIES_TXT handling to remote-media.yml.
- Add workflow_call support to allow one workflow to call another.
- Replace or remove tikwm fallback if it becomes unreliable.
- Consider a shared script file for the progress helpers if duplication
  becomes a maintenance problem.
