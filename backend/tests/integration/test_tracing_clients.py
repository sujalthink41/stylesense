from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import text

from stylesense.bootstrap.container import Container
from stylesense.main import create_app
from stylesense.platform.config import Settings
from stylesense.platform.observability.tracing import build_tracer_provider


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def traced_client(settings: Settings, exporter: InMemorySpanExporter) -> Iterator[TestClient]:
    provider = build_tracer_provider(
        settings.model_copy(update={"otel_enabled": True}), exporter=exporter
    )
    with TestClient(create_app(settings, tracer_provider=provider)) as client:
        yield client


def test_database_and_redis_calls_are_traced(
    traced_client: TestClient, exporter: InMemorySpanExporter
) -> None:
    container: Container = traced_client.app.state.container  # type: ignore[attr-defined]
    provider: TracerProvider = traced_client.app.state.tracer_provider  # type: ignore[attr-defined]

    async def touch_clients() -> None:
        async with container.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await container.redis.ping()

    traced_client.portal.call(touch_clients)  # type: ignore[union-attr]
    provider.force_flush()

    names = {s.name for s in exporter.get_finished_spans()}
    assert any(n.startswith("SELECT") for n in names), names
    assert "PING" in names


def test_readiness_probes_emit_no_spans(
    traced_client: TestClient, exporter: InMemorySpanExporter
) -> None:
    exporter.clear()

    assert traced_client.get("/readyz").status_code == 200

    assert exporter.get_finished_spans() == ()
