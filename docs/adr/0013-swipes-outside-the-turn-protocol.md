# 0013 — Swipes outside the turn protocol, learned synchronously

**Status:** Accepted (2026-10-05)

## Context
CP7 made every user action a turn: CAS on `turn_id`, a background task, an SSE stream, a persisted screen. That's right for questions and refinements, but a swipe deck produces an action every second or so. Routing each swipe through a turn would mean:

- the app waits for a full re-render after every card, though it already holds the next one;
- double taps and offline retries collide on `turn_id` (409s) for something that's naturally idempotent;
- the exit target (swipe p95 < 50 ms) is out of reach, since a turn re-runs search and ranking.

The spec also left open whether taste should be learned in the request or in a background job.

## Decision
- **`POST /v1/me/swipes`** records a swipe outside the turn protocol. It's idempotent by a unique key `(user_id, product_id, session_id)` with `NULLS NOT DISTINCT`, so a replay returns `{recorded: false}` and learns nothing twice. The `swipe` GenUI action still works and records the same way.
- **Learning is synchronous, in one short transaction:** insert swipe → lock the `style_profiles` row (`SELECT … FOR UPDATE`, upserted first) → update the taste vector (EMA) and tag affinity in code → commit. No outbox: the very next refill must already reflect the swipe, and the work is ~1 ms of arithmetic on 1,536 floats. The row lock makes concurrent swipes queue instead of losing updates.
- **`GET /v1/stylist/sessions/{id}/deck`** tops the deck up between turns: read-only (no CAS), `Cache-Control: no-store`, excludes swiped cards (state + `swipes`) and cards the app already holds (`exclude=`). Reasons are rules-only, because the app calls it often to prefetch.
- `session_id` on `swipes` is a dedupe scope, **not a foreign key**. Swipes outlive sessions, and `ON DELETE SET NULL` could collide with the unique key.
- **Rate limits:** swipes get their own per-user token bucket (`swipes.per_user`, 240/min) instead of sharing `api.per_user`. `api.per_ip` rises from 60 to 600/min: Indian mobile carriers put many users behind one IP (CGNAT), so per-IP is only a flood guard and per-user limits do the real work.

## Consequences
- Swipes are cheap (measured p95 ≈ 18 ms end to end on the dev stack) and safe to retry or queue offline.
- The session's persisted state doesn't list REST swipes; the flow reads them from `swipes` when it builds a deck. Two sources, one query.
- A burst of swipes from one user serialises on their profile row. That's fine at human speed; a bot is stopped by the token bucket first.
- If learning ever gets expensive (e.g. a learned re-ranker), it can move to the outbox without changing the API.
