# Cookies Guide

Some media platforms require cookies for restricted, age-gated, region-gated, account-only, or anti-bot protected media.

## Supported secret names

```text
YOUTUBE_COOKIES_TXT
FACEBOOK_COOKIES_TXT
```

## Format

Use Netscape HTTP Cookie File format.

The first line usually looks like:

```text
# Netscape HTTP Cookie File
```

## Storage

Store cookies only as GitHub Actions repository secrets.

Do not store cookies in:

- Workflow files.
- README examples.
- Issues.
- Discussions.
- Screenshots.
- Public logs.

## Renewal

Cookies expire. If a workflow suddenly starts failing for a platform that previously worked, refresh the relevant cookie secret.

## Safety

Cookies can grant account access. Treat them like passwords.

If cookies are exposed publicly, remove them and log out of the related browser sessions where possible.
