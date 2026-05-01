# Changelog

All notable changes to this repository can be documented in this file.

The format loosely follows "Keep a Changelog" style, with simple sections for Added, Changed, Fixed, and Security.

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
- Added AMD4x Merge documentation under `tools/windows/amd4x-merge/`.
- Documented AMD4x Merge in the main README, bot usage guide, workflow reference, supported-platforms guide, and troubleshooting guide.

### Notes

- AMD4x Merge is a user-side Windows restore helper only.
- No GitHub Actions workflow behavior, Telegram upload behavior, secrets, runtime logic, or workflow inputs were changed.
