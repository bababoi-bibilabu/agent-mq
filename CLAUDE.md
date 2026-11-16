# CLAUDE.md

> Status: **being rewritten**. The old implementation (v0.2.0) will be deleted entirely and rebuilt from scratch. This file lands before the new code and is the source of constraints for the rewrite.
> Once the new layout is settled, fill in "Repository layout" and "Common commands", and remove items from "Open decisions" as they get decided.

## What this project is

agent-mq: a message queue for AI coding assistants (Claude Code, Cursor, etc.), letting agents in different sessions or on different machines send each other messages and tasks.

Core model:
- A **token** is a namespace. Agents under the same token can see each other; different tokens are fully isolated.
- Agents are addressed by **name**; messages are delivered to the target agent's inbox.
- Receivers **poll** for messages; reading consumes them. There is no push.
- **No MCP.** The only interface is an HTTP API; agents call it directly with `curl` or any HTTP client.
- One auth mechanism only: a server-issued **API key**, sent as `Authorization: Bearer <api_key>`. No OAuth, sessions, or cookies.

## External contracts to keep

These are published and depended on by external users or config. Don't change them casually; any change needs the user's approval and a migration plan:

| Contract | Current value |
|---|---|
| Website / doc URLs | `https://agent-mq.com`, `/usage.md`, `/install.md`, `/llms.txt` (linked from README and from users' prompts) |
| Hosted API | Fly.io app `agent-mq-api`, `Authorization: Bearer <token>` |
| CI secret names | `FLY_API_TOKEN`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` |

### Dropped (delete during the rewrite)

- The MCP server: `mcp/`, `.mcp.json`, root `Dockerfile`, `glama.json`, and the npm / Glama badges in README.
- The npm package `@agent-mq/mcp` gets no new releases (whether to mark it deprecated on npm is the user's call); the `NPM_TOKEN` CI secret is no longer used.
- The `mq_*` MCP tool names and the local config `~/.agent-mq/config.json` go away.

## Lessons from the old implementation (fix in the rewrite)

Old code: `server/app.py` (FastAPI + SQLite, single file), `mcp/src/*.ts` (MCP server + HTTP client, now dropped), `site/` (static site on Cloudflare Pages).

1. **Sender is spoofable**: `sender` in `mq_send` is whatever the caller says; the server doesn't check it.
2. **Token is the user ID, stored in plaintext**, and any string of 16+ chars is auto-registered as a new user. The new version issues API keys server-side and stores only hashes.
3. **Cross-tenant data leak**: `/api/v1/analytics/summary` returns global stats to any token.
4. **recv is not atomic**: select-then-delete, so concurrent recvs can double-deliver; type filtering happens in Python.
5. **No expiry or cleanup**: inbox, done, and analytics tables have no TTL or cap; `history`'s `limit` is unbounded.
6. **Version number duplicated in 6 places** (server, mcp package.json, index.ts, client.ts, plugin.json, SKILL.md), synced by hand.
7. **Polling only**: relies on agents setting up their own cron to call `mq_recv`; slow cold starts led to a timeout-and-retry patch in the client.
8. Stale error messages (telling users to run a nonexistent `mq login` command); agents can't be deleted once registered.
9. Two language stacks (Python server + TS client) each defined the message format separately with no shared schema. With MCP gone only the server remains, and its API spec (e.g. OpenAPI) is the single definition of the format.

## Working conventions

- Branches: commit and push to the branch assigned for the session. Without the user asking, don't open PRs, don't push to `main`, and don't push `v*` tags (a tag triggers a release: Fly deploy + Pages deploy).
- Write or update tests before changing the implementation; run the full test suite and make it pass before every commit.
- Define the message format and API request/response shapes once (single schema source); external docs are generated from it or kept consistent with it.
- Every endpoint must be callable with a single `curl` command, and the docs show a `curl` example for each — that's how agents learn to use the service.
- Keep the version number in one place; anything else is synced by script or build.
- Update all user-facing docs (README, `site/*.md`, SKILL.md) together with the implementation; leave no stale instructions.
- Never commit secrets, tokens, or database files under `server/data/`.
- Keep dependencies minimal; justify any new dependency before adding it.

## Open decisions (confirm with the user before the rewrite)

- [ ] Server language / framework: stay on Python + FastAPI, or switch?
- [ ] Storage: stay on SQLite (Fly volume), or something else?
- [ ] Keep `/api/v1` compatible, or ship `/api/v2` and keep v1 around for a while?
- [ ] How are API keys issued (open signup endpoint / generated on the website / issued manually by an admin)? Can a namespace have multiple keys, and can keys be revoked?
- [ ] Sender identity: one key per agent (sender determined by the key, unforgeable), or one key per namespace with the sender still self-reported?
- [ ] Keep the Claude Code plugin + `skills/mq/SKILL.md` (rewritten to teach agents to call the API with `curl`), or delete them too?
- [ ] Delivery semantics: add ack / visibility timeout / long polling / message TTL?
- [ ] Rebuild `site/` as well? Keep the same deploy target (Cloudflare Pages)?

## Repository layout

_TBD — fill in once the new layout is settled._

## Common commands

_TBD — fill in once the new layout is settled (install, build, test, run locally, release)._
