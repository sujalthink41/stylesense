"""CP10: detail screen, store comparison with a similar-items fallback, complete the look."""

import uuid
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stylesense.ai.gateway.exceptions import AIQuotaExceededError
from stylesense.ai.gateway.tasks import TaskSpec
from stylesense.genui.actions import Back, CardOpen, SliderSet
from stylesense.genui.components import (
    BudgetSlider,
    CompleteTheLook,
    ProductCarousel,
    ProductDetail,
    StoreComparison,
)
from stylesense.modules.catalog.exceptions import ProductNotFoundError
from stylesense.modules.catalog.models import Offer, Product
from stylesense.modules.catalog.rules import TYPICAL_PRICE_PAISE
from stylesense.modules.looks.rules import CASUAL, OCCASIONS
from stylesense.modules.looks.tasks import LookItemWords, LookOutput
from tests.integration.stylist.driver import App

REQUEST = "t-shirt for men under 1500"


class WordsmithAI:
    """Answers look.complete with fixed words; everything else is unavailable."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[str] = []

    async def run(
        self, spec: TaskSpec[Any, Any], payload: Any, *, user_id: uuid.UUID | None = None
    ) -> Any:
        self.calls.append(spec.name)
        if self.error is not None or spec.name != "look.complete":
            raise self.error or AIQuotaExceededError()
        return LookOutput(
            title="Weekend easy",
            items=[
                LookItemWords(product_id=item.id, reasons=["Chill pairing"])
                for item in payload.items
            ]
            + [LookItemWords(product_id=str(uuid.uuid4()), reasons=["Invented"])],
        )


async def _product_with_in_stock_stores(
    sessions: async_sessionmaker[AsyncSession], stores: int, category: str = "tshirt"
) -> uuid.UUID:
    in_stock = func.count().filter(Offer.in_stock)
    async with sessions() as s:
        product_id = await s.scalar(
            select(Product.id)
            .join(Offer, Offer.product_id == Product.id)
            .where(Product.category == category, Product.gender == "men")
            .group_by(Product.id)
            .having(in_stock == stores)
            .order_by(Product.id)
            .limit(1)
        )
    assert product_id is not None, f"mock catalog has no {category} in {stores} stores"
    return product_id


async def _open(
    app: App, sessions: async_sessionmaker[AsyncSession], product_id: uuid.UUID
) -> None:
    """Search by the product's own title so it lands in the deck, then open it."""
    async with sessions() as s:
        title = await s.scalar(select(Product.title).where(Product.id == product_id))
    await app.start("search", f"{title} under 5000")
    cards = [c.product_id for c in app.deck().props.cards]
    assert product_id in cards, "the title search should surface the product itself"
    await app.send(CardOpen(component_id="deck", product_id=product_id))


async def test_detail_screen_shows_the_item_its_stores_and_a_look(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id)
    await app.start("search", REQUEST)
    card = app.deck().props.cards[0]

    await app.send(CardOpen(component_id="deck", product_id=card.product_id))

    detail = app.component("detail")
    assert isinstance(detail, ProductDetail)
    assert detail.props.product_id == card.product_id
    assert detail.props.price_paise == card.price_paise
    assert detail.props.facts
    compare = app.component("compare")
    assert isinstance(compare, StoreComparison)
    assert sum(o.is_best for o in compare.props.offers) == 1
    look = app.component("look")
    assert isinstance(look, CompleteTheLook)
    assert {i.product_id for i in look.props.items}.isdisjoint({card.product_id})
    assert isinstance(app.component("q_look_budget"), BudgetSlider)


async def test_well_stocked_items_compare_stores_without_alternatives(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id)

    await _open(app, catalog_sessions, await _product_with_in_stock_stores(catalog_sessions, 3))

    assert len(app.component("compare").props.offers) == 3
    assert not app.has("similar")


async def test_items_in_one_store_fall_back_to_similar_buyable_items(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id)
    product_id = await _product_with_in_stock_stores(catalog_sessions, 1)

    await _open(app, catalog_sessions, product_id)

    similar = app.component("similar")
    assert isinstance(similar, ProductCarousel)
    ids = {i.product_id for i in similar.props.items}
    assert product_id not in ids
    assert all(i.price_paise is not None and i.price_paise <= 500_000 for i in similar.props.items)
    # Opening a similar item works like any other card.
    await app.send(CardOpen(component_id="similar", product_id=next(iter(ids))))
    assert app.component("detail").props.product_id in ids


async def test_alternatives_stay_in_category_and_budget(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id)
    product_id = await _product_with_in_stock_stores(catalog_sessions, 1)

    alternatives = await app.catalog.alternatives(product_id, max_price_paise=80_000, limit=4)

    assert 0 < len(alternatives) <= 4
    assert product_id not in {a.id for a in alternatives}
    assert {a.category for a in alternatives} == {"tshirt"}
    assert all(a.min_price_paise is not None and a.min_price_paise <= 80_000 for a in alternatives)


async def test_alternatives_of_an_unknown_product_are_404(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    with pytest.raises(ProductNotFoundError):
        await App(catalog_sessions, user_id).catalog.alternatives(uuid.uuid4())


async def test_setting_a_look_budget_keeps_the_whole_look_within_it(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id)
    await app.start("search", REQUEST)
    card = app.deck().props.cards[0]
    await app.send(CardOpen(component_id="deck", product_id=card.product_id))
    budget = (card.price_paise or 0) + 150_000

    await app.send(SliderSet(component_id="q_look_budget", min_paise=0, max_paise=budget))

    assert app.has("detail")  # still on the detail screen
    look = app.component("look")
    total = (card.price_paise or 0) + sum(i.price_paise or 0 for i in look.props.items)
    assert total <= budget
    assert look.props.remaining_budget_paise == budget - total
    assert app.component("q_look_budget").props.default_max_paise == budget


async def test_a_budget_the_item_alone_uses_up_leaves_no_look(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id)
    await app.start("search", REQUEST)
    card = app.deck().props.cards[0]
    await app.send(CardOpen(component_id="deck", product_id=card.product_id))

    await app.send(
        SliderSet(component_id="q_look_budget", min_paise=0, max_paise=card.price_paise or 10_000)
    )

    assert not app.has("look")
    assert app.has("q_look_budget")  # so the user can raise it again


async def test_opening_a_look_item_then_back_returns_to_the_first_item(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id)
    await app.start("search", REQUEST)
    first = app.deck().props.cards[0].product_id
    await app.send(CardOpen(component_id="deck", product_id=first))
    piece = app.component("look").props.items[0].product_id

    await app.send(CardOpen(component_id="look", product_id=piece))
    assert app.component("detail").props.product_id == piece

    await app.send(Back())
    assert app.component("detail").props.product_id == first
    await app.send(Back())
    assert "product_swipe_deck" in app.types()


async def test_look_pieces_respect_typical_prices_and_gender(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id)
    product_id = await _product_with_in_stock_stores(catalog_sessions, 3)

    look = await app.looks.complete(product_id)

    assert look.items
    assert {i.slot for i in look.items} <= {"bottom", "shoes"}  # no layer outside cold weather
    for item in look.items:
        assert item.product.gender in {"men", "unisex"}
        assert item.product.min_price_paise is not None
        assert item.product.min_price_paise <= TYPICAL_PRICE_PAISE[item.product.category]
        assert item.reasons
    assert look.budget_paise is None
    assert look.remaining_paise is None


async def test_cold_occasions_add_a_layer(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id)
    product_id = await _product_with_in_stock_stores(catalog_sessions, 3)

    look = await app.looks.complete(product_id, occasion="winter")

    assert "layer" in {i.slot for i in look.items}
    assert look.title == "Complete the winter look"


async def test_ai_words_the_look_but_cannot_add_products(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id, ai=WordsmithAI())
    product_id = await _product_with_in_stock_stores(catalog_sessions, 3)
    plain = await App(catalog_sessions, user_id).looks.complete(product_id)

    look = await app.looks.complete(product_id, polish=True)

    assert look.title == "Weekend easy"
    assert [i.product.id for i in look.items] == [i.product.id for i in plain.items]
    assert all(i.reasons == ["Chill pairing"] for i in look.items)


async def test_ai_failure_keeps_the_rule_look(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    ai = WordsmithAI(error=AIQuotaExceededError())
    app = App(catalog_sessions, user_id, ai=ai)
    product_id = await _product_with_in_stock_stores(catalog_sessions, 3)

    look = await app.looks.complete(product_id, polish=True)

    assert ai.calls == ["look.complete"]
    assert look.title == "Complete the look" or look.title.startswith("Complete the ")
    assert look.items


async def test_looks_without_polish_never_call_the_ai(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    ai = WordsmithAI()
    app = App(catalog_sessions, user_id, ai=ai)

    await app.looks.complete(await _product_with_in_stock_stores(catalog_sessions, 3))

    assert ai.calls == []


async def test_the_shoppers_occasion_steers_the_pieces(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = App(catalog_sessions, user_id)
    product_id = await _product_with_in_stock_stores(catalog_sessions, 3)

    look = await app.looks.complete(product_id, occasion="sports")

    assert look.items
    for item in look.items:  # a casual occasion never gets dressy-only pieces
        occasions = set(item.product.tags) & OCCASIONS
        assert not occasions or occasions & CASUAL
