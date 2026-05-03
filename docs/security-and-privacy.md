# Security and Privacy

This repository processes user-supplied media URLs and Telegram credentials through GitHub Actions. Treat workflow inputs and logs carefully.

## Never commit secrets

Do not commit:

- `TELEGRAM_TOKEN`,
- `TELEGRAM_CHAT_ID`,
- `TELEGRAM_API_ID`,
- `TELEGRAM_API_HASH`,
- cookies,
- private media URLs,
- signed URLs,
- personal download links,
- package manifest encryption keys.

Use GitHub Actions repository secrets only.

## Sensitive runtime data

The workflows can receive or generate sensitive data:

- source media URL,
- normalized URL,
- video ID,
- requested output filename,
- Telegram bot token,
- destination chat ID,
- progress chat ID,
- progress message ID,
- Telegram API ID/hash,
- cookie files,
- downloaded filenames,
- file paths,
- file sizes,
- API responses,
- Package Inspector manifests,
- package rename maps,
- selected package indexes.

The workflows mask many of these values, but masking is best-effort and does not make raw logs safe to publish.

## Cookies

Cookies should be stored only in repository secrets:

- `YOUTUBE_COOKIES_TXT`
- `FACEBOOK_COOKIES_TXT`

Use Netscape HTTP Cookie File format.

Cookie risks:

- cookies may provide access to private or account-sensitive media,
- cookies expire,
- cookies can be revoked by the platform,
- leaked cookies should be considered compromised.

Rotate cookies if they are exposed.

## Log safety

Do not share raw logs publicly. Before sharing logs:

- remove URLs,
- remove tokens,
- remove cookies,
- remove chat IDs,
- remove message IDs,
- remove filenames if they expose private content,
- remove Telegram API responses that may include private metadata.

The generic workflow contains log sanitization helpers, but external tools may print new patterns that are not covered.

Package Inspector stores bot-readable manifests as encrypted `.enc` files under `.package_manifests/`. The bot should decrypt the manifest locally, avoid printing file names from the manifest into public logs, and delete the `.enc` file after successful read.

## Public issue policy

Safe to include:

- workflow name,
- platform name,
- requested quality,
- send mode,
- document mode,
- sanitized error message,
- whether cookies were enabled,
- approximate file size category, e.g. small/large, not exact private filenames.

Do not include:

- private URLs,
- signed download URLs,
- real cookies,
- bot tokens,
- chat IDs,
- screenshots containing secrets,
- complete raw logs.

## Telegram bot permissions

Use the minimum bot permissions needed.

Recommended:

- use a dedicated bot for media-worker tasks,
- avoid using an admin bot unless required,
- restrict the bot's destination chats/channels,
- rotate token if exposed.

## Local Bot API

Local Bot API requires:

- `TELEGRAM_API_ID`,
- `TELEGRAM_API_HASH`.

These values must remain private. They are masked in logs when present.

## Direct file downloads

Direct file URLs can be sensitive, especially signed URLs. Treat them as private.

The generic workflow tries to reject HTML pages in document mode, but it still downloads user-provided URLs. A bot using this repository should reject unsafe URL schemes and private-network URLs before dispatching.

## Suggested bot-side URL restrictions

Reject:

- non-HTTP/HTTPS URLs,
- localhost URLs,
- private IP ranges,
- link-local IP ranges,
- internal hostnames,
- extremely long URLs,
- suspicious filenames,
- URLs that include secrets in query parameters when public logging cannot be avoided.

## Incident response

If a secret leaks:

1. Revoke or rotate the secret immediately.
2. Delete public logs/screenshots containing it.
3. Re-run affected workflows only after rotation.
4. Check bot activity if `TELEGRAM_TOKEN` leaked.
5. Refresh cookies if cookie data leaked.
