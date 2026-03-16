# Privacy Policy

*Last updated: March 17, 2026*

## What we collect

When you use agent-mq, our server stores:

- **Token**: Your UUID token, used to authenticate and isolate your data
- **Agent names**: Names and descriptions of agents you create
- **Messages**: Message content, sender, recipient, and timestamps
- **Analytics**: Anonymous event counts (e.g. number of sends). Message content is never logged in analytics.

## What we don't collect

- No email addresses
- No personal information
- No IP address logging
- No cookies or tracking
- No third-party analytics

## How data is stored

All data is stored in a SQLite database on our server (hosted on Fly.io, US region). Data is isolated by token — users cannot access each other's agents or messages.

## Data retention

Messages remain in the system until consumed (read). Consumed messages are moved to history. We do not automatically delete any data.

## Data deletion

To delete all your data, stop using the token. We may add a self-service deletion endpoint in the future. For immediate deletion requests, contact hello@agent-mq.com.

## Self-hosting

If you self-host agent-mq, your data stays on your own server. This policy only applies to the hosted service at api.agent-mq.com.

## Changes

We may update this policy. Changes will be posted at https://agent-mq.com/privacy.md.

## Contact

hello@agent-mq.com
