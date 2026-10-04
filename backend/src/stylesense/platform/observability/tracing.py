from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from typing import Any

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from sqlalchemy.ext.asyncio import AsyncEngine

from stylesense.platform.config import Settings

UNTRACED_URLS = "healthz,readyz,metrics"


def build_tracer_provider(
    settings: Settings, *, exporter: SpanExporter | None = None
) -> TracerProvider | None:
    if not settings.otel_enabled:
        return None
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": settings.name,
                "service.version": settings.version,
                "deployment.environment.name": settings.env.value,
            }
        ),
        sampler=ParentBased(TraceIdRatioBased(settings.otel_sample_ratio)),
    )
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        return provider
    if settings.otel_endpoint is None:
        raise ValueError("otel_endpoint is required when otel_enabled is true")
    endpoint = f"{str(settings.otel_endpoint).rstrip('/')}/v1/traces"
    # Batching keeps export off the request path; a slow collector never slows users.
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, timeout=5)))
    return provider


def instrument_app(app: FastAPI, provider: TracerProvider) -> None:
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, excluded_urls=UNTRACED_URLS)


def uninstrument_app(app: FastAPI) -> None:
    FastAPIInstrumentor.uninstrument_app(app)


def instrument_clients(engine: AsyncEngine, provider: TracerProvider) -> None:
    SQLAlchemyInstrumentor().instrument(
        engine=engine.sync_engine, tracer_provider=provider, enable_commenter=False
    )
    RedisInstrumentor().instrument(tracer_provider=provider)


def uninstrument_clients() -> None:
    SQLAlchemyInstrumentor().uninstrument()
    RedisInstrumentor().uninstrument()


@contextmanager
def untraced() -> Iterator[None]:
    """Run without emitting spans, e.g. frequent probes that would drown real traces."""
    with suppress_instrumentation():
        yield


def add_trace_context(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: correlate every log line with the active trace."""
    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict
