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
| Magnet / `.torrent` | No | `torrent-document-local-api.yml` | Not needed | No | Yes | Admin-oriented torrent document workflow. Supports listing, selected indexes, all files, Public Bot API for small documents, Local Bot API for large documents, and split raw binary parts. |
| Archive / package source | No | `package-inspect.yml` + `package-repack.yml` | Not needed | No | ZIP output | Inspect archives, direct files, torrents, magnets, directory listings, or URL lists, then repack selected items. |
| Generic media URL | Yes | No | No | Possible | Possible | Falls through to generic extraction/direct-download behavior. |
| Compressible video URL | Through `video-compress.yml` | `video-compress.yml` | YouTube/Facebook cookies where applicable | Yes | Yes, including ZIP | Uses `yt-dlp` first, direct download fallback, then MP4/H.264/AAC compression. |

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

## Video compression workflow

`video-compress.yml` can be used for any source URL that `yt-dlp` or direct download can resolve into a readable video stream. It detects common platforms such as YouTube, Facebook, Instagram, TikTok, X/Twitter, and Reddit for progress summaries and default file names.

Output modes:

| Mode | Telegram output | Extension |
|:---:|:---:|:---:|
| `video` | streamable video | `.mp4` |
| `document` | document | `.mp4` |
| `zip` | document | `.zip` |

Compression strength is controlled by `compression_level` from `1` to `100`; higher values produce stronger compression and smaller files.

## Cookies

| Secret | Used by | Format | Purpose |
|---|---|---|---|
| `YOUTUBE_COOKIES_TXT` | `remote-media.yml`, `youtube-video-local-api.yml`, `video-compress.yml` | Netscape HTTP Cookie File | Restricted, age-gated, region-gated, or account-sensitive YouTube content. |
| `FACEBOOK_COOKIES_TXT` | `remote-media.yml`, `facebook-long-video-local-api.yml`, `video-compress.yml` | Netscape HTTP Cookie File | Account-sensitive or restricted Facebook content. |

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


## Package Inspector / Repacker

Package workflows are intended for archive-like or multi-item sources that should be inspected before final Telegram delivery.

Supported source categories include:

- ZIP/RAR/7z-style archives when supported by the worker tools,
- direct single files,
- magnet links,
- direct `.torrent` URLs,
- directory listings,
- URL lists.

Recommended bot flow:

1. Run `package-inspect.yml` with `source_url`.
2. Read and decrypt `.package_manifests/<dispatch_key>.enc` on the bot side.
3. Show the Package Browser to the admin.
4. Let the admin select files, rename selected files, rename the current folder, or change the output ZIP name.
5. Keep the most recently renamed file or folder-derived item at the top of the current Package Browser list while reviewing long package manifests.
6. Run `package-repack.yml` with selected indexes and optional `rename_map_json`.

This ordering behavior belongs to the Package Inspector / Repacker bot UI. It improves long-list navigation but does not change the manifest schema or workflow inputs.

## Torrent links

Torrent links are handled by `torrent-document-local-api.yml`.

Supported inputs:

- magnet links,
- direct `.torrent` URLs.

Recommended flow:

1. Run `file_mode=list` to inspect torrent contents.
2. Run `file_mode=selected` with explicit indexes such as `1`, `1,2`, or `3-5`.
3. Use `file_mode=all` only when every torrent file is intended.

The workflow sends selected files as Telegram documents. Small documents can be sent through Telegram Public Bot API, while larger documents use Telegram Local Bot API. Oversized files can be split into ordered raw binary parts.

Split parts are named like:

```text
filename.ext.part001
filename.ext.part002
```

They are not ZIP/RAR archives. Download all parts and join them in order to restore the original file. On Windows, use `copy /b` or the optional AMD4x Merge helper in `tools/windows/amd4x-merge/`; on Linux/macOS, use `cat *.part??? > output.ext`.

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
