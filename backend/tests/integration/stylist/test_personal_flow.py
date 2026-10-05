"""CP9: Style DNA onboarding, swipe learning and deck refill, end to end over the real catalog."""

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stylesense.genui.actions import (
    Back,
    ChipSelect,
    Shortcut,
    Swipe,
)
from stylesense.genui.components import (
    ChipQuestion,
    ImageChoiceGrid,
    InfoBanner,
)
from stylesense.genui.validation import InvalidActionError
from stylesense.infra.database import UnitOfWork
from stylesense.integrations.embeddings.hashing import HashingEmbedder
from stylesense.modules.catalog.models import Product
from stylesense.modules.catalog.service import CatalogService
from stylesense.modules.personalization.models import StyleProfile
from stylesense.modules.personalization.schemas import (
    Sizes,
    StyleProfileUpdate,
    SwipeInput,
    SwipeReceipt,
    Taste,
)
from stylesense.modules.stylist.exceptions import DeckUnavailableError, SessionNotFoundError
from stylesense.modules.stylist.flows.stylist import StylistFlow
from stylesense.modules.stylist.service import StylistService
from tests.fakes.clock import FixedClock
from tests.integration.stylist.driver import App, new_user

REQUEST = "t-shirt for men under 1500"
STYLE_TAG = "sports"  # ~19 tees: enough to like 10 and still have some left to rank


async def _tags(
    sessions: async_sessionmaker[AsyncSession], ids: list[uuid.UUID]
) -> list[list[str]]:
    async with sessions() as s:
        result = await s.execute(select(Product.id, Product.tags).where(Product.id.in_(ids)))
        rows: dict[uuid.UUID, list[str]] = {row[0]: row[1] for row in result.all()}
    return [rows[i] for i in ids]


async def _tshirts(
    sessions: async_sessionmaker[AsyncSession], *, with_tag: bool, n: int
) -> list[uuid.UUID]:
    has_tag = Product.tags.contains([STYLE_TAG])
    async with sessions() as s:
        rows = await s.scalars(
            select(Product.id)
            .where(
                Product.category == "tshirt",
                has_tag if with_tag else ~has_tag,
            )
            .order_by(Product.id)
            .limit(n)
        )
        return list(rows.all())


async def _any_tshirt(app: App) -> None:
    await app.start("search", "t-shirt under 2000")
    await app.send(ChipSelect(component_id="q_gender", option_ids=["any"]))


# ---------- exit criterion: ranking shifts toward liked styles ----------


async def test_ten_right_swipes_on_one_style_shift_the_next_deck_towards_it(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    liked = await _tshirts(catalog_sessions, with_tag=True, n=10)
    skipped = await _tshirts(catalog_sessions, with_tag=False, n=10)
    swiped = liked + skipped

    # Baseline: a user with no taste, same request, same items already out of the deck.
    stranger = App(catalog_sessions, await new_user(catalog_sessions), version=1)
    await _any_tshirt(stranger)
    before = await stranger.refill(exclude=swiped)

    app = App(catalog_sessions, user_id, version=1)
    await _any_tshirt(app)
    for product_id in liked:
        await app.personal.record_swipe(
            user_id, SwipeInput(product_id=product_id, direction="right", session_id=app.session_id)
        )
    for product_id in skipped:
        await app.personal.record_swipe(
            user_id, SwipeInput(product_id=product_id, direction="left", session_id=app.session_id)
        )
    after = await app.refill()

    def share(page: Any) -> int:
        return sum(STYLE_TAG in t for t in tags_of[id(page)])

    tags_of = {
        id(before): await _tags(catalog_sessions, [c.product_id for c in before.cards]),
        id(after): await _tags(catalog_sessions, [c.product_id for c in after.cards]),
    }
    assert share(after) > share(before)
    assert share(after) >= 5
    assert STYLE_TAG in tags_of[id(after)][0]
    assert f"Your style: {STYLE_TAG}" in after.cards[0].reasons
    assert not {c.product_id for c in after.cards} & set(swiped)  # swiped cards never come back


# ---------- swipes inside the turn protocol ----------


async def test_swipe_actions_are_recorded_and_leave_the_deck(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id, version=1)
    await app.start("search", REQUEST)
    card = app.deck().props.cards[0]

    await app.send(Swipe(component_id="deck", product_id=card.product_id, direction="super"))

    async with catalog_sessions() as s:
        profile = await s.get(StyleProfile, user_id)
    assert profile is not None
    assert profile.swipe_count == 1
    assert card.product_id not in {c.product_id for c in app.deck().props.cards}
    refill = await app.refill()
    assert card.product_id not in {c.product_id for c in refill.cards}


async def test_refill_skips_cards_the_app_already_holds(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id, version=1)
    await app.start("search", REQUEST)
    held = [c.product_id for c in app.deck().props.cards]

    refill = await app.refill(exclude=held, limit=5)

    assert len(refill.cards) == 5
    assert not {c.product_id for c in refill.cards} & set(held)
    assert all(c.price_paise is not None and c.price_paise <= 150_000 for c in refill.cards)
    assert all(c.reasons for c in refill.cards)


async def test_refill_is_unavailable_while_the_stylist_is_still_asking(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id, version=1)
    await app.start("occasion_tile", "party")

    with pytest.raises(DeckUnavailableError):
        await app.refill()


async def test_refill_of_someone_elses_session_looks_missing(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id, version=1)
    await app.start("search", REQUEST)
    intruder = await new_user(catalog_sessions)

    with pytest.raises(SessionNotFoundError):
        await app.service.deck(app.session_id, intruder, exclude=[], limit=5)


# ---------- Style DNA prefill ----------


async def test_style_dna_answers_the_gender_question_up_front(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id, version=1)
    await app.personal.update_profile(user_id, StyleProfileUpdate(fit_preference="men"))

    await app.start("search", "summer t-shirt under 500")

    assert app.deck().props.title.startswith("Summer t-shirts for men")  # type: ignore[union-attr]


async def test_the_request_beats_style_dna(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id, version=1)
    await app.personal.update_profile(user_id, StyleProfileUpdate(fit_preference="men"))

    await app.start("search", "dress for my wife under 3000")

    assert "for women" in (app.deck().props.title or "")


async def test_saved_size_filters_the_deck(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id, version=1)
    await app.personal.update_profile(
        user_id, StyleProfileUpdate(fit_preference="men", sizes=Sizes(top="XXL"))
    )

    await app.start("search", REQUEST)

    ids = [c.product_id for c in app.deck().props.cards]
    async with catalog_sessions() as s:
        sizes = (await s.scalars(select(Product.sizes_available).where(Product.id.in_(ids)))).all()
    assert ids
    assert all("XXL" in available for available in sizes)


class SoldOutTaste:
    """A saved size nothing in the catalog comes in."""

    async def taste(self, user_id: uuid.UUID) -> Taste:
        return Taste(fit_preference="men", sizes={"top": "XXXS"})

    async def record_swipe(self, user_id: uuid.UUID, swipe: SwipeInput) -> SwipeReceipt:
        return SwipeReceipt(recorded=True)

    async def session_swipes(self, user_id: uuid.UUID, session_id: uuid.UUID) -> list[uuid.UUID]:
        return []


async def test_a_sold_out_size_falls_back_to_all_sizes(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id, version=1)
    catalog = CatalogService(
        lambda: UnitOfWork(catalog_sessions), clock=FixedClock(), embedder=HashingEmbedder()
    )
    app.service = StylistService(
        lambda: UnitOfWork(catalog_sessions),
        flows={"stylist": StylistFlow(catalog, None, SoldOutTaste())},
        default_flow="stylist",
        clock=FixedClock(),
    )

    await app.start("search", REQUEST)

    assert app.deck().props.cards


# ---------- Style DNA onboarding flow ----------


async def test_onboarding_with_taps_only_saves_style_dna(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id, version=1)

    await app.start("onboarding")
    assert isinstance(app.component("q_fit"), ChipQuestion)
    await app.send(ChipSelect(component_id="q_fit", option_ids=["women"]))
    assert isinstance(app.component("q_styles"), ImageChoiceGrid)
    await app.send(ChipSelect(component_id="q_styles", option_ids=["boho", "party"]))
    await app.send(ChipSelect(component_id="q_top", option_ids=["s"]))
    await app.send(Shortcut(value="skip"))  # waist
    await app.send(ChipSelect(component_id="q_shoe", option_ids=["uk5"]))

    banner = app.component("saved")
    assert isinstance(banner, InfoBanner)
    assert "Boho, Party" in banner.props.text
    snapshot = await app.service.snapshot(app.session_id, user_id, client_version=1)
    assert snapshot.status == "ended"
    view = await app.personal.profile(user_id)
    assert (view.fit_preference, view.styles, view.onboarding_done) == (
        "women",
        ["boho", "party"],
        True,
    )
    assert view.sizes == Sizes(top="S", shoe="UK5")


async def test_onboarding_back_undoes_the_last_answer(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id, version=1)
    await app.start("onboarding")
    await app.send(ChipSelect(component_id="q_fit", option_ids=["men"]))

    await app.send(Back())
    await app.send(ChipSelect(component_id="q_fit", option_ids=["unisex"]))
    for _ in range(4):
        await app.send(Shortcut(value="skip"))

    assert (await app.personal.profile(user_id)).fit_preference == "unisex"


async def test_onboarding_rejects_styles_that_were_not_offered_or_too_many(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id, version=1)
    await app.start("onboarding")
    await app.send(Shortcut(value="skip"))

    for chosen in (["goth"], ["boho", "party", "minimal", "sporty"]):
        with pytest.raises(InvalidActionError):
            await app.send(ChipSelect(component_id="q_styles", option_ids=chosen))


async def test_abandoned_onboarding_saves_nothing(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id, version=1)
    await app.start("onboarding")
    await app.send(ChipSelect(component_id="q_fit", option_ids=["men"]))

    assert (await app.personal.profile(user_id)).onboarding_done is False
