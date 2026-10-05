# 0010 — LLM observability through OpenTelemetry GenAI spans and a usage ledger

**Status:** Accepted (2026-10-05). Supersedes [0004](0004-defer-langfuse.md).

## Context
ADR 0004 planned to deploy self-hosted Langfuse in CP6. Langfuse v3 needs Postgres, ClickHouse, Redis and S3 storage: heavy for a homelab, before any real AI traffic exists.

## Decision
- Every provider call is an **OpenTelemetry span** following the GenAI semantic conventions (`gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`), so it shows up in Tempo alongside the HTTP and DB spans of the same request.
- Every attempt is a row in **`llm_usage`** (task, model, tokens, cost in micro-USD, latency, outcome), the source for cost reports and the admin usage API. Prometheus counters feed the Grafana AI panels.
- Langfuse accepts OTLP, so when prompt/response inspection is needed it attaches as an **extra exporter in the OTel Collector**, with no application change.

## Consequences
- Cost, latency and failures are fully visible today with the existing stack.
- Prompt/response bodies are not stored anywhere (privacy by default); adding Langfuse later is an explicit decision.
