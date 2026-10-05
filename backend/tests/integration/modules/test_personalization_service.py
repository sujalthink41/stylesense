import asyncio
import uuid
from collections.abc import Sequence

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stylesense.ai.gateway.exceptions import AIUnavailableError
from stylesense.infra.database import UnitOfWork
from stylesense.integrations.embeddings.hashing import HashingEmbedder
from stylesense.modules.catalog.exceptions import ProductNotFoundError
from stylesense.modules.catalog.models import Product
from stylesense.modules.personalization.models import StyleProfile, Swipe
from stylesense.modules.personalization.schemas import Sizes, StyleProfileUpdate, SwipeInput
from stylesense.modules.personalization.service import PersonalizationService
from stylesense.modules.personalization.styles import STYLES
from stylesense.modules.users.models import User
from tests.fakes.clock import FixedClock


class DownEmbedder:
    model = "down"

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise AIUnavailableError("no embedding provider")


def _service(
    sessions: async_sessionmaker[AsyncSession], embedder: object | None = None
) -> PersonalizationService:
    return PersonalizationService(
        lambda: UnitOfWork(sessions),
        embedder=embedder or HashingEmbedder(),  # type: ignore[arg-type]
        clock=FixedClock(),
    )


async def _products(
    sessions: async_sessionmaker[AsyncSession], n: int, *, tag: str | None = None
) -> list[Product]:
    stmt = select(Product).where(Product.category == "tshirt").order_by(Product.id).limit(n)
    if tag:
        stmt = stmt.where(Product.tags.contains([tag]))
    async with sessions() as s:
        return list((await s.scalars(stmt)).all())


async def _profile(sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID) -> StyleProfile:
    async with sessions() as s:
        profile = await s.get(StyleProfile, user_id)
    assert profile is not None
    return profile


# ---------- swipes ----------


async def test_a_like_learns_taste_and_tag_affinity(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    [product] = await _products(catalog_sessions, 1, tag="oversized")
    service = _service(catalog_sessions)

    receipt = await service.record_swipe(
        user_id, SwipeInput(product_id=product.id, direction="right")
    )

    profile = await _profile(catalog_sessions, user_id)
    assert receipt.recorded is True
    assert profile.swipe_count == 1
    assert profile.taste_vector is not None
    assert profile.tag_affinity["oversized"] == 1
    # Category and gender are hard filters, not taste.
    assert "tshirt" not in profile.tag_affinity
    assert product.gender not in profile.tag_affinity


async def test_replayed_swipe_is_ignored_and_learns_nothing_twice(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    [product] = await _products(catalog_sessions, 1, tag="oversized")
    service = _service(catalog_sessions)
    swipe = SwipeInput(product_id=product.id, direction="super", session_id=uuid.uuid4())

    first = await service.record_swipe(user_id, swipe)
    replay = await service.record_swipe(user_id, swipe)

    profile = await _profile(catalog_sessions, user_id)
    assert (first.recorded, replay.recorded) == (True, False)
    assert (profile.swipe_count, profile.tag_affinity["oversized"]) == (1, 2)


async def test_swipes_without_a_session_are_deduplicated_too(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    [product] = await _products(catalog_sessions, 1)
    service = _service(catalog_sessions)
    swipe = SwipeInput(product_id=product.id, direction="left")

    assert (await service.record_swipe(user_id, swipe)).recorded is True
    assert (await service.record_swipe(user_id, swipe)).recorded is False  # NULLS NOT DISTINCT


async def test_the_same_product_in_another_session_counts_again(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    [product] = await _products(catalog_sessions, 1)
    service = _service(catalog_sessions)

    for session_id in (uuid.uuid4(), uuid.uuid4()):
        await service.record_swipe(
            user_id, SwipeInput(product_id=product.id, direction="right", session_id=session_id)
        )

    assert (await _profile(catalog_sessions, user_id)).swipe_count == 2


async def test_a_first_dislike_records_affinity_but_no_taste_vector(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    [product] = await _products(catalog_sessions, 1, tag="oversized")

    await _service(catalog_sessions).record_swipe(
        user_id, SwipeInput(product_id=product.id, direction="left")
    )

    profile = await _profile(catalog_sessions, user_id)
    assert profile.taste_vector is None
    assert profile.tag_affinity["oversized"] == -1


async def test_swiping_an_unknown_product_is_404_and_stores_nothing(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    with pytest.raises(ProductNotFoundError):
        await _service(catalog_sessions).record_swipe(
            user_id, SwipeInput(product_id=uuid.uuid4(), direction="right")
        )

    async with catalog_sessions() as s:
        count = await s.scalar(
            select(func.count()).select_from(Swipe).where(Swipe.user_id == user_id)
        )
    assert count == 0


async def test_concurrent_swipes_never_lose_an_update(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    products = await _products(catalog_sessions, 12)
    service = _service(catalog_sessions)

    await asyncio.gather(
        *(
            service.record_swipe(user_id, SwipeInput(product_id=p.id, direction="right"))
            for p in products
        )
    )

    assert (await _profile(catalog_sessions, user_id)).swipe_count == len(products)


async def test_session_swipes_are_scoped_to_the_user(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    [product] = await _products(catalog_sessions, 1)
    service = _service(catalog_sessions)
    session_id = uuid.uuid4()
    await service.record_swipe(
        user_id, SwipeInput(product_id=product.id, direction="right", session_id=session_id)
    )
    async with catalog_sessions() as s, s.begin():
        other = User(email=f"{uuid.uuid4().hex}@example.com")
        s.add(other)

    assert await service.session_swipes(user_id, session_id) == [product.id]
    assert await service.session_swipes(other.id, session_id) == []


async def test_deleting_the_user_removes_profile_and_swipes(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    [product] = await _products(catalog_sessions, 1)
    await _service(catalog_sessions).record_swipe(
        user_id, SwipeInput(product_id=product.id, direction="right")
    )

    async with catalog_sessions() as s, s.begin():
        await s.execute(delete(User).where(User.id == user_id))

    async with catalog_sessions() as s:
        assert await s.get(StyleProfile, user_id) is None
        assert (
            await s.scalar(select(func.count()).select_from(Swipe).where(Swipe.user_id == user_id))
            == 0
        )


# ---------- Style DNA ----------


async def test_profile_of_a_new_user_is_empty(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    view = await _service(catalog_sessions).profile(user_id)

    assert (view.onboarding_done, view.styles, view.swipe_count, view.top_tags) == (
        False,
        [],
        0,
        [],
    )


async def test_style_dna_seeds_taste_and_saves_answers(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    update = StyleProfileUpdate(
        fit_preference="men", styles=["streetwear", "minimal"], sizes=Sizes(top="L", bottom="32")
    )

    view = await _service(catalog_sessions).update_profile(user_id, update)

    profile = await _profile(catalog_sessions, user_id)
    assert view.onboarding_done is True
    assert (view.fit_preference, view.styles) == ("men", ["streetwear", "minimal"])
    assert profile.sizes == {"top": "L", "bottom": "32"}
    assert profile.taste_vector is not None
    for tag in STYLES["streetwear"].tags:
        assert profile.tag_affinity[tag] >= 2
    assert set(view.top_tags) <= set(STYLES["streetwear"].tags) | set(STYLES["minimal"].tags)


async def test_saving_the_same_style_dna_twice_changes_nothing(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    service = _service(catalog_sessions)
    update = StyleProfileUpdate(styles=["ethnic"])
    await service.update_profile(user_id, update)
    first = await _profile(catalog_sessions, user_id)

    await service.update_profile(user_id, update)

    second = await _profile(catalog_sessions, user_id)
    assert second.tag_affinity == first.tag_affinity
    assert list(second.taste_vector) == list(first.taste_vector)  # type: ignore[arg-type]


async def test_new_picks_blend_into_learned_taste_instead_of_replacing_it(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    [product] = await _products(catalog_sessions, 1, tag="oversized")
    service = _service(catalog_sessions)
    await service.record_swipe(user_id, SwipeInput(product_id=product.id, direction="right"))
    learned = list((await _profile(catalog_sessions, user_id)).taste_vector)  # type: ignore[arg-type]

    await service.update_profile(user_id, StyleProfileUpdate(styles=["ethnic"]))

    after = await _profile(catalog_sessions, user_id)
    assert list(after.taste_vector) != learned  # type: ignore[arg-type]
    assert after.tag_affinity["oversized"] == 1  # swipe learning kept
    assert after.swipe_count == 1


async def test_style_dna_still_saves_when_embeddings_are_down(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    service = _service(catalog_sessions, embedder=DownEmbedder())

    view = await service.update_profile(user_id, StyleProfileUpdate(styles=["sporty"]))

    profile = await _profile(catalog_sessions, user_id)
    assert view.styles == ["sporty"]
    assert profile.taste_vector is None
    assert profile.tag_affinity["sports"] == 2


async def test_taste_returns_none_without_a_profile_and_the_signals_with_one(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    service = _service(catalog_sessions)
    assert await service.taste(user_id) is None

    await service.update_profile(
        user_id, StyleProfileUpdate(fit_preference="women", sizes=Sizes(shoe="UK5"))
    )

    taste = await service.taste(user_id)
    assert taste is not None
    assert (taste.fit_preference, taste.sizes, taste.vector) == ("women", {"shoe": "UK5"}, None)


@pytest.mark.parametrize(
    "body",
    [
        {"styles": ["goth"]},
        {"styles": ["streetwear", "minimal", "classic", "boho"]},
        {"sizes": {"top": "XXXL"}},
        {"fit_preference": "kids"},
        {"unexpected": True},
    ],
)
def test_invalid_style_dna_is_rejected(body: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        StyleProfileUpdate.model_validate(body)


def test_duplicate_style_picks_collapse() -> None:
    assert StyleProfileUpdate(styles=["boho", "boho"]).styles == ["boho"]


def test_options_offer_every_style_with_an_https_image() -> None:
    options = PersonalizationService.options()

    assert {o.id for o in options.styles} == set(STYLES)
    assert all(o.image_url.startswith("https://") for o in options.styles)
