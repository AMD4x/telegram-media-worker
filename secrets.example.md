# Secrets Example

Create these values in:

`Repository Settings → Secrets and variables → Actions → Repository secrets`

Do not commit real secrets to the repository.

## Required for most workflows

```text
TELEGRAM_TOKEN=123456789:REPLACE_WITH_YOUR_BOT_TOKEN
TELEGRAM_CHAT_ID=123456789
```

## Required for Local Bot API workflows

```text
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=replace_with_your_api_hash
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
- Some platforms may work without cookies, but cookies can be required for restricted, age-gated, region-gated, or account-sensitive media.
