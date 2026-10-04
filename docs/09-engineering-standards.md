# 09 — Engineering Standards

These rules are **mandatory** for all code in this repo. A pull request that breaks them doesn't merge.

> Production systems at large companies still fail. The goal isn't "never fails"; it's **fail safely, detect fast, recover fast**. Every rule below serves one of those three.

---

## 1. Design principles

### 1.1 SOLID, applied pragmatically
| Principle | How it shows up here |
|---|---|
| **S**ingle responsibility | Routers only handle HTTP. Services hold business logic. Repositories hold data access. One reason to change per class. |
| **O**pen/closed | New LLM providers, product sources, try-on providers and GenUI components are **added** as new classes and registered, never by editing `if/elif` chains. |
| **L**iskov substitution | Every adapter fully honors its `Protocol` (including errors raised). The fake provider in tests is a valid substitute for the real one. |
| **I**nterface segregation | Small protocols (`ProductSearcher`, `OfferFetcher`) instead of one giant interface. |
| **D**ependency inversion | Services depend on protocols, not concrete classes. Wiring happens in one place (the composition root / FastAPI dependencies). |

### 1.2 Also
- **YAGNI:** a pattern is used only when it removes a real problem. No speculative abstractions, no "manager/helper/util" dumping grounds.
- **KISS:** the simplest design that meets the requirement and its tests.
- **Composition over inheritance.** Inheritance only for true "is-a" plus framework base classes.
- **Pure core, effects at the edges:** ranking, slot logic, taste math and pricing are pure functions (easy to test). I/O lives in repositories and adapters.

### 1.3 Design patterns we use (and where)
| Pattern | Where |
|---|---|
| Adapter | LLM providers, product sources, try-on providers, push, storage |
| Strategy | Ranking strategies, fallback chains, rate-limit algorithms |
| Registry | GenUI component catalog, provider registry |
| Repository | Data access per aggregate |
| Unit of Work | One DB transaction per use case |
| Factory | Building provider clients from config |
| Circuit Breaker, Retry, Bulkhead | Every outbound call (doc 03 §6.4) |
| Transactional Outbox | Side effects after commit (push, jobs, emails) |
| Decorator | Cross-cutting concerns: tracing, metering, caching around the gateway |
| State machine | The stylist flow (LangGraph) |

## 2. Architecture rules (backend)

**Modular monolith.** One deployable, internally split into **domain modules** with clear boundaries. A module can be extracted into a service later if scale ever demands it.

```
backend/
├── pyproject.toml / uv.lock       # deps (uv) + all tool config
├── Dockerfile / .dockerignore     # multi-stage, non-root runtime image
├── alembic.ini / alembic/         # migrations
├── src/stylesense/
│   ├── main.py                    # app factory: middleware, handlers, routers, lifespan
│   ├── api/                       # HTTP layer only: routers, request deps, I/O schemas
│   │   ├── dependencies.py
│   │   ├── health.py
│   │   └── v1/<module>.py         # one router per module (added per checkpoint)
│   ├── bootstrap/                 # composition root: the only place concrete classes are chosen
│   │   └── container.py
│   ├── modules/<domain>/          # business logic, no HTTP knowledge
│   │   ├── service.py             # use cases
│   │   ├── repository.py          # data access
│   │   ├── models.py              # SQLAlchemy
│   │   ├── schemas.py             # domain DTOs
│   │   ├── ports.py               # protocols this module needs (sources, providers…)
│   │   └── exceptions.py
│   ├── ai/                        # gateway/, genui/, prompts/ (CP6–CP7)
│   ├── integrations/              # adapters implementing module ports (sources, try-on, push, storage)
│   ├── guards/                    # idempotency, rate limits, locks, single-flight, bulkheads, outbox
│   ├── infra/                     # clients for external infra: database, redis, health probes
│   ├── platform/                  # pure foundations: config, logging, errors, clock, health runner
│   └── workers/                   # worker process: outbox relay, periodic tasks
└── tests/
    ├── unit/                      # mirrors src/, no I/O
    ├── integration/               # real Postgres/Redis (testcontainers)
    ├── contract/                  # GenUI schema, API schema
    ├── fakes/                     # fake clock, health checks, LLM, sources
    └── factories.py               # test data builders
```

Folders appear only when the checkpoint that needs them lands (YAGNI): no empty packages.

**Dependency rules (enforced by `import-linter` in CI)**

```
main → api → bootstrap → modules → guards → infra → platform
```

- A layer may import only layers **below** it. `platform` imports nothing from the app.
- Routers live in `api/`, so modules stay HTTP-agnostic and reusable from workers.
- Within a module: `service → repository`. Never skip or reverse.
- Modules talk to each other **only through the other module's service**, never its repository or models.
- `integrations` implement protocols declared in a module's `ports.py`; only `bootstrap` wires them in.

## 3. Code quality

- **Typing:** Python `mypy --strict`; TypeScript `strict: true`. No `Any` without a comment explaining why.
- **Lint/format:** `ruff` (Python), `eslint` + `prettier` (TS). Enforced by pre-commit and CI.
- **Naming:** intention-revealing names; no abbreviations except well-known ones (`id`, `url`, `db`).
- **Functions:** small, one level of abstraction, ≤ ~30 lines as a guide; max 3–4 parameters (else a parameter object).
- **No magic values:** constants or config.
- **Errors:** raise domain exceptions (`BudgetExceeded`, `ProductNotFound`). One handler maps them to problem+json. Never `except Exception: pass`. Never leak stack traces to clients.
- **Comments:** short and sharp, only where the *why* isn't obvious. No narrating what the code already says. Docstrings on public interfaces only.
- **No dead code, no commented-out code.**
- **Config:** 12-factor; everything from env via typed settings; app fails fast on startup if config is invalid.

## 4. Test-driven development

**Workflow:** write a failing test → make it pass with the simplest code → refactor. No feature code merges without tests.

### 4.1 Test pyramid
| Level | Scope | Tools |
|---|---|---|
| Unit (most) | Pure logic, services with fakes | pytest |
| Integration | Repositories, API endpoints, workers with real Postgres + Redis | pytest + testcontainers + httpx |
| Contract | GenUI schemas, OpenAPI, provider adapter conformance | pytest, schema diff |
| Property-based | Ranking, money math, rate limiters, taste vector | Hypothesis |
| LLM evals | Prompt/model changes against a golden set | custom eval runner |
| Load | NFR targets | k6 |
| E2E (later) | Mobile flows | Maestro |

### 4.2 Every feature must test
- **Happy path.**
- **Bad input:** validation errors, wrong types, missing fields, oversized payloads.
- **Auth:** unauthenticated, expired token, **another user's resource (IDOR)**, wrong role.
- **Not found / conflict / stale state** (`turn_id`, already deleted).
- **Boundaries:** empty lists, budget exactly at the limit, zero results, max page size, unicode/emoji text.
- **Failure of dependencies:** DB down, Redis down, LLM timeout/429/500/invalid JSON, storage down.
- **Concurrency:** double submit, parallel requests on the same resource, race on quotas.
- **Idempotency:** same key twice returns the same result with no duplicate side effects.
- **Time:** expiry, day rollover for quotas (with an injected clock, never `sleep`).

### 4.3 Test rules
- Deterministic: no real network, no real LLM in CI (fake provider), frozen time, seeded randomness.
- Isolated: each test owns its data (transaction rollback or truncation).
- Fast: the unit suite runs in seconds.
- Named as behavior: `test_returns_409_when_turn_is_stale`.
- **Coverage gate: ≥ 90% lines on `modules/`, `ai/`, `core/`**, plus mandatory branch coverage on critical paths (auth, quotas, budget, idempotency). Coverage is a floor, not the goal.

## 5. Scalability rules

- **Stateless API:** no in-process state that matters. Sessions, limits, breaker state, idempotency and locks all live in Redis or Postgres. Any instance can serve any request.
- **Async all the way:** no blocking I/O in request handlers; CPU-heavy work goes to workers.
- **DB:**
  - Indexes designed with queries.
  - No N+1 queries (tested with query-count assertions on hot endpoints).
  - Cursor pagination only; max page size enforced.
  - Bounded connection pools.
  - Statement timeouts.
- **Caching:** cache-aside with explicit TTLs and invalidation on write; cache keys versioned.
- **Backpressure:** queues have limits; when full, return `503` + `Retry-After` instead of falling over.
- **Timeouts on every outbound call.** No call may wait forever.
- **Graceful shutdown:** stop accepting requests, drain in-flight work, close pools.
- **Horizontal scale readiness:** running 2 API instances + 2 workers locally must pass the integration suite.

## 6. Idempotency & duplicate-call prevention

### 6.1 Where idempotency is required
| Operation | Mechanism |
|---|---|
| Stylist actions (`POST …/actions`) | `Idempotency-Key` header → stored response in Redis (10 min) + `turn_id` stale guard |
| Create stylist session, poll, share, try-on, upload completion | `Idempotency-Key` header (24 h) |
| Add item to board | Natural key `UNIQUE(board_id, product_id)` → upsert |
| Poll vote | Natural key `UNIQUE(poll_id, voter_fingerprint)` |
| Try-on job | Key + dedupe on `(user, selfie, product)` within 10 min, so a double tap doesn't make two paid calls |
| Token refresh | Rotation + a **short grace window** (≈ 30 s) where a just-rotated token returns the same new pair, so parallel app requests aren't flagged as theft |
| Background jobs (outbox delivery is at-least-once) | Handlers dedupe on `envelope.id` / check state before acting |
| Push notifications | Dedupe key per event (e.g. `price_drop:{alert_id}:{snapshot_id}`) stored before send |
| Cron jobs | Distributed lock (Redis) so only one instance runs each schedule |
| Embedding generation | Skip when the content hash is unchanged |
| Future affiliate/webhook postbacks | Dedupe by provider event id |

### 6.2 Where it's naturally idempotent (no extra mechanism)
`GET`, `PUT` (full replace), `DELETE` (deleting twice → still deleted, return `204`).

### 6.3 Avoiding repeated expensive calls
- **Single-flight (request coalescing):** concurrent identical LLM/embedding requests share one in-flight call.
- **Response caching** for LLM tasks (doc 03 §6.3).
- **ETag / `If-None-Match`** on catalog and feed GETs.
- **Client:** disabled buttons while pending, debounced search input, TanStack Query dedupe.

## 7. Observability (all of it)

| Pillar | Standard |
|---|---|
| **Logs** | structlog JSON. Every line carries `request_id`, `trace_id`, `user_id` (hashed), `session_id`, `module`. Levels used correctly. **PII redaction** processor (emails, tokens, phone numbers) is mandatory. |
| **Metrics** | RED per endpoint (Rate, Errors, Duration). USE for resources (DB pool, Redis, queue depth). Business metrics (sessions, clicks, saves). AI metrics (tokens, cost, cache hit %, breaker state, fallback %, degraded %). |
| **Traces** | OpenTelemetry on API → DB → Redis → outbound HTTP → LLM, propagated into workers. |
| **LLM traces** | Langfuse per call: prompt version, model, tokens, cost, latency, outcome. |
| **Errors** | GlitchTip for backend + mobile, with release and environment tags. |
| **Health** | `/healthz` (process alive), `/readyz` (dependencies), worker heartbeats. |
| **SLOs** | Availability 99.5%; stylist turn p95 < 1.5 s to first component; error rate < 1%. Alerts fire on **error-budget burn**, not single blips. |
| **Runbooks** | Every alert links to a runbook in `docs/runbooks/` (what it means, how to check, how to fix). |
| **Audit** | Admin and security-relevant actions in `audit_logs`. |

## 8. Data & consistency

- **One transaction per use case** (Unit of Work). Side effects that must happen after commit go through the **outbox** table, which is processed by a worker.
- **Optimistic locking** (`version` column) where concurrent edits matter (boards, admin edits).
- **Ids:** primary keys come from `platform.ids.new_id()` (UUIDv7) so inserts batch; never rely on server defaults being loaded after INSERT (`refresh()` explicitly) (ADR 0008).
- **Relationships are `lazy="raise"`**: load what you need with `selectinload`; accidental lazy loads must fail in tests.
- **Atomic counters** for quotas (Redis `INCR` with expiry / Lua scripts), never read-then-write.
- **Migrations:** expand → migrate → contract; reviewed; tested on a copy of prod data before release; every migration has a downgrade or a documented reason why not.

## 9. Security in code

- Validate all input (Pydantic), encode all output.
- **Authorization check in the service layer** for every resource access (ownership), not just "is logged in".
- Parameterized queries only (SQLAlchemy).
- Secrets only from env; `gitleaks` in CI; never log secrets or tokens.
- Dependency scanning (`pip-audit`, `npm audit`, Dependabot).
- Upload validation (type, size, EXIF strip).

## 10. API evolution & mobile clients

- URL versioning (`/v1`); additive changes only within a version.
- Old app versions stay in users' hands for months: the backend must keep supporting them.
- **Minimum supported app version** endpoint + client "please update" screen (soft and hard force-update), so broken old builds can be retired.
- GenUI catalog version negotiation (doc 03 §5.5).

## 11. Feature flags & kill switches

Every risky feature (try-on, photo search, each real store source, each AI task) has a flag that can be turned off at runtime from the admin without a deploy.

## 12. Workflow

- **Branches:** `main` is always releasable. Short-lived `feat/…`, `fix/…` branches.
- **Commits:** Conventional Commits (`feat(stylist): …`).
- **Pull requests:** small, one concern. CI must pass (lint, types, tests, coverage, import rules, contract check, secret scan). Self-review checklist below.
- **ADRs:** significant decisions are recorded in `docs/adr/NNNN-title.md` (context, decision, consequences).
- **Definition of Done:** tests written first and passing; edge cases covered; logs/metrics/traces added; errors handled; docs 07/08 updated at checkpoint end.

### PR checklist
- [ ] Tests first; happy + bad + edge + failure paths covered
- [ ] No layer violations; dependencies injected
- [ ] Inputs validated; authorization checked
- [ ] Outbound calls have timeouts/retries/breaker as appropriate
- [ ] Idempotency considered for every write
- [ ] Logs (no PII), metrics, traces added
- [ ] Feature flag for risky behavior
- [ ] Migration is backward compatible
- [ ] Docs updated if behavior or architecture changed
