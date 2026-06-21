# Security Policy

This project may handle sensitive values through GitHub Actions secrets, workflow dispatch inputs, and runtime-generated files. Sensitive values include Telegram bot tokens, Telegram API credentials, site cookies, chat IDs, private media URLs, requested filenames, and package metadata.

## Sensitive data

Do not place any of the following in public files, issues, comments, screenshots, discussions, examples, or workflow logs:

- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `YOUTUBE_COOKIES_TXT`
- `FACEBOOK_COOKIES_TXT`
- Private media URLs
- Requested `output_filename` values
- Opaque `dispatch_key` values when they can identify a user task
- `progress_chat_id`, `progress_message_id`, and `reply_to_message_id`
- `rename_map_json`, selected package indexes, package item names, and private filenames
- Telegram message links from private chats
- Full raw workflow logs that may contain source URLs, filenames, chat IDs, or package details

## Recommended handling

- Store credentials only in GitHub repository secrets.
- Use Netscape-format cookie files only through secrets.
- Rotate cookies and tokens periodically.
- Prefer sanitized logs when reporting bugs.
- Mask private URLs before opening issues.
- Avoid sharing workflow run logs publicly when they include private inputs.
- Keep `dispatch_key` opaque. Do not embed chat IDs, message IDs, URLs, filenames, usernames, or request details in it.
- Do not pass sensitive workflow inputs through Actions `env:` blocks, `run-name`, job outputs, public examples, or debug logs.
- Workflows should load sensitive dispatch inputs after the job starts from the GitHub event payload and mask them before use.

## If a secret is exposed

1. Revoke or rotate the exposed token/cookie immediately.
2. Delete or redact the public log, issue, comment, or screenshot if possible.
3. Re-run the workflow with clean secrets.
4. Review repository Actions logs for additional exposure.

## Reporting security issues

Please do not open a public issue for a token, cookie, credential, or private-link exposure. Report privately to the repository owner.
