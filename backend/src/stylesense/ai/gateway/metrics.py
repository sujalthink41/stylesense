from prometheus_client import CollectorRegistry, Counter, Histogram

from stylesense.ai.gateway.types import Usage

_LATENCY_BUCKETS = (0.1, 0.25, 0.5, 1, 2, 4, 8, 15, 30)


class GatewayMetrics:
    """Labels are bounded: task names and configured models only."""

    def __init__(self, registry: CollectorRegistry) -> None:
        self._calls = Counter(
            "llm_calls", "LLM provider attempts", ["task", "model", "outcome"], registry=registry
        )
        self._tokens = Counter(
            "llm_tokens", "Tokens processed", ["task", "model", "direction"], registry=registry
        )
        self._cost = Counter(
            "llm_cost_micro_usd", "Spend in micro-USD", ["task", "model"], registry=registry
        )
        self._latency = Histogram(
            "llm_latency_seconds",
            "Provider latency",
            ["task", "model"],
            buckets=_LATENCY_BUCKETS,
            registry=registry,
        )

    def observe(
        self,
        *,
        task: str,
        model: str,
        outcome: str,
        usage: Usage,
        cost_micro_usd: int,
        latency_ms: int,
    ) -> None:
        self._calls.labels(task, model, outcome).inc()
        self._tokens.labels(task, model, "input").inc(usage.input_tokens)
        self._tokens.labels(task, model, "output").inc(usage.output_tokens)
        self._cost.labels(task, model).inc(cost_micro_usd)
        if outcome != "cache_hit":
            self._latency.labels(task, model).observe(latency_ms / 1000)
