# 0002 — Layered modular monolith with routers in `api/`

**Status:** Accepted (2026-10-04)

## Context
The original plan had one `core/` package and routers inside each module. `core/` would grow into a grab-bag, and routers inside modules force modules to know HTTP and the DI container, which creates import cycles.

## Decision
Split cross-cutting code into three layers and enforce the order with `import-linter`:

`main → api → bootstrap → modules → guards → infra → platform`

- **platform:** pure foundations (config, logging, errors, clock, health runner).
- **infra:** clients for external infrastructure (DB, Redis, probes).
- **guards:** reliability mechanisms (idempotency, rate limits, breaker, locks, outbox).
- **bootstrap:** composition root; the only place concrete implementations are chosen.
- **api:** HTTP routers and request dependencies; modules stay HTTP-agnostic.

## Consequences
- Modules are reusable from workers and testable without HTTP.
- Layer violations fail CI.
- One deployable today, with clean seams if a module ever needs to become a service.
