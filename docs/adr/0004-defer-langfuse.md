# 0004 — Defer Langfuse until the LLM gateway (CP6)

**Status:** Superseded by [0010](0010-llm-observability-via-otel.md) (2026-10-05)

## Context
CP2 planned to deploy Langfuse for LLM tracing. Self-hosted Langfuse v3 needs Postgres, ClickHouse, Redis and S3-compatible storage. Nothing calls an LLM until CP6, and object storage is deferred (ADR 0003).

## Decision
Ship CP2 with traces (OpenTelemetry → Tempo), metrics (Prometheus), dashboards (Grafana), errors (GlitchTip) and uptime (Uptime Kuma). Add Langfuse in CP6, together with the gateway that emits LLM traces.

## Consequences
- A lighter homelab footprint now; no idle ClickHouse.
- Every LLM call will still carry an OpenTelemetry span, so Tempo shows LLM latency from day one; Langfuse adds prompt/token/cost detail in CP6.
