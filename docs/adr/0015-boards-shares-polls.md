# 0015 — Boards, share links and polls: optimistic locking, natural idempotency, token voting

**Status:** Accepted (2026-10-05)

## Context
CP11 adds the first user-owned data that several devices edit (boards) and the first endpoints anyone can call without signing in (share pages, poll votes). Decisions were needed on:

- how two devices editing the same board avoid silently overwriting each other;
- how offline-first clients create things and retry safely;
- how anonymous voting resists stuffing without logins, while storing as little personal data as possible.

## Decision
- **Optimistic locking on boards.** Every board has a `version`, returned as `ETag: "<n>"`. Renames, cover changes and reorders require `If-Match: "<n>"`: missing → **428**, stale → **412** with the current version (and its ETag) so the app can refresh and retry. Each write locks the board row (`FOR UPDATE`), checks, bumps `version`, commits.
- **Adds and removes don't need a version**, because they're naturally idempotent: `PUT /boards/{id}/items/{product_id}` uses a unique `(board_id, product_id)` with `ON CONFLICT DO NOTHING`; `DELETE` of a missing item is 204. Only real changes bump the version. The wishlist is addressed as `wishlist`, created on first use under a partial unique index (one per user, race-safe).
- **Client-generated ids make creates idempotent:** `POST /boards` and `POST /polls` accept an optional UUID; replaying it returns the same row (200 rather than 201), and someone else's id is a 409. Shares are idempotent by **content**: a unique `(user_id, content_hash)` returns the same slug for the same look, and re-sharing a revoked link revives it.
- **Public links are random slugs** (8 base62 chars, ≈ 2·10¹⁴), allocated with `ON CONFLICT DO NOTHING` + retry. Share pages expose products and live prices only, never the owner. Board shares follow the live board; a deleted board or revoked link answers **410**.
- **Voting uses a token, not a cookie.** The public vote page stores a random token (localStorage) and sends `X-Voter-Token`; that works across the web and API domains with no third-party cookies or CORS credentials. Anti-abuse in three layers:
  1. `UNIQUE(poll_id, voter_hash)`: one vote per device per poll, final even under races; the same vote again is a harmless replay, a different option is 409;
  2. 25 new votes per IP per poll per day (Redis sliding window, CGNAT-friendly);
  3. `votes.per_ip` 30/min and `public.per_ip` 120/min at the edge.
  Tokens and IPs are stored only as **HMAC pseudonyms**, keyed by a purpose-bound key derived from the deployment secret. Results stay hidden until you vote (no bandwagon); the owner always sees them.

## Consequences
- No lost updates between devices, and every retry of an offline queue is safe.
- Rotating `APP_JWT_SECRET` changes the voter-hash key: someone could vote again in a poll that's still open. Acceptable for "which one should I buy?" polls.
- A determined attacker with many IPs and tokens can still stuff a poll. Abuse at that level for a friends' poll isn't worth CAPTCHAs in v1; the per-IP caps bound casual abuse.
- The public web app (CP18) must persist the voter token and send it on every poll call.
