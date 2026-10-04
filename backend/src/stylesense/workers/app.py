from collections.abc import Mapping

from prometheus_client import CollectorRegistry, Gauge

from stylesense.bootstrap.container import Container
from stylesense.guards.outbox import Handler, OutboxRelay
from stylesense.workers.heartbeat import FileHeartbeat
from stylesense.workers.runtime import PeriodicTask, Worker

OUTBOX_GAUGE_INTERVAL_S = 30


def build_worker(
    container: Container,
    *,
    handlers: Mapping[str, Handler],
    registry: CollectorRegistry | None = None,
) -> Worker:
    settings = container.settings
    registry = registry or CollectorRegistry()
    relay = OutboxRelay(
        container.session_factory,
        handlers,
        clock=container.clock,
        batch_size=settings.outbox_batch_size,
        max_attempts=settings.outbox_max_attempts,
    )
    pending = Gauge("outbox_pending", "Outbox messages waiting for delivery", registry=registry)

    async def relay_outbox() -> bool:
        return await relay.run_batch() >= settings.outbox_batch_size

    async def measure_backlog() -> bool:
        pending.set(await relay.pending_count())
        return False

    return Worker(
        [
            PeriodicTask("outbox.relay", settings.outbox_poll_interval_s, relay_outbox),
            PeriodicTask("outbox.backlog", OUTBOX_GAUGE_INTERVAL_S, measure_backlog),
        ],
        locks=container.locks,
        heartbeat=FileHeartbeat(settings.worker_heartbeat_file).beat,
        registry=registry,
    )
