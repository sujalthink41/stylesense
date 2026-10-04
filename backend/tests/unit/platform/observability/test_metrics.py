import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry

from stylesense.platform.errors import register_error_handlers
from stylesense.platform.observability.metrics import (
    HttpMetrics,
    PoolStats,
    PoolStatsCollector,
    metrics_router,
)
from stylesense.platform.observability.middleware import RequestContextMiddleware


@pytest.fixture
def registry() -> CollectorRegistry:
    return CollectorRegistry()


@pytest.fixture
def client(registry: CollectorRegistry) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware, metrics=HttpMetrics(registry))
    app.include_router(metrics_router(registry))

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError

    return TestClient(app, raise_server_exceptions=False)


def _value(registry: CollectorRegistry, name: str, **labels: str) -> float:
    value = registry.get_sample_value(name, labels)
    return 0.0 if value is None else value


def test_counts_requests_by_route_template(client: TestClient, registry: CollectorRegistry) -> None:
    for item_id in ("1", "2", "3"):
        client.get(f"/items/{item_id}")

    labels = {"method": "GET", "route": "/items/{item_id}", "status": "200"}
    assert _value(registry, "http_requests_total", **labels) == 3


def test_records_latency_histogram(client: TestClient, registry: CollectorRegistry) -> None:
    client.get("/items/1")

    count = _value(
        registry, "http_request_duration_seconds_count", method="GET", route="/items/{item_id}"
    )
    assert count == 1


def test_unmatched_paths_share_one_label(client: TestClient, registry: CollectorRegistry) -> None:
    for path in ("/a", "/b/c", "/wp-admin.php"):
        client.get(path)

    labels = {"method": "GET", "route": "<unmatched>", "status": "404"}
    assert _value(registry, "http_requests_total", **labels) == 3


def test_unhandled_errors_are_counted_as_500(
    client: TestClient, registry: CollectorRegistry
) -> None:
    client.get("/boom")

    labels = {"method": "GET", "route": "/boom", "status": "500"}
    assert _value(registry, "http_requests_total", **labels) == 1


def test_in_progress_gauge_returns_to_zero(client: TestClient, registry: CollectorRegistry) -> None:
    client.get("/items/1")

    assert _value(registry, "http_requests_in_progress", method="GET") == 0


def test_metrics_endpoint_exposes_prometheus_text(client: TestClient) -> None:
    client.get("/items/1")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "http_requests_total" in response.text


def test_metrics_endpoint_is_not_itself_counted(
    client: TestClient, registry: CollectorRegistry
) -> None:
    client.get("/metrics")

    assert (
        _value(registry, "http_requests_total", method="GET", route="/metrics", status="200") == 0
    )


def test_metrics_endpoint_is_hidden_from_openapi(client: TestClient) -> None:
    assert "/metrics" not in client.get("/openapi.json").json()["paths"]


def test_pool_collector_reports_current_pool_state(registry: CollectorRegistry) -> None:
    stats = PoolStats(size=10, checked_out=3, overflow=1)
    registry.register(PoolStatsCollector(lambda: stats))

    assert _value(registry, "db_pool_size") == 10
    assert _value(registry, "db_pool_checked_out") == 3
    assert _value(registry, "db_pool_overflow") == 1
