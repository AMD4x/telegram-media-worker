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
```

or:

```text
archive.zip.001
archive.zip.002
archive.zip.003
```

These files are raw split parts. They are not ZIP/RAR archives by themselves.

## Install

1. Run `uninstall.reg` first if an older version was installed.
2. Run `install.reg`.
3. Approve the Windows Registry prompt.
4. Put all split parts in the same folder.
5. Right-click the first part only.
6. Choose `[</> AMD4x Merge </>]`.

## Uninstall

Run:

```text
uninstall.reg
```

## Supported patterns

AMD4x Merge is intended for ordered split parts that use predictable numeric suffixes, especially:

```text
.part001
.001
.chunk001
.split001
.seg001
.segment001
```

For best results, keep all parts in the same folder and use the first part only.

## Notes

- Uses `cmd.exe` and `copy /b`.
- Does not require PowerShell.
- Does not require external programs.
- Does not create log files.
- Installs under `HKCU`, so it applies to the current Windows user.
- This is a user-side restore helper only.
- It does not change GitHub Actions workflows.
- It does not change Telegram upload behavior.
- It does not add new secrets or workflow inputs.

## Safety

Only use this helper on split parts from a source you trust. The helper joins files locally on your Windows machine and does not upload anything.

## Related documentation

- `docs/usage-from-bot.md`
- `docs/workflows.md`
- `docs/supported-platforms.md`
- `docs/troubleshooting.md`.
