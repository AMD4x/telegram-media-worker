# AMD4x Merge

Windows Explorer context-menu helper for joining split files generated or delivered by Telegram Media Worker.

## What it does

AMD4x Merge adds a right-click menu item for first split parts such as:

- `.part001`
- `.001`
- `.chunk001`
- `.split001`
- `.seg001`
- `.segment001`

When used on the first part, it joins matching parts in the same folder using Windows `cmd.exe` and `copy /b`.

## When to use it

Use this helper when Telegram Media Worker sends a large file as ordered split parts, for example:

```text
video.mp4.part001
video.mp4.part002
video.mp4.part003
