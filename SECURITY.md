# Security Policy

This project may handle sensitive values through GitHub Actions secrets, including Telegram bot tokens, Telegram API credentials, site cookies, chat IDs, and private media URLs.

## Sensitive data

Do not place any of the following in public files, issues, comments, screenshots, discussions, examples, or workflow logs:

- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `YOUTUBE_COOKIES_TXT`
- `FACEBOOK_COOKIES_TXT`
- Private media URLs
- Telegram message links from private chats
- Full raw workflow logs that may contain source URLs or filenames

## Recommended handling

- Store credentials only in GitHub repository secrets.
- Use Netscape-format cookie files only through secrets.
- Rotate cookies and tokens periodically.
- Prefer sanitized logs when reporting bugs.
- Mask private URLs before opening issues.
- Avoid sharing workflow run logs publicly when they include private inputs.

## If a secret is exposed

1. Revoke or rotate the exposed token/cookie immediately.
2. Delete or redact the public log, issue, comment, or screenshot if possible.
3. Re-run the workflow with clean secrets.
4. Review repository Actions logs for additional exposure.

## Reporting security issues

Please do not open a public issue for a token, cookie, credential, or private-link exposure. Report privately to the repository owner.
