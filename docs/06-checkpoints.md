# 06 — Build Checkpoints

We build StyleSense **backend first, then frontend**, checkpoint by checkpoint. Every checkpoint ends with something that **runs and is proven by tests**. Backend checkpoints are demoed through the API (OpenAPI docs, scripted SSE client, tests).

**Rules for every checkpoint**
1. Built test-first; all exit criteria met; CI green (lint, types, tests, coverage, import rules, contract check, secret scan).
2. **`07-system-architecture.md` updated** to the current state, plus a changelog entry.
3. New concepts added to `08-key-concepts.md`; significant decisions recorded as ADRs.
4. Commit and tag `cp-<n>`.

**Status legend:** ⬜ not started · 🟨 in progress · ✅ done

| # | Checkpoint | Slices | Status |
|---|---|---|---|
| CP0 | Product, technical & engineering docs | — | ✅ |
| **Phase 1: Backend** | | | |
| CP1 | Backend foundation & project structure | S0 | ✅ |
| CP2 | Observability foundation | S0 | ✅ |
| CP3 | Cross-cutting guards: idempotency, rate limiting, locks, outbox | S0 | ✅ |
| CP4 | Auth & accounts | S1 | ✅ |
| CP5 | Catalog & mock data | S2 | ⬜ |
| CP6 | LLM gateway & AI guardrails | S3 | ⬜ |
| CP7 | GenUI protocol (backend) | S4 | ⬜ |
| CP8 | AI Stylist graph v1 | S5 | ⬜ |
| CP9 | Swipes, taste learning, Style DNA | S6, S7 | ⬜ |
| CP10 | Detail, store comparison, complete the look | S8 | ⬜ |
| CP11 | Boards, shares, polls | S9, S10, S13 | ⬜ |
| CP12 | Uploads, shop from photo, virtual try-on | S11, S12 | ⬜ |
| CP13 | Feed, notifications, price-drop alerts | S14, S15 | ⬜ |
| CP14 | Admin API complete | S16 | ⬜ |
| **Phase 2: Frontend** | | | |
| CP15 | Mobile foundation + auth + GenUI renderer | S0, S1, S4 | ⬜ |
| CP16 | Mobile stylist, swipe, Style DNA, detail | S5–S8 | ⬜ |
| CP17 | Mobile boards, share, polls, photo, try-on, feed, alerts | S9–S15 | ⬜ |
| CP18 | Admin dashboard + public web pages | S16 | ⬜ |
| **Phase 3: Production** | | | |
| CP19 | Hardening, compliance & homelab production deploy | S17 | ⬜ |
| CP20 | Play Store closed testing → public release | — | ⬜ |
| CP21 | Real store integrations (post-v1) | S18 | ⬜ |

---

# Phase 1: Backend

## CP1 — Backend foundation & project structure
**Deliverables**
- Monorepo root (`backend/`, `infra/`, `docs/`; mobile/admin folders created in Phase 2).
- Backend structure per doc 09 §2; `uv`, `ruff`, `mypy --strict`, `import-linter`, pre-commit.
- Compose (dev): Postgres 18 + pgvector, Redis; `.env.example` (object storage deferred to CP12, ADR 0003).
- App factory, typed settings (fail fast), DB engine + Unit of Work, Redis client, injectable clock, error model (problem+json), `/healthz`, `/readyz`, graceful shutdown; Alembic baseline.
- Test harness: testcontainers fixtures, factories, fakes folder, coverage gate.
- GitHub Actions: lint, types, import rules, tests + coverage, gitleaks, pip-audit.

**Exit:** `docker compose up` → healthy; `/readyz` reflects DB/Redis outages (tested); CI green on a clean clone.

## CP2 — Observability foundation
**Deliverables:** structlog JSON with request context + PII redaction, request-id/trace-id middleware, OpenTelemetry tracing (API, DB, Redis), Prometheus metrics (RED + pools), GlitchTip SDK, Compose overlay for OTel Collector, Tempo, Prometheus, Grafana (provisioned dashboard), GlitchTip, Uptime Kuma; `docs/runbooks/` template. Langfuse moves to CP6 (ADR 0004).
**Exit:** one request is traceable across logs/metrics/traces by id; PII redaction tested; a forced error appears in GlitchTip.

## CP3 — Cross-cutting guards
**Deliverables:** idempotency middleware/dependency (Redis, stored responses, concurrent-duplicate handling), rate limiter (sliding window + token bucket, policy table + Redis cache), distributed locks, single-flight helper, transactional outbox + worker process (ADR 0005), backpressure (`503 + Retry-After`). Rate-limit policies are code defaults until the admin store in CP14.
**Exit:** property tests for limiters; same idempotency key in parallel → one execution; outbox delivers exactly once to the handler, which is idempotent under redelivery; 2 API + 2 worker instances pass the suite.

## CP4 — Auth & accounts
**Deliverables:** Google ID-token verification, access JWT + rotating refresh tokens (reuse detection + grace window), `/me`, devices, consents, account deletion + purge job, roles, admin allow-list, min-supported-app-version endpoint.
**Exit:** full auth edge-case matrix tested (expired, tampered, wrong audience, reuse, parallel refresh, IDOR, deleted user).

## CP5 — Catalog & mock data
**Deliverables:** catalog tables, `ProductSource` protocol + `MockSource`, ~300-product realistic seed, embedding job (content-hash skip), product/offer endpoints with ETags, `/out/{offer_id}` + click log, price snapshots on change.
**Exit:** idempotent seed; vector neighbors sensible; no N+1 queries (query-count tests).

## CP6 — LLM gateway & AI guardrails
**Deliverables:** `LLMGateway`, provider adapters (OpenAI + one more to prove swappability), task configs (DB + Redis, hot reload), fallbacks, Redis-shared circuit breaker, retries, timeouts, token limits, response cache, single-flight, quotas, global budget cap + degraded mode, bulkheads, Langfuse, `llm_usage`, fake provider, prompt templates, admin LLM endpoints.
**Exit:** fault-injection tests (timeouts, 429, 500, invalid JSON) → breaker/fallback/degraded behave as specified; model change applies without restart; budget cap enforced.

## CP7 — GenUI protocol (backend)
**Deliverables:** Pydantic component catalog v1, JSON Schema export + snapshot contract test, session endpoints, SSE stream, actions (turn_id + idempotency), version negotiation, scripted demo flow.
**Exit:** scripted SSE client completes the demo flow; stale turn → 409; unsupported version degrades.

## CP8 — AI Stylist graph v1
**Deliverables:** LangGraph stylist with Postgres checkpointer, ingest/route/understand/slot_check/ask/retrieve/rank/explain/compose nodes, deterministic questions, hybrid retrieval + ranking, degraded mode, golden eval set (~50 intents) + runner.
**Exit:** "summer t-shirt under 500" → ≤ 3 questions → in-budget ranked results with reasons; LLM disabled → still works; eval ≥ 90% slot accuracy.

## CP9 — Swipes, taste learning, Style DNA
**Deliverables:** swipe actions, taste vector EMA + tag affinity, taste-aware ranking, deck refill/prefetch API, Style DNA endpoints + taste seeding.
**Exit:** offline test shows ranking shifts toward liked styles; swipe endpoint p95 < 50 ms.

## CP10 — Detail, store comparison, complete the look
**Deliverables:** detail endpoint/components, comparison (exact → similar fallback), complete-the-look (rules first, LLM optional) within remaining budget.
**Exit:** best-price and budget rules proven with property tests.

## CP11 — Boards, shares, polls
**Deliverables:** boards CRUD (optimistic locking), share slugs + payloads, polls + public vote API with anti-abuse.
**Exit:** duplicate votes/items blocked under concurrency; public endpoints rate-limited.

## CP12 — Uploads, shop from photo, virtual try-on
**Deliverables:** presigned uploads, EXIF strip, moderation, `photo.understand` flow, try-on provider evaluation (ADR) + adapter, outbox-driven job with dedupe, SSE patch on completion, quotas, 24 h purge, reports.
**Exit:** double-tap creates one paid try-on; provider failure is recoverable; purge verified.

## CP13 — Feed, notifications, price-drop alerts
**Deliverables:** feed collections cron (locked) + curation API, notifications inbox, FCM push adapter with dedupe, price-alert cron.
**Exit:** price drop → exactly one notification per alert event, even with cron overlap or retries.

## CP14 — Admin API complete
**Deliverables:** users, products, feed, LLM config/prompts/cost, limits, flags, reports, audit log, metrics endpoints.
**Exit:** every admin write audited; role checks enforced and tested.

# Phase 2: Frontend

## CP15 — Mobile foundation + auth + GenUI renderer
Expo app structure, design system, API client (generated types), Google sign-in + token handling, force-update screen, GenUI registry + renderer + Zustand store, base components, Crashlytics.
**Exit:** the demo flow renders on device; contract types generated in CI.

## CP16 — Mobile stylist, swipe, Style DNA, detail
Home tiles, stylist screen, swipe deck (Reanimated, prefetch, haptics), onboarding, detail, comparison, complete the look.
**Exit:** first products < 5 s on a mid-range Android device; swipe at 60 fps.

## CP17 — Mobile boards, share, polls, photo, try-on, feed, alerts
All remaining v1 screens; offline-first boards; view-shot share cards; App Links.
**Exit:** Maestro E2E suite green for all core flows.

## CP18 — Admin dashboard + public web pages
Next.js admin over the admin API; public poll/share/delete-account/privacy pages.
**Exit:** all admin features usable; public pages pass a Lighthouse ≥ 90 score.

# Phase 3: Production

## CP19 — Hardening, compliance & production deploy
Prod Compose, Caddy, Cloudflare Tunnel, alert rules + runbooks, backups + **restore drill**, k6 load test, ZAP scan, data export, Data Safety answers, privacy policy/terms.
**Exit:** NFR targets (doc 03 §1.2) met on staging; restore drill passes; no high-severity findings.

## CP20 — Play Store release
Signed build, listing, Data Safety, content rating, **closed test ≥ 12 testers × 14 days**, fixes, staged rollout.
**Exit:** live on the Play Store; crash-free sessions ≥ 99.5%.

## CP21 — Real store integrations (post-v1)
Apply to Amazon Associates, Flipkart Affiliate and Cuelinks/EarnKaro; real adapters; affiliate tagging; offer refresh jobs; canonical dedup; flagged rollout.
**Exit:** real offers live; clicks carry affiliate tags.
