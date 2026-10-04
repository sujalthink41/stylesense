from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.sdk.trace import TracerProvider
from prometheus_client import CollectorRegistry, GCCollector, PlatformCollector, ProcessCollector

from stylesense.api.health import router as health_router
from stylesense.bootstrap.container import Container, build_container
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
    settings: Settings | None = None, *, tracer_provider: TracerProvider | None = None
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.env is not Environment.LOCAL)
    configure_error_reporting(settings)
    provider = tracer_provider or build_tracer_provider(settings)
    registry = _metrics_registry()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = build_container(settings)
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
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
            expose_headers=["X-Request-ID", "Retry-After"],
        )
    # Added last so it wraps everything: every response gets an id, every request is measured.
    app.add_middleware(
        RequestContextMiddleware, metrics=HttpMetrics(registry), quiet_paths=QUIET_PATHS
    )
    app.include_router(health_router)
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
