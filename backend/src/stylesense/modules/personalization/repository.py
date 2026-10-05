import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from stylesense.modules.catalog.models import Product
from stylesense.modules.personalization.models import StyleProfile, Swipe


@dataclass(frozen=True, slots=True)
class ProductSignal:
    """What a swipe teaches: the item's embedding and its descriptive tags."""

    embedding: list[float] | None
    tags: list[str]


class PersonalizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add_swipe(
        self,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
        session_id: uuid.UUID | None,
        direction: str,
    ) -> bool:
        """True if stored; False if this (user, product, session) swipe already exists."""
        stmt = (
            insert(Swipe)
            .values(
                user_id=user_id, product_id=product_id, session_id=session_id, direction=direction
            )
            .on_conflict_do_nothing(constraint="uq_swipes_once")
            .returning(Swipe.id)
        )
        return (await self._s.execute(stmt)).scalar_one_or_none() is not None

    async def product_signal(self, product_id: uuid.UUID) -> ProductSignal | None:
        row = (
            await self._s.execute(
                select(Product.embedding, Product.tags, Product.category, Product.gender).where(
                    Product.id == product_id
                )
            )
        ).one_or_none()
        if row is None:
            return None
        embedding, tags, category, gender = row
        # Category and gender are hard filters already; learning them would only add noise.
        descriptive = [t for t in tags if t not in {category, gender}]
        return ProductSignal(
            embedding=list(embedding) if embedding is not None else None, tags=descriptive
        )

    async def profile(self, user_id: uuid.UUID, *, for_update: bool = False) -> StyleProfile | None:
        stmt = select(StyleProfile).where(StyleProfile.user_id == user_id)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self._s.scalars(stmt)).one_or_none()

    async def profile_for_update(self, user_id: uuid.UUID) -> StyleProfile:
        """Creates the row if needed, then locks it: concurrent swipes queue instead of racing."""
        await self._s.execute(insert(StyleProfile).values(user_id=user_id).on_conflict_do_nothing())
        profile = await self.profile(user_id, for_update=True)
        assert profile is not None  # noqa: S101  # just upserted
        return profile

    async def session_swipes(
        self, user_id: uuid.UUID, session_id: uuid.UUID, *, limit: int = 500
    ) -> Sequence[uuid.UUID]:
        stmt = (
            select(Swipe.product_id)
            .where(Swipe.user_id == user_id, Swipe.session_id == session_id)
            .order_by(Swipe.created_at.desc())
            .limit(limit)
        )
        return (await self._s.scalars(stmt)).all()
