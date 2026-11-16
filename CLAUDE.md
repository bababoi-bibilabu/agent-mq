# CLAUDE.md

> Status: **being rewritten from scratch**. The old implementation (v0.2.0) has been deleted from the tree; it is still in git history (last commit before deletion: `6dd150d`) if you need to look something up. This file is the source of constraints for the rewrite.
> Once the new layout is settled, fill in "Repository layout" and "Common commands", and remove items from "Open decisions" as they get decided.

## What this project is

agent-mq: a message queue for AI coding assistants (Claude Code, Cursor, etc.), letting agents in different sessions or on different machines send each other messages and tasks.

Core model:
- A **token** is a namespace. Agents under the same token can see each other; different tokens are fully isolated.
- Agents are addressed by **name**; messages are delivered to the target agent's inbox.
- Receivers **poll** for messages; reading consumes them. There is no push.
- **No MCP.** The only interface is an HTTP API; agents call it directly with `curl` or any HTTP client.
- One auth mechanism only: a server-issued **API key**, sent as `Authorization: Bearer <api_key>`. No OAuth, sessions, or cookies.
- **Agents get keys themselves, for free**: an unauthenticated signup endpoint mints a key; no human, email, or payment in the loop. Because anyone can mint keys, abuse limits are part of the core design (see "Abuse and DoS protection"), not an afterthought.
- Written in **Rust**.

## Tech stack

- Rust (stable), single binary, one Cargo crate until there's a real reason to split.
- Proposed: `tokio` + `axum` for HTTP, `tower` / `tower-http` layers for limits and timeouts, SQLite for storage. Confirm with the user before swapping any of these.
- API keys: 32+ random bytes from a CSPRNG, with a recognizable prefix (e.g. `amq_`). Store only the SHA-256 of the key. Keys are high-entropy, so a fast hash is correct here; a slow password hash (argon2/bcrypt) would turn every authenticated request into a CPU DoS vector.

## Abuse and DoS protection

Free self-service keys mean the per-key limits alone don't protect anything — an attacker just mints more keys. Defend in layers; every limit is a config value (env var) with the defaults below as starting points:

1. **Signup is the choke point.**
   - Rate-limit signup per client IP (IPv6 grouped by /64), e.g. 5 keys/hour/IP, plus a global cap on new keys per hour.
   - Behind Fly, take the client IP from `Fly-Client-IP`; never trust `X-Forwarded-For` or other client-supplied headers when not behind a known proxy.
   - Keep a switch to disable signup entirely without a redeploy.
   - **Proof-of-work is required for signup** (hashcash-style), on top of the IP limits. See "Signup proof-of-work" below.
2. **Per-key quotas** bound what one key can cost:
   - request rate (token bucket, e.g. 10 req/s, burst 20) and a daily message quota;
   - max agents per namespace, max pending messages per inbox, max message size (e.g. 10 KB);
   - message TTL for undelivered messages and capped history, so storage per key has a hard ceiling.
3. **Per-IP request rate limit** on all endpoints, so many keys from one IP don't multiply throughput.
4. **Bounded storage overall**: keys with no activity for N days (e.g. 30) are deleted along with their data. Total storage ≤ live keys × per-key ceiling, and live keys are bounded by the signup limits.
5. **Cheap rejection**: check auth and rate limits before reading the body or touching the database; enforce the body-size limit at the transport layer; request timeouts on everything; a global concurrency limit; if long polling is added, cap open connections per key and globally.
6. **Operator controls**: revoke a single key, and the signup kill switch above. No admin UI needed at first; a CLI subcommand or env/config is fine.

### Limits for key holders

PoW only makes keys cost something to get. Once someone has a key, these keep it from being used to hurt the service:

- **Limits grow with key age.** A fresh key is the cheapest thing an attacker can get, so it gets the lowest limits (e.g. half the normal request rate and daily quota for the first 24 h). Keys reach full limits after a set age with no violations. Mass-minted keys are therefore weak for exactly as long as they're new.
- **Penalty box.** A key that keeps hitting `429` after being told to back off (e.g. many rejected requests in a minute) is suspended for a while, and the suspension grows exponentially on repeat. While suspended, requests are rejected before any database work. Every `429` carries `Retry-After`, so well-behaved agents never get here.
- **Weight requests by cost.** Writes (send, create agent) draw more from the rate budget than reads. An empty poll is the most common request, so make it the cheapest: answer "nothing new" without a database query where possible (e.g. an in-memory per-inbox counter or version), and document the minimum sensible poll interval in `SKILL.md`.
- **Abuse stays inside the namespace.** A key can only reach agents in its own namespace, so a bad key can't spam other users; it can only spend server resources, which the limits above cap.
- **Per-key concurrency limit** on in-flight requests (and on open connections, if long polling is added).
- **Self-service key management.** A holder can rotate its key (new key, old one stops working) and delete it along with its data. If a key leaks, the owner fixes it without an operator.
- **Operator escalation.** Revoke a key; and since every key is tied to the IP that minted it, optionally tighten signup limits for that IP range.

### Signup proof-of-work

Flow:
1. `POST /signup/challenge` (no auth) → `{challenge, difficulty, expires_at}`. Rate-limited per IP like signup itself.
2. The client finds a `nonce` such that `SHA-256(challenge || ":" || nonce)` has at least `difficulty` leading zero bits.
3. `POST /signup` with `{challenge, nonce}` → `{api_key, ...}`.

Rules:
- Challenges are stateless: random bytes + expiry + difficulty, authenticated with an HMAC under a server secret (secret from env, never committed). The server doesn't store issued challenges.
- Each challenge is single-use: remember redeemed challenges until they expire, so one solution can't mint many keys.
- Short expiry (e.g. 5 minutes).
- Verification is a single hash, cheap enough that verifying bad submissions is never the bottleneck.
- Difficulty is configurable. Default target: about 1–2 s of single-core CPU in Python's `hashlib` (roughly 20–22 bits). It may later scale up automatically when the global signup rate is high; keep the code ready for that, but don't build it until needed.
- **`SKILL.md` spells out exactly what to compute**, so any agent can implement the solver itself in whatever it has at hand. Specify it unambiguously:
  - input bytes: the UTF-8 bytes of `challenge + ":" + nonce`, where `challenge` is the string exactly as returned and `nonce` is a non-negative integer written in decimal ASCII with no leading zeros;
  - hash: SHA-256 over those bytes;
  - success: at least `difficulty` leading zero bits, counted from the most significant bit of the first byte of the digest;
  - what to send back, and the error returned for a wrong, expired, or reused solution.
- `SKILL.md` also includes a worked test vector (challenge, difficulty, a valid nonce, its digest in hex) and a short reference solver using only the `python3` standard library. Server tests verify both against the real implementation, so the docs can't drift.
- A native solver (e.g. a tiny Rust CLI) is optional, later.

Tests must cover each limit: hitting it returns `429` (or `413` for size) with a clear JSON error, and it resets as specified.

## External contracts to keep

These are published and depended on by external users or config. Deleting the old code did not take them down (the site and API are still deployed). Don't change them casually; any change needs the user's approval and a migration plan:

| Contract | Current value |
|---|---|
| Website / doc URLs | `https://agent-mq.com`, `/usage.md`, `/install.md`, `/llms.txt` (linked from README and from users' prompts) |
| Hosted API | Fly.io app `agent-mq-api`, `Authorization: Bearer <token>` |
| CI secret names | `FLY_API_TOKEN`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` |

### Dropped

- The MCP server and everything around it (`mcp/`, `.mcp.json`, root `Dockerfile`, `glama.json`, npm / Glama badges) — already deleted; don't bring them back.
- The npm package `@agent-mq/mcp` gets no new releases (whether to mark it deprecated on npm is the user's call); the `NPM_TOKEN` CI secret is no longer used.
- The `mq_*` MCP tool names and the local config `~/.agent-mq/config.json` go away.

## Lessons from the old implementation (fix in the rewrite)

Old code (deleted; see git history at `6dd150d`): `server/app.py` (FastAPI + SQLite, single file), `mcp/src/*.ts` (MCP server + HTTP client), `site/` (static site on Cloudflare Pages), `.github/workflows/` (CI + tag-triggered release).

1. **Sender is spoofable**: `sender` in `mq_send` is whatever the caller says; the server doesn't check it.
2. **Token is the user ID, stored in plaintext**, and any string of 16+ chars is auto-registered as a new user. The new version issues API keys server-side, stores only hashes, and rate-limits issuance.
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
- Update all user-facing docs (README, `site/*.md`, `SKILL.md`) together with the implementation; leave no stale instructions. `SKILL.md` is the primary doc for agents: it must be complete enough to go from zero to sending a message with nothing else.
- Never commit secrets, tokens, or database files under `server/data/`.
- Keep dependencies minimal; justify any new dependency before adding it.

## Open decisions (confirm with the user before the rewrite)

- [x] Language: Rust.
- [x] API keys: self-service signup by agents, free.
- [ ] Rust stack: confirm `axum` + `tokio` + SQLite (see "Tech stack").
- [ ] Keep `/api/v1` compatible, or ship `/api/v2` and keep v1 around for a while?
- [ ] Key vs. namespace: does signup create one key per agent (sender identity comes from the key, unforgeable; agents then need a way to join a shared namespace, e.g. an invite code), or one key per namespace shared by all its agents (sender self-reported, as before)?
- [x] Signup requires proof-of-work.
- [ ] Default values for the limits in "Abuse and DoS protection", including the PoW difficulty, the new-key period, and the penalty-box thresholds.
- [x] Keep a `SKILL.md`, rewritten to teach agents the HTTP API with `curl`, including the exact PoW computation.
- [ ] Ship the skill via a Claude Code plugin again, or only as a file served from the website?
- [ ] Delivery semantics: add ack / visibility timeout / long polling / message TTL?
- [ ] Website: what goes into the new `site/`? Keep the same deploy target (Cloudflare Pages)?

## Repository layout

Currently only `CLAUDE.md`, `LICENSE` (MIT), and `.gitignore` (still has old entries like `mcp/dist/`; clean up when the new layout lands). No CI workflows exist yet.

_Fill in once the new layout is settled._

## Common commands

_TBD — fill in once the new layout is settled (install, build, test, run locally, release)._
