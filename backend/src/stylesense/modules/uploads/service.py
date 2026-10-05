"""User photos: issue a signed upload slot → the app uploads straight to storage → confirm
(we check what actually landed) → use → deleted after `ttl` by the purge job.

We never trust the client's word that an upload is fine: `confirm` inspects the stored asset
and rejects (and deletes) anything of the wrong type, size or shape.
"""

import uuid
from collections.abc import Callable
from datetime import timedelta

import structlog
from sqlalchemy import func, select

from stylesense.guards.rate_limit import Algorithm, RateLimiter, RateLimitPolicy
from stylesense.infra.database import UnitOfWork
from stylesense.modules.uploads.exceptions import (
    DailyLimitError,
    UploadMissingError,
    UploadNotFoundError,
    UploadNotReadyError,
    UploadRejectedError,
)
from stylesense.modules.uploads.models import Upload
from stylesense.modules.uploads.ports import MediaStore, MediaUnavailableError, StoredAsset
from stylesense.modules.uploads.schemas import (
    ALLOWED_FORMATS,
    MAX_BYTES,
    MIN_SIDE,
    UploadForm,
    UploadKind,
    UploadView,
)
from stylesense.platform.clock import Clock
from stylesense.platform.ids import new_id

logger = structlog.get_logger(__name__)

PUBLIC_ID_PREFIX = "stylesense/u"
VISION_MAX_SIDE = 768  # what vision models get: plenty for garments, far fewer tokens
PURGE_BATCH = 200
_DAY = 86_400


class UploadsService:
    def __init__(
        self,
        uow: Callable[[], UnitOfWork],
        *,
        store: MediaStore | None,
        limiter: RateLimiter,
        clock: Clock,
        ttl: timedelta,
        daily_limit: int,
        photo_search_daily_limit: int,
    ) -> None:
        self._uow = uow
        self._store = store
        self._limiter = limiter
        self._clock = clock
        self._ttl = ttl
        self._daily_limit = daily_limit
        self._photo_policy = RateLimitPolicy(
            "photo.per_user", photo_search_daily_limit, _DAY, Algorithm.SLIDING_WINDOW
        )

    @property
    def enabled(self) -> bool:
        return self._store is not None

    async def create(self, user_id: uuid.UUID, kind: UploadKind) -> UploadView:
        store = self._require_store()
        now = self._clock.now()
        async with self._uow() as uow:
            today = await uow.session.scalar(
                select(func.count()).where(
                    Upload.user_id == user_id, Upload.created_at > now - timedelta(days=1)
                )
            )
            if (today or 0) >= self._daily_limit:
                raise DailyLimitError
            upload_id = new_id()
            upload = Upload(
                id=upload_id,
                user_id=user_id,
                kind=kind,
                public_id=f"{PUBLIC_ID_PREFIX}/{upload_id}",  # unguessable, never user-chosen
                status="pending",
                created_at=now,
                expires_at=now + self._ttl,
            )
            uow.session.add(upload)
        ticket = store.upload_ticket(upload.public_id)
        view = _view(upload)
        view.upload = UploadForm(url=ticket.url, fields=ticket.fields)
        return view

    async def confirm(self, user_id: uuid.UUID, upload_id: uuid.UUID) -> UploadView:
        """Idempotent: confirming a ready upload again just returns it."""
        store = self._require_store()
        async with self._uow() as uow:
            upload = await self._owned(uow, user_id, upload_id, for_update=True)
            if upload.status == "ready":
                return self._view_with_url(upload)
            if upload.status == "rejected":
                raise UploadRejectedError(upload.reject_reason or "rejected")
            if upload.status == "deleted" or upload.expires_at <= self._clock.now():
                raise UploadNotFoundError
            asset = await store.inspect(upload.public_id)
            if asset is None:
                raise UploadMissingError
            if (reason := _problem(asset)) is not None:
                upload.status, upload.reject_reason = "rejected", reason
                await store.delete([upload.public_id])
                logger.info("upload_rejected", upload_id=str(upload.id), reason=reason)
                rejected = UploadRejectedError(reason)
            else:
                upload.status, upload.confirmed_at = "ready", self._clock.now()
                upload.format, upload.bytes = asset.format, asset.bytes
                upload.width, upload.height = asset.width, asset.height
                rejected = None
        if rejected is not None:
            raise rejected
        return self._view_with_url(upload)

    async def get(self, user_id: uuid.UUID, upload_id: uuid.UUID) -> UploadView:
        async with self._uow() as uow:
            upload = await self._owned(uow, user_id, upload_id)
        return self._view_with_url(upload)

    async def delete(self, user_id: uuid.UUID, upload_id: uuid.UUID) -> None:
        """Delete now instead of waiting for expiry. Idempotent."""
        async with self._uow() as uow:
            upload = await self._owned(uow, user_id, upload_id, for_update=True)
            if upload.status == "deleted":
                return
            if self._store is not None:
                await self._store.delete([upload.public_id])
            upload.status, upload.deleted_at = "deleted", self._clock.now()

    async def image_url(
        self,
        user_id: uuid.UUID,
        upload_id: uuid.UUID,
        *,
        kind: UploadKind,
        max_side: int | None = VISION_MAX_SIDE,
    ) -> str:
        """A signed URL for a ready photo of the right kind (for vision and try-on)."""
        store = self._require_store()
        async with self._uow() as uow:
            upload = await self._owned(uow, user_id, upload_id)
        if upload.kind != kind or upload.status != "ready":
            raise UploadNotReadyError
        if upload.expires_at <= self._clock.now():
            raise UploadNotFoundError
        return store.url(upload.public_id, max_side=max_side)

    async def photo_for_search(self, user_id: uuid.UUID, upload_id: uuid.UUID) -> str:
        """Photo search costs a vision call: check the photo first, then spend a daily credit."""
        url = await self.image_url(user_id, upload_id, kind="photo_search")
        decision = await self._limiter.hit(self._photo_policy, f"user:{user_id}")
        if not decision.allowed:
            raise DailyLimitError
        return url

    async def purge_expired(self) -> int:
        """Delete expired photos from storage, then mark them. Safe to run concurrently."""
        if self._store is None:
            return 0
        async with self._uow() as uow:
            expired = list(
                (
                    await uow.session.scalars(
                        select(Upload)
                        .where(Upload.deleted_at.is_(None), Upload.expires_at <= self._clock.now())
                        .order_by(Upload.expires_at)
                        .limit(PURGE_BATCH)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            if not expired:
                return 0
            # Storage first: if it fails, rows stay unmarked and the next run retries.
            await self._store.delete([u.public_id for u in expired])
            now = self._clock.now()
            for upload in expired:
                upload.status, upload.deleted_at = "deleted", now
        logger.info("uploads_purged", count=len(expired))
        return len(expired)

    # ---------- helpers ----------

    def _require_store(self) -> MediaStore:
        if self._store is None:
            raise MediaUnavailableError("photo storage isn't configured")
        return self._store

    async def _owned(
        self, uow: UnitOfWork, user_id: uuid.UUID, upload_id: uuid.UUID, *, for_update: bool = False
    ) -> Upload:
        stmt = select(Upload).where(Upload.id == upload_id, Upload.user_id == user_id)
        if for_update:
            stmt = stmt.with_for_update()
        upload: Upload | None = await uow.session.scalar(stmt)
        if upload is None:
            raise UploadNotFoundError
        return upload

    def _view_with_url(self, upload: Upload) -> UploadView:
        view = _view(upload)
        if upload.status == "ready" and self._store is not None:
            view.url = self._store.url(upload.public_id, max_side=1200)
        return view


def _problem(asset: StoredAsset) -> str | None:
    if asset.format.lower() not in ALLOWED_FORMATS:
        return "unsupported_format"
    if asset.bytes > MAX_BYTES:
        return "too_large"
    if min(asset.width, asset.height) < MIN_SIDE:
        return "too_small"
    return None


def _view(upload: Upload) -> UploadView:
    return UploadView(
        id=upload.id,
        kind=upload.kind,
        status=upload.status,
        expires_at=upload.expires_at,
    )
