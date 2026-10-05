# 0011 — Action-scoped SSE streams and turn compare-and-swap

**Status:** Accepted (2026-10-05)

## Context
The spec planned a long-lived `GET …/stream` SSE connection per session plus `POST …/actions`, with an `Idempotency-Key` on every action. With several API instances, the stream and the POST can land on different instances, which needs a message broker (Redis pub/sub or streams) between them, plus reconnection and replay logic.

## Decision
- **The response to `POST …/actions` *is* the SSE stream for that turn** (`Accept: text/event-stream`), carrying `ui.loading` → `ui.render` → `done` (or `error`). Clients that don't stream get the final screen as JSON.
- **`turn_id` compare-and-swap is the idempotency mechanism.** An action names the turn it acts on; a single `UPDATE … WHERE turn_id = :t AND status = 'active'` lets exactly one request advance it. Double taps, retries and second devices get `409 stale_turn` (with `current_turn`) or `409 session_busy`.
- **The turn runs in a background task** and feeds the stream through a queue, so a client that disconnects mid-stream never aborts or corrupts a turn. **`GET …/sessions/{id}`** returns the last rendered screen: the resume point.
- Long-running turns send SSE keep-alive comments every 15 s so proxies don't cut the stream.

## Consequences
- No broker; any instance can serve any request.
- No idempotency-key storage for actions; the session row itself is the source of truth.
- A client must fetch the snapshot after a `409` or a dropped stream. That's one extra GET in rare cases.
