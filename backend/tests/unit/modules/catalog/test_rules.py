import pytest
from hypothesis import given
from hypothesis import strategies as st

from stylesense.modules.catalog.rules import (
    OfferView,
    best_offer,
    content_hash,
    derive_tags,
    discount_percent,
    embedding_hash,
    is_allowed_store_url,
    product_text,
)

AMAZON_HOSTS = ("amazon.in", "amzn.to")


# ---------- outbound URL allow-list (open-redirect protection) ----------


@pytest.mark.parametrize(
    "url",
    [
        "https://www.amazon.in/s?k=black+tshirt",
        "https://amazon.in/dp/B0MOCK",
        "https://amzn.to/abc123",
    ],
)
def test_store_urls_on_allowed_hosts_pass(url: str) -> None:
    assert is_allowed_store_url(url, AMAZON_HOSTS)


@pytest.mark.parametrize(
    "url",
    [
        "http://www.amazon.in/s?k=x",  # not https
        "https://amazon.in.evil.com/phish",  # suffix trick
        "https://evilamazon.in/x",  # lookalike
        "https://evil.com/?r=https://amazon.in",  # host is evil.com
        "https://amazon.in@evil.com/x",  # userinfo trick
        "javascript:alert(1)",
        "//amazon.in/x",  # scheme-relative
        "",
        "not a url",
    ],
)
def test_everything_else_is_rejected(url: str) -> None:
    assert not is_allowed_store_url(url, AMAZON_HOSTS)


# ---------- offers ----------


def _offer(
    store: str, price: int, *, in_stock: bool = True, rating: float | None = 4.0
) -> OfferView:
    return OfferView(store=store, price_paise=price, in_stock=in_stock, rating=rating)


def test_best_offer_is_the_cheapest_in_stock() -> None:
    offers = [
        _offer("amazon", 59_900),
        _offer("myntra", 49_900, in_stock=False),
        _offer("flipkart", 54_900),
    ]

    best = best_offer(offers)

    assert best is not None
    assert best.store == "flipkart"


def test_price_ties_go_to_the_better_rated_store() -> None:
    offers = [_offer("amazon", 49_900, rating=3.9), _offer("myntra", 49_900, rating=4.4)]

    best = best_offer(offers)

    assert best is not None
    assert best.store == "myntra"


def test_no_offer_when_nothing_is_in_stock() -> None:
    assert best_offer([_offer("amazon", 100, in_stock=False)]) is None
    assert best_offer([]) is None


@pytest.mark.parametrize(
    ("price", "mrp", "expected"),
    [
        (49_900, 99_900, 50),
        (79_900, 99_900, 20),
        (99_900, 99_900, 0),
        (49_900, None, 0),
        (100, 0, 0),
    ],
)
def test_discount_percent(price: int, mrp: int | None, expected: int) -> None:
    assert discount_percent(price, mrp) == expected


# ---------- content & tags ----------


def test_tags_combine_category_colours_and_attribute_values() -> None:
    tags = derive_tags(
        category="tshirt",
        gender="men",
        colors=("Navy",),
        attributes={"fit": "Oversized", "occasion": "casual, summer"},
    )

    assert tags == ("casual", "men", "navy", "oversized", "summer", "tshirt")


def test_product_text_reads_naturally_and_includes_key_facts() -> None:
    text = product_text(
        title="Urbano Basics Men Navy Oversized T-Shirt",
        brand="Urbano Basics",
        category="tshirt",
        subcategory="oversized",
        gender="men",
        colors=("navy",),
        attributes={"fabric": "cotton"},
    )

    assert "Urbano Basics Men Navy Oversized T-Shirt" in text
    assert "fabric: cotton" in text
    assert "for men" in text


def test_content_hash_depends_only_on_text() -> None:
    assert content_hash("a") == content_hash("a")
    assert content_hash("a") != content_hash("b")


def test_embedding_hash_changes_with_content_or_model() -> None:
    assert embedding_hash("c1", model="m1") == embedding_hash("c1", model="m1")
    assert embedding_hash("c1", model="m1") != embedding_hash("c2", model="m1")
    assert embedding_hash("c1", model="m1") != embedding_hash("c1", model="m2")


@given(
    price=st.integers(min_value=1, max_value=10_000_000),
    mrp=st.integers(min_value=0, max_value=10_000_000),
)
def test_discount_is_always_between_0_and_99(price: int, mrp: int) -> None:
    assert 0 <= discount_percent(price, mrp) <= 99
