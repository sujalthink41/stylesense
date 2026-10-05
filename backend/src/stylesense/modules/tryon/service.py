"""Virtual try-on as a background job.

    POST /tryon ─► job (queued) + outbox message, one transaction
    worker      ─► running ─► provider.render ─► copy result into storage ─► done
                          └─► busy/timeout: back to queued, outbox retries (≤ MAX_ATTEMPTS)
                          └─► refused photo: failed (not retryable)

Paid calls are protected three ways: an Idempotency-Key on the request (API layer), a per-user
advisory lock plus a unique "active job" index (a double tap finds the existing job), and the
job id passed to the provider as its idempotency key.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import timedelta

import structlog
from prometheus_client import CollectorRegistry, Counter
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from stylesense.guards.outbox import OutboxEnvelope, OutboxWriter
from stylesense.infra.database import UnitOfWork
from stylesense.modules.catalog.exceptions import ProductNotFoundError
from stylesense.modules.catalog.models import Product
from stylesense.modules.catalog.service import CatalogService
from stylesense.modules.polls.models import Poll
from stylesense.modules.sharing.models import Share
from stylesense.modules.tryon.exceptions import (
    TryOnNotFoundError,
    TryOnNotRetryableError,
    TryOnUnavailableError,
)
from stylesense.modules.tryon.models import ContentReport, TryOnJob
from stylesense.modules.tryon.ports import (
    TryOnProvider,
    TryOnRejectedError,
    TryOnRetryableError,
)
from stylesense.modules.tryon.schemas import ReportCreate, ReportReceipt, TryOnCreate, TryOnView
from stylesense.modules.uploads.exceptions import DailyLimitError
from stylesense.modules.uploads.models import Upload
from stylesense.modules.uploads.ports import (
    MediaRejectedError,
    MediaStore,
    MediaUnavailableError,
)
from stylesense.modules.uploads.service import UploadsService
from stylesense.platform.clock import Clock
from stylesense.platform.ids import new_id

logger = structlog.get_logger(__name__)

TOPIC = "tryon.run"
MAX_ATTEMPTS = 3
RENDER_TIMEOUT_S = 120
RESULT_PREFIX = "stylesense/t"
PURGE_BATCH = 200
EVENTS_POLL_S = 1.0
EVENTS_MAX_S = 180
_ACTIVE = ("queued", "running", "done")
_REJECTED = "We couldn't use that photo. Try a clear, well-lit photo of yourself."
_GAVE_UP = "Try-on is busy right now. Tap retry in a minute."
_EXPIRED = "Your photo has expired. Take a new one to try again."
_UNSAVABLE = "We couldn't save this try-on. Please try a different item."
_OUTCOMES = {"done": "done", _REJECTED: "rejected", _GAVE_UP: "gave_up", _UNSAVABLE: "unsavable"}


class MediaMetrics:
    """Bounded labels only: outcome and kind."""

    def __init__(self, registry: CollectorRegistry) -> None:
        self.jobs = Counter(
            "tryon_jobs", "Try-on jobs finished, by outcome", ["outcome"], registry=registry
        )
        self.purged = Counter(
            "media_purged", "Stored images deleted after expiry", ["kind"], registry=registry
        )


class TryOnService:
    def __init__(
        self,
        uow: Callable[[], UnitOfWork],
        *,
        uploads: UploadsService,
        catalog: CatalogService,
        store: MediaStore | None,
        provider: TryOnProvider | None,
        outbox: OutboxWriter,
        clock: Clock,
        ttl: timedelta,
        daily_limit: int,
        global_daily_limit: int,
        metrics: MediaMetrics | None = None,
    ) -> None:
        self._uow = uow
        self._uploads = uploads
        self._catalog = catalog
        self._store = store
        self._provider = provider
        self._outbox = outbox
        self._clock = clock
        self._ttl = ttl
        self._daily_limit = daily_limit
        self._global_limit = global_daily_limit
        self.metrics = metrics

    @property
    def enabled(self) -> bool:
        return self._provider is not None and self._store is not None

    # ---------- requests ----------

    async def request(self, user_id: uuid.UUID, body: TryOnCreate) -> tuple[TryOnView, bool]:
        """Returns (job, created). The same selfie + product while a job is active = that job."""
        if self._provider is None or self._store is None:
            raise TryOnUnavailableError
        await self._uploads.image_url(user_id, body.selfie_upload_id, kind="selfie")  # owned, ready
        product = (await self._catalog.summaries([body.product_id])).get(body.product_id)
        if product is None or not product.primary_image_url:
            raise ProductNotFoundError
        now = self._clock.now()
        async with self._uow() as uow:
            s = uow.session
            # One user's requests run one at a time: quota checks can't race each other.
            await s.execute(select(func.pg_advisory_xact_lock(_lock_key(user_id))))
            existing = await s.scalar(
                select(TryOnJob).where(
                    TryOnJob.user_id == user_id,
                    TryOnJob.selfie_upload_id == body.selfie_upload_id,
                    TryOnJob.product_id == body.product_id,
                    TryOnJob.status.in_(_ACTIVE),
                )
            )
            if existing is not None:
                return self._view(existing), False
            since = now - timedelta(days=1)
            counted = TryOnJob.status != "failed"  # failures don't use up the quota
            mine = await s.scalar(
                select(func.count()).where(
                    TryOnJob.user_id == user_id, TryOnJob.created_at > since, counted
                )
            )
            if (mine or 0) >= self._daily_limit:
                raise DailyLimitError
            everyone = await s.scalar(
                select(func.count()).where(TryOnJob.created_at > since, counted)
            )
            if (everyone or 0) >= self._global_limit:
                raise TryOnUnavailableError("today's try-on capacity is used up")
            job = TryOnJob(
                id=new_id(),
                user_id=user_id,
                selfie_upload_id=body.selfie_upload_id,
                product_id=body.product_id,
                provider=self._provider.name,
                status="queued",
                attempts=0,
                cost_micro_usd=0,
                created_at=now,
                expires_at=now + self._ttl,
            )
            s.add(job)
            await s.flush()
            await self._outbox.add(
                s, TOPIC, {"job_id": str(job.id)}, dedupe_key=f"{TOPIC}:{job.id}:0"
            )
        logger.info("tryon_requested", job_id=str(job.id), provider=job.provider)
        return self._view(job), True

    async def get(self, user_id: uuid.UUID, job_id: uuid.UUID) -> TryOnView:
        async with self._uow() as uow:
            return self._view(await self._owned(uow, user_id, job_id))

    async def retry(self, user_id: uuid.UUID, job_id: uuid.UUID) -> TryOnView:
        async with self._uow() as uow:
            s = uow.session
            await s.execute(select(func.pg_advisory_xact_lock(_lock_key(user_id))))
            job = await self._owned(uow, user_id, job_id, for_update=True)
            if job.status != "failed" or job.error == _REJECTED:
                raise TryOnNotRetryableError
            twin = await s.scalar(
                select(TryOnJob).where(
                    TryOnJob.user_id == user_id,
                    TryOnJob.selfie_upload_id == job.selfie_upload_id,
                    TryOnJob.product_id == job.product_id,
                    TryOnJob.status.in_(_ACTIVE),
                )
            )
            if twin is not None:  # the user already asked again: that job is the answer
                return self._view(twin)
            job.status, job.error, job.attempts = "queued", None, 0
            await self._outbox.add(
                s, TOPIC, {"job_id": str(job.id)}, dedupe_key=f"{TOPIC}:{job.id}:{new_id()}"
            )
            return self._view(job)

    async def events(self, user_id: uuid.UUID, job_id: uuid.UUID) -> AsyncIterator[TryOnView]:
        """Yields the job whenever its status changes, until it's done or failed."""
        last: str | None = None
        deadline = asyncio.get_running_loop().time() + EVENTS_MAX_S
        while True:
            view = await self.get(user_id, job_id)
            if view.status != last:
                last = view.status
                yield view
            if view.status in {"done", "failed"} or asyncio.get_running_loop().time() > deadline:
                return
            await asyncio.sleep(EVENTS_POLL_S)

    # ---------- worker ----------

    async def handle(self, envelope: OutboxEnvelope) -> None:
        """Outbox handler for `tryon.run`. Safe to deliver twice."""
        job_id = uuid.UUID(envelope.payload["job_id"])
        started = await self._start(job_id)
        if started is None:
            return
        person_url, garment_url = started
        assert self._provider is not None  # noqa: S101 # checked in _start
        assert self._store is not None  # noqa: S101
        try:
            async with asyncio.timeout(RENDER_TIMEOUT_S):
                result = await self._provider.render(
                    person_url=person_url, garment_url=garment_url, idempotency_key=str(job_id)
                )
            asset = await self._store.import_url(result.image_url, f"{RESULT_PREFIX}/{job_id}")
        except TryOnRejectedError:
            await self._finish(job_id, status="failed", error=_REJECTED)
            return
        except MediaRejectedError:
            logger.warning("tryon_result_refused_by_storage", job_id=str(job_id))
            await self._finish(job_id, status="failed", error=_UNSAVABLE)
            return
        except (TryOnRetryableError, TimeoutError, MediaUnavailableError) as exc:
            if await self._give_up_or_requeue(job_id):
                return
            raise TryOnRetryableError(str(exc)) from exc  # the outbox retries with backoff
        await self._finish(
            job_id,
            status="done",
            result_public_id=asset.public_id,
            cost_micro_usd=result.cost_micro_usd,
        )
        logger.info("tryon_done", job_id=str(job_id), cost_micro_usd=result.cost_micro_usd)

    async def _start(self, job_id: uuid.UUID) -> tuple[str, str] | None:
        if self._provider is None or self._store is None:
            raise TryOnUnavailableError  # config changed under a queued job: retry later
        async with self._uow() as uow:
            s = uow.session
            job = await s.get(TryOnJob, job_id, with_for_update=True)
            if job is None or job.status not in {"queued", "running"}:
                return None  # done, failed or gone: a duplicate delivery
            selfie = await s.get(Upload, job.selfie_upload_id)
            product = await s.get(Product, job.product_id)
            if (
                selfie is None
                or selfie.status != "ready"
                or selfie.expires_at <= self._clock.now()
                or product is None
                or not product.primary_image_url
            ):
                job.status, job.error, job.finished_at = "failed", _EXPIRED, self._clock.now()
                if self.metrics:
                    self.metrics.jobs.labels("expired").inc()
                return None
            job.status, job.started_at = "running", self._clock.now()
            job.attempts += 1
            return self._store.url(selfie.public_id, max_side=1024), product.primary_image_url

    async def _give_up_or_requeue(self, job_id: uuid.UUID) -> bool:
        async with self._uow() as uow:
            job = await uow.session.get(TryOnJob, job_id, with_for_update=True)
            if job is None:
                return True
            if job.attempts >= MAX_ATTEMPTS:
                job.status, job.error, job.finished_at = "failed", _GAVE_UP, self._clock.now()
                logger.warning("tryon_gave_up", job_id=str(job_id), attempts=job.attempts)
                if self.metrics:
                    self.metrics.jobs.labels("gave_up").inc()
                return True
            job.status = "queued"
            return False

    async def _finish(self, job_id: uuid.UUID, **changes: object) -> None:
        async with self._uow() as uow:
            job = await uow.session.get(TryOnJob, job_id, with_for_update=True)
            if job is None:
                return
            for key, value in changes.items():
                setattr(job, key, value)
            job.finished_at = self._clock.now()
        if self.metrics:
            outcome = (
                "done" if changes.get("status") == "done" else str(changes.get("error", "failed"))
            )
            self.metrics.jobs.labels(_OUTCOMES.get(outcome, "failed")).inc()

    async def purge_expired(self) -> int:
        """Delete expired try-on results from storage (selfies go with the uploads purge)."""
        if self._store is None:
            return 0
        async with self._uow() as uow:
            jobs = list(
                (
                    await uow.session.scalars(
                        select(TryOnJob)
                        .where(
                            TryOnJob.result_public_id.is_not(None),
                            TryOnJob.result_deleted_at.is_(None),
                            TryOnJob.expires_at <= self._clock.now(),
                        )
                        .order_by(TryOnJob.expires_at)
                        .limit(PURGE_BATCH)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            if not jobs:
                return 0
            await self._store.delete([j.result_public_id for j in jobs if j.result_public_id])
            now = self._clock.now()
            for job in jobs:
                job.result_deleted_at = now
        logger.info("tryon_results_purged", count=len(jobs))
        if self.metrics:
            self.metrics.purged.labels("tryon_result").inc(len(jobs))
        return len(jobs)

    # ---------- reports ----------

    async def report(self, user_id: uuid.UUID, body: ReportCreate) -> ReportReceipt:
        """Idempotent per (reporter, target). A reported try-on result is hidden at once."""
        async with self._uow() as uow:
            s = uow.session
            if body.target_kind == "tryon":
                job = await self._owned(uow, user_id, body.target_id, for_update=True)
                job.reported_at = job.reported_at or self._clock.now()
            elif not await _exists(s, body.target_kind, body.target_id):
                raise TryOnNotFoundError("nothing to report under that id")
            report_id = await s.scalar(
                insert(ContentReport)
                .values(
                    reporter_user_id=user_id,
                    target_kind=body.target_kind,
                    target_id=body.target_id,
                    reason=body.reason,
                    note=body.note,
                )
                .on_conflict_do_nothing(constraint="uq_content_reports_once")
                .returning(ContentReport.id)
            )
            if report_id is not None:
                logger.info("content_reported", kind=body.target_kind, reason=body.reason)
                return ReportReceipt(id=report_id, created=True)
            existing = await s.scalar(
                select(ContentReport.id).where(
                    ContentReport.reporter_user_id == user_id,
                    ContentReport.target_kind == body.target_kind,
                    ContentReport.target_id == body.target_id,
                )
            )
            assert existing is not None  # noqa: S101 # the conflict means it's there
            return ReportReceipt(id=existing, created=False)

    # ---------- helpers ----------

    async def _owned(
        self, uow: UnitOfWork, user_id: uuid.UUID, job_id: uuid.UUID, *, for_update: bool = False
    ) -> TryOnJob:
        stmt = select(TryOnJob).where(TryOnJob.id == job_id, TryOnJob.user_id == user_id)
        if for_update:
            stmt = stmt.with_for_update()
        job: TryOnJob | None = await uow.session.scalar(stmt)
        if job is None:
            raise TryOnNotFoundError
        return job

    def _view(self, job: TryOnJob) -> TryOnView:
        visible = (
            job.status == "done"
            and job.result_public_id is not None
            and job.result_deleted_at is None
            and job.reported_at is None
            and self._store is not None
        )
        return TryOnView(
            id=job.id,
            status=job.status,
            product_id=job.product_id,
            result_url=self._store.url(job.result_public_id, max_side=1200)  # type: ignore[union-attr, arg-type]
            if visible
            else None,
            error=job.error,
            retryable=job.status == "failed" and job.error != _REJECTED,
            created_at=job.created_at,
            expires_at=job.expires_at,
        )


def _lock_key(user_id: uuid.UUID) -> int:
    """An advisory-lock key per user: the UUID's random low 63 bits (its high bits are a
    timestamp, so users created in the same millisecond would share them)."""
    return user_id.int & ((1 << 63) - 1)


async def _exists(s: AsyncSession, kind: str, target_id: uuid.UUID) -> bool:
    column = {"product": Product.id, "share": Share.id, "poll": Poll.id}[kind]
    return await s.scalar(select(column).where(column == target_id)) is not None
