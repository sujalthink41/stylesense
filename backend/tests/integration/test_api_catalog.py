from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import event, select, text, update

from stylesense.bootstrap.container import Container
from stylesense.integrations.sources.mock import MockSource
from stylesense.main import create_app
from stylesense.modules.catalog.models import Offer, OutboundClick
from stylesense.platform.config import Settings


@pytest.fixture(scope="module")
def client(settings: Settings, migrated: None) -> Iterator[TestClient]:
    """One seeded catalog for the module; seeding 300 products per test would be wasteful."""
    app = create_app(settings)
    with TestClient(app) as c:
        container: Container = app.state.container

        async def seed() -> None:
            async with container.engine.begin() as conn:
                await conn.execute(text("TRUNCATE products, users CASCADE"))
            await container.catalog.ingest(MockSource())
            while await container.catalog.embed_pending(batch_size=300):
                pass

        c.portal.call(seed)  # type: ignore[union-attr]
        yield c


@pytest.fixture(autouse=True)
def fresh_rate_limits(client: TestClient, settings: Settings) -> None:
    async def flush() -> None:
        redis = Redis.from_url(str(settings.redis_url))
        await redis.flushdb()
        await redis.aclose()

    client.portal.call(flush)  # type: ignore[union-attr]


def _container(client: TestClient) -> Container:
    container: Container = client.app.state.container  # type: ignore[attr-defined]
    return container


def _first_product(client: TestClient, **params: Any) -> dict[str, Any]:
    items: list[dict[str, Any]] = client.get("/v1/products", params={"limit": 1, **params}).json()[
        "items"
    ]
    return items[0]


# ---------- listing ----------


def test_list_filters_by_category_gender_and_budget(client: TestClient) -> None:
    response = client.get(
        "/v1/products",
        params={"category": "tshirt", "gender": "men", "max_price_paise": 50_000, "limit": 50},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert items
    assert all(i["category"] == "tshirt" and i["min_price_paise"] <= 50_000 for i in items)
    assert all(i["gender"] in {"men", "unisex"} for i in items)


def test_pagination_follows_next_cursor(client: TestClient) -> None:
    first = client.get("/v1/products", params={"limit": 2}).json()
    second = client.get("/v1/products", params={"limit": 2, "cursor": first["next_cursor"]}).json()

    assert first["next_cursor"]
    assert {i["id"] for i in first["items"]}.isdisjoint({i["id"] for i in second["items"]})


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 51}, {"gender": "other"}, {"max_price_paise": -1}, {"unknown": "x"}],
)
def test_invalid_filters_are_422(client: TestClient, params: dict[str, Any]) -> None:
    assert client.get("/v1/products", params=params).status_code == 422


def test_garbage_cursor_is_400(client: TestClient) -> None:
    response = client.get("/v1/products", params={"cursor": "!!not-a-cursor!!"})

    assert (response.status_code, response.json()["code"]) == (400, "invalid_cursor")


def test_listing_has_no_n_plus_one_queries(client: TestClient) -> None:
    engine = _container(client).engine.sync_engine
    counts = []
    for limit in (5, 50):
        statements = 0

        def count(*_: Any) -> None:
            nonlocal statements
            statements += 1

        event.listen(engine, "before_cursor_execute", count)
        try:
            assert client.get("/v1/products", params={"limit": limit}).status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", count)
        counts.append(statements)

    assert counts[0] == counts[1]


# ---------- detail & caching ----------


def test_detail_returns_offers_with_tracked_buy_links(client: TestClient) -> None:
    product = _first_product(client)

    response = client.get(f"/v1/products/{product['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["offers"]
    assert sum(o["is_best"] for o in body["offers"]) <= 1
    assert all(o["buy_path"] == f"/v1/out/{o['id']}" for o in body["offers"])
    assert "url" not in body["offers"][0]  # raw store URLs are never exposed


def test_detail_supports_conditional_requests(client: TestClient) -> None:
    product_id = _first_product(client)["id"]
    first = client.get(f"/v1/products/{product_id}")
    etag = first.headers["etag"]

    cached = client.get(f"/v1/products/{product_id}", headers={"If-None-Match": etag})

    assert etag.startswith('W/"')
    assert first.headers["cache-control"] == "private, max-age=60"
    assert cached.status_code == 304
    assert cached.content == b""
    assert cached.headers["etag"] == etag


def test_stale_etag_gets_the_full_response(client: TestClient) -> None:
    product_id = _first_product(client)["id"]

    response = client.get(f"/v1/products/{product_id}", headers={"If-None-Match": 'W/"stale"'})

    assert response.status_code == 200


@pytest.mark.parametrize("bad_id", ["018f2a3b-7c4d-7e8f-9a0b-1c2d3e4f5a6b", "not-a-uuid"])
def test_unknown_product(client: TestClient, bad_id: str) -> None:
    response = client.get(f"/v1/products/{bad_id}")

    assert response.status_code in {404, 422}


def test_similar_products(client: TestClient) -> None:
    product = _first_product(client, category="jeans")

    response = client.get(f"/v1/products/{product['id']}/similar", params={"limit": 5})

    assert response.status_code == 200
    similar = response.json()
    assert len(similar) == 5
    assert product["id"] not in {p["id"] for p in similar}


# ---------- outbound ----------


def _an_offer_id(client: TestClient) -> str:
    detail = client.get(f"/v1/products/{_first_product(client)['id']}").json()
    offer_id: str = detail["offers"][0]["id"]
    return offer_id


def _clicks(client: TestClient) -> list[OutboundClick]:
    async def load() -> list[OutboundClick]:
        async with _container(client).session_factory() as s:
            return list(
                (await s.scalars(select(OutboundClick).order_by(OutboundClick.created_at))).all()
            )

    result: list[OutboundClick] = client.portal.call(load)  # type: ignore[union-attr]
    return result


def test_buy_redirects_to_the_store_and_logs_the_click(client: TestClient) -> None:
    offer_id = _an_offer_id(client)

    response = client.get(f"/v1/out/{offer_id}", params={"src": "stylist"}, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert (str(_clicks(client)[-1].offer_id), _clicks(client)[-1].source) == (offer_id, "stylist")


def test_buy_works_signed_out_and_with_a_broken_token(client: TestClient) -> None:
    offer_id = _an_offer_id(client)

    response = client.get(
        f"/v1/out/{offer_id}", headers={"Authorization": "Bearer garbage"}, follow_redirects=False
    )

    assert response.status_code == 302
    assert _clicks(client)[-1].user_id is None


def test_unknown_source_is_rejected(client: TestClient) -> None:
    response = client.get(
        f"/v1/out/{_an_offer_id(client)}", params={"src": "evil"}, follow_redirects=False
    )

    assert response.status_code == 422


def test_tampered_store_url_is_never_redirected(client: TestClient) -> None:
    offer_id = _an_offer_id(client)

    async def tamper() -> None:
        async with _container(client).engine.begin() as conn:
            await conn.execute(
                update(Offer).where(Offer.id == offer_id).values(url="https://evil.example")
            )

    client.portal.call(tamper)  # type: ignore[union-attr]
    response = client.get(f"/v1/out/{offer_id}", follow_redirects=False)

    assert response.status_code == 404
    assert "evil.example" not in response.text


# ---------- alternatives & complete the look (CP10) ----------


def test_alternatives_stay_in_category_and_under_the_price_cap(client: TestClient) -> None:
    product = _first_product(client, category="tshirt")

    response = client.get(
        f"/v1/products/{product['id']}/alternatives", params={"max_price_paise": 90_000}
    )

    assert response.status_code == 200
    items = response.json()
    assert items
    assert all(i["category"] == "tshirt" for i in items)
    assert all(i["min_price_paise"] <= 90_000 for i in items)
    assert product["id"] not in {i["id"] for i in items}


def test_complete_look_keeps_the_whole_look_within_budget(client: TestClient) -> None:
    product = _first_product(client, category="tshirt", gender="men")
    budget = product["min_price_paise"] + 200_000

    response = client.get(
        f"/v1/products/{product['id']}/complete-look", params={"budget_paise": budget}
    )

    assert response.status_code == 200
    look = response.json()
    assert look["items"]
    assert look["total_paise"] <= budget
    assert look["remaining_paise"] == budget - look["total_paise"]
    assert look["total_paise"] == product["min_price_paise"] + sum(
        i["product"]["min_price_paise"] for i in look["items"]
    )


def test_complete_look_supports_conditional_requests(client: TestClient) -> None:
    product = _first_product(client, category="jeans")
    path = f"/v1/products/{product['id']}/complete-look"
    etag = client.get(path).headers["etag"]

    assert client.get(path, headers={"If-None-Match": etag}).status_code == 304


@pytest.mark.parametrize(
    "params",
    [{"budget_paise": -1}, {"gender": "kids"}, {"occasion": "DROP TABLE"}, {"budget_paise": "x"}],
)
def test_complete_look_validates_its_query(client: TestClient, params: dict[str, Any]) -> None:
    product = _first_product(client)

    response = client.get(f"/v1/products/{product['id']}/complete-look", params=params)

    assert response.status_code == 422


def test_complete_look_and_alternatives_of_unknown_products_are_404(client: TestClient) -> None:
    missing = "01a10000-0000-7000-8000-000000000000"

    assert client.get(f"/v1/products/{missing}/complete-look").status_code == 404
    assert client.get(f"/v1/products/{missing}/alternatives").status_code == 404
