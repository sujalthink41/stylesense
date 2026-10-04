from collections.abc import Iterator

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from stylesense.platform.observability.middleware import RequestContextMiddleware
from stylesense.platform.observability.tracing import (
    build_tracer_provider,
    instrument_app,
    uninstrument_app,
)
from tests.factories import make_settings
from tests.unit.platform.observability.conftest import LogReader


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def provider(exporter: InMemorySpanExporter) -> TracerProvider:
    tp = build_tracer_provider(make_settings(otel_enabled=True), exporter=exporter)
    assert tp is not None
    return tp


@pytest.fixture
def client(provider: TracerProvider) -> Iterator[TestClient]:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        structlog.get_logger("test").info("inside_handler")
        return {"id": item_id}

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    instrument_app(app, provider)
    yield TestClient(app)
    uninstrument_app(app)


def _server_spans(exporter: InMemorySpanExporter) -> list[str]:
    return [s.name for s in exporter.get_finished_spans() if s.kind is SpanKind.SERVER]


def test_disabled_tracing_builds_no_provider() -> None:
    assert build_tracer_provider(make_settings(otel_enabled=False)) is None


def test_enabled_tracing_requires_endpoint_without_custom_exporter() -> None:
    with pytest.raises(ValueError, match="otel_endpoint"):
        build_tracer_provider(make_settings(otel_enabled=True))


def test_resource_identifies_the_service(provider: TracerProvider) -> None:
    attrs = provider.resource.attributes

    assert attrs["service.name"] == "stylesense"
    assert attrs["deployment.environment.name"] == "test"


def test_request_creates_server_span_named_by_route(
    client: TestClient, exporter: InMemorySpanExporter, provider: TracerProvider
) -> None:
    client.get("/items/42")
    provider.force_flush()

    assert _server_spans(exporter) == ["GET /items/{item_id}"]


def test_probes_are_not_traced(
    client: TestClient, exporter: InMemorySpanExporter, provider: TracerProvider
) -> None:
    client.get("/healthz")
    provider.force_flush()

    assert _server_spans(exporter) == []


def test_logs_are_correlated_with_trace(
    client: TestClient,
    exporter: InMemorySpanExporter,
    provider: TracerProvider,
    json_logs: LogReader,
) -> None:
    client.get("/items/42")
    provider.force_flush()

    log = next(r for r in json_logs() if r["event"] == "inside_handler")
    span = next(s for s in exporter.get_finished_spans() if s.kind is SpanKind.SERVER)
    assert span.context is not None
    assert log["trace_id"] == format(span.context.trace_id, "032x")
    assert len(str(log["span_id"])) == 16


def test_logs_outside_a_span_have_no_trace_ids(json_logs: LogReader) -> None:
    structlog.get_logger("test").info("no_span")

    log = next(r for r in json_logs() if r["event"] == "no_span")
    assert "trace_id" not in log


def test_otlp_exporter_is_batched_and_shuts_down_cleanly() -> None:
    settings = make_settings(otel_enabled=True, otel_endpoint="http://collector.invalid:4318/")

    provider = build_tracer_provider(settings)

    assert provider is not None
    processors = provider._active_span_processor._span_processors
    assert [type(p).__name__ for p in processors] == ["BatchSpanProcessor"]
    provider.shutdown()
