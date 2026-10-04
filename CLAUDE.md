# StyleSense — Working Rules

Production-grade AI fashion stylist app. Read `docs/README.md` for the doc map.

## Non-negotiables
- Follow `docs/09-engineering-standards.md` strictly: SOLID, modular monolith, `router → service → repository`, DI via protocols.
- **TDD:** write failing tests first. Cover happy, bad-input, auth/IDOR, edge, dependency-failure, concurrency and idempotency paths. No real network or LLM in tests (use `tests/fakes`).
- Comments: short and sharp, only where the *why* isn't obvious.
- Every write operation: decide its idempotency mechanism (standards §6).
- Every outbound call: timeout, plus retry/breaker where it makes sense.
- Observability on every feature: structured logs (no PII), metrics, traces.
- AI provider/model is never hardcoded; everything goes through `LLMGateway` with task config.
- Money in integer paise. Time via the injectable clock.

## Build order
Backend first (Phase 1), then frontend (Phase 2). Follow `docs/06-checkpoints.md`.

## Git workflow (every checkpoint or change)
Repo: github.com/sujalthink41/stylesense (private). Never commit to `main`.
1. Branch from `main`: `feat/cp<n>-<slug>`, `fix/…`, `docs/…`.
2. Conventional Commits; `make check` green before pushing.
3. `gh pr create` with the PR template filled in; wait for CI.
4. Squash merge, delete the branch, pull `main`, tag `cp-<n>`.

## At the end of every checkpoint
1. All exit criteria met, CI green.
2. Update `docs/07-system-architecture.md` (current state + changelog).
3. Add new concepts to `docs/08-key-concepts.md`.
4. Mark status in `docs/06-checkpoints.md`.
5. Record significant decisions as ADRs in `docs/adr/`.
