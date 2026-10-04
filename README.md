# StyleSense

**An AI fashion stylist for India.** Tell it what you need ("summer t-shirt around ₹500"), answer a few quick taps, and swipe through the best picks across Amazon, Flipkart and Myntra, with price comparison, virtual try-on and outfit suggestions.

> Status: **in active development**: backend Phase 1, checkpoint **CP2 complete**. See [progress](docs/06-checkpoints.md).

---

## Why it's different

- **Tap-first generative UI:** the AI replies with interactive components (chips, cards, sliders), not paragraphs.
- **Learns your taste:** every swipe updates a personal taste profile; no retraining needed.
- **Budget is sacred:** hard filters guarantee results stay within budget; AI only explains and ranks.
- **Built to run cheap and reliably:** most steps are deterministic code; the LLM is called only where it adds value, behind circuit breakers, quotas and a daily budget cap.

## Architecture

```
Mobile app (React Native)  ──HTTPS / SSE──▶  FastAPI (stateless)  ──▶  PostgreSQL 18 + pgvector
Admin (Next.js)            ──────────────▶   LangGraph stylist    ──▶  Redis 8
                                              LLM gateway (provider-agnostic, config-driven)
```

The backend is a **layered modular monolith** with boundaries enforced in CI:

```
main → api → bootstrap → modules → guards → infra → platform
```

Details: [How the system works](docs/07-system-architecture.md) · [Technical spec](docs/03-technical-spec.md) · [ADRs](docs/adr/README.md)

## Tech stack

| Area | Stack |
|---|---|
| Backend | Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic, structlog |
| AI | LangGraph, provider-agnostic LLM gateway (OpenAI by default) |
| Data | PostgreSQL 18 + pgvector, Redis 8 |
| Mobile *(Phase 2)* | React Native (Expo), TypeScript, Zustand, TanStack Query |
| Admin *(Phase 2)* | Next.js, shadcn/ui |
| Tooling | uv, ruff, mypy (strict), import-linter, pytest + testcontainers, pre-commit |
| Observability | structlog (PII-redacted JSON), Prometheus, OpenTelemetry → Tempo, Grafana, GlitchTip, Uptime Kuma |
| Ops | Docker (multi-stage, non-root), Docker Compose, GitHub Actions, self-hosted |

## Getting started

**Prerequisites:** [Docker](https://docs.docker.com/get-docker/), [uv](https://docs.astral.sh/uv/getting-started/installation/), `make` (Windows: `winget install ezwinports.make`).

```bash
git clone https://github.com/sujalthink41/stylesense.git
cd stylesense
make setup   # install deps + git hooks, create .env
make up      # start postgres, redis, migrations and the API (hot reload)
```

- API docs: http://localhost:8000/docs
- Liveness: http://localhost:8000/healthz · Readiness: http://localhost:8000/readyz

Optional observability stack:

```bash
make obs-up   # + Grafana :3001, Prometheus :9090, GlitchTip :8001, Uptime Kuma :3002, Tempo
```

Run `make help` to see every command.

## Development

```bash
make check             # everything CI runs: lint, format, types, layers, tests + coverage
make test-unit         # fast, no Docker
make test-integration  # real Postgres/Redis via testcontainers
make migration m="add users"   # new Alembic migration
```

**Standards:** test-driven, SOLID, `mypy --strict`, ≥ 90% coverage, idempotency for every write, full observability. Read [Engineering standards](docs/09-engineering-standards.md) before contributing.

**Workflow:** branch from `main` (`feat/…`, `fix/…`, `docs/…`) → Conventional Commits → pull request → CI green → squash merge.

## Repository layout

```
backend/        FastAPI service (src/stylesense, tests, alembic, Dockerfile)
infra/compose/  Docker Compose stack (base, dev and observability overlays)
infra/observability/  Collector, Tempo, Prometheus and Grafana config
docs/           Product, business, spec, DB design, checkpoints, ADRs, runbooks
.github/        CI workflows, Dependabot, PR template
Makefile        Developer commands
```

## Documentation

| Doc | |
|---|---|
| [Product overview](docs/01-product-overview.md) | What we're building and for whom |
| [Business intent](docs/02-business-intent.md) | Revenue model, growth, risks |
| [Technical spec](docs/03-technical-spec.md) | Architecture, GenUI protocol, AI layer, security |
| [Spec slices](docs/04-spec-slices.md) | Buildable vertical slices |
| [Database design](docs/05-db-design.md) | Schema, indexes, retention |
| [Checkpoints](docs/06-checkpoints.md) | Build plan and progress |
| [How the system works](docs/07-system-architecture.md) | Living developer guide |
| [Key concepts](docs/08-key-concepts.md) | Concepts to learn from this codebase |
| [Engineering standards](docs/09-engineering-standards.md) | Mandatory coding rules |

## License

Proprietary. All rights reserved.
