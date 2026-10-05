from collections import Counter, defaultdict

import pytest

from stylesense.integrations.sources.mock import CATEGORIES, STORE_HOSTS, MockSource
from stylesense.modules.catalog.ports import RawOffer
from stylesense.modules.catalog.rules import is_allowed_store_url


@pytest.fixture(scope="module")
async def offers() -> list[RawOffer]:
    return list(await MockSource().offers())


@pytest.fixture(scope="module")
def products(offers: list[RawOffer]) -> dict[str, list[RawOffer]]:
    grouped: dict[str, list[RawOffer]] = defaultdict(list)
    for offer in offers:
        grouped[offer.canonical_key].append(offer)
    return grouped


async def test_generation_is_deterministic() -> None:
    assert await MockSource(seed=7).offers() == await MockSource(seed=7).offers()
    assert await MockSource(seed=7).offers() != await MockSource(seed=8).offers()


def test_about_three_hundred_products_each_sold_by_one_to_three_stores(
    products: dict[str, list[RawOffer]],
) -> None:
    assert len(products) == 300
    for group in products.values():
        stores = [o.store for o in group]
        assert 1 <= len(stores) <= 3
        assert len(set(stores)) == len(stores)


def test_offers_have_unique_store_ids(offers: list[RawOffer]) -> None:
    keys = Counter((o.store, o.external_id) for o in offers)

    assert max(keys.values()) == 1


def test_offers_of_one_product_agree_on_what_it_is(products: dict[str, list[RawOffer]]) -> None:
    for group in products.values():
        assert len({(o.title, o.brand, o.category, o.gender) for o in group}) == 1


def test_prices_are_realistic_for_each_category(offers: list[RawOffer]) -> None:
    for offer in offers:
        assert offer.price_paise is not None  # the mock source always has a price
        low, high = CATEGORIES[offer.category].price_range_rupees
        assert low * 100 * 0.85 <= offer.price_paise <= high * 100 * 1.15
        assert offer.price_paise % 100 == 0  # whole rupees, like real listings
        assert offer.mrp_paise is None or offer.mrp_paise >= offer.price_paise


def test_every_link_is_a_safe_store_url(offers: list[RawOffer]) -> None:
    for offer in offers:
        assert is_allowed_store_url(offer.url, STORE_HOSTS[offer.store]), offer.url


def test_catalog_covers_all_categories_genders_and_a_budget_range(offers: list[RawOffer]) -> None:
    assert {o.category for o in offers} == set(CATEGORIES)
    assert {o.gender for o in offers} >= {"men", "women", "unisex"}
    assert any((o.price_paise or 0) <= 50_000 for o in offers)  # "under ₹500" must return results


def test_sizes_match_the_category(offers: list[RawOffer]) -> None:
    for offer in offers:
        assert offer.sizes
        assert set(offer.sizes_in_stock) <= set(offer.sizes)
        if offer.category == "sneakers":
            assert all(s.startswith("UK") for s in offer.sizes)
        elif offer.category in {"jeans", "trousers"}:
            assert all(s.isdigit() for s in offer.sizes)


def test_brands_are_fictional_and_images_are_placeholders(offers: list[RawOffer]) -> None:
    for offer in offers:
        assert offer.image_urls
        assert all(u.startswith("https://placehold.co/") for u in offer.image_urls)
    assert "Nike" not in {o.brand for o in offers}


def test_money_is_always_integer_paise(offers: list[RawOffer]) -> None:
    for offer in offers:
        assert type(offer.price_paise) is int
        assert offer.mrp_paise is None or type(offer.mrp_paise) is int
