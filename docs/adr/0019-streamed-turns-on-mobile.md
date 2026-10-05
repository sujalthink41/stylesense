# 0019 — Streamed stylist turns on mobile, resume instead of resend

**Status:** Accepted (2026-10-05)

## Context
The server already streams each turn as Server-Sent Events (ADR 0011): `ui.loading` with a skeleton of the coming screen, then `ui.render`, then `done`. CP15's app used the plain JSON answer, so every wait looked the same and a dropped connection meant an error. On SDK 57 the global `fetch` on Android and iOS is `expo/fetch`, which can read a response body as it arrives; no extra library is needed.

## Decision
- **`ApiClient.events()`** posts with `Accept: text/event-stream` and parses frames incrementally (`api/sse.ts`; chunks may split anywhere, keep-alive comments are ignored). If a proxy buffers and answers JSON, that body is used as before. Without an incremental body reader, the whole stream is parsed at the end, so it's still correct, just not progressive.
- **Shape-aware waiting.** The current screen stays up, with taps disabled, until `ui.loading` names the shape of the next one: the print loader for cards, bones for questions and the detail screen. The new screen then fades in, so the layout doesn't jump.
- **Resume, never resend.** Once the server has accepted an action, a dropped or silent stream (no bytes for 45 s; keep-alives come every 15 s) becomes `stream_lost`. The store then polls the session snapshot until the turn is no longer `busy` (up to 8 s). Resending could apply a tap twice; the turn compare-and-swap would refuse it, but the poll is simpler and always correct.
- **System back follows the server.** Android back sends the Back that the screen itself offers. With none on offer (the first screen), it leaves the session. Mid-turn, it's ignored.
- **One welcome per account per phone.** After sign-in, people without a Style DNA see the welcome once (`onboarding/store.ts`); answering either way records it, and sign-out forgets it. The splash waits for this check (capped at 2.5 s, and offline counts as "skip") so the first screen doesn't jump.
- **Wishlist heart is optimistic.** It flips at once, then sends an idempotent PUT or DELETE on the item; a refusal flips it back with an error haptic.

## Consequences
- Slow AI turns now show a meaningful skeleton within milliseconds, and a flaky network no longer loses a turn.
- Time to first products is measured on the device (`lib/perf.ts`, `tap_to_products`, logged in development and sent as a breadcrumb) and checked against the CP16 target of under 5 s.
