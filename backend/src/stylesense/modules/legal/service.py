"""Legal pages live in the database: the web pages and the app read the latest published
version; publishing adds a new version (old ones stay for the record)."""

import time
from collections.abc import Callable

import structlog
from sqlalchemy import func, select

from stylesense.infra.database import UnitOfWork
from stylesense.modules.legal.models import LegalDocument
from stylesense.modules.legal.schemas import LegalKind, LegalPublish, LegalView
from stylesense.platform.clock import Clock
from stylesense.platform.errors import NotFoundError

logger = structlog.get_logger(__name__)


class LegalNotFoundError(NotFoundError):
    code = "legal_not_found"
    title = "That page isn't published yet"


class LegalService:
    def __init__(
        self,
        uow: Callable[[], UnitOfWork],
        *,
        clock: Clock,
        support_email: str,
        cache_s: float = 300,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._email = support_email
        self._cache_s = cache_s
        self._now = now
        self._cache: dict[str, tuple[float, LegalView]] = {}

    async def latest(self, kind: LegalKind) -> LegalView:
        """The current version, ready to show (cached for a few minutes: pages are read a lot,
        published rarely)."""
        hit = self._cache.get(kind)
        if hit and self._now() - hit[0] < self._cache_s:
            return hit[1]
        async with self._uow() as uow:
            doc = await uow.session.scalar(
                select(LegalDocument)
                .where(LegalDocument.kind == kind, LegalDocument.published_at <= self._clock.now())
                .order_by(LegalDocument.version.desc())
                .limit(1)
            )
        if doc is None:
            raise LegalNotFoundError
        view = self._view(doc)
        self._cache[kind] = (self._now(), view)
        return view

    async def publish(self, body: LegalPublish) -> LegalView:
        async with self._uow() as uow:
            s = uow.session
            current = await s.scalar(
                select(func.max(LegalDocument.version)).where(LegalDocument.kind == body.kind)
            )
            doc = LegalDocument(
                kind=body.kind,
                version=(current or 0) + 1,
                title=body.title,
                body_html=body.body_html,
                published_at=self._clock.now(),
            )
            s.add(doc)
            await s.flush()
            view = self._view(doc)
        self._cache.pop(body.kind, None)
        logger.info("legal_published", kind=body.kind, version=view.version)
        return view

    def _view(self, doc: LegalDocument) -> LegalView:
        return LegalView(
            kind=doc.kind,
            version=doc.version,
            title=doc.title,
            body_html=doc.body_html.replace("{{support_email}}", self._email),
            published_at=doc.published_at,
        )
