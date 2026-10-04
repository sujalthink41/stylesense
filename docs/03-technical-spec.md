# 03 — Technical Specification

This document defines **how** StyleSense is built. Slices (doc 04) break it into buildable features; checkpoints (doc 06) give the build order.

## 1. Requirements

### 1.1 Functional
See the feature list in `01-product-overview.md` §6 (F1–F14).

### 1.2 Non-functional

| Area | Target |
|---|---|
| Scale (design point) | 1,000 DAU, ~10 sessions/min average, 5× peak bursts. Stateless API so it can scale horizontally later. |
| Latency | API p95 < 300 ms (non-AI). First generative-UI component streamed < 1.5 s. First products visible < 5 s. |
| Availability | 99.5% monthly (homelab realistic). Graceful degradation when AI is down. |
| AI cost | Hard daily global cap plus per-user quotas. Every call metered. |
| Security | OWASP ASVS L1 baseline, JWT with refresh rotation, secrets only in env, least-privilege DB roles. |
| Privacy | India DPDP Act 2023: consent, export and deletion. Selfies auto-deleted. |
| Observability | Structured logs, metrics, traces, LLM traces, error tracking, uptime alerts. |
| Cost | All infrastructure free/self-hosted. Paid items: AI tokens, try-on API, Play Store fee, domain. |

## 2. Architecture overview

```
┌────────────────────┐      HTTPS (Cloudflare Tunnel)      ┌──────────────────────────────────────────┐
│ Mobile app (Expo)  │ ──────────────────────────────────▶ │ Caddy (reverse proxy)                    │
│ GenUI renderer     │ ◀── SSE stream of UI envelopes ──── │                                          │
└────────────────────┘                                     │  ├─ api       FastAPI (stateless, N pods)│
┌────────────────────┐                                     │  ├─ worker    ARQ background workers     │
│ Admin (Next.js)    │ ──────────────────────────────────▶ │  ├─ admin     Next.js admin + public web │
└────────────────────┘                                     │  ├─ postgres  PG 18 + pgvector           │
┌────────────────────┐                                     │  ├─ redis     cache/limits/queue         │
│ Public web pages   │ (poll vote, share, delete account)  │  ├─ minio     object storage             │
└────────────────────┘                                     │  ├─ langfuse  LLM tracing                │
                                                           │  └─ glitchtip, prometheus, grafana,      │
                                                           │     uptime-kuma                          │
                                                           └──────────────────────────────────────────┘
                                                                 │                     │
                                                    LLM providers (OpenAI default,   Try-on provider
                                                    swappable via config)            (swappable)
```

## 3. Tech stack

### 3.1 Mobile: React Native
| Concern | Choice |
|---|---|
| Framework | Expo (SDK latest) + TypeScript (strict) + expo-router |
| Client state | Zustand (GenUI session store) |
| Server state | TanStack Query |
| Animation & gestures | react-native-reanimated + react-native-gesture-handler |
| Images | expo-image |
| Local storage | react-native-mmkv; expo-secure-store for tokens |
| Auth | Google Sign-In (native) → backend token exchange |
| Push | expo-notifications + FCM |
| Crash/analytics | Firebase Crashlytics + Analytics |
| Share card | react-native-view-shot (rendered on device, so zero server cost) |
| SSE | react-native-sse (or fetch streaming) |
| Testing | Jest + React Native Testing Library; Maestro for E2E |

### 3.2 Backend: Python
| Concern | Choice |
|---|---|
| API | FastAPI + Uvicorn, Python 3.12+ |
| Validation | Pydantic v2 (all I/O, including every LLM output) |
| DB access | SQLAlchemy 2.0 (async) + asyncpg; Alembic migrations |
| AI orchestration | LangGraph (Postgres checkpointer) |
| LLM abstraction | Own `LLMGateway` over LangChain `init_chat_model` (provider-agnostic) |
| Background jobs | ARQ (async-native, Redis-backed) + scheduled cron jobs |
| Rate limiting | Redis sliding-window/token-bucket (own middleware; `limits` library) |
| Resilience | `pybreaker`-style circuit breaker (Redis-shared state) + `tenacity` retries |
| Auth | Google ID-token verification (`google-auth`) + own JWT (PyJWT) |
| Storage | MinIO through the S3 API (boto3/aioboto3) |
| Embeddings search | pgvector (HNSW indexes) |
| Observability | structlog (JSON), OpenTelemetry, prometheus-fastapi-instrumentator, Sentry SDK → GlitchTip, Langfuse SDK |
| Testing | pytest, pytest-asyncio, httpx, testcontainers (real Postgres/Redis) |
| Tooling | uv (deps), ruff (lint/format), mypy (types), pre-commit |

### 3.3 Admin & public web
Next.js (App Router) + TypeScript + shadcn/ui + TanStack Query/Table + Recharts. It holds the admin dashboard (role-protected) and the public pages (poll voting, share landing, account deletion, privacy policy, terms).

### 3.4 Infrastructure (homelab)
Docker Compose (separate `dev` and `prod` profiles), Caddy, Cloudflare Tunnel, GitHub Actions CI, GHCR images, nightly `pg_dump` + MinIO mirror to off-site storage, UPS.

## 4. Repository layout (monorepo)

> The backend layout (modular monolith with `platform`/`infra`/`guards` layers) is defined in `09-engineering-standards.md` §2 and takes precedence over the backend tree below.

```
StyleSense/
├── docs/                 # these docs
├── mobile/               # Expo app
│   └── src/genui/        # component registry + renderer
├── backend/
│   ├── app/
│   │   ├── api/          # routers (v1)
│   │   ├── core/         # config, security, logging, errors
│   │   ├── db/           # models, session, migrations (alembic)
│   │   ├── domain/       # services per module (catalog, users, boards, polls…)
│   │   ├── ai/
│   │   │   ├── gateway/  # LLMGateway, providers, breaker, budgets
│   │   │   ├── graphs/   # LangGraph graphs (stylist, photo_search…)
│   │   │   ├── prompts/  # versioned prompt templates
│   │   │   └── genui/    # component schemas (Pydantic) = the contract
│   │   ├── sources/      # product source adapters (mock, amazon, flipkart, network)
│   │   ├── tryon/        # try-on provider adapters
│   │   └── workers/      # ARQ tasks & cron
│   └── tests/
├── admin/                # Next.js admin + public pages
├── packages/
│   └── genui-schema/     # JSON Schema generated from Pydantic → TS types for mobile/admin
└── infra/
    ├── compose/          # docker-compose.*.yml
    ├── caddy/
    └── scripts/          # backup, restore, seed
```

**Single source of truth for the GenUI contract:** Pydantic models in `backend/app/ai/genui/` → exported to JSON Schema → TypeScript types generated for mobile and admin in CI. Contract drift fails the build.

## 5. Generative UI (GenUI) protocol

### 5.1 Concept
The server decides **what UI to show next**. The client is a **renderer** of a fixed, versioned component catalog. The LLM only ever chooses from that catalog and fills its props. The LLM output is validated, never trusted.

### 5.2 Server → client: UI envelope (SSE events)

```json
{
  "event": "ui.render",
  "session_id": "018f…",
  "turn_id": 7,
  "mode": "append",                      // append | replace | patch
  "components": [
    {
      "id": "c_budget",
      "type": "chip_question",
      "v": 1,
      "props": {
        "question": "What's your budget?",
        "options": [
          {"id": "lt500", "label": "Under ₹500"},
          {"id": "500_1000", "label": "₹500–1,000"},
          {"id": "gt1000", "label": "₹1,000+"}
        ],
        "multi": false,
        "allow_custom": true
      }
    }
  ],
  "suggestions": [{"id": "s1", "label": "Surprise me", "action": {"type": "shortcut", "value": "surprise"}}],
  "state": {"slots": {"category": "tshirt", "occasion": "summer"}, "step": "ask_budget"}
}
```

SSE event types: `ui.render`, `ui.patch` (update one component's props, e.g. a loading → loaded card), `ui.loading` (skeleton placeholders), `session.state`, `error`, `done`.

### 5.3 Client → server: action

```json
POST /v1/stylist/sessions/{session_id}/actions
{ "turn_id": 7, "idempotency_key": "uuid", "action": {"type": "chip_select", "component_id": "c_budget", "value": ["lt500"]} }
```

Action types: `chip_select`, `slider_set`, `swipe` (`left`/`right`/`super`), `card_open`, `text_input`, `photo_input`, `shortcut`, `back`, `restart`.

- `turn_id` guards against stale taps (an action on an old turn is rejected with `409`).
- `idempotency_key` makes retries safe on flaky mobile networks.

### 5.4 Component catalog v1

| Type | Purpose |
|---|---|
| `chip_question` | Single/multi choice chips, optional custom text |
| `budget_slider` | Min–max ₹ range |
| `image_choice_grid` | Pick styles visually (Style DNA, "which vibe?") |
| `product_swipe_deck` | Stack of product cards for swiping |
| `product_card` | Single product with price, store, rating, why-this-pick |
| `product_detail` | Full detail: images, sizes, offers, actions |
| `store_comparison` | Offers across stores, best price highlighted |
| `why_this_pick` | Attribute-based reason chips |
| `complete_the_look` | Horizontal rail of matching items with a budget meter |
| `tryon_result` | Try-on image + status (pending/done/failed) |
| `poll_card` | Create or view a friend poll |
| `share_card` | Outfit card for sharing |
| `suggestion_bar` | Next-step quick actions |
| `info_banner` | Small notice (e.g. "Showing similar items, exact match not found") |
| `empty_state` | Nothing found + recovery chips |
| `text_input_bar` | Optional free text/photo input (always available) |

### 5.5 Versioning & compatibility
- Each component has a version `v`. The client sends `X-GenUI-Version` (catalog version supported).
- The server never sends a component/version the client doesn't support. If it must, it degrades to a supported one.
- The client renders unknown types as a safe fallback (`info_banner`), never crashes.

### 5.6 Where state lives
| State | Owner | Store |
|---|---|---|
| Conversation/flow state (slots, step, shown products) | Server (authoritative) | LangGraph checkpoint in Postgres |
| Rendered component tree | Client (derived) | Zustand, rebuilt from server envelopes; resumable via `GET /sessions/{id}` |
| User profile, Style DNA, taste vector | Server | Postgres |
| Wishlist/boards | Server (client caches) | Postgres + TanStack Query cache |
| Ephemeral UI (scroll, animations) | Client | Component state |

## 6. AI layer

### 6.1 Stylist graph (LangGraph)

```
            ┌──────────────┐
 action ──▶ │ ingest_action│  (validate, apply to state; swipes update taste — no LLM)
            └──────┬───────┘
                   ▼
            ┌──────────────┐  text/photo?   ┌────────────────┐
            │ route        │ ─────────────▶ │ understand (LLM)│ → extracts slots from free text / image
            └──────┬───────┘                └───────┬────────┘
                   ▼                                ▼
            ┌──────────────┐  missing slot  ┌────────────────┐
            │ slot_check   │ ─────────────▶ │ ask_question   │ → deterministic templates (no LLM);
            └──────┬───────┘                │                │   LLM only to propose smart options
                   │ all slots filled       └───────┬────────┘   when the intent is unusual
                   ▼                                ▼
            ┌──────────────┐                 interrupt() → wait for next action
            │ retrieve     │  SQL filters (budget, size, category, gender) + pgvector similarity
            └──────┬───────┘
                   ▼
            ┌──────────────┐
            │ rank (code)  │  score = filters ∧ (w1·taste_sim + w2·rating + w3·budget_fit + w4·diversity)
            └──────┬───────┘
                   ▼
            ┌──────────────┐
            │ explain (LLM)│  one batched call: "why this pick" for top N, from attributes only
            └──────┬───────┘
                   ▼
            ┌──────────────┐
            │ compose_ui   │  build components + suggestions → stream → interrupt()
            └──────────────┘
```

Required slots (v1): `category`, `occasion`, `budget`, `size` (prefilled from Style DNA), `gender_fit` (from Style DNA), optional `color`, `fit`, `fabric`, `style`.

Other graphs: `photo_search` (vision → attributes → retrieve), `complete_the_look`, `trending_curation` (offline, cron).

### 6.2 LLM Gateway (provider-agnostic)

All AI calls go through `LLMGateway`. No code imports a provider SDK directly.

```python
result = await gateway.run(
    task="stylist.explain",          # task name → resolved to provider/model via config
    messages=[...],
    output_schema=WhyThisPickBatch,  # Pydantic → structured output
    user_id=user.id,
)
```

**Task routing config** (DB table `llm_task_configs`, cached in Redis, editable in admin, hot-reloaded):

| Task | Default | Notes |
|---|---|---|
| `stylist.understand` | OpenAI small/fast model | text → slots |
| `stylist.smart_options` | OpenAI small model | rare |
| `stylist.explain` | OpenAI small model | batched |
| `photo.understand` | OpenAI vision-capable model | image → attributes |
| `look.complete` | OpenAI mid model | outfit reasoning |
| `embed.text` | OpenAI embeddings model | catalog + queries |

Each task config holds: `provider`, `model`, `fallbacks[]` (ordered), `temperature`, `max_input_tokens`, `max_output_tokens`, `timeout_s`, `cache_ttl_s`, `prompt_version`, `enabled`.

Providers are registered adapters (`openai`, `anthropic`, `google`, `ollama`, …) behind one interface. API keys come only from environment variables or a secret file, never from the database.

### 6.3 Token optimization

1. **No LLM for deterministic steps.** Standard questions, swipes, ranking, filtering and UI composition are code.
2. **Compact state, not chat history.** The LLM receives a small structured summary: `{slots, liked_tags[top 10], disliked_tags, last_action}`.
3. **Compact product views.** The LLM sees `id | title ≤ 60 chars | price | 3 tags`, never full product JSON or images (except in photo search).
4. **Batching.** One explain call for the top N products, not N calls.
5. **Prompt caching.** The static prefix (system prompt + component schema + rules) comes first and is identical across calls, so provider-side prefix caching applies (OpenAI caches long, repeated prefixes automatically).
6. **Response cache.** Redis key = `hash(task, prompt_version, model, normalized_input)`. For example, explain results are cached per (product_id, slot signature).
7. **Hard limits.** `max_input_tokens` is checked before sending (tiktoken-based count; input is trimmed or rejected). `max_output_tokens` is always set.
8. **Image downscaling.** Photos are resized to ≤ 768 px and use a low-detail vision mode where possible.
9. **Embeddings computed once** per product at ingest and cached for queries.

### 6.4 Reliability

| Mechanism | Design |
|---|---|
| **Timeouts** | Per-task `timeout_s` (default 15 s; streaming first-token timeout 5 s). |
| **Retries** | `tenacity`: max 2 retries, exponential backoff + jitter, only on retryable errors (429, 5xx, timeouts). Respects `Retry-After`. Never retries 4xx validation errors. |
| **Circuit breaker** | Per `(provider, model)`, state in Redis, shared by all API instances. **Closed → Open** after 5 failures in 30 s or >50% error rate over 20 calls; **Open** for 60 s (fail fast); **Half-open** lets 1 probe call through; success → Closed. |
| **Fallback chain** | Primary model → `fallbacks[]` → **degraded mode** (rule-based: deterministic questions, plain ranking, template "why this pick" built from attributes). The user always gets UI. |
| **Output validation** | Pydantic-validate. On failure: 1 repair attempt (send the validation errors back), then degraded mode. Invalid components never reach the client. |
| **Bulkheads** | Separate concurrency limits (asyncio semaphores) per task class so try-on/vision load can't starve the stylist chat. |
| **Idempotency** | Actions with the same `idempotency_key` return the cached result (Redis, 10 min). |

### 6.5 Rate limiting & quotas

| Scope | Limit (defaults, admin-editable) | Algorithm |
|---|---|---|
| Per IP (unauthenticated) | 60 req/min | sliding window |
| Per user (all API) | 120 req/min | sliding window |
| Per user AI actions | 30/hour, 150/day | token bucket |
| Per user photo searches | 10/day | fixed daily counter |
| Per user try-ons | 3/day free | fixed daily counter |
| Poll votes | 1 per device per poll, 30/min per IP | unique + sliding window |
| **Global AI budget** | Daily USD cap (e.g. $X) | Running cost sum in Redis. At 80%: alert. At 100%: switch every task to its cheapest fallback or degraded mode; try-on paused. |

Responses include `X-RateLimit-Remaining` / `Retry-After`. The client renders a friendly `info_banner`, never a raw error.

### 6.6 AI safety
- User text and image-derived text are wrapped as **data**, never concatenated into instructions. The system prompt states the rules; output is schema-constrained, so the LLM cannot emit arbitrary UI or links.
- **Links never come from the LLM.** Product URLs come only from the database.
- Uploaded images go through a moderation check before processing.
- Try-on results get a "Report" action (Play Store AI-content policy).
- Prompts are versioned (`prompt_templates` table). Every LLM call logs `prompt_version` for reproducibility.

### 6.7 LLM observability
Every call → Langfuse trace with task, model, prompt version, tokens in/out, cost, latency, cache hit, breaker state and user id (pseudonymous). Costs are aggregated into `llm_usage` for the admin cost dashboard.

## 7. Product data layer

### 7.1 Model
**Canonical product** (what the item *is*) + **offers** (where it's sold, at what price). Store comparison = one product with several offers. When an exact match doesn't exist, comparison falls back to "similar items" by embedding similarity.

### 7.2 Source adapters
```python
class ProductSource(Protocol):
    name: str                                   # "mock", "amazon", "flipkart", "cuelinks"
    async def search(self, q: SearchQuery) -> list[RawOffer]: ...
    async def get_offer(self, external_id: str) -> RawOffer | None: ...
    def build_outbound_url(self, offer: Offer, ctx: ClickContext) -> str: ...   # affiliate tagging lives here later
```
v1 ships `MockSource` (seeded from `infra/seed/catalog.json`). Real adapters are added later behind feature flags without client changes.

### 7.3 Outbound clicks
Every "Buy" goes through `GET /v1/out/{offer_id}` → logged in `outbound_clicks` → 302 to the store URL (later the affiliate URL). This gives CTR analytics now and affiliate tracking later.

## 8. Feature-specific designs

- **Swipe learning:** each product has an embedding. The user's `taste_vector` is an exponential moving average: `taste = normalize(taste + α·liked − β·skipped)`. Tag counters also update. No LLM is involved.
- **Style DNA:** a tap-only onboarding writing to `style_profiles`. It seeds the taste vector from chosen style images.
- **Shop from photo:** upload → MinIO (private) → moderation → `photo.understand` (vision → attributes JSON) → embedding → retrieve + rank → UI.
- **Virtual try-on:** `POST /v1/tryon` → job row → ARQ worker → `TryOnProvider` adapter → result to MinIO → push + SSE patch. Selfies and results are deleted after 24 h (cron). Signed URLs expire in 15 min.
- **Polls:** create from 2–4 items → public URL `https://<domain>/p/{slug}` → web vote page (Next.js, no login; device cookie + rate limit). The owner sees live results in the app.
- **Share a look:** rendered on device with view-shot. Deep link `https://<domain>/l/{slug}` (Android App Links; falls back to the web page + Play Store link).
- **Trending feed:** a nightly cron builds curated collections (rules + an optional LLM title). The admin can pin or curate.
- **Price-drop alerts:** `price_snapshots` written on every offer refresh. A cron compares wishlisted offers; a drop ≥ threshold → notification + push. In v1 mock prices are changed from the admin to simulate drops.

## 9. API surface (v1, all under `/v1`)

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/google` (ID token → access+refresh), `POST /auth/refresh`, `POST /auth/logout` |
| Me | `GET/PATCH /me`, `GET/PUT /me/style-profile`, `POST /me/devices`, `POST /me/export`, `DELETE /me` |
| Stylist | `POST /stylist/sessions`, `GET /stylist/sessions/{id}`, `GET /stylist/sessions/{id}/stream` (SSE), `POST /stylist/sessions/{id}/actions` |
| Catalog | `GET /products/{id}`, `GET /products/{id}/offers`, `GET /products/{id}/complete-look` |
| Photo | `POST /uploads` (presigned), `POST /photo-search` |
| Try-on | `POST /tryon`, `GET /tryon/{id}` |
| Boards | `GET/POST /boards`, `PATCH/DELETE /boards/{id}`, `POST/DELETE /boards/{id}/items` |
| Polls | `POST /polls`, `GET /polls/{id}`, public: `GET /public/polls/{slug}`, `POST /public/polls/{slug}/vote` |
| Feed | `GET /feed` |
| Alerts | `GET /notifications`, `POST /notifications/read`, `PUT /price-alerts/{offer_id}` |
| Outbound | `GET /out/{offer_id}` |
| Reports | `POST /reports` |
| Admin | `/admin/*` (products, users, llm configs, prompts, usage, flags, reports, feed curation, limits) |
| Ops | `GET /healthz` (liveness), `GET /readyz` (DB/Redis checks), `GET /metrics` (internal only) |

Conventions: JSON, cursor pagination, RFC 9457 problem+json errors, `Idempotency-Key` on POSTs that create things, OpenAPI generated and published from FastAPI.

## 10. Security

- **Auth flow:** the app gets a Google ID token → `POST /auth/google` → the backend verifies signature, audience and expiry → upserts the user → issues an **access JWT (15 min)** + an **opaque refresh token (30 days, rotating, stored hashed, reuse detection revokes the family)**.
- **Tokens on device:** expo-secure-store only.
- **Admin:** separate role (`admin`, `curator`), Google login restricted to an allow-list, all admin actions written to `audit_logs`.
- **Transport:** HTTPS only (Cloudflare). No ports open on the homelab (tunnel). Internal services are not exposed.
- **Data:** least-privilege DB roles (app vs migrations vs read-only analytics). Private MinIO buckets + short-lived signed URLs.
- **Input:** Pydantic everywhere, upload type/size checks (≤ 8 MB, JPEG/PNG/WebP), EXIF stripping.
- **Secrets:** `.env` / Docker secrets, never committed. `gitleaks` in CI.
- **Dependencies:** Dependabot + `pip-audit` + `npm audit` in CI.
- **Headers/CORS:** strict CORS (admin + public web origins only), security headers via Caddy.

## 11. Privacy & compliance

- Consent captured at onboarding (`consents` table, versioned).
- Selfies/try-on images: purpose-limited, deleted after 24 h, never used for training.
- Data export (`POST /me/export` → zipped JSON emailed/downloadable) and deletion (in-app + public web page). Deletion is a soft delete followed by a hard purge within 30 days.
- Play Store: privacy policy URL, Data Safety form, account deletion URL, AI-content report button, affiliate disclosure in the app and listing.
- Analytics are pseudonymous. No selling of personal data.

## 12. Observability

| Signal | Tool |
|---|---|
| Logs | structlog JSON → Docker logs (later Loki) with `request_id`, `user_id` (hashed), `session_id` |
| Metrics | Prometheus (API latency/errors, queue depth, breaker state, AI cost/tokens, rate-limit hits) → Grafana |
| Traces | OpenTelemetry (API → DB → LLM) |
| LLM | Langfuse |
| Errors | GlitchTip (Sentry SDK) for backend and mobile |
| Uptime | Uptime Kuma → Telegram/email alert |
| Alerts | API 5xx > 2%, p95 > 1 s, breaker open, AI budget 80%, queue backlog, disk > 80%, backup failed |

## 13. Environments & delivery

- **Environments:** `local` (Compose dev profile), `staging` and `prod` (homelab, separate Compose projects and databases).
- **CI (GitHub Actions):** lint + typecheck + tests (backend with testcontainers; mobile Jest; admin) → build Docker images → push to GHCR → GenUI contract check.
- **CD:** a pull-based deploy on the homelab (script or Watchtower restricted to tagged images) → run Alembic migrations → health check → rollback on failure.
- **Mobile builds:** local Gradle/EAS builds → Play Console internal track → closed test → production. OTA updates via EAS Update for JS-only fixes (within Play policy).
- **Migrations:** expand → migrate → contract. Never a destructive change in the same release as the code change.

## 14. Backups & disaster recovery

- Nightly `pg_dump` (compressed, encrypted) + MinIO mirror → off-site. 14 daily + 8 weekly kept.
- **RPO 24 h, RTO 4 h.** A restore drill is run before launch and then monthly.
- Infra as code (Compose + scripts in git) so the server can be rebuilt from scratch.

## 15. Testing strategy

| Layer | What |
|---|---|
| Unit | Ranking, slot logic, breaker, rate limiter, prompt builders, schema validation |
| Integration | API + real Postgres/Redis (testcontainers), graph runs with a **fake LLM provider** (deterministic) |
| Contract | GenUI JSON Schema ↔ TS types; every component in the catalog has a renderer + fixture |
| LLM evals | A golden set of ~50 intents → expected slots/filters; run on prompt or model change (offline, scored) |
| E2E | Maestro flows: onboarding → stylist → swipe → detail → wishlist → poll |
| Load | k6: 5× peak of the 1,000 DAU profile with a mocked LLM; targets from §1.2 |
| Security | ZAP baseline scan on staging, dependency audits |
