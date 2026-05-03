# Scripts

This directory contains helper scripts used by GitHub Actions workflows.

## Current script groups

| Directory | Purpose |
|:---:|---|
| `video_compress` | Scripts for the Video Compress workflow. |
| `package_tools` | Scripts for Package Inspector / Repacker manifest building, encrypted manifest handoff, source staging, selected-item ZIP creation, split sending, and Telegram delivery. |

## Notes

- Scripts in this directory are intended to run inside GitHub Actions.
- They are not required on the Raspberry Pi bot runtime.
- Keep workflow-specific scripts inside their own subdirectories.
