"""Share links: `/l/{slug}` on the public site, opening the app when it's installed.

Idempotent by content: sharing the same look twice returns the same link, so a retried or
double-tapped share never mints a second slug. Board shares follow the live board.
"""

import hashlib
import json
import uuid
from collections.abc import Callable
from typing import Protocol

import structlog
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from stylesense.infra.database import UnitOfWork
from stylesense.modules.catalog.exceptions import ProductNotFoundError
from stylesense.modules.catalog.service import CatalogService
from stylesense.modules.sharing.exceptions import ShareGoneError, ShareNotFoundError
from stylesense.modules.sharing.models import Share
from stylesense.modules.sharing.schemas import PublicShare, ShareCreate, ShareView
from stylesense.platform.clock import Clock
from stylesense.platform.slugs import new_slug

logger = structlog.get_logger(__name__)

_SLUG_ATTEMPTS = 5
MAX_SHARES_LISTED = 100


class BoardSource(Protocol):
    """What sharing needs from boards (BoardsService)."""

    async def owns(self, user_id: uuid.UUID, board_id: uuid.UUID) -> bool: ...

    async def shared_items(self, board_id: uuid.UUID) -> tuple[str, list[uuid.UUID]] | None: ...


class SharingService:
    def __init__(
        self,
        uow: Callable[[], UnitOfWork],
        *,
        catalog: CatalogService,
        boards: BoardSource,
        clock: Clock,
        public_url: str,
    ) -> None:
        self._uow = uow
        self._catalog = catalog
        self._boards = boards
        self._clock = clock
        self._public_url = public_url.rstrip("/")

    async def create(self, user_id: uuid.UUID, body: ShareCreate) -> tuple[ShareView, bool]:
        """Returns (share, created)."""
        if body.kind == "board":
            if not await self._boards.owns(user_id, body.board_id):  # type: ignore[arg-type]
                raise ShareNotFoundError("board not found")
        else:
            found = await self._catalog.summaries(body.product_ids)
            if len(found) != len(body.product_ids):
                raise ProductNotFoundError
        payload = {
            "title": body.title,
            "product_ids": [str(p) for p in body.product_ids],
            "board_id": str(body.board_id) if body.board_id else None,
        }
        content = hashlib.sha256(
            json.dumps({"kind": body.kind, **payload}, sort_keys=True).encode()
        ).hexdigest()
        async with self._uow() as uow:
            for _ in range(_SLUG_ATTEMPTS):
                inserted = await uow.session.scalar(
                    insert(Share)
                    .values(
                        user_id=user_id,
                        slug=new_slug(),
                        kind=body.kind,
                        payload=payload,
                        content_hash=content,
                    )
                    .on_conflict_do_nothing()
                    .returning(Share.id)
                )
                existing = await uow.session.scalar(
                    select(Share).where(Share.user_id == user_id, Share.content_hash == content)
                )
                if existing is not None:
                    if existing.revoked_at is not None:  # re-sharing revives the same link
                        existing.revoked_at = None
                    return self._view(existing), inserted is not None
                # Nothing inserted and no same-content row: the random slug collided. Retry.
        raise RuntimeError("could not allocate a share slug")  # ~impossible at 62**8

    async def list_mine(self, user_id: uuid.UUID) -> list[ShareView]:
        async with self._uow() as uow:
            rows = await uow.session.scalars(
                select(Share)
                .where(Share.user_id == user_id, Share.revoked_at.is_(None))
                .order_by(Share.created_at.desc())
                .limit(MAX_SHARES_LISTED)
            )
            return [self._view(s) for s in rows.all()]

    async def revoke(self, user_id: uuid.UUID, slug: str) -> None:
        """Idempotent; another user's slug looks missing."""
        async with self._uow() as uow:
            share = await uow.session.scalar(
                select(Share).where(Share.slug == slug, Share.user_id == user_id)
            )
            if share is None:
                raise ShareNotFoundError
            if share.revoked_at is None:
                share.revoked_at = self._clock.now()

    async def open(self, slug: str) -> PublicShare:
        """Public view; counts the view."""
        async with self._uow() as uow:
            share = await uow.session.scalar(
                update(Share)
                .where(Share.slug == slug, Share.revoked_at.is_(None))
                .values(views=Share.views + 1)
                .returning(Share)
            )
            if share is None:
                exists = await uow.session.scalar(select(Share.id).where(Share.slug == slug))
                raise ShareGoneError if exists else ShareNotFoundError
        title, ids = (
            share.payload.get("title"),
            [uuid.UUID(p) for p in share.payload["product_ids"]],
        )
        if share.kind == "board":
            live = await self._boards.shared_items(uuid.UUID(share.payload["board_id"]))
            if live is None:
                raise ShareGoneError  # the board was deleted
            title, ids = title or live[0], live[1]
        products = await self._catalog.summaries(ids)
        return PublicShare(
            slug=share.slug,
            kind=share.kind,
            title=title,
            products=[products[i] for i in ids if i in products],
            created_at=share.created_at,
        )

    def _view(self, share: Share) -> ShareView:
        return ShareView(
            slug=share.slug,
            kind=share.kind,
            url=f"{self._public_url}/l/{share.slug}",
            title=share.payload.get("title"),
            views=share.views,
            created_at=share.created_at,
        )
