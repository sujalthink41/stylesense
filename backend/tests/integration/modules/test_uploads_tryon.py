"""CP12: photo uploads, virtual try-on jobs, reports and the 24 h purge."""

import asyncio
import uuid
from datetime import timedelta

import pytest
from prometheus_client import CollectorRegistry
from redis.asyncio import Redis
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stylesense.guards.outbox import OutboxMessage, OutboxRelay, OutboxWriter
from stylesense.guards.rate_limit import RateLimiter
from stylesense.infra.database import UnitOfWork
from stylesense.integrations.embeddings.hashing import HashingEmbedder
from stylesense.modules.catalog.exceptions import ProductNotFoundError
from stylesense.modules.catalog.models import Product
from stylesense.modules.catalog.service import CatalogService
from stylesense.modules.tryon.exceptions import (
    TryOnNotFoundError,
    TryOnNotRetryableError,
    TryOnQuotaError,
    TryOnUnavailableError,
)
from stylesense.modules.tryon.models import TryOnJob
from stylesense.modules.tryon.schemas import ReportCreate, TryOnCreate
from stylesense.modules.tryon.service import MAX_ATTEMPTS, TOPIC, MediaMetrics, TryOnService
from stylesense.modules.uploads.exceptions import (
    DailyLimitError,
    UploadMissingError,
    UploadNotFoundError,
    UploadNotReadyError,
    UploadRejectedError,
)
from stylesense.modules.uploads.models import Upload
from stylesense.modules.uploads.ports import MediaUnavailableError, StoredAsset
from stylesense.modules.uploads.service import UploadsService
from stylesense.modules.users.models import User
from tests.fakes.clock import FixedClock
from tests.fakes.media import FakeMediaStore, ScriptedTryOn

TTL = timedelta(hours=24)


class World:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        redis: Redis,
        *,
        store: FakeMediaStore | None = None,
        provider: ScriptedTryOn | None = None,
        tryon_daily: int = 3,
        tryon_global: int = 100,
    ) -> None:
        def uow() -> UnitOfWork:
            return UnitOfWork(sessions)

        self.sessions = sessions
        self.clock = FixedClock()
        self.store = store if store is not None else FakeMediaStore()
        self.provider = provider if provider is not None else ScriptedTryOn()
        catalog = CatalogService(uow, clock=self.clock, embedder=HashingEmbedder())
        self.uploads = UploadsService(
            uow,
            store=self.store,
            limiter=RateLimiter(redis, self.clock, prefix=f"t{uuid.uuid4().hex}:"),
            clock=self.clock,
            ttl=TTL,
            daily_limit=5,
            photo_search_daily_limit=2,
        )
        self.tryon = TryOnService(
            uow,
            uploads=self.uploads,
            catalog=catalog,
            store=self.store,
            provider=self.provider,
            outbox=OutboxWriter(self.clock),
            clock=self.clock,
            ttl=TTL,
            daily_limit=tryon_daily,
            global_daily_limit=tryon_global,
        )

    async def ready_photo(self, user_id: uuid.UUID, kind: str = "selfie") -> uuid.UUID:
        upload = await self.uploads.create(user_id, kind)  # type: ignore[arg-type]
        self.store.simulate_upload(_public_id(upload.upload.fields))  # type: ignore[union-attr]
        await self.uploads.confirm(user_id, upload.id)
        return upload.id

    async def run_queue(self) -> None:
        """One pass of the real outbox relay (zero backoff, so retries happen in the pass)."""
        relay = OutboxRelay(
            self.sessions,
            {TOPIC: self.tryon.handle},
            clock=self.clock,
            batch_size=50,
            max_attempts=10,
            base_backoff_s=0,
        )
        await relay.run_batch()


def _public_id(fields: dict[str, str]) -> str:
    return fields["public_id"]


@pytest.fixture
async def world(catalog_sessions: async_sessionmaker[AsyncSession], redis: Redis) -> World:
    # The catalog DB is shared by the module: start each test with an empty try-on queue.
    async with catalog_sessions() as s, s.begin():
        await s.execute(
            update(OutboxMessage).where(OutboxMessage.status == "pending").values(status="done")
        )
    return World(catalog_sessions, redis)


async def _product(sessions: async_sessionmaker[AsyncSession], n: int = 0) -> uuid.UUID:
    async with sessions() as s:
        ids = (await s.scalars(select(Product.id).order_by(Product.id).limit(n + 1))).all()
    return ids[n]


async def _user(sessions: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with sessions() as s, s.begin():
        user = User(email=f"{uuid.uuid4().hex}@example.com")
        s.add(user)
    return user.id


# ---------- uploads ----------


async def test_an_upload_slot_is_signed_private_and_expires_in_a_day(
    world: World, user_id: uuid.UUID
) -> None:
    upload = await world.uploads.create(user_id, "photo_search")

    assert upload.status == "pending"
    assert upload.upload is not None
    assert upload.upload.fields["public_id"] == f"stylesense/u/{upload.id}"
    assert upload.expires_at == world.clock.now() + TTL
    assert upload.url is None


async def test_confirm_checks_what_actually_landed(world: World, user_id: uuid.UUID) -> None:
    upload = await world.uploads.create(user_id, "selfie")

    with pytest.raises(UploadMissingError):
        await world.uploads.confirm(user_id, upload.id)
    world.store.simulate_upload(f"stylesense/u/{upload.id}")
    ready = await world.uploads.confirm(user_id, upload.id)
    again = await world.uploads.confirm(user_id, upload.id)

    assert (ready.status, again.status) == ("ready", "ready")
    assert ready.url is not None


@pytest.mark.parametrize(
    ("asset", "reason"),
    [
        (StoredAsset("", "gif", 1_000, 800, 800), "unsupported_format"),
        (StoredAsset("", "jpg", 9 * 1024 * 1024, 800, 800), "too_large"),
        (StoredAsset("", "png", 1_000, 120, 800), "too_small"),
    ],
)
async def test_bad_uploads_are_rejected_and_deleted(
    world: World, user_id: uuid.UUID, asset: StoredAsset, reason: str
) -> None:
    upload = await world.uploads.create(user_id, "selfie")
    public_id = f"stylesense/u/{upload.id}"
    world.store.simulate_upload(public_id, asset)

    with pytest.raises(UploadRejectedError) as first:
        await world.uploads.confirm(user_id, upload.id)
    with pytest.raises(UploadRejectedError):
        await world.uploads.confirm(user_id, upload.id)

    assert first.value.extra == {"reason": reason}
    assert public_id not in world.store.assets


async def test_uploads_are_private_to_their_owner(world: World, user_id: uuid.UUID) -> None:
    upload_id = await world.ready_photo(user_id)
    intruder = await _user(world.sessions)

    for call in (world.uploads.get, world.uploads.confirm, world.uploads.delete):
        with pytest.raises(UploadNotFoundError):
            await call(intruder, upload_id)


async def test_daily_upload_limit(world: World, user_id: uuid.UUID) -> None:
    for _ in range(5):
        await world.uploads.create(user_id, "photo_search")

    with pytest.raises(DailyLimitError):
        await world.uploads.create(user_id, "photo_search")
    world.clock.advance(timedelta(days=1, seconds=1))
    await world.uploads.create(user_id, "photo_search")


async def test_photo_search_needs_a_ready_photo_of_that_kind_and_spends_a_credit(
    world: World, user_id: uuid.UUID
) -> None:
    selfie = await world.ready_photo(user_id, "selfie")
    photo = await world.ready_photo(user_id, "photo_search")

    with pytest.raises(UploadNotReadyError):
        await world.uploads.photo_for_search(user_id, selfie)
    assert (await world.uploads.photo_for_search(user_id, photo)).endswith("side=768&sig=ok")
    await world.uploads.photo_for_search(user_id, photo)
    with pytest.raises(DailyLimitError):
        await world.uploads.photo_for_search(user_id, photo)


async def test_deleting_a_photo_removes_it_from_storage_now(
    world: World, user_id: uuid.UUID
) -> None:
    upload_id = await world.ready_photo(user_id)

    await world.uploads.delete(user_id, upload_id)
    await world.uploads.delete(user_id, upload_id)

    assert f"stylesense/u/{upload_id}" not in world.store.assets
    assert (await world.uploads.get(user_id, upload_id)).status == "deleted"


async def test_without_storage_photos_are_unavailable(
    catalog_sessions: async_sessionmaker[AsyncSession], redis: Redis, user_id: uuid.UUID
) -> None:
    w = World(catalog_sessions, redis)
    w.uploads._store = None

    with pytest.raises(MediaUnavailableError):
        await w.uploads.create(user_id, "selfie")


# ---------- purge (exit criterion) ----------


async def test_expired_photos_and_results_are_purged_from_storage(
    world: World, user_id: uuid.UUID
) -> None:
    selfie = await world.ready_photo(user_id)
    job, _ = await world.tryon.request(
        user_id, TryOnCreate(selfie_upload_id=selfie, product_id=await _product(world.sessions))
    )
    await world.run_queue()
    result_id = f"stylesense/t/{job.id}"
    assert result_id in world.store.assets

    world.clock.advance(TTL - timedelta(minutes=1))
    assert await world.uploads.purge_expired() == 0  # not yet
    world.clock.advance(timedelta(minutes=2))
    assert await world.uploads.purge_expired() >= 1
    assert await world.tryon.purge_expired() == 1

    assert f"stylesense/u/{selfie}" not in world.store.assets
    assert result_id not in world.store.assets
    assert (await world.tryon.get(user_id, job.id)).result_url is None
    assert await world.uploads.purge_expired() == 0
    assert await world.tryon.purge_expired() == 0


async def test_a_storage_outage_postpones_the_purge_without_losing_track(
    world: World, user_id: uuid.UUID
) -> None:
    upload_id = await world.ready_photo(user_id)
    world.clock.advance(TTL + timedelta(seconds=1))
    world.store.down = True

    with pytest.raises(MediaUnavailableError):
        await world.uploads.purge_expired()
    world.store.down = False

    assert await world.uploads.purge_expired() >= 1
    assert f"stylesense/u/{upload_id}" not in world.store.assets


async def test_photos_of_a_deleted_account_are_still_purged(
    world: World, catalog_sessions: async_sessionmaker[AsyncSession]
) -> None:
    owner = await _user(catalog_sessions)
    upload_id = await world.ready_photo(owner)

    async with catalog_sessions() as s, s.begin():
        await s.execute(delete(User).where(User.id == owner))
    world.clock.advance(TTL + timedelta(seconds=1))
    await world.uploads.purge_expired()

    async with catalog_sessions() as s:
        row = await s.get(Upload, upload_id)
    assert row is not None
    assert (row.user_id, row.status) == (None, "deleted")
    assert f"stylesense/u/{upload_id}" not in world.store.assets


# ---------- try-on ----------


async def test_a_double_tap_creates_one_paid_try_on(world: World, user_id: uuid.UUID) -> None:
    body = TryOnCreate(
        selfie_upload_id=await world.ready_photo(user_id),
        product_id=await _product(world.sessions),
    )

    results = await asyncio.gather(*(world.tryon.request(user_id, body) for _ in range(6)))
    await world.run_queue()
    await world.run_queue()  # a redelivery changes nothing

    assert sum(created for _, created in results) == 1
    assert len({job.id for job, _ in results}) == 1
    assert world.provider.calls == [str(results[0][0].id)]  # the provider was paid once
    done = await world.tryon.get(user_id, results[0][0].id)
    assert done.status == "done"
    assert done.result_url is not None


async def test_the_same_look_again_reuses_the_result_without_paying_twice(
    world: World, user_id: uuid.UUID
) -> None:
    body = TryOnCreate(
        selfie_upload_id=await world.ready_photo(user_id), product_id=await _product(world.sessions)
    )
    first, _ = await world.tryon.request(user_id, body)
    await world.run_queue()

    again, created = await world.tryon.request(user_id, body)

    assert (again.id, again.status, created) == (first.id, "done", False)
    assert len(world.provider.calls) == 1  # one paid render for the look


async def test_a_finished_job_records_its_cost_and_stored_result(
    world: World, user_id: uuid.UUID
) -> None:
    job, _ = await world.tryon.request(
        user_id,
        TryOnCreate(
            selfie_upload_id=await world.ready_photo(user_id),
            product_id=await _product(world.sessions),
        ),
    )
    await world.run_queue()

    async with world.sessions() as s:
        row = await s.get(TryOnJob, job.id)
    assert row is not None
    assert (row.status, row.cost_micro_usd, row.attempts) == ("done", 40_000, 1)
    assert world.store.imported == [(f"https://vendor.test/{job.id}.jpg", f"stylesense/t/{job.id}")]


async def test_a_busy_provider_is_retried_then_succeeds(world: World, user_id: uuid.UUID) -> None:
    world.provider.busy(times=1)
    job, _ = await world.tryon.request(
        user_id,
        TryOnCreate(
            selfie_upload_id=await world.ready_photo(user_id),
            product_id=await _product(world.sessions),
        ),
    )

    await world.run_queue()

    assert (await world.tryon.get(user_id, job.id)).status == "done"
    assert world.provider.calls == [str(job.id)] * 2  # same idempotency key both times


async def test_a_provider_outage_fails_softly_and_retry_recovers_without_quota(
    world: World, user_id: uuid.UUID
) -> None:
    world.provider.busy(times=MAX_ATTEMPTS)
    body = TryOnCreate(
        selfie_upload_id=await world.ready_photo(user_id),
        product_id=await _product(world.sessions),
    )
    job, _ = await world.tryon.request(user_id, body)
    await world.run_queue()

    failed = await world.tryon.get(user_id, job.id)
    assert (failed.status, failed.retryable) == ("failed", True)
    assert failed.error is not None

    retried = await world.tryon.retry(user_id, job.id)
    await world.run_queue()

    assert retried.status == "queued"
    assert (await world.tryon.get(user_id, job.id)).status == "done"
    for n in range(2):  # the failed attempts didn't eat the 3-a-day quota
        await world.tryon.request(
            user_id,
            TryOnCreate(
                selfie_upload_id=body.selfie_upload_id,
                product_id=await _product(world.sessions, n + 1),
            ),
        )


async def test_a_refused_photo_fails_for_good(world: World, user_id: uuid.UUID) -> None:
    world.provider.refuse()
    job, _ = await world.tryon.request(
        user_id,
        TryOnCreate(
            selfie_upload_id=await world.ready_photo(user_id),
            product_id=await _product(world.sessions),
        ),
    )
    await world.run_queue()

    failed = await world.tryon.get(user_id, job.id)
    assert (failed.status, failed.retryable) == ("failed", False)
    with pytest.raises(TryOnNotRetryableError):
        await world.tryon.retry(user_id, job.id)


async def test_a_selfie_that_expired_in_the_queue_fails_gracefully(
    world: World, user_id: uuid.UUID
) -> None:
    job, _ = await world.tryon.request(
        user_id,
        TryOnCreate(
            selfie_upload_id=await world.ready_photo(user_id),
            product_id=await _product(world.sessions),
        ),
    )
    world.clock.advance(TTL + timedelta(seconds=1))

    await world.run_queue()

    failed = await world.tryon.get(user_id, job.id)
    assert failed.status == "failed"
    assert "expired" in (failed.error or "")
    assert world.provider.calls == []


async def test_try_on_quota_is_per_user_and_per_day(world: World, user_id: uuid.UUID) -> None:
    selfie = await world.ready_photo(user_id)
    for n in range(3):
        await world.tryon.request(
            user_id,
            TryOnCreate(selfie_upload_id=selfie, product_id=await _product(world.sessions, n)),
        )

    quota = await world.tryon.quota(user_id)
    assert (quota.limit, quota.used, quota.remaining) == (3, 3, 0)
    assert quota.resets_at is not None

    with pytest.raises(TryOnQuotaError) as caught:
        await world.tryon.request(
            user_id,
            TryOnCreate(selfie_upload_id=selfie, product_id=await _product(world.sessions, 3)),
        )
    assert caught.value.extra["limit"] == 3
    assert "3 try-ons for today" in str(caught.value)


async def test_a_fresh_account_has_all_its_try_ons(world: World, user_id: uuid.UUID) -> None:
    quota = await world.tryon.quota(user_id)

    assert (quota.limit, quota.used, quota.remaining, quota.resets_at, quota.available) == (
        3,
        0,
        3,
        None,
        True,
    )


async def test_out_of_credit_fails_at_once_without_retries_or_using_quota(
    world: World, user_id: uuid.UUID
) -> None:
    world.provider.out_of_credit()
    job, _ = await world.tryon.request(
        user_id,
        TryOnCreate(
            selfie_upload_id=await world.ready_photo(user_id),
            product_id=await _product(world.sessions),
        ),
    )

    await world.run_queue()

    failed = await world.tryon.get(user_id, job.id)
    assert failed.status == "failed"
    assert "busy right now" in (failed.error or "")
    assert failed.retryable  # free retry later
    assert len(world.provider.calls) == 1  # no retry storm against an empty account
    assert (await world.tryon.quota(user_id)).remaining == 3  # failures don't count


async def test_concurrent_requests_for_different_items_respect_the_quota(
    world: World, user_id: uuid.UUID
) -> None:
    selfie = await world.ready_photo(user_id)
    products = [await _product(world.sessions, n) for n in range(6)]

    results = await asyncio.gather(
        *(
            world.tryon.request(user_id, TryOnCreate(selfie_upload_id=selfie, product_id=p))
            for p in products
        ),
        return_exceptions=True,
    )

    assert sum(not isinstance(r, Exception) for r in results) == 3
    assert all(isinstance(r, TryOnQuotaError) for r in results if isinstance(r, Exception))


async def test_the_global_daily_cap_protects_the_budget(
    catalog_sessions: async_sessionmaker[AsyncSession], redis: Redis, user_id: uuid.UUID
) -> None:
    w = World(catalog_sessions, redis, tryon_global=0)

    with pytest.raises(TryOnUnavailableError):
        await w.tryon.request(
            user_id,
            TryOnCreate(
                selfie_upload_id=await w.ready_photo(user_id),
                product_id=await _product(catalog_sessions),
            ),
        )


async def test_try_on_needs_my_ready_selfie_and_a_real_product(
    world: World, user_id: uuid.UUID
) -> None:
    mine = await world.ready_photo(user_id)
    photo = await world.ready_photo(user_id, "photo_search")
    theirs = await world.ready_photo(await _user(world.sessions))
    product = await _product(world.sessions)

    with pytest.raises(UploadNotFoundError):
        await world.tryon.request(user_id, TryOnCreate(selfie_upload_id=theirs, product_id=product))
    with pytest.raises(UploadNotReadyError):
        await world.tryon.request(user_id, TryOnCreate(selfie_upload_id=photo, product_id=product))
    with pytest.raises(ProductNotFoundError):
        await world.tryon.request(
            user_id, TryOnCreate(selfie_upload_id=mine, product_id=uuid.uuid4())
        )


async def test_try_on_is_unavailable_without_a_provider(
    catalog_sessions: async_sessionmaker[AsyncSession], redis: Redis, user_id: uuid.UUID
) -> None:
    w = World(catalog_sessions, redis)
    w.tryon._provider = None

    with pytest.raises(TryOnUnavailableError):
        await w.tryon.request(
            user_id,
            TryOnCreate(selfie_upload_id=uuid.uuid4(), product_id=await _product(catalog_sessions)),
        )


async def test_events_stream_status_changes_until_done(world: World, user_id: uuid.UUID) -> None:
    job, _ = await world.tryon.request(
        user_id,
        TryOnCreate(
            selfie_upload_id=await world.ready_photo(user_id),
            product_id=await _product(world.sessions),
        ),
    )

    async def watch() -> list[str]:
        return [view.status async for view in world.tryon.events(user_id, job.id)]

    watcher = asyncio.create_task(watch())
    await asyncio.sleep(0.2)
    await world.run_queue()

    assert await asyncio.wait_for(watcher, timeout=5) == ["queued", "done"]


# ---------- reports ----------


async def test_reporting_a_result_hides_it_and_reporting_twice_is_harmless(
    world: World, user_id: uuid.UUID
) -> None:
    job, _ = await world.tryon.request(
        user_id,
        TryOnCreate(
            selfie_upload_id=await world.ready_photo(user_id),
            product_id=await _product(world.sessions),
        ),
    )
    await world.run_queue()
    body = ReportCreate(target_kind="tryon", target_id=job.id, reason="inappropriate")

    first = await world.tryon.report(user_id, body)
    again = await world.tryon.report(user_id, body)

    assert (first.created, again.created, first.id == again.id) == (True, False, True)
    assert (await world.tryon.get(user_id, job.id)).result_url is None


async def test_reports_need_a_real_target_and_try_ons_stay_private(
    world: World, user_id: uuid.UUID
) -> None:
    job, _ = await world.tryon.request(
        user_id,
        TryOnCreate(
            selfie_upload_id=await world.ready_photo(user_id),
            product_id=await _product(world.sessions),
        ),
    )
    stranger = await _user(world.sessions)

    product_report = await world.tryon.report(
        stranger,
        ReportCreate(
            target_kind="product", target_id=await _product(world.sessions), reason="wrong_item"
        ),
    )
    assert product_report.created
    with pytest.raises(TryOnNotFoundError):
        await world.tryon.report(
            stranger, ReportCreate(target_kind="tryon", target_id=job.id, reason="offensive")
        )
    with pytest.raises(TryOnNotFoundError):
        await world.tryon.report(
            user_id, ReportCreate(target_kind="poll", target_id=uuid.uuid4(), reason="spam")
        )


async def test_a_result_storage_refuses_fails_once_without_retrying(
    world: World, user_id: uuid.UUID
) -> None:
    world.provider.result_url = "https://vendor.test/result.svg"
    job, _ = await world.tryon.request(
        user_id,
        TryOnCreate(
            selfie_upload_id=await world.ready_photo(user_id),
            product_id=await _product(world.sessions),
        ),
    )

    await world.run_queue()

    failed = await world.tryon.get(user_id, job.id)
    assert failed.status == "failed"
    assert "couldn't save" in (failed.error or "")
    assert len(world.provider.calls) == 1  # not retried: storage said no for good


async def test_outcomes_and_purges_are_measured(
    catalog_sessions: async_sessionmaker[AsyncSession], redis: Redis, user_id: uuid.UUID
) -> None:
    registry = CollectorRegistry()
    w = World(catalog_sessions, redis)
    w.tryon.metrics = MediaMetrics(registry)
    await w.tryon.request(
        user_id,
        TryOnCreate(
            selfie_upload_id=await w.ready_photo(user_id), product_id=await _product(w.sessions)
        ),
    )
    await w.run_queue()
    w.clock.advance(TTL + timedelta(seconds=1))
    await w.tryon.purge_expired()

    assert registry.get_sample_value("tryon_jobs_total", {"outcome": "done"}) == 1
    # >= 1: the module shares one database, so earlier tests' results expire too.
    assert (registry.get_sample_value("media_purged_total", {"kind": "tryon_result"}) or 0) >= 1
