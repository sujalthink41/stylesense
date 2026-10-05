"""Best-price and comparison rules, proven over generated inputs (CP10 exit criterion)."""

import uuid
from dataclasses import dataclass

from hypothesis import given
from hypothesis import strategies as st

from stylesense.modules.catalog.rules import (
    OfferView,
    best_offer,
    needs_alternatives,
    pick_alternatives,
)

STORES = ("amazon", "flipkart", "myntra")

offer = st.builds(
    OfferView,
    store=st.sampled_from(STORES),
    price_paise=st.integers(min_value=100, max_value=1_000_000),
    in_stock=st.booleans(),
    rating=st.none() | st.floats(min_value=1, max_value=5),
)
offers = st.lists(offer, max_size=6, unique_by=lambda o: o.store)


@given(offers)
def test_best_offer_is_in_stock_and_never_beaten_on_price(candidates: list[OfferView]) -> None:
    best = best_offer(candidates)
    in_stock = [o for o in candidates if o.in_stock]

    if not in_stock:
        assert best is None
        return
    assert best is not None
    assert best.in_stock
    assert all(best.price_paise <= o.price_paise for o in in_stock)


@given(offers)
def test_price_ties_go_to_the_best_rating(candidates: list[OfferView]) -> None:
    best = best_offer(candidates)
    if best is None:
        return
    tied = [o for o in candidates if o.in_stock and o.price_paise == best.price_paise]

    assert all((best.rating or 0) >= (o.rating or 0) for o in tied)


@given(offers, st.randoms())
def test_best_offer_ignores_listing_order(candidates: list[OfferView], rnd: object) -> None:
    shuffled = list(candidates)
    rnd.shuffle(shuffled)  # type: ignore[attr-defined]

    assert best_offer(shuffled) == best_offer(candidates)


@given(offers)
def test_alternatives_are_needed_exactly_when_fewer_than_two_stores_stock_it(
    candidates: list[OfferView],
) -> None:
    assert needs_alternatives(candidates) == (sum(o.in_stock for o in candidates) < 2)


@dataclass(frozen=True)
class Item:
    id: uuid.UUID
    min_price_paise: int | None


ANCHOR = uuid.UUID(int=0)
ids = st.sampled_from([ANCHOR, *(uuid.UUID(int=i) for i in range(1, 12))])
items = st.lists(
    st.builds(
        Item, id=ids, min_price_paise=st.none() | st.integers(min_value=100, max_value=500_000)
    ),
    max_size=30,
)


@given(
    items,
    st.none() | st.integers(min_value=100, max_value=500_000),
    st.integers(min_value=1, max_value=10),
)
def test_alternatives_respect_budget_stock_limit_and_never_repeat(
    candidates: list[Item], budget: int | None, limit: int
) -> None:
    picked = pick_alternatives(ANCHOR, candidates, max_price_paise=budget, limit=limit)

    assert len(picked) <= limit
    assert ANCHOR not in {p.id for p in picked}
    assert len({p.id for p in picked}) == len(picked)
    for p in picked:
        assert p.min_price_paise is not None
        assert budget is None or p.min_price_paise <= budget


def test_alternatives_keep_similarity_order() -> None:
    a, b, c = (Item(uuid.uuid4(), price) for price in (900, 300, 600))

    assert pick_alternatives(ANCHOR, [a, b, c], max_price_paise=None, limit=3) == [a, b, c]
    assert pick_alternatives(ANCHOR, [a, b, c], max_price_paise=700, limit=3) == [b, c]
