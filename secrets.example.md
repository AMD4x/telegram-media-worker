# Secrets Example

Create these values in:

`Repository Settings → Secrets and variables → Actions → Repository secrets`

Do not commit real secrets to the repository.

## Required for most workflows

```text
TELEGRAM_TOKEN=123456789:REPLACE_WITH_YOUR_BOT_TOKEN
TELEGRAM_CHAT_ID=123456789
ADMIN_ID=123456789
```

## Required for Local Bot API workflows

```text
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=replace_with_your_api_hash
```

## Required for Package Inspector / Repacker bot integration

```text
PACKAGE_MANIFEST_KEY=replace_with_long_random_manifest_key
```

## Optional platform cookies

Use Netscape HTTP Cookie File format.

```text
YOUTUBE_COOKIES_TXT=# Netscape HTTP Cookie File
FACEBOOK_COOKIES_TXT=# Netscape HTTP Cookie File
```

## Notes

- Keep cookies in repository secrets only.
- Do not put cookies inside workflow inputs.
- Do not paste real cookies into issues or screenshots.
- Rotate tokens and cookies if they ever appear in logs.
- `ADMIN_ID` is a fallback destination used by workflows such as `video-compress.yml` when `chat_id` and `TELEGRAM_CHAT_ID` are empty.
- `PACKAGE_MANIFEST_KEY` must match the bot-side value used to decrypt Package Inspector manifests stored as `.package_manifests/<dispatch_key>.enc`.
- Some platforms may work without cookies, but cookies can be required for restricted, age-gated, region-gated, or account-sensitive media.
