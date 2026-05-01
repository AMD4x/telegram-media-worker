# Supported Platforms

Platform support depends on the workflow, the selected quality, the source URL, and the current behavior of the source website.

## General support matrix

| Platform | Generic remote media | Dedicated Local Bot API workflow | Cookies may help | Notes |
|---|---:|---:|---:|---|
| YouTube | Yes | Yes | Yes | Some videos may require cookies or specific clients. |
| TikTok | Yes | Yes | Usually no | Direct mode may avoid unnecessary re-encoding when a compatible file is available. |
| Facebook | Yes | Yes | Yes | Cookies are often useful for parsing and restricted content. |
| Instagram | Partial | No dedicated workflow listed | Often yes | Extraction behavior can change frequently. |
| X / Twitter | Partial | No dedicated workflow listed | Sometimes | Depends on media and access restrictions. |
| Reddit | Partial | No dedicated workflow listed | Sometimes | Depends on the media source. |
| Direct file URL | Yes, especially document mode | Not platform-specific | No | Works best when the URL points directly to a downloadable file. |

## Quality selection

Common values:

```text
auto
2160
1440
1080
720
480
360
```

Actual quality depends on the formats exposed by the source platform and the format selector inside the selected workflow.

## Telegram compatibility

For video messages, Telegram/iPhone compatibility usually benefits from:

- MP4 container.
- H.264 video.
- AAC audio.
- `+faststart` metadata layout.
- Reasonable dimensions and bitrate.

Dedicated Local Bot API workflows may prepare or transcode media to improve compatibility.
