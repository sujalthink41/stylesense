# 07 — How the System Works (Living Document)

> **Audience:** any developer joining the project.
> **Rule:** updated at the end of **every checkpoint** to describe the system **as it exists now**. Planned parts are marked *(planned)*.

**Current state:** CP2 complete. The backend skeleton runs in Docker with Postgres + pgvector and Redis, exposes liveness/readiness probes, renders all errors as problem+json, and runs migrations on deploy. Every request is observable end to end: request id, PII-safe JSON logs, RED metrics, OpenTelemetry traces (API, DB, Redis) and error reports to GlitchTip. No product features yet. Parts marked *(planned)* arrive in later checkpoints.

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
| `backend/src/stylesense/workers` *(planned)* | ARQ | Try-on, embeddings, alerts, feed, purges |
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

## 3. Request lifecycle: a stylist turn *(planned)*

1. The user taps **"Party"** on the home screen → `POST /v1/stylist/sessions {entry: "occasion_tile", value: "party"}` → the backend creates `stylist_sessions` row and LangGraph thread.
2. The app opens `GET /v1/stylist/sessions/{id}/stream` (SSE).
3. The graph runs: `ingest_action → route → slot_check`. The budget is missing → `ask_question` builds a `chip_question` (template, no LLM) → `compose_ui` → **streams `ui.render`** → `interrupt()` (the graph pauses; state saved in Postgres).
4. The user taps **"Under ₹500"** → `POST …/actions {turn_id, idempotency_key, action}`. The backend checks `turn_id`, resumes the graph.
5. All slots are filled → `retrieve` (SQL filters + pgvector) → `rank` (code) → `explain` (**one** batched LLM call through the gateway) → `compose_ui` streams a `product_swipe_deck`.
6. Swipes are sent as actions; they update the taste vector in code (no LLM) and refill the deck.
7. "Buy" → `GET /v1/out/{offer_id}` → click logged → 302 to the store.

## 4. LLM call lifecycle *(planned)*

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
See `05-db-design.md`. Key ideas: canonical **products** + per-store **offers**; money in **paise**; **embeddings** on products and a **taste vector** per user; LangGraph checkpoints in the `lg` schema.

## 6. Deployment *(planned)*
Homelab → Docker Compose (`prod` profile) → Caddy → Cloudflare Tunnel → the internet. No inbound ports. Nightly encrypted backups off-site. See `03-technical-spec.md` §13–14.

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

## 8. Where to look for…

| I want to… | Go to |
|---|---|
| Add a config value | `platform/config.py` (`APP_*` env var, validated) + `.env.example` |
| Add an error type | Subclass `AppError` in `platform/errors.py` or the module's `exceptions.py` |
| Add a metric | Define it next to its owner with the app's registry; label by bounded values only (route template, status), never ids |
| Log something | `structlog.get_logger(__name__).info("event_name", key=value)`; never log raw request bodies |
| Investigate a user report | Ask for the `X-Request-ID` → search logs → open the trace by `trace_id` in Tempo |
| Add a dependency probe | Implement `HealthCheck` in `infra/health.py`, register it in `bootstrap/container.py` |
| Add a new UI component | `backend/src/stylesense/ai/genui/` (schema) → regenerate types → `mobile/src/genui/components/` + register |
| Change which model a task uses | Admin → AI → Task configs (or `llm_task_configs`) |
| Add a new AI provider | `backend/src/stylesense/ai/gateway/providers/` |
| Add a product source | `backend/src/stylesense/integrations/sources/` (implement `ProductSource`) |
| Change the stylist flow | `backend/src/stylesense/ai/graphs/stylist/` |

---

## Changelog

| Checkpoint | Date | What changed in the system |
|---|---|---|
| CP0 | 2026-10-04 | Initial docs: product, business, spec, slices, DB design, checkpoints, this doc, key concepts. |
| CP0 | 2026-10-04 | Added engineering standards (doc 09), root `CLAUDE.md`; checkpoints reordered backend-first. |
| CP1 | 2026-10-04 | Backend foundation: layered package (`platform`/`infra`/`bootstrap`/`api`), typed config, JSON logging, problem+json errors, DB engine + Unit of Work, Redis, `/healthz` + `/readyz`, Alembic baseline (vector, citext), multi-stage non-root Docker image, Compose stack, Makefile, pre-commit, CI. |
| CP2 | 2026-10-04 | Observability: request ids, PII-redacted JSON logs with trace correlation, RED + pool metrics on `/metrics`, OpenTelemetry tracing (API, SQLAlchemy, Redis) via collector → Tempo, GlitchTip error reporting, provisioned Grafana dashboard, Uptime Kuma, runbooks. SQLAlchemy pinned <2.1. |
