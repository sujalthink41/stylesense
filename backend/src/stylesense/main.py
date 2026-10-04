from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from stylesense.api.health import router as health_router
from stylesense.bootstrap.container import build_container
from stylesense.platform.config import Environment, Settings, get_settings
from stylesense.platform.errors import register_error_handlers
from stylesense.platform.logging import configure_logging

logger = structlog.get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.env is not Environment.LOCAL)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = build_container(settings)
        app.state.container = container
        logger.info("startup", env=settings.env, version=settings.version)
        try:
            yield
        finally:
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
    register_error_handlers(app)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        )
    app.include_router(health_router)
    return app
