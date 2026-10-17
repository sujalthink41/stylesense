from collections.abc import Mapping
from datetime import timedelta

from prometheus_client import CollectorRegistry, Gauge

from stylesense.bootstrap.container import Container
from stylesense.guards.outbox import Handler, OutboxRelay
from stylesense.modules.tryon.service import TOPIC as TRYON_TOPIC
from stylesense.modules.users.service import PURGE_TOPIC
from stylesense.workers.heartbeat import FileHeartbeat
from stylesense.workers.runtime import PeriodicTask, Worker

# Longer than the try-on provider's own timeout (150 s), so its retry/fail logic decides.
TRYON_HANDLER_TIMEOUT_S = 210

OUTBOX_GAUGE_INTERVAL_S = 30
TOKEN_PRUNE_INTERVAL_S = 6 * 3_600
EMBED_INTERVAL_S = 60
EMBED_BATCH = 64
EVENT_PRUNE_INTERVAL_S = 24 * 3_600
EVENT_RETENTION = timedelta(days=90)
MEDIA_PURGE_INTERVAL_S = 15 * 60


def default_handlers(container: Container) -> dict[str, Handler]:
    """Outbox topic -> handler. Each feature registers its topics here."""
    return {PURGE_TOPIC: container.users.handle_purge, TRYON_TOPIC: container.tryon.handle}


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
        topic_timeouts_s={TRYON_TOPIC: TRYON_HANDLER_TIMEOUT_S},
    )
    pending = Gauge("outbox_pending", "Outbox messages waiting for delivery", registry=registry)

    async def relay_outbox() -> bool:
        return await relay.run_batch() >= settings.outbox_batch_size

    async def measure_backlog() -> bool:
        pending.set(await relay.pending_count())
        return False

    async def prune_tokens() -> bool:
        await container.auth.prune_expired()
        return False

    async def prune_session_events() -> bool:
        await container.stylist.prune_events(older_than=EVENT_RETENTION)
        return False

    async def purge_media() -> bool:
        # Photos and try-on results live 24 h; the storage copies go first, then the rows.
        uploads = await container.uploads.purge_expired()
        if container.tryon.metrics and uploads:
            container.tryon.metrics.purged.labels("upload").inc(uploads)
        return uploads + await container.tryon.purge_expired() > 0

    async def embed_catalog() -> bool:
        return await container.catalog.embed_pending(batch_size=EMBED_BATCH) >= EMBED_BATCH

    return Worker(
        [
            PeriodicTask("outbox.relay", settings.outbox_poll_interval_s, relay_outbox),
            PeriodicTask("outbox.backlog", OUTBOX_GAUGE_INTERVAL_S, measure_backlog),
            PeriodicTask("auth.prune_tokens", TOKEN_PRUNE_INTERVAL_S, prune_tokens, exclusive=True),
            PeriodicTask("catalog.embed", EMBED_INTERVAL_S, embed_catalog),
            PeriodicTask("media.purge", MEDIA_PURGE_INTERVAL_S, purge_media, exclusive=True),
            PeriodicTask(
                "stylist.prune_events", EVENT_PRUNE_INTERVAL_S, prune_session_events, exclusive=True
            ),
        ],
        locks=container.locks,
        heartbeat=FileHeartbeat(settings.worker_heartbeat_file).beat,
        registry=registry,
    )
