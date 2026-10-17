import json
from typing import Any

import pytest

from stylesense.integrations.sources.web_search import (
    SITES,
    WebCatalog,
    WebQuery,
    WebSearchFinder,
    amazon_facts,
    brand_of,
    clean_title,
    flipkart_product,
    myntra_facts,
    product_id,
)

FLIPKART, AMAZON, MYNTRA = SITES


@pytest.mark.parametrize(
    ("site", "url", "expected"),
    [
        (
            AMAZON,
            "https://www.amazon.in/KLOSIA-Women-Kurta/dp/B0DG5ZN8BF?th=1",
            ("B0DG5ZN8BF", "https://www.amazon.in/dp/B0DG5ZN8BF"),
        ),
        (
            FLIPKART,
            "https://dl.flipkart.com/dl/levi-s-jeans/p/itm24895edc69b39?pid=JEAG7&x=1",
            ("JEAG7", "https://www.flipkart.com/dl/levi-s-jeans/p/itm24895edc69b39?pid=JEAG7"),
        ),
        (
            MYNTRA,
            "https://www.myntra.com/jeans/herenow/herenow-men-black-jeans/14139454/buy",
            (
                "14139454",
                "https://www.myntra.com/jeans/herenow/herenow-men-black-jeans/14139454/buy",
            ),
        ),
        (MYNTRA, "https://www.myntra.com/men-jeans", None),  # a listing page, not a product
        (AMAZON, "https://www.amazon.com/dp/B0DG5ZN8BF", None),  # wrong country store
        (FLIPKART, "https://evil.example/flipkart.com/p/itm1", None),
    ],
)
def test_only_real_product_pages_on_the_three_stores_count(
    site: Any, url: str, expected: Any
) -> None:
    assert product_id(site, url) == expected


def test_titles_and_brands_are_cleaned() -> None:
    assert (
        clean_title(MYNTRA, "Buy Biba Women Printed Kurta - Kurtas for Women 123 | Myntra")
        == "Biba Women Printed Kurta"
    )
    assert (
        clean_title(AMAZON, "Levi's Men's 511 Slim Jeans : Amazon.in: Clothing")
        == "Levi's Men's 511 Slim Jeans"
    )
    assert brand_of("HERE&NOW Men Black Jeans") == "HERE&NOW"
    assert brand_of("LYMI LABEL Kurta Set for Women") == "LYMI LABEL"
    assert brand_of("rytras Rayon Women's Kurta") == "rytras"


def _page(price: object = 1293, availability: str = "https://schema.org/InStock") -> str:
    product = {
        "@type": "Product",
        "name": "LEVI'S 511 Slim Men Black Jeans",
        "brand": {"@type": "Brand", "name": "LEVI'S"},
        "image": ["https://rukmini1.flixcart.com/image/1500/1500/x.jpeg"],
        "offers": {"price": price, "priceCurrency": "INR", "availability": availability},
        "aggregateRating": {"ratingValue": 4.3, "reviewCount": 812},
    }
    return f'<html><script type="application/ld+json">{json.dumps(product)}</script></html>'


def test_flipkart_structured_data_is_read() -> None:
    assert flipkart_product(_page())["name"] == "LEVI'S 511 Slim Men Black Jeans"  # type: ignore[index]
    assert flipkart_product("<html>no data</html>") is None


class FakeEngine:
    def __init__(
        self, results: dict[str, list[dict[str, Any]]], fail: set[str] | None = None
    ) -> None:
        self.results = results
        self.fail = fail or set()
        self.queries: list[str] = []

    async def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        self.queries.append(query)
        store = query.rsplit(" ", 1)[-1]
        if store in self.fail:
            raise RuntimeError("ratelimited")
        return self.results.get(store, [])


async def test_flipkart_items_get_real_prices_and_the_others_stay_unpriced() -> None:
    engine = FakeEngine(
        {
            "flipkart": [
                {
                    "title": "LEVI'S Slim Men Black Jeans",
                    "url": "https://www.flipkart.com/x/p/itm1abc",
                    "image": "https://rukminim2.flixcart.com/image/128/128/a.jpeg",
                },
                {
                    "title": "Jeans listing",
                    "url": "https://www.flipkart.com/jeans/pr?sid=x",
                    "image": "https://x/a.jpg",
                },
            ],
            "myntra": [
                {
                    "title": "Buy Roadster Men Black Slim Fit Jeans - Jeans for Men 1 | Myntra",
                    "url": "https://www.myntra.com/jeans/roadster/r/12345/buy",
                    "image": "https://assets.myntassets.com/h_200,w_200,c_fill,g_auto/h_1440,q_100,w_1080/v1/a.jpg",
                }
            ],
        }
    )

    async def fetch(url: str) -> str:
        return _page()

    offers = await WebSearchFinder(search=engine.search, fetch=fetch).find(
        WebQuery("men black jeans", "jeans", "men")
    )

    by_store = {o.store: o for o in offers}
    assert set(by_store) == {"flipkart", "myntra"}  # the listing page was dropped
    fk, my = by_store["flipkart"], by_store["myntra"]
    assert (fk.price_paise, fk.brand, fk.rating, fk.rating_count) == (129_300, "LEVI'S", 4.3, 812)
    assert fk.image_urls == ("https://rukmini1.flixcart.com/image/1500/1500/x.jpeg",)
    assert my.price_paise is None  # never estimated
    assert (my.category, my.gender, my.colors) == ("jeans", "men", ("black",))
    assert my.image_urls == ("https://assets.myntassets.com/h_1440,q_100,w_1080/v1/a.jpg",)
    assert my.canonical_key == "web-myntra-12345"


async def test_a_failing_store_or_unreadable_page_never_breaks_the_search() -> None:
    engine = FakeEngine(
        {
            "flipkart": [
                {
                    "title": "DASHING Men Black Jeans",
                    "url": "https://www.flipkart.com/d/p/itm9",
                    "image": "https://rukminim2.flixcart.com/image/128/128/b.jpeg",
                }
            ]
        },
        fail={"amazon.in"},
    )

    async def fetch(url: str) -> str:
        raise TimeoutError

    offers = await WebSearchFinder(search=engine.search, fetch=fetch).find(
        WebQuery("men black jeans", "jeans", "men")
    )

    assert [(o.store, o.price_paise) for o in offers] == [("flipkart", None)]


async def test_vague_titles_fall_back_to_the_query_and_unplaceable_ones_are_skipped() -> None:
    engine = FakeEngine(
        {
            "amazon.in": [
                {
                    "title": "KLOSIA Women Printed Set",
                    "url": "https://www.amazon.in/k/dp/B000000001",
                    "image": "https://m.media-amazon.com/images/I/a.jpg",
                },
                {
                    "title": "Something",
                    "url": "https://www.amazon.in/k/dp/B000000002",
                    "image": "http://insecure/a.jpg",
                },
            ]
        }
    )

    async def fetch(url: str) -> None:
        return None

    offers = await WebSearchFinder(search=engine.search, fetch=fetch).find(
        WebQuery("women kurta", "kurta", "women")
    )

    assert [(o.external_id, o.category) for o in offers] == [("B000000001", "kurta")]


class FakeCatalog:
    def __init__(self) -> None:
        self.ingested: list[int] = []

    async def ingest(self, source: Any) -> Any:
        offers = await source.offers()
        self.ingested.append(len(offers))
        return type("Report", (), {"products_created": len(offers)})()

    async def embed_pending(self) -> int:
        return 0


class CountingFinder:
    def __init__(self, n: int = 2) -> None:
        self.calls = 0
        self.n = n

    async def find(self, query: WebQuery) -> list[Any]:
        self.calls += 1
        return [object()] * self.n


async def test_each_request_shape_is_searched_once_per_ttl() -> None:
    now = [0.0]
    catalog, finder = FakeCatalog(), CountingFinder()
    live = WebCatalog(catalog, finder, ttl_s=100, now=lambda: now[0])  # type: ignore[arg-type]

    first = await live.refresh("Women  Kurta", category="kurta", gender="women")
    again = await live.refresh("women kurta", category="kurta", gender="women")
    now[0] = 101
    later = await live.refresh("women kurta", category="kurta", gender="women")

    assert (first, again, later, finder.calls) == (2, 0, 2, 2)


def test_myntra_and_amazon_pages_give_real_prices() -> None:
    myntra = (
        "<script>window.__myx = "
        + json.dumps(
            {
                "pdpData": {
                    "name": "Roadster Men Black Jeans",
                    "brand": {"name": "Roadster"},
                    "price": {"mrp": 2699, "discounted": 1349},
                    "ratings": {"averageRating": 4.21, "totalCount": 950},
                    "flags": {"outOfStock": False},
                    "media": {
                        "albums": [{"images": [{"imageURL": "http://assets.myntassets.com/a.jpg"}]}]
                    },
                }
            }
        )
        + "</script>"
    )
    m = myntra_facts(myntra)
    assert m is not None
    assert (m.price_paise, m.mrp_paise, m.rating, m.rating_count, m.in_stock) == (
        134_900,
        269_900,
        4.2,
        950,
        True,
    )
    assert m.image == "https://assets.myntassets.com/a.jpg"

    amazon = (
        '<span id="productTitle"> KLOSIA Women Kurta </span>{"priceAmount":626.00}'
        '<div id="availability"><span> In stock </span></div>'
    )
    a = amazon_facts(amazon)
    assert a is not None
    assert (a.title, a.price_paise, a.in_stock) == ("KLOSIA Women Kurta", 62_600, True)

    assert myntra_facts("<html></html>") is None
    assert amazon_facts("<html></html>") is None
