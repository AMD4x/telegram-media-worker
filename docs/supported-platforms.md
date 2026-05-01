# Supported Platforms

Platform support depends on the selected workflow, source URL, available cookies, requested output mode, `yt-dlp` behavior, and current platform restrictions.

## Support matrix

| Platform / URL type | Generic `remote-media.yml` | Dedicated workflow | Cookies supported by repo | Video output | Document output | Notes |
|---|:---:|:---:|:---:|:---:|:---:|---|
| YouTube | Yes | `youtube-video-local-api.yml` | `YOUTUBE_COOKIES_TXT` | Yes | Generic only | Generic workflow normalizes YouTube URLs. Dedicated workflow prepares Telegram/iPhone-safe video. |
| YouTube Shorts | Yes | `youtube-video-local-api.yml` | `YOUTUBE_COOKIES_TXT` | Yes | Generic only | Generic workflow can normalize Shorts URLs to a watch URL. |
| YouTube Music | Not explicitly detected in generic YouTube test | `youtube-video-local-api.yml` accepts it | `YOUTUBE_COOKIES_TXT` | Dedicated only | Generic may still try through generic path | Dedicated workflow validates `music.youtube.com`. |
| TikTok | Yes | `tiktok-direct-local-api.yml` | No dedicated cookie secret | Yes | Generic only | Dedicated workflow uses `tikwm.com` first, then `yt-dlp` fallbacks. |
| Facebook | Yes | `facebook-long-video-local-api.yml` | `FACEBOOK_COOKIES_TXT` | Yes | Generic only | Cookies are often needed for account-sensitive content. |
| Instagram | Partial | No | No dedicated cookie secret | Generic only | Generic only | Extractability depends heavily on access restrictions and platform changes. |
| X / Twitter | Partial | No | No dedicated cookie secret | Generic only | Generic only | Generic workflow sets X referer but has no X cookies secret. |
| Reddit | Partial | No | No dedicated cookie secret | Generic only | Generic only | Depends on embedded media availability and `yt-dlp` support. |
| Direct downloadable file | Yes | No | Not needed | Possible if media | Yes | Best route for document mode. |
| Magnet / `.torrent` | No | `torrent-document-local-api.yml` | Not needed | No | Yes | Admin-oriented torrent document workflow. Supports listing, selected indexes, all files, and split document parts. |
| Generic media URL | Yes | No | No | Possible | Possible | Falls through to generic extraction/direct-download behavior. |

## Quality values

The generic workflow exposes these `max_height` choices:

```text
auto
2160
1440
1080
720
480
360
```

The dedicated YouTube and TikTok workflows accept `max_height` as a string. Invalid values are normalized to `auto`.

`auto` means:

- `remote-media.yml`: internally starts from 2160 and builds candidates down to 360.
- `youtube-video-local-api.yml`: target height becomes 2160.
- `tiktok-direct-local-api.yml`: uses best available compatible selectors.
- `facebook-long-video-local-api.yml`: input exists but is ignored.

Actual quality depends on what the source platform exposes.

## Telegram/iPhone video compatibility

A Telegram/iPhone-friendly video generally benefits from:

- MP4 container,
- H.264 video,
- AAC audio,
- `yuv420p` pixel format,
- `+faststart`,
- sane sample aspect ratio,
- reasonable dimensions and H.264 level.

### Generic workflow

Normalizes media with `ffmpeg` to H.264/AAC MP4 with `yuv420p`, `setsar=1`, capped dimensions, and `+faststart`.

### YouTube and Facebook workflows

Use a two-path approach:

1. Fast remux if the file already satisfies compatibility checks.
2. Safe transcode when it does not.

### TikTok workflow

Requires a final file with both video and audio streams, H.264 video, and AAC audio. It may transcode fallback candidates when needed.

## Cookies

| Secret | Used by | Format | Purpose |
|---|---|---|---|
| `YOUTUBE_COOKIES_TXT` | `remote-media.yml`, `youtube-video-local-api.yml` | Netscape HTTP Cookie File | Restricted, age-gated, region-gated, or account-sensitive YouTube content. |
| `FACEBOOK_COOKIES_TXT` | `remote-media.yml`, `facebook-long-video-local-api.yml` | Netscape HTTP Cookie File | Account-sensitive or restricted Facebook content. |

No dedicated repository secret currently exists for TikTok, Instagram, X/Twitter, or Reddit cookies.

## Direct file URLs

Direct file URLs are best handled by `remote-media.yml` with `send_as=document`.

The generic workflow can:

- perform a `HEAD` probe,
- infer filenames from URL path or response headers,
- download with browser-like headers,
- reject HTML pages,
- send the original file,
- wrap it in a ZIP,
- split very large ZIP output into parts.


## Torrent links

Torrent links are handled by `torrent-document-local-api.yml`.

Supported inputs:

- magnet links,
- direct `.torrent` URLs.

Recommended flow:

1. Run `file_mode=list` to inspect torrent contents.
2. Run `file_mode=selected` with explicit indexes such as `1`, `1,2`, or `3-5`.
3. Use `file_mode=all` only when every torrent file is intended.

The workflow sends selected files as Telegram documents through Telegram Local Bot API and can split oversized files into ordered parts.

## Reliability expectations

Platform support can change without repository changes because the workflows depend on:

- source website behavior,
- access restrictions,
- cookies validity,
- `yt-dlp` extractor support,
- third-party TikTok resolver behavior,
- Telegram Bot API limits and responses.

When a platform fails, first check:

1. whether the URL is publicly accessible,
2. whether cookies are needed or expired,
3. whether `yt-dlp` changed behavior,
4. whether Telegram rejected the final output or file size.
