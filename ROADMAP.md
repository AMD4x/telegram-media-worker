# Roadmap

This roadmap lists possible future improvements. It does not imply that the current workflows need to be changed immediately.

## v0.1 — Documentation and public usage

- ✅ Add README.
- ✅ Add security notes.
- ✅ Add secrets guide.
- ✅ Add troubleshooting guide.
- ✅ Add examples for common workflow inputs.

## v0.2 — Better user-facing packaging

- ✅ Add clear repository description and topics.
- Add GitHub releases.
- Add changelog discipline.
- Add issue and pull request templates.

## v0.3 — Safer workflow interface

- Add optional `payload_json` input while preserving existing inputs.
- Add stricter input validation.
- Add private/sanitized logging mode.
- Add consistent output summaries across workflows.

## v0.4 — Additional output modes

- Add artifact-only output mode.
- Add optional S3/R2-compatible upload mode.
- Add result manifest JSON.
- Add output checksum metadata.

## v0.5 — Code organization

- Move large inline Bash blocks into versioned worker scripts.
- Add shared libraries for progress, Telegram sending, ffmpeg, yt-dlp, and input sanitation.
- Keep existing workflow names stable for backward compatibility.

## v1.0 — Stable public worker

- Freeze a public input contract.
- Publish tagged releases.
- Provide reusable GitHub Action usage.
- Provide documented bot integration examples.
