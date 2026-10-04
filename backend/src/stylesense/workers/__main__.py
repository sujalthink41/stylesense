"""Entry point: `python -m stylesense.workers`."""

import asyncio
import signal

import structlog
from prometheus_client import CollectorRegistry, ProcessCollector, start_http_server

from stylesense.bootstrap.container import build_container
from stylesense.platform.config import Environment, get_settings
from stylesense.platform.logging import configure_logging
from stylesense.platform.observability.error_reporting import configure_error_reporting
from stylesense.workers.app import build_worker, default_handlers

logger = structlog.get_logger("stylesense.worker")


async def main(stop: asyncio.Event | None = None) -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.env is not Environment.LOCAL)
    configure_error_reporting(settings)

    registry = CollectorRegistry()
    ProcessCollector(registry=registry)
    metrics_server, _ = start_http_server(settings.worker_metrics_port, registry=registry)

    container = build_container(settings)
    worker = build_worker(container, handlers=default_handlers(container), registry=registry)
    if stop is None:
        stop = asyncio.Event()
        _install_signal_handlers(stop)

    logger.info("worker_started", env=settings.env, version=settings.version)
    try:
        await worker.run(stop)
    finally:
        await container.aclose()
        metrics_server.shutdown()
        metrics_server.server_close()
        logger.info("worker_stopped")


def _install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows dev machines
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))


if __name__ == "__main__":
    asyncio.run(main())
