# Telegram Secrets Guide

This repository uses Telegram-related secrets to send media after a GitHub Actions worker finishes processing.

## `TELEGRAM_TOKEN`

Telegram bot token created through BotFather.

Required by workflows that send progress updates or final media to Telegram.

## `TELEGRAM_CHAT_ID`

Destination chat ID used for the final media message.

This can be a private chat ID, group ID, or channel ID depending on your bot permissions.

## `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`

Telegram API credentials used by Telegram Local Bot API workflows.

These are required when a workflow starts `telegram-bot-api --local` and uploads through the local endpoint.

## Progress message inputs

Some workflows accept:

```text
progress_chat_id
progress_message_id
```

These are not repository secrets. They are runtime inputs used to edit a previously sent Telegram message with progress updates.

## Good practice

- Give the bot only the permissions it needs.
- Use a dedicated bot for media-worker tasks when possible.
- Avoid sharing workflow logs publicly.
- Rotate the bot token if it is exposed.
