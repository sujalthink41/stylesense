# 04 — Technical Spec Slices

The technical spec (doc 03) is split into **vertical slices**. Each slice is a thin, end-to-end piece (DB → backend → AI → mobile/admin) that can be built, tested and demoed on its own. Checkpoints (doc 06) group slices into build milestones.

Each slice lists: **scope**, **backend**, **AI**, **mobile/web**, **data**, **acceptance criteria**.

---

## Foundation slices

### S0 — Platform foundation
- **Scope:** monorepo, Docker Compose (Postgres+pgvector, Redis, MinIO), FastAPI skeleton, config, logging, error format, health checks, CI.
- **Backend:** `core/config.py` (pydantic-settings), structlog, problem+json errors, request-id middleware, `/healthz`, `/readyz`, `/metrics`; Alembic set up.
- **Mobile:** Expo app shell, routing, theme/design tokens, API client.
- **Admin:** Next.js shell with layout.
- **Acceptance:** `docker compose up` brings every service up healthy; CI is green on lint, type checks and tests; the app opens and calls `/healthz`.

### S1 — Auth & accounts
- **Scope:** Google sign-in, JWT access + rotating refresh, profile, devices, logout, account deletion, consent.
- **Backend:** `/auth/google`, `/auth/refresh`, `/auth/logout`, `/me`, `DELETE /me`; refresh-token reuse detection.
- **Mobile:** sign-in screen, secure token storage, auto-refresh interceptor, sign-out, delete account.
- **Web:** public account-deletion page + privacy policy page.
- **Data:** `users`, `auth_identities`, `refresh_tokens`, `user_devices`, `consents`, `account_deletions`.
- **Acceptance:** sign in → protected call works → access token expires → refresh happens silently → a reused refresh token revokes the session family → deletion purges the user.

### S2 — Catalog & mock data
- **Scope:** canonical products + offers, stores, mock seed (~300 products across 3 stores), embeddings, outbound click redirect.
- **Backend:** `ProductSource` protocol + `MockSource`, seed script, embedding job, `GET /products/{id}`, `/offers`, `/out/{offer_id}`.
- **Admin:** product list/detail/edit (price edits are used to simulate price drops later).
- **Data:** `stores`, `products`, `product_images`, `offers`, `outbound_clicks`, `price_snapshots`.
- **Acceptance:** the seed loads idempotently; every product has an embedding; vector search returns sensible neighbors; outbound clicks are logged and redirect.

### S3 — LLM gateway & AI guardrails
- **Scope:** provider-agnostic gateway, task routing config, fallbacks, circuit breaker, retries, timeouts, token counting/limits, response cache, per-user quotas, global budget cap, Langfuse tracing, usage metering, fake provider for tests.
- **Backend:** `ai/gateway/*`, `llm_task_configs` hot reload, `llm_usage` writes, `/admin/llm/*`.
- **Admin:** task → model config editor, prompt versions, cost/token dashboard.
- **Data:** `llm_providers`, `llm_task_configs`, `prompt_templates`, `llm_usage`.
- **Acceptance:** changing a task's model in admin takes effect without a redeploy; killing the primary provider (fault injection) trips the breaker and the fallback answers; exceeding the budget switches to degraded mode; every call shows in Langfuse with its cost.

### S4 — GenUI protocol & renderer
- **Scope:** Pydantic component schemas, JSON Schema → TS codegen, SSE stream, action endpoint (turn_id + idempotency), client component registry, renderer, Zustand session store, fallback renderer, loading skeletons.
- **Backend:** `ai/genui/*`, `/stylist/sessions` endpoints (with a static demo flow first).
- **Mobile:** `src/genui/registry.ts`, `Renderer`, a component per catalog type (initially `chip_question`, `budget_slider`, `suggestion_bar`, `info_banner`, `empty_state`, `text_input_bar`).
- **Acceptance:** the demo flow streams components; taps send actions; a stale `turn_id` is rejected; an unknown component renders the fallback; the contract check fails CI on drift.

---

## Feature slices

### S5 — AI Stylist v1 (F1, F5)
- **Scope:** LangGraph stylist graph: ingest → route → understand → slot_check → ask_question → retrieve → rank → explain → compose_ui, with `interrupt()` between turns and the Postgres checkpointer.
- **AI tasks:** `stylist.understand`, `stylist.smart_options`, `stylist.explain`.
- **Mobile:** home occasion tiles + quick search → stylist screen; `product_card`, `why_this_pick`.
- **Data:** `stylist_sessions`, `session_events`, LangGraph checkpoint tables.
- **Acceptance:** "summer t-shirt under 500" → at most 3 chip questions → ranked results within budget, each with a reason; with the LLM disabled, the whole flow still works in degraded mode.

### S6 — Swipe discovery & taste learning (F3)
- **Scope:** `product_swipe_deck`, swipe actions, taste-vector EMA + tag counters, re-ranking with taste, deck refill.
- **Data:** `swipes`, `style_profiles.taste_vector`.
- **Acceptance:** after 10 right-swipes on one style, the next deck is measurably closer to it (offline test); swipe → next card in < 100 ms on device (prefetched).

### S7 — Style DNA onboarding (F2)
- **Scope:** tap-only onboarding (fit/gender preference, body type, skin tone, sizes, style image picks), editable later; seeds the taste vector.
- **Components:** `image_choice_grid`, `chip_question`.
- **Data:** `style_profiles`.
- **Acceptance:** onboarding completes in ≤ 30 s with taps only; stylist sessions prefill size/fit from Style DNA.

### S8 — Product detail, store comparison, complete the look (F4, F6)
- **Scope:** `product_detail`, `store_comparison` (exact offers; else similar by embedding with a label), `complete_the_look` (complementary categories within remaining budget).
- **AI task:** `look.complete` (optional; rule-based pairing first).
- **Acceptance:** the best price is highlighted correctly; complete-the-look never exceeds the remaining budget; every Buy goes through `/out`.

### S9 — Wishlist & outfit boards (F9)
- **Scope:** default "Wishlist" board, custom outfit boards, add/remove/reorder, save from any card.
- **Data:** `boards`, `board_items`.
- **Acceptance:** works offline-first (optimistic updates + sync); data survives reinstall after sign-in.

### S10 — Share a look (F10)
- **Scope:** on-device outfit card rendering (view-shot), share sheet, short link `/l/{slug}`, web landing page, Android App Links.
- **Data:** `shares`.
- **Acceptance:** a shared link opens the app if installed, otherwise the web page with a Play Store button.

### S11 — Shop from a photo (F7)
- **Scope:** upload (presigned to MinIO), EXIF strip, moderation, `photo.understand`, embedding search, results as stylist UI.
- **Data:** `uploads`.
- **Acceptance:** an outfit photo returns ≥ 5 similar in-budget items; daily quota enforced; the upload is deleted after 24 h.

### S12 — Virtual try-on (F8)
- **Scope:** `TryOnProvider` adapter, ARQ job, progress via SSE patch + push, `tryon_result`, report action, 24 h deletion, daily quota.
- **Data:** `tryon_jobs`, `uploads`, `content_reports`.
- **Acceptance:** try-on finishes asynchronously while the user keeps browsing; failure shows a friendly retry; images are purged by cron.

### S13 — Ask friends polls (F11)
- **Scope:** create a poll from 2–4 products, public vote page (no login), anti-abuse (device cookie + IP limit), live results in the app.
- **Data:** `polls`, `poll_options`, `poll_votes`.
- **Acceptance:** a friend votes from WhatsApp in under 10 s; duplicate votes are blocked; results update in the app.

### S14 — Trending feed (F12)
- **Scope:** a nightly cron builds collections ("Under ₹500", season/festival edits); admin pin/curate; feed endpoint with cursor pagination.
- **Data:** `feed_collections`, `feed_items`.
- **Acceptance:** the feed refreshes daily; admin pins appear first; the feed loads in < 1 s.

### S15 — Notifications & price-drop alerts (F13)
- **Scope:** `price_snapshots` on each offer change, an alerts cron, in-app notifications, FCM push, user settings.
- **Data:** `price_alerts`, `notifications`, `user_devices`.
- **Acceptance:** an admin price drop on a wishlisted item → push within 15 min; users can mute alerts.

### S16 — Admin dashboard complete
- **Scope:** users, products, feed curation, LLM configs/prompts/cost, rate limits & feature flags, content reports, audit log, business metrics (doc 02 §7).
- **Data:** `feature_flags`, `audit_logs`, `content_reports`.
- **Acceptance:** every admin write is audited; role checks are enforced server-side.

### S17 — Hardening & compliance
- **Scope:** load test, security scan, backups + restore drill, alerts, data export, Play Store compliance items, performance tuning.
- **Acceptance:** all NFR targets in doc 03 §1.2 met on staging.

### S18 — Real integrations (post-v1)
- **Scope:** `AmazonSource`, `FlipkartSource`, network source (Cuelinks/EarnKaro for Myntra), affiliate tagging in `build_outbound_url`, offer refresh jobs, catalog deduplication into canonical products.
- **Acceptance:** real offers appear behind a feature flag; clicks carry affiliate tags; mock data is disabled in prod.
