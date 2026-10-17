# 07 — How the System Works (Living Document)

> **Audience:** any developer joining the project.
> **Rule:** updated at the end of **every checkpoint** to describe the system **as it exists now**. Planned parts are marked *(planned)*.

**Current state:** CP12 complete. The backend skeleton runs in Docker with Postgres + pgvector and Redis, exposes liveness/readiness probes, renders all errors as problem+json, and runs migrations on deploy. Every request is observable end to end: request id, PII-safe JSON logs, RED metrics, OpenTelemetry traces (API, DB, Redis) and error reports to GlitchTip. Reliability guards are in place (idempotency, rate limits, load shedding, distributed locks, single-flight, bulkheads) and a worker process delivers outbox messages. Users can sign in with Google, manage their profile, devices and consents, and delete their account. A 300-product mock catalog across Amazon, Flipkart and Myntra is browsable, with store price comparison, similar-item search and tracked Buy redirects. All AI access goes through a provider-agnostic gateway with routing, fallbacks, breakers, budgets and metering; The generative-UI protocol is live: sessions stream typed UI components turn by turn. The AI stylist drives them: it understands requests with rules (the LLM only fills gaps), asks at most one tappable question per missing slot, and returns ranked, in-budget products with reasons, and it keeps working with no AI key at all. It learns from swipes: a taste vector and tag affinities reshape every deck, Style DNA onboarding (taps only) prefills gender and size, and decks refill between turns. Opening a card shows the full product, every store's price (best one flagged), similar picks when few stores stock it, and a complete look that stays within a whole-look budget. Users save items to a wishlist and outfit boards (safe across devices), share looks as links anyone can open, and ask friends to vote in polls without signing in. Users can shop from a photo, and try clothes on virtually: photos go straight to Cloudinary, live 24 hours, and try-ons run as background jobs that never charge twice. Parts marked *(planned)* arrive in later checkpoints.

---

## 1. The big picture in 60 seconds

StyleSense is a mobile app where an AI stylist helps users find clothes within budget across Amazon, Flipkart and Myntra.

- The **mobile app** (React Native/Expo) is mostly a **renderer**. It doesn't hardcode the stylist screens. Instead, the backend streams **UI components** (chips, sliders, product cards) and the app draws them. This is *generative UI*.
- The **backend** (FastAPI) runs the stylist as a **LangGraph state machine**. Most steps are plain code (questions, filtering, ranking). The LLM is used only where it adds real value: understanding free text or photos, writing "why this pick", and complex outfit pairing.
- **All AI calls go through one `LLMGateway`**, which picks the provider/model from config and handles fallbacks, circuit breaking, rate limits, budgets, caching and tracing. Swapping OpenAI for another provider is a config change.
- **Products** come from **source adapters**. Today: mock data. Later: Amazon/Flipkart/affiliate networks. The rest of the system doesn't know or care which.
- Everything runs in **Docker Compose on a homelab**, exposed to the internet through a **Cloudflare Tunnel**.

## 2. Components

| Component | Tech | Responsibility |
|---|---|---|
| `mobile/` *(planned)* | Expo, TS, Zustand, TanStack Query | Auth, GenUI renderer, swipe deck, boards, share, polls, notifications |
| `backend/src/stylesense/api` *(built: health)* | FastAPI | HTTP routers + request dependencies; REST + SSE *(planned)* |
| `backend/src/stylesense/bootstrap` *(built)* | Python | Composition root: builds the `Container` at startup, closes it on shutdown |
| `backend/src/stylesense/platform` *(built)* | Python | Config, logging, error taxonomy, clock, health runner |
| `backend/src/stylesense/infra` *(built)* | SQLAlchemy, redis-py | DB engine + Unit of Work, Redis client, dependency probes |
| `backend/src/stylesense/ai/graphs` *(planned)* | LangGraph | Stylist and photo-search flows |
| `backend/src/stylesense/ai/gateway` *(planned)* | LangChain models + own code | Provider-agnostic LLM calls with guardrails |
| `backend/src/stylesense/ai/genui` *(planned)* | Pydantic | The UI component contract |
| `backend/src/stylesense/integrations/sources` *(planned)* | Python adapters | Product data sources |
| `backend/src/stylesense/workers` *(built: runtime + outbox relay)* | asyncio | Outbox delivery, periodic jobs; later try-on, embeddings, alerts, feed, purges |
| `backend/src/stylesense/guards` *(built)* | Redis, Postgres | Idempotency, rate limits, locks, single-flight, bulkheads, outbox |
| `admin/` *(planned)* | Next.js | Admin dashboard + public web pages |
| Postgres 18 + pgvector *(built)* | | All data + vector search + LangGraph checkpoints |
| Redis 8 *(built)* | | Cache, rate limits, breaker state, job queue, idempotency (`noeviction`) |
| Object storage *(CP12, ADR 0003)* | | Uploads, try-on images |
| Langfuse / GlitchTip / Prometheus / Grafana / Uptime Kuma | | Observability |

## 2a. What happens at startup and shutdown *(built)*

1. `create_app(settings)` (`main.py`) loads typed settings; **invalid config crashes immediately** (fail fast).
2. Logging is configured: JSON everywhere except `local`, where it's human-readable.
3. Error handlers are registered, so every error leaves the API as `application/problem+json`.
4. On startup (lifespan), `build_container()` creates the DB engine, session factory, Redis client, clock and health checks. Clients are lazy and connect on first use.
5. On shutdown, `Container.aclose()` closes Redis and disposes the DB pool; Uvicorn gives in-flight requests up to 20 s to finish.

## 2b. Probes *(built)*

| Endpoint | Meaning | Touches dependencies? | Used by |
|---|---|---|---|
| `GET /healthz` | Process is alive | **Never** (a DB blip must not restart the app) | Docker `HEALTHCHECK`, orchestrator liveness |
| `GET /readyz` | Can serve traffic | Yes: Postgres + Redis, concurrently, each bounded by `APP_READINESS_TIMEOUT_S` | Load balancer / deploy gate |

`/readyz` returns 503 with per-check results when anything is down. Errors show only the exception type, never hosts or credentials.

## 2c. Errors *(built)*

Raise a subclass of `AppError` (`NotFoundError`, `ConflictError`, …). One handler maps it to RFC 9457 problem+json with a stable `code`. Validation errors list field locations but **never echo the input back**. Unexpected exceptions become a generic 500 and are logged with the stack trace server-side.

## 2d. Database access *(built)*

- `create_engine` sets the pool size/overflow/timeout from config, `pool_pre_ping`, and per-connection `statement_timeout`, `timezone=UTC` and `application_name`.
- `UnitOfWork` = one transaction per use case: commit on clean exit, roll back on any exception.
- `Base` uses a naming convention so constraint names, and therefore Alembic diffs, are deterministic.
- Migrations run as a one-shot `migrate` container before `api` starts. Migrations get no statement timeout but a 10 s lock timeout.

## 2e. Observability *(built)*

```
request ──▶ RequestContextMiddleware ──▶ OTel server span ──▶ handler ──▶ DB / Redis spans
              │ request id (X-Request-ID)
              │ access log (route template, status, duration)
              │ RED metrics (http_requests_total, http_request_duration_seconds)
              └ last-resort 500 → GlitchTip
```

| Signal | How it's produced | Where to see it |
|---|---|---|
| **Request id** | Every request gets one (a safe inbound `X-Request-ID` is reused). It's bound to every log line and returned in the response header and in problem+json bodies. | Response header; logs; GlitchTip tag |
| **Logs** | structlog JSON → stdout. Each line has `request_id`, `trace_id`, `span_id`. A **redaction processor** masks emails, Indian mobile numbers, bearer tokens, JWTs and sensitive keys before anything is written. | `make logs s=api` |
| **Metrics** | `GET /metrics` (internal only; the proxy must never expose it). HTTP RED by **route template**, unknown methods collapsed to `OTHER`, DB pool gauges read at scrape time, process/GC stats. Per-app registry, so no global state. | Prometheus → Grafana "StyleSense API" dashboard |
| **Traces** | OpenTelemetry server spans named `GET /route/{param}`, plus SQLAlchemy and Redis client spans. Exported over OTLP/HTTP to the collector, batched off the request path. Probes and `/metrics` are not traced. Off unless `APP_OTEL_ENABLED=true`. | Grafana → Explore → Tempo |
| **Errors** | Unexpected exceptions are captured once with the request id, after scrubbing (only user-data fields are scrubbed, so `release` stays intact). Expected `AppError`s are not reported. Off unless `APP_SENTRY_DSN` is set. | GlitchTip |
| **Uptime** | Uptime Kuma monitors `/healthz` and `/readyz` from outside the app (monitors are added in its UI). | Uptime Kuma |

**Middleware is pure ASGI** (not `BaseHTTPMiddleware`) so SSE streaming in CP7 works. If an error happens *after* a stream has started, it re-raises instead of writing a second response.

**SQLAlchemy is pinned to `<2.1`**: the OpenTelemetry SQLAlchemy instrumentation silently does nothing on 2.1. `tests/integration/test_tracing_clients.py` fails if DB spans ever disappear.

## 2f. Reliability guards *(built)*

| Guard | Problem it prevents | How | Failure mode |
|---|---|---|---|
| **Idempotency** (`guards/idempotency.py`, `api/idempotency.py`) | A retry or double tap creating two orders/try-ons | `Idempotency-Key` header → Redis record: claim (`SET NX`) → run once → store result (24 h). Same key + same request → replay with `Idempotent-Replayed: true`; same key + different request → 422; still running → 409 + `Retry-After` | **Fails closed** (503): we never run a side effect we can't deduplicate |
| **Rate limiting** (`guards/rate_limit.py`, `api/rate_limit.py`) | Abuse, bots, runaway clients | Atomic Lua in Redis: exact **sliding-window log** or **token bucket**. Every `/v1` route inherits `api.per_ip` (600/min: a flood guard, since mobile carriers share IPs); swipes have their own `swipes.per_user` bucket. 429 problem + `Retry-After`, `X-RateLimit-*` headers | **Fails open**: a Redis outage shouldn't take the API down |
| **Load shedding** (`api/middleware.py`) | Overload turning into timeouts for everyone | Bulkhead caps in-flight requests per instance (`APP_MAX_IN_FLIGHT`, small queue); excess gets 503 + `Retry-After` immediately. Probes exempt | — |
| **Distributed locks** (`guards/locks.py`) | Two workers running the same cron job | Redis `SET NX PX` + owner token; release/extend only by the owner (Lua) | Lock expires if the holder dies |
| **Single-flight** (`guards/singleflight.py`) | Paying twice for identical concurrent LLM/embedding calls | Concurrent callers with the same key share one in-flight task (per process) | Errors reach every waiter; nothing is cached |
| **Bulkheads** (`guards/bulkhead.py`) | One slow dependency starving everything | Bounded concurrency + bounded queue with wait timeout | 503 + `Retry-After` |

### Outbox and worker *(built)*

```
use case ─┬─ business change ─┐
          └─ OutboxWriter.add ┴─ one DB transaction ─► outbox_messages (pending)
                                                            │
worker: OutboxRelay ── FOR UPDATE SKIP LOCKED, one per tx ◄─┘
          ├─ handler OK      → done
          ├─ handler fails   → attempts+1, retry at now + backoff (exp + jitter)
          └─ max attempts / no handler → dead (see runbook outbox-backlog)
```

- Run it: `python -m stylesense.workers` (the `worker` Compose service). Handlers are registered by topic in `workers/__main__.py`.
- Periodic tasks: `PeriodicTask(name, interval_s, run, exclusive=False)`. `run` returns True when more work is waiting. `exclusive=True` takes a Redis lock so one worker runs it at a time.
- Health: the worker touches a heartbeat file after each healthy iteration; `python -m stylesense.workers.healthcheck` fails if it's older than 90 s.
- Metrics on `:9100`: `worker_task_runs_total{task,outcome}`, `worker_task_duration_seconds`, `outbox_pending`.
- Graceful shutdown: SIGTERM lets in-flight iterations finish (20 s grace), then cancels stragglers.

**Models registry:** every ORM model is imported in `bootstrap/models.py`. Alembic uses it, and `test_models_and_migrations_do_not_drift` fails if a model and the migrations disagree.

## 2g. Authentication & accounts *(built)*

```
app ── Google ID token ──► POST /v1/auth/google
                             │ GoogleIdTokenVerifier (RS256, aud = our client ids, verified email)
                             │ UsersService.sign_in: find by (google, sub) or create; admin allow-list → role
                             └► AuthService: new session family → access JWT (15 min) + refresh token (30 d, hashed)

app ── Bearer access JWT ──► any /v1 route: authenticate() checks signature + expiry (no DB) → AccessClaims
app ── refresh token ─────► POST /v1/auth/refresh: lock row → spend → issue child in same family
                             reused after 30 s grace ⇒ revoke whole family (committed before the 401)
```

| Concern | Where | Notes |
|---|---|---|
| Google verification | `integrations/google_identity.py` | Implements the `IdentityVerifier` port from `modules/auth/ports.py`; keys cached 1 h; Google unreachable → 503, bad token → 401 |
| Tokens | `modules/auth/tokens.py` | HS256 pinned; `iss`/`aud`/`exp`/`sid` required; previous secrets still verify (rotation) |
| Sessions | `modules/auth/service.py`, `refresh_tokens` | One family per sign-in per install; logout revokes the family; prune task deletes long-expired rows |
| Accounts | `modules/users/service.py` | Keyed by Google `sub`; concurrent first sign-ins produce one user; same email + different Google account → 409 |
| Roles | `api/auth.py` `require_role(...)` | `user`, `curator`, `admin`; admins from `APP_ADMIN_EMAILS` |
| Deletion | `DELETE /v1/me` | Status `deleting` + all sessions revoked + outbox `users.purge` after 30 days; handler retries if fired early and never purges a restored account |
| Force update | `GET /v1/app/config` | `min_supported_version` / `latest_version` |

Module dependency direction: **auth → users**. Users declares the identity shape it needs as a `Protocol` (`modules/users/ports.py`), so it never imports auth.

Setup: `docs/guides/google-sign-in-setup.md`.

## 2h. Catalog *(built)*

```
ProductSource (mock now) ─► CatalogService.ingest ─► products + offers + images + price_snapshots
                                 │ rejects unknown stores, non-allow-listed URLs, bad prices
                                 └─ idempotent: unchanged data writes nothing
worker "catalog.embed" (every 60 s) ─► Embedder port (hashing now, model in CP6) ─► products.embedding
```

| Endpoint | Behaviour |
|---|---|
| `GET /v1/products` | Filters: category, gender (also returns unisex), min/max price; keyset cursor pagination; constant number of queries regardless of page size |
| `GET /v1/products/{id}` | Detail with every offer, cheapest in-stock flagged `is_best`, discount %; weak **ETag** + `If-None-Match` → 304 |
| `GET /v1/products/{id}/similar` | Nearest neighbours by cosine distance (HNSW, iterative scan), same gender or unisex |
| `GET /v1/out/{offer_id}?src=…` | Logs the click (user attached when a valid token is sent), then 302 to the store. URL re-checked against the store allow-list; `no-store`, `no-referrer` |

- **Raw store URLs are never sent to clients**; offers carry `buy_path = /v1/out/{id}`, so every purchase is tracked and affiliate tagging can be added in one place (CP21).
- **Seed:** `make seed` (refuses `APP_ENV=production`). The mock catalog is deterministic: fictional brands, placeholder images, real store *search* links.
- **Performance:** client-side UUIDv7 ids + no eager defaults (ADR 0008) batch inserts: a full ingest is ~37 statements.

## 2i. AI gateway *(built)*

| Piece | Where | Notes |
|---|---|---|
| Gateway | `ai/gateway/gateway.py` | `run(TaskSpec, input, user_id=…)` → validated Pydantic output; `embed(ref, texts)` |
| Tasks | `ai/gateway/tasks.py` | Instructions + input/output schemas + `prompt_version`, in code. User data is sent as JSON inside `<input>` tags and the system prompt forbids following instructions inside it |
| Routing & prices | `llm_task_configs`, `llm_models` | Hot-reloaded on every instance via a Redis version counter; a model with no price is never called |
| Providers | `integrations/llm/` | OpenAI (chat + embeddings), Anthropic (chat); enabled only when their key is set; SDK retries off |
| Guards | gateway + `guards/circuit_breaker.py` | Input cap → per-user quota (30/h) → cache → single-flight → daily budget → per-target breaker + bulkhead → timeout + retries (backoff, Retry-After ≤ 5 s) → JSON validation + one repair → next target |
| Ledger & telemetry | `llm_usage`, `ai/gateway/metrics.py` | One row per attempt with cost in micro-USD; Prometheus `llm_*` metrics; OTel GenAI spans |
| Admin | `/v1/admin/ai/*`, CLI `llm-price`, `llm-route`, `llm-check` | See `docs/guides/ai-setup.md` |
| Embeddings | `integrations/embeddings/gateway.py` | `APP_EMBEDDING_MODEL=provider:model` switches the catalog from hashing to a real model (auto re-embed) |

**Degraded mode:** the gateway raises `AIUnavailableError` (not configured, disabled, budget exhausted, or every target failed); callers catch it and fall back to rule-based behaviour. The catalog already does: embedding is deferred, never lost.

## 2j. Generative UI protocol *(built)*

```
POST /v1/stylist/sessions ──► flow.start ──► UiEnvelope (turn 1) ──► stylist_sessions.envelope
POST …/actions {turn_id, action}
   ├─ validate action against the stored screen (422)
   ├─ claim turn: UPDATE … WHERE turn_id=:t AND status='active' (409 if lost)
   └─ background task: flow.act ─► ui.loading … ─► persist screen + session_events ─► ui.render ─► done
                         (queue) ─► SSE frames to the client (keep-alive every 15 s)
GET …/sessions/{id} ──► last screen (resume)
```

| Piece | Where | Notes |
|---|---|---|
| Component catalog | `genui/components.py` | 14 typed components, strict limits (ids, lengths, counts); `CATALOG_VERSION` = 2 (`product_detail`, `product_carousel`); buy links must be `/v1/out/…` |
| Actions | `genui/actions.py` | 8 action types; `validate_action` checks them against the rendered screen |
| Versioning | `genui/versioning.py` | `X-GenUI-Version`; newer components become an "update the app" banner in the same slot; too-old apps get 426 |
| Contract | `contracts/genui.schema.json` | JSON Schema the mobile types are generated from; a test fails if it drifts (`make contracts`) |
| Engine | `modules/stylist/service.py` | CAS turns, background turns, failure → safe fallback screen (never stuck busy) |
| Flows | `modules/stylist/flows/` | `Flow` protocol; `DemoFlow` (scripted: category → budget → deck → store comparison, back/restart/swipe); the LangGraph stylist plugs in at CP8 |

Try it locally without Google: `python -m stylesense.cli dev-token you@example.com` (refuses production), then call the API with the access token.

## 2k. AI stylist *(built)*

Code: `modules/stylist/flows/stylist.py` (graph), `understanding.py` (rules), `ranking.py`, `explain.py`, `tasks.py` (AI tasks), `slots.py`, `evals/`.

- **One LangGraph run per turn**, no checkpointer (ADR 0012). Input: the session's persisted state; output: a `Rendered` screen + new state, saved by the session engine.
- **Understand:** `parse_request` (regex tables, Hinglish budgets, size numbers ignored) → slots. If a required slot is still empty and AI is available, `stylist.understand` fills it; it never overrides a value.
- **Ask:** template questions for `category → gender → budget`; the question echoes what was understood ("Got it: summer t-shirts. Who is it for?").
- **Search → rank:** `CatalogService.search` filters in SQL and orders by pgvector distance (falls back to rating if embedding is unavailable); `rank()` scores and diversifies; deck of 10, "more" pages through.
- **Explain:** rule reasons always; one batched `stylist.explain` call may rephrase them.
- **Degraded:** `AIUnavailable`, quota and input-size errors set `ai: "degraded"` and the turn carries on with rules.
- **Evals:** `python -m stylesense.cli eval-understand` (rules, offline) or `--engine llm` (needs a key). The golden set isn't held-out yet; see ADR 0012.
- The scripted `demo` flow stays registered so sessions started on it keep working.

## 2l. Personalization: swipes, taste, Style DNA *(built)*

Code: `modules/personalization/` (`taste.py` maths, `styles.py` vocabulary, `service.py`), `modules/stylist/flows/style_dna.py` (onboarding), `modules/stylist/ports.py` (`TasteSource`, what the stylist needs).

- **Swipe** (`POST /v1/me/swipes`, or the `swipe` GenUI action): one transaction inserts the swipe (unique per user/product/session, replays return `recorded: false`), locks the profile row, updates the taste vector (EMA) and tag affinity, commits. Category/gender tags are excluded: they're hard filters already. ADR 0013.
- **Ranking with taste:** `rank(..., affinity=)` switches to `0.30 match + 0.25 similarity + 0.25 taste + 0.20 rating`, where taste = mean(taste-vector similarity from SQL, tag affinity score). With no taste, the CP8 weights apply unchanged. When the request has no text, SQL orders candidates by taste-vector distance.
- **Deck refill** (`GET /v1/stylist/sessions/{id}/deck?exclude=…&limit=…`): read-only, no turn; excludes swiped and held cards; rule reasons only (cheap prefetch). 409 `no_deck` while the stylist is still asking.
- **Style DNA:** `POST /v1/stylist/sessions {entry: "onboarding"}` runs the `style_dna` flow (fit → styles image grid → sizes; skip/back everywhere; saved once at the end, session ends). Also `GET/PUT /v1/me/style-profile` and `/options`. New picks blend into an existing taste (50%) instead of replacing it; an embedding outage still saves the answers.
- **Prefill:** fit preference answers the gender question (the request still wins: "dress for my wife" stays women); the saved size filters the deck, falling back to all sizes when nothing is left.
- **Observe:** `swipes_total{direction,outcome}`; dashboard panels "Swipes by direction" and "Swipe p95 latency".

## 2m. Detail, comparison and complete the look *(built)*

Code: `modules/catalog/rules.py` (`best_offer`, `needs_alternatives`, `pick_alternatives`, `TYPICAL_PRICE_PAISE`), `CatalogService.alternatives`, `modules/looks/` (`rules.py` pure outfit logic, `service.py`, `tasks.py`), the stylist's `_detail` node. ADR 0014.

- **Detail screen** (after `card_open`): `product_detail` → `store_comparison` → `product_carousel` "Similar picks" (only when < 2 stores have it in stock) → `complete_the_look` → `budget_slider` `q_look_budget` → back/restart. Opening a look or similar item pushes history, so Back walks back item by item. Setting the look budget re-renders the same screen.
- **Best price:** one rule everywhere: cheapest in-stock offer, ties to the better rating, then store code. `is_best` is on exactly one offer when anything is in stock.
- **Complete the look:** slots per anchor category (`COMPLEMENTS`), a layer only for cold occasions. Candidates per category come from catalog search (same gender, capped price). Score = colour harmony + occasion fit + rating; casual/dressy clashes are excluded. The combination is chosen exactly over a small shortlist under the budget. Without a look budget, pieces are capped at typical category prices; with one, the whole look (anchor included) stays within it.
- **AI:** `look.complete` only renames and rewords, in signed-in sessions when AI is configured; the REST endpoints are rules-only and cacheable.

## 2n. Boards, shares, polls *(built)*

Code: `modules/boards/`, `modules/sharing/`, `modules/polls/`; routes `api/v1/boards.py`, `api/v1/social.py` (owner + `/v1/public/*`); `api/preconditions.py` (If-Match); `platform/slugs.py` (slugs, HMAC pseudonyms). ADR 0015.

- **Boards:** each write locks the board row, checks `If-Match` when the operation needs it (rename, cover, reorder), bumps `version` and returns it as `ETag`. Item saves and removes are idempotent (unique key) and need no version. `wishlist` is a path alias, created on first use. Limits: 50 outfit boards, 200 items each.
- **Idempotent creates:** boards and polls accept a client UUID (replay → 200, same row); shares dedupe by content hash (same look → same slug).
- **Public routes** (`/v1/public/...`, no auth, `public.per_ip` 120/min): share pages (products + live prices, no owner data; 410 when revoked or the board is gone) and poll pages.
- **Votes:** `X-Voter-Token` header (the web page's random token). One vote per token per poll (unique key, race-safe; same vote again = replay, other option = 409). 25 new votes per IP per poll per day plus `votes.per_ip` 30/min. Only HMAC pseudonyms are stored. Results show after voting; the owner sees them live (`GET /v1/polls/{id}`).
- **Links** point at `APP_PUBLIC_WEB_URL` (`/l/{slug}`, `/p/{slug}`), the public Next.js site (CP18) that opens the app via App Links.

## 2o. Photos, shop from a photo, virtual try-on *(built)*

Code: `modules/uploads/` (port, service), `integrations/media/cloudinary.py`, `modules/tryon/` (jobs, reports), `integrations/tryon/fake.py`, the stylist's `_from_photo`, routes `api/v1/media.py`. ADRs 0016 and 0017; setup in `guides/cloudinary-setup.md`.

- **Upload:** `POST /v1/uploads {kind}` → signed form → the app POSTs the file **directly to Cloudinary** → `POST /v1/uploads/{id}/confirm` inspects the stored file (format, ≤ 8 MB, ≥ 200 px) → `ready` with a signed view URL. The preset re-encodes on arrival (≤ 1600 px, EXIF stripped). 30 uploads per user per day.
- **Photo search:** a stylist session with `entry: "photo", value: <upload id>`; `photo.understand` (vision bulkhead, 768 px signed URL) fills the slots, then the usual flow. Unusable photo, no AI, daily limit (10) or a bad id → a notice, and the stylist asks instead.
- **Try-on:** `POST /v1/tryon` (Idempotency-Key) → job + outbox message (advisory lock per user; active-job unique index) → worker renders via `TryOnProvider`, copies the result into Cloudinary, marks it `done` → app watches `GET /v1/tryon/{id}/events` (SSE). Busy → retried (≤ 3), then a friendly retryable failure; refused photo → final; `POST …/retry` is free. Quotas: 3/user/day, global daily cap.
- **Reports:** `POST /v1/reports`; reported try-on results are hidden immediately.
- **Purge:** worker `media.purge` every 15 min deletes expired photos and results from Cloudinary, then marks rows (storage first, so failures retry). `cli purge-media` runs it on demand.
- **Observe:** `tryon_jobs_total{outcome}`, `media_purged_total{kind}`; dashboard panels; runbook `media-and-tryon`.

## 2p. Mobile app foundation *(built)*

Code: `mobile/` (Expo SDK 57, expo-router). ADR 0018; product record `PRODUCT.md`.

- **Routes** (`src/app`): `_layout` loads fonts, restores the session, checks `/v1/app/config` for a forced update, then guards with `Stack.Protected`: `update` → `sign-in` → `(tabs)` (Home, Stylist, Saved, Me) + `session/[id]`.
- **Design system "Indigo & Block"** (`src/design`, `src/ui`): tokens (vat indigo shell, cotton ground, madder for actions only, turmeric for best price), Anek Latin type scale with per-variant font-scale caps, atoms → molecules → organisms. Signature moments: the buti block stamp on a like, the print-repeat loader.
- **API** (`src/api`): `ApiClient` sends `X-GenUI-Version` / `X-App-Version`, times out every call, parses problem+json into `ApiError`, and on 401 does one shared refresh then retries once. Types come from `backend/contracts` (`npm run gen`; CI fails on drift).
- **Auth** (`src/auth`): refresh token in SecureStore, access token in memory; dev sign-in (`POST /v1/auth/dev`) when the server allows it.
- **GenUI** (`src/genui`, `src/stylist`): the renderer maps each component type to an organism; unknown types show an update prompt. The stylist store keeps one turn in flight and recovers from `stale_turn` / `session_busy`. The swipe deck records swipes over REST and refills itself.
- **Quality:** Jest (jest-expo + Testing Library), `tsc --strict`, `expo lint`; `mobile-ci` workflow also bundles for Android.

## 2q. Mobile stylist experience *(built)*

Code: `mobile/src/api/sse.ts`, `api/client.ts` (`events`), `stylist/store.ts`, `app/session/[id].tsx`, `genui/navigation.ts`, `boards/wishlist.ts`, `onboarding/`, `app/welcome.tsx`, `lib/perf.ts`. ADR 0019.

- **Streamed turns:** actions are POSTed with `Accept: text/event-stream`; `ui.loading` shows a skeleton of the coming screen (`organisms/Skeleton`), `ui.render` fades the new screen in, `error` keeps the screen and shows a banner. A dropped stream resumes from `GET /v1/stylist/sessions/{id}` (polling while `busy`) and is never resent.
- **Back:** Android back sends the screen's own Back action; with none, it leaves the session.
- **Detail:** the save heart (wishlist, optimistic, idempotent PUT/DELETE) sits on the photos; a docked buy bar opens the best in-stock offer through `/v1/out/{offer}?src=detail`.
- **Swipe deck:** gesture and animation on the UI thread, memoised cards, the next three photos prefetched to the disk cache, `expo-image` recycling.
- **Onboarding:** a one-time welcome after the first sign-in for anyone without a Style DNA; the Me tab shows the Style DNA card (chosen looks, sizes, learned tags) with Retake.
- **Measured:** `tap_to_products` (tap → first deck), logged in development (Metro terminal) and sent as a breadcrumb.

## 3. Request lifecycle: a stylist turn *(built)*

1. The user types **"summer t-shirt under 500"** → `POST /v1/stylist/sessions {entry: "search", value: …}`.
2. Graph: `ingest → understand` (rules: category tshirt, occasion summer, budget ≤ ₹500) → `decide`: gender missing → `ask` builds a `chip_question` → screen saved with `turn_id = 1` and returned.
3. The user taps **"Men"** → `POST …/actions {turn_id: 1, action: chip_select}` with `Accept: text/event-stream`. CAS claims the turn (ADR 0011).
4. Graph: `ingest` (gender = men) → `search` streams a `ui.loading` skeleton → SQL filters + pgvector → `rank` → `explain` → `compose` → `ui.render` (a `product_swipe_deck`) → `done`.
5. Swipes go to `POST /v1/me/swipes` (fast, idempotent); they update taste immediately, and the app prefetches more cards from `GET …/deck` before the deck runs out.
6. "Buy" → `GET /v1/out/{offer_id}` → click logged → 302 to the store.

## 4. LLM call lifecycle *(built)*

```
graph node → gateway.run(task, …)
  → load task config (Redis cache ← Postgres)
  → check quotas (per user) + global budget
  → response cache lookup (Redis)          → hit: return
  → count tokens, enforce max_input_tokens
  → circuit breaker for (provider, model)  → open: next fallback
  → call provider (timeout, retries w/ backoff)
  → validate output against Pydantic schema (1 repair attempt)
  → record usage (llm_usage + Langfuse), update budget, cache result
  → all options failed → degraded mode (rule-based result)
```

## 5. Data model summary
See `05-db-design.md`. Key ideas: canonical **products** + per-store **offers**; money in **paise**; **embeddings** on products and a **taste vector** per user; stylist session state lives in `stylist_sessions` (no LangGraph checkpoint tables, ADR 0012).

## 6. Deployment *(homelab: built; hardening: planned)*
Homelab → Docker Compose (`compose.yml` + `compose.prod.yml`) → `cloudflared` container → Cloudflare Tunnel → the internet. No inbound ports, nothing published on the host; Cloudflare terminates HTTPS and forwards to `api:8000`. One domain serves the API, share/poll pages and the legal pages.
- `scripts/deploy.sh` (`make deploy`): pull `main`, back up, build, migrate, restart, set LLM routes (`scripts/bootstrap-ai.sh`).
- `backup` container: nightly `pg_dump` at 02:30 IST into `./backups`, 7 days kept; `scripts/restore.sh` restores one.
- Guide: `docs/guides/homelab-deploy.md`. Still planned for CP19: Caddy (if a second app shares the host), off-site encrypted backups, alert rules, load and ZAP tests. See `03-technical-spec.md` §13–14.

## 7. Local development *(built)*

Prerequisites: Docker, [uv](https://docs.astral.sh/uv/), `make` (Windows: `winget install ezwinports.make`).

```bash
make setup     # deps, git hooks, .env from .env.example
make up        # postgres + redis + migrate + api (hot reload) -> http://localhost:8000/docs
make check     # lint, format, mypy --strict, import layers, tests + coverage gate
make help      # every command
```

Observability: `make obs-up` adds Grafana (http://localhost:3001), Prometheus (:9090), GlitchTip (:8001), Uptime Kuma (:3002), Tempo and the OTel Collector. First run: create a GlitchTip account and project, then put its DSN in `APP_SENTRY_DSN`.

Dev host ports come from `.env` (`POSTGRES_HOST_PORT=5434` by default, to avoid clashing with a native Postgres or other projects).

**The app on a phone (Expo Go):** set `APP_DEV_SIGN_IN_ENABLED=true` in `.env`; start the API on the LAN with `API_BIND=0.0.0.0 API_HOST_PORT=8010 make up`; put `EXPO_PUBLIC_API_URL=http://<your-pc-ip>:8010` in `mobile/.env.local`; `cd mobile && npx expo start --lan`; scan the QR with Expo Go (same Wi-Fi) and sign in with any email.

## 8. Where to look for…

| I want to… | Go to |
|---|---|
| Add a config value | `platform/config.py` (`APP_*` env var, validated) + `.env.example` |
| Add an error type | Subclass `AppError` in `platform/errors.py` or the module's `exceptions.py` |
| Add a metric | Define it next to its owner with the app's registry; label by bounded values only (route template, status), never ids |
| Log something | `structlog.get_logger(__name__).info("event_name", key=value)`; never log raw request bodies |
| Investigate a user report | Ask for the `X-Request-ID` → search logs → open the trace by `trace_id` in Tempo |
| Protect a route | Take `claims: Claims` (from `api/auth.py`); add `Depends(require_role(Role.ADMIN))` for admin-only |
| Add a new identity provider | Implement `IdentityVerifier` in `integrations/`, wire it in `bootstrap/container.py` |
| Add a product source | Implement `ProductSource` (`modules/catalog/ports.py`) in `integrations/sources/`; ingest it with `CatalogService.ingest` |
| Swap the embedder | Implement `Embedder`; wire it in `bootstrap/container.py`; the worker re-embeds automatically |
| Return cacheable reads | `api/http_cache.etag_response(request, model, max_age_s=…)` |
| Add an AI task | Define a `TaskSpec` (instructions, schemas, `prompt_version`); route it with `llm-route`; catch `AIUnavailableError` and degrade |
| Add an AI provider | Implement `ChatProvider` (and/or `EmbeddingProvider`) in `integrations/llm/`; register it in `bootstrap/container.py` and `KNOWN_LLM_PROVIDERS` |
| Add a GenUI component | Add props + component in `genui/components.py`, register it in `INTRODUCED_IN` with the new catalog version, bump `CATALOG_VERSION`, run `make contracts` |
| Add a stylist flow | Implement `Flow` (`start`, `act` yielding `Progress`… then one `Rendered`); register it in `bootstrap/container.py` |
| Teach the stylist a new phrase | Add the term to the tables in `modules/stylist/understanding.py`, add a line to `evals/understand_golden.jsonl`, run `eval-understand` |
| Tune ranking | Weights and diversity penalty in `modules/stylist/ranking.py`; the property test guards the budget |
| Tune taste learning | Rates and caps in `modules/personalization/taste.py`; the exit test in `tests/integration/stylist/test_personal_flow.py` measures the shift |
| Add a Style DNA look | Add a `Style` (label, catalog tags, colour) to `modules/personalization/styles.py` |
| Plug in a real try-on vendor | Implement `TryOnProvider` in `integrations/tryon/`, wire it in `_tryon_provider` (container), add its settings; tests use `tests/fakes/media.py` |
| Swap image storage | Implement `MediaStore` (`modules/uploads/ports.py`) in `integrations/media/` |
| Make a write safe across devices | Version column + row lock in the service; `IfMatch` dependency and `set_version` in the route (see `api/v1/boards.py`) |
| Add a public (no sign-in) endpoint | Put it on `social.public` (`/v1/public`, per-IP limit); never return owner data |
| Change what goes with what | `COMPLEMENTS`, colour and occasion rules in `modules/looks/rules.py`; the property tests guard budget and clashes |
| Make a write endpoint safe to retry | Take `IdempotencyKey` as a dependency and wrap the use case in `run_idempotent(...)` |
| Trigger a side effect after a write | `container.outbox.add(uow.session, topic, payload)` in the same Unit of Work; register a handler for `topic` |
| Add a cron job | `PeriodicTask(..., exclusive=True)` in `workers/app.py` |
| Rate-limit a route differently | `Depends(rate_limited("policy.name"))`; add the policy to `DEFAULT_POLICIES` |
| Add a dependency probe | Implement `HealthCheck` in `infra/health.py`, register it in `bootstrap/container.py` |
| Add a new UI component | Backend `genui/components.py` → `make contracts` → a case in `mobile/src/genui/Renderer.tsx` built from `src/ui` pieces |
| Add a screen | A file in `mobile/src/app/`; use `src/ui` atoms/molecules and `useTheme()` tokens, never raw colours |
| Call a new endpoint from the app | `api.get/post<Type>(path)` from `@/auth/session`, with types from `@/api/types` (regenerate after backend changes) |
| Change which model a task uses | Admin → AI → Task configs (or `llm_task_configs`) |
| Add a new AI provider | `backend/src/stylesense/ai/gateway/providers/` |
| Add a product source | `backend/src/stylesense/integrations/sources/` (implement `ProductSource`) |
| Change the stylist flow | `backend/src/stylesense/modules/stylist/flows/stylist.py` |

---

## Changelog

| Checkpoint | Date | What changed in the system |
|---|---|---|
| CP0 | 2026-10-04 | Initial docs: product, business, spec, slices, DB design, checkpoints, this doc, key concepts. |
| CP0 | 2026-10-04 | Added engineering standards (doc 09), root `CLAUDE.md`; checkpoints reordered backend-first. |
| CP1 | 2026-10-04 | Backend foundation: layered package (`platform`/`infra`/`bootstrap`/`api`), typed config, JSON logging, problem+json errors, DB engine + Unit of Work, Redis, `/healthz` + `/readyz`, Alembic baseline (vector, citext), multi-stage non-root Docker image, Compose stack, Makefile, pre-commit, CI. |
| CP2 | 2026-10-04 | Observability: request ids, PII-redacted JSON logs with trace correlation, RED + pool metrics on `/metrics`, OpenTelemetry tracing (API, SQLAlchemy, Redis) via collector → Tempo, GlitchTip error reporting, provisioned Grafana dashboard, Uptime Kuma, runbooks. SQLAlchemy pinned <2.1. |
| CP3 | 2026-10-04 | Reliability guards: Redis idempotency (fail-closed), exact sliding-window + token-bucket rate limits on `/v1` (fail-open), load shedding, distributed locks, single-flight, bulkheads; transactional outbox (`SKIP LOCKED`) + worker process with heartbeat, metrics and graceful shutdown; model registry + migration drift test; exception logs no longer include stack-frame locals. |
| CP4 | 2026-10-05 | Auth & accounts: Google ID-token verification, own HS256 access JWT + rotating hashed refresh tokens with reuse detection and grace window, one session per install, roles + admin allow-list, `/v1/auth/*`, `/v1/me` (profile, devices, consents, deletion with 30-day outbox purge), `/v1/app/config`, per-user and auth rate limits, token pruning task; migration 0003. |
| CP5 | 2026-10-05 | Catalog: stores (with redirect allow-lists), canonical products + offers, price snapshots, outbound clicks; deterministic 300-product mock source; idempotent ingest; Embedder port + hashing embedder and pgvector HNSW similarity; `/v1/products`, `/v1/products/{id}` (ETag), `/similar`, `/v1/out/{offer_id}`; `make seed` CLI; worker embedding task; client-side UUIDv7 ids + batched inserts; migration 0004. |
| CP6 | 2026-10-05 | AI gateway: OpenAI + Anthropic adapters, DB routing + prices hot-reloaded via Redis, fallbacks, Redis-shared circuit breaker, retries with Retry-After, input cap, response cache + single-flight, per-user quota, daily budget, bulkheads, JSON validation + repair, `llm_usage` ledger, Prometheus + OTel GenAI telemetry, admin AI API + CLI, gateway-backed embedder; migration 0005; ADRs 0009–0010. |
| CP7 | 2026-10-05 | GenUI protocol: typed component catalog v1 + actions + versioning + JSON Schema contract; stylist sessions with turn compare-and-swap, action-scoped SSE (ADR 0011), background turns that survive disconnects, failure fallback, session event log (90-day pruning); scripted demo flow over the real catalog; `dev-token` CLI; migration 0006. |
| CP8 | 2026-10-05 | AI stylist: LangGraph graph run per turn without a checkpointer (ADR 0012); rules-first request understanding (Hinglish budgets) with LLM gap filling; template questions; catalog hybrid search (SQL filters + pgvector); code ranking with diversity; rule reasons + optional batched LLM explain; degraded mode; golden eval set + `eval-understand` CLI; stylist is the default flow. |
| CP9 | 2026-10-05 | Personalization: `style_profiles` + `swipes` (migration 0007); idempotent swipe endpoint with synchronous taste learning (EMA vector + tag affinity, row lock; ADR 0013); taste-aware ranking and "Your style" reasons; deck refill endpoint; Style DNA onboarding flow + `/me/style-profile` API with taste seeding; gender/size prefill; `swipes.per_user` bucket, `api.per_ip` 60 → 600/min; swipe dashboard panels. |
| CP10 | 2026-10-05 | Detail screen: GenUI catalog v2 (`product_detail`, `product_carousel`), store comparison with a similar-items fallback (`/products/{id}/alternatives`), complete-the-look rules (slots, colour harmony, occasion register, exact budgeted assembly) with optional `look.complete` wording, whole-look budget slider, `/products/{id}/complete-look` (rules only, ETag); one best-offer rule for ingest and display; property tests for best price and look budgets; ADR 0014. |
| CP11 | 2026-10-05 | Boards (wishlist alias + outfit boards) with optimistic locking (ETag/If-Match, 428/412) and idempotent item saves; share links (content-idempotent slugs, public page with live prices, revoke → 410); polls with public token voting (unique per token, per-IP-per-poll cap, `votes.per_ip`, `public.per_ip`, HMAC pseudonyms); client-id idempotent creates; `APP_PUBLIC_WEB_URL`; CORS allows If-Match / X-Voter-Token and exposes ETag; migration 0008; ADR 0015. |
| CP12 | 2026-10-05 | Photos via Cloudinary (ADR 0016, supersedes 0003): signed direct uploads, server-side verification, authenticated delivery with signed URLs, 24 h purge (storage first, SET NULL user FKs); vision support in the LLM gateway (image parts for OpenAI/Anthropic, vision bulkhead) and `photo.understand`; shop from a photo via the stylist; try-on as outbox jobs (ADR 0017) with double-tap protection, retries, free retry, quotas and a global cap, SSE progress; content reports; `cli purge-media`; metrics + panels; runbook; migration 0009. |
| CP15 | 2026-10-05 | Mobile foundation (ADR 0018): Expo SDK 57 app with expo-router guards, "Indigo & Block" design system (tokens, Anek Latin, atoms/molecules/organisms), API client with shared refresh and problem errors, SecureStore session, force-update screen, GenUI renderer for all 14 component types + stylist store + swipe deck; generated contract types checked in CI (`mobile-ci`); backend `POST /v1/auth/dev` (non-production) and `python -m stylesense.main openapi`; dev API can bind to the LAN. CP13/CP14 deferred. |
| CP16 | 2026-10-05 | Mobile stylist (ADR 0019): streamed turns over SSE with shape-aware skeletons and resume-not-resend; Android back follows the server's Back; detail save heart (wishlist) and docked best-price buy bar; swipe deck prefetch + memoised cards; one-time welcome / Style DNA onboarding and a Style DNA card on Me; `tap_to_products` timing. |
| CP19 (part) | 2026-10-17 | Homelab production deploy: `compose.prod.yml` (production env, Cloudflare Tunnel, nightly backups), `.env.prod.example`, deploy/restore/AI-route scripts, `make deploy`/`prod-*`, APK builds point at the public URL. CP17 stylist: open item categories, typo-tolerant items, only the item is required (gender and budget are optional taps), Style DNA is one screen. |
