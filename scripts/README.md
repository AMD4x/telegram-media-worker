# Scripts

This directory contains helper scripts used by GitHub Actions workflows.

## Current script groups

| Directory | Purpose |
|:---:|---|
| `video_compress` | Scripts for the Video Compress workflow. |
| `audio_media` | Script for the Audio Media workflow, including audio extraction, video-to-audio conversion, metadata fallback, and Telegram delivery. |
| `package_tools` | Scripts for Package Inspector / Repacker manifest building, encrypted manifest handoff, source staging, selected-item ZIP creation, split sending, and Telegram delivery. |

## Notes

- Scripts in this directory are intended to run inside GitHub Actions.
- Keep workflow-specific scripts inside their own subdirectories.
