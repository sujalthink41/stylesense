from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.sdk.trace import TracerProvider
from prometheus_client import CollectorRegistry, GCCollector, PlatformCollector, ProcessCollector

from stylesense.api.health import router as health_router
from stylesense.api.middleware import LoadSheddingMiddleware
from stylesense.api.v1 import router as v1_router
from stylesense.bootstrap.container import Container, Telemetry, build_container
from stylesense.guards.bulkhead import Bulkhead
from stylesense.infra.database import pool_stats
from stylesense.platform.config import Environment, Settings, get_settings
from stylesense.platform.errors import register_error_handlers
from stylesense.platform.logging import configure_logging
from stylesense.platform.observability.error_reporting import configure_error_reporting
from stylesense.platform.observability.metrics import (
    HttpMetrics,
    PoolStatsCollector,
    metrics_router,
)
from stylesense.platform.observability.middleware import RequestContextMiddleware
from stylesense.platform.observability.tracing import (
    build_tracer_provider,
    instrument_app,
    instrument_clients,
    uninstrument_clients,
)

logger = structlog.get_logger(__name__)

QUIET_PATHS = frozenset({"/healthz", "/readyz", "/metrics"})


def create_app(
    settings: Settings | None = None,
    *,
    tracer_provider: TracerProvider | None = None,
    container_factory: Callable[..., Container] = build_container,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.env is not Environment.LOCAL)
    configure_error_reporting(settings)
    provider = tracer_provider or build_tracer_provider(settings)
    registry = _metrics_registry()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = container_factory(
            settings, telemetry=Telemetry(registry=registry, tracer_provider=provider)
        )
        app.state.container = container
        pool_collector = _attach_client_telemetry(container, registry, provider)
        logger.info("startup", env=settings.env, version=settings.version)
        try:
            yield
        finally:
            registry.unregister(pool_collector)
            if provider is not None:
                uninstrument_clients()
                provider.shutdown()  # flushes buffered spans
            await container.aclose()
            logger.info("shutdown")

    app = FastAPI(
        title="StyleSense API",
        version=settings.version,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.tracer_provider = provider
    register_error_handlers(app)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "Idempotency-Key",
                "If-Match",
                "If-None-Match",
                "X-Request-ID",
                "X-GenUI-Version",
                "X-Voter-Token",
            ],
            expose_headers=["X-Request-ID", "Retry-After", "ETag", "X-RateLimit-Remaining"],
        )
    # Probes stay exempt: a busy instance is still alive and must not be restarted.
    app.add_middleware(
        LoadSheddingMiddleware,
        bulkhead=Bulkhead(
            "http", max_concurrent=settings.max_in_flight, max_waiting=settings.max_queued
        ),
        exempt_paths=QUIET_PATHS,
    )
    # Added last so it wraps everything: every response gets an id, every request is measured.
    app.add_middleware(
        RequestContextMiddleware, metrics=HttpMetrics(registry), quiet_paths=QUIET_PATHS
    )
    app.include_router(health_router)
    app.include_router(v1_router)
    if settings.metrics_enabled:
        app.include_router(metrics_router(registry))
    if provider is not None:
        instrument_app(app, provider)
    return app


def _metrics_registry() -> CollectorRegistry:
    # Per-app registry: no global state, so multiple apps (tests, workers) never collide.
    registry = CollectorRegistry()
    ProcessCollector(registry=registry)
    PlatformCollector(registry=registry)
    GCCollector(registry=registry)
    return registry


def _attach_client_telemetry(
    container: Container, registry: CollectorRegistry, provider: TracerProvider | None
) -> PoolStatsCollector:
    collector = PoolStatsCollector(lambda: pool_stats(container.engine))
    registry.register(collector)
    if provider is not None:
        instrument_clients(container.engine, provider)
    return collector
