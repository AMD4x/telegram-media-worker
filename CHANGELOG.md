# Changelog

All notable changes to this repository can be documented in this file.

The format loosely follows "Keep a Changelog" style, with simple sections for Added, Changed, Fixed, and Security.


## [v1.4.0] — 2026-05-03

### Added

- Documented Package Inspector / Repacker as the main v1.4.0 feature set: inspect a package-like source, return an encrypted manifest to the bot, browse items, select files, rename files or folders, and repack the final selection into a Telegram ZIP document.
- Added Package Inspector / Repacker references to the README, bot usage guide, workflow reference, architecture notes, supported-platforms guide, troubleshooting guide, scripts guide, and secrets documentation.
- Added package workflow dispatch examples under `examples/package-inspect.json` and `examples/package-repack.json`.
- Documented Package Browser ordering as part of the Package Inspector / Repacker bot UI: the most recently renamed item stays at the top of the current list, older renamed items follow, and unchanged items remain below.

### Security

- Documented `PACKAGE_MANIFEST_KEY` as the shared secret used for encrypted Package Inspector manifests.
- Clarified that Package Inspector manifests are temporary encrypted `.enc` files under `.package_manifests/` and should be deleted by the bot after successful read/decrypt.
- Documented that source URLs, manifest contents, selected indexes, file names, and `rename_map_json` should not be printed into public GitHub Actions logs.

### Notes

- This release documents the Package Inspector / Repacker workflow family and the bot-side Package Browser behavior around it.
- No workflow runtime behavior was changed in this documentation package.
- Rename ordering is bot-side UI state only; `package-repack.yml` still receives only selected indexes and the final `rename_map_json`.

## [v1.0.0] — 2026-05-01

### Added

- Four working workflow families: `remote-media.yml`, `youtube-video-local-api.yml`, `tiktok-direct-local-api.yml`, and `facebook-long-video-local-api.yml`.
- Automated Docker image build with daily version checks for yt-dlp and Deno.
- Public README documentation.
- Security policy.
- Secrets reference guide.
- Supported platforms guide.
- Troubleshooting guide.
- Bot integration notes.
- Example workflow input payloads.
- Issue and pull request templates.

### Security

- Added guidance for handling Telegram tokens, Telegram API credentials, cookies, private URLs, and sanitized logs.

## [Unreleased]

### Added

- Added AMD4x Merge as an optional Windows Explorer helper for joining downloaded split parts.
- Added `video-compress.yml` for remote video compression with `video`, `document`, and `zip` Telegram output modes.
- Added `scripts/video_compress/video_compress_worker.py` as an isolated worker for compression, naming, progress updates, and Telegram delivery.
- Added `docs/video-compress.md` with manual and bot-side usage examples.
- Added AMD4x Merge documentation under `tools/windows/amd4x-merge/`.
- Documented AMD4x Merge in the main README, bot usage guide, workflow reference, supported-platforms guide, and troubleshooting guide.

### Notes

- `video-compress.yml` uses `compression_level` as compression strength, not quality.
- AMD4x Merge is a user-side Windows restore helper only.
- No GitHub Actions workflow behavior, Telegram upload behavior, secrets, runtime logic, or workflow inputs were changed.
