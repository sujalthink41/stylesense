from collections.abc import Callable, Iterable
from dataclasses import dataclass

from fastapi import APIRouter, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client.core import GaugeMetricFamily, Metric
from prometheus_client.registry import Collector

_KNOWN_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)


def _method_label(method: str) -> str:
    # Arbitrary client-sent methods must not create new time series.
    return method if method in _KNOWN_METHODS else "OTHER"


class HttpMetrics:
    """RED metrics: request rate, errors (by status), duration."""

    def __init__(self, registry: CollectorRegistry) -> None:
        self._requests = Counter(
            "http_requests",
            "HTTP requests handled",
            ["method", "route", "status"],
            registry=registry,
        )
        self._latency = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency",
            ["method", "route"],
            buckets=_LATENCY_BUCKETS,
            registry=registry,
        )
        self._in_progress = Gauge(
            "http_requests_in_progress",
            "HTTP requests currently being served",
            ["method"],
            registry=registry,
        )

    def started(self, method: str) -> None:
        self._in_progress.labels(_method_label(method)).inc()

    def finished(self, method: str, route: str, status: int, seconds: float) -> None:
        label = _method_label(method)
        self._in_progress.labels(label).dec()
        self._requests.labels(label, route, str(status)).inc()
        self._latency.labels(label, route).observe(seconds)


@dataclass(frozen=True, slots=True)
class PoolStats:
    size: int
    checked_out: int
    overflow: int


class PoolStatsCollector(Collector):
    """Reads DB pool state at scrape time, so values are never stale."""

    def __init__(self, read: Callable[[], PoolStats]) -> None:
        self._read = read

    def collect(self) -> Iterable[Metric]:
        stats = self._read()
        yield GaugeMetricFamily("db_pool_size", "Configured pool size", value=stats.size)
        yield GaugeMetricFamily(
            "db_pool_checked_out", "Connections in use", value=stats.checked_out
        )
        yield GaugeMetricFamily(
            "db_pool_overflow", "Connections beyond pool size", value=stats.overflow
        )


def metrics_router(registry: CollectorRegistry) -> APIRouter:
    router = APIRouter()

    # Internal only: the reverse proxy must never route /metrics publicly.
    @router.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    return router
