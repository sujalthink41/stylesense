# 0017 — Virtual try-on: background jobs, a pluggable vendor, paid-call safety

**Status:** Accepted (2026-10-05)

## Context
Try-on vendors are paid per image, take seconds to a minute, and fail in ways that are sometimes worth retrying (busy, timeouts) and sometimes not (no person in the photo). No free or self-hostable option fits the homelab, so the vendor is still to be chosen.

## Decision
- **A `TryOnProvider` port** (`render(person_url, garment_url, idempotency_key) → image URL + cost`). A `FakeTryOnProvider` (returns the garment image) lets the whole pipeline run locally; settings refuse it in production. `APP_TRYON_PROVIDER=none` turns try-on off (503 `tryon_unavailable`).
- **Jobs, not requests.** `POST /v1/tryon` writes a `tryon_jobs` row (`queued`) and an outbox message in one transaction and returns 202. The worker renders, **copies the result into our storage at once** (vendor URLs are temporary), and marks it `done`. The app follows progress over SSE (`GET /v1/tryon/{id}/events`) or polls `GET /v1/tryon/{id}`.
- **A double tap pays once.** Three layers:
  1. `Idempotency-Key` is required on `POST /v1/tryon`, so a replay returns the stored response;
  2. a per-user Postgres advisory lock plus a unique index on active `(user, selfie, product)` jobs, so a second tap with a different key gets the same job;
  3. the job id goes to the vendor as its idempotency key, for vendors that dedupe.
- **Failure handling.** Busy or timeout → the job goes back to `queued` and the outbox retries with backoff, up to 3 attempts; then `failed` with a friendly, retryable message. A refused photo → `failed`, not retryable. A storage refusal → `failed` at once. `POST /v1/tryon/{id}/retry` re-queues a retryable failure **without** using quota.
- **Quotas.** 3 per user per day (failures don't count), checked under the per-user lock so concurrent requests can't exceed it, plus a global daily cap (`APP_TRYON_GLOBAL_DAILY_LIMIT`) as a hard spend ceiling.
- **Reports.** `POST /v1/reports` (try-on, product, share, poll; idempotent per reporter and target). A reported try-on result is hidden at once; review comes with the admin (CP14).

## Consequences
- Choosing a vendor means writing one adapter (`integrations/tryon/`), adding its key, and setting `APP_TRYON_PROVIDER`; nothing else changes.
- Retries can call the vendor more than once for one job: at most 3 attempts, and dedupe-capable vendors charge once thanks to the idempotency key.
- Selfies and results follow the 24 h purge (ADR 0016).
