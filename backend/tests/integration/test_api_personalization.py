import statistics
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import select, text

from stylesense.bootstrap.container import Container, build_container
from stylesense.integrations.sources.mock import MockSource
from stylesense.main import create_app
from stylesense.modules.catalog.models import Product
from stylesense.platform.config import Settings
from tests.fakes.identity import FakeIdentityVerifier

SWIPE_P95_BUDGET_MS = 50  # CP9 exit criterion


@pytest.fixture(scope="module")
def client(settings: Settings, migrated: None) -> Iterator[TestClient]:
    verifier = FakeIdentityVerifier()
    verifier.register("google-asha", subject="g-11", email="asha@example.com")
    verifier.register("google-dev", subject="g-12", email="dev@example.com")
    app = create_app(
        settings, container_factory=lambda s, **kw: build_container(s, verifier=verifier, **kw)
    )
    with TestClient(app) as c:
        container: Container = app.state.container

        async def seed() -> None:
            async with container.engine.begin() as conn:
                await conn.execute(text("TRUNCATE users, products CASCADE"))
            await container.catalog.ingest(MockSource())

        c.portal.call(seed)  # type: ignore[union-attr]
        yield c


@pytest.fixture(autouse=True)
def fresh_limits(client: TestClient, settings: Settings) -> None:
    async def flush() -> None:
        redis = Redis.from_url(str(settings.redis_url))
        await redis.flushdb()
        await redis.aclose()

    client.portal.call(flush)  # type: ignore[union-attr]


def _auth(client: TestClient, token: str = "google-asha") -> dict[str, str]:
    body = client.post("/v1/auth/google", json={"id_token": token}).json()
    return {"Authorization": f"Bearer {body['tokens']['access_token']}", "X-GenUI-Version": "1"}


def _product_ids(client: TestClient, n: int) -> list[str]:
    container: Container = client.app.state.container  # type: ignore[attr-defined]

    async def ids() -> list[str]:
        async with container.session_factory() as s:
            rows = await s.scalars(select(Product.id).order_by(Product.id).limit(n))
            return [str(i) for i in rows.all()]

    return client.portal.call(ids)  # type: ignore[union-attr]


# ---------- Style DNA ----------


def test_style_profile_round_trip(client: TestClient) -> None:
    headers = _auth(client)
    assert client.get("/v1/me/style-profile", headers=headers).json()["onboarding_done"] is False

    body = {"fit_preference": "men", "styles": ["streetwear"], "sizes": {"top": "L"}}
    saved = client.put("/v1/me/style-profile", json=body, headers=headers)

    assert saved.status_code == 200
    fetched = client.get("/v1/me/style-profile", headers=headers).json()
    assert fetched == saved.json()
    assert (fetched["styles"], fetched["sizes"]["top"], fetched["onboarding_done"]) == (
        ["streetwear"],
        "L",
        True,
    )
    assert fetched["top_tags"]


@pytest.mark.parametrize(
    "body", [{"styles": ["goth"]}, {"sizes": {"top": "XXXL"}}, {"fit_preference": "kids"}]
)
def test_invalid_style_profile_is_422(client: TestClient, body: dict[str, Any]) -> None:
    response = client.put("/v1/me/style-profile", json=body, headers=_auth(client))

    assert response.status_code == 422


def test_style_options_list_styles_and_sizes(client: TestClient) -> None:
    options = client.get("/v1/me/style-profile/options", headers=_auth(client)).json()

    assert options["max_styles"] == 3
    assert len(options["styles"]) >= 6
    assert "UK9" in options["shoe_sizes"]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/v1/me/style-profile"),
        ("put", "/v1/me/style-profile"),
        ("post", "/v1/me/swipes"),
    ],
)
def test_personal_endpoints_require_sign_in(client: TestClient, method: str, path: str) -> None:
    assert client.request(method.upper(), path, json={}).status_code == 401


# ---------- swipes ----------


def test_swipe_is_recorded_once_and_replays_are_harmless(client: TestClient) -> None:
    headers = _auth(client)
    [product_id] = _product_ids(client, 1)
    body = {"product_id": product_id, "direction": "right"}

    first = client.post("/v1/me/swipes", json=body, headers=headers)
    replay = client.post("/v1/me/swipes", json=body, headers=headers)

    assert (first.status_code, first.json()) == (200, {"recorded": True})
    assert (replay.status_code, replay.json()) == (200, {"recorded": False})
    assert client.get("/v1/me/style-profile", headers=headers).json()["swipe_count"] == 1


def test_swiping_an_unknown_product_is_404(client: TestClient) -> None:
    response = client.post(
        "/v1/me/swipes",
        json={"product_id": str(uuid.uuid4()), "direction": "left"},
        headers=_auth(client),
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"product_id": "not-a-uuid", "direction": "right"},
        {"direction": "up"},
        {"product_id": str(uuid.uuid4()), "direction": "sideways"},
    ],
)
def test_malformed_swipes_are_422(client: TestClient, body: dict[str, Any]) -> None:
    assert client.post("/v1/me/swipes", json=body, headers=_auth(client)).status_code == 422


def test_swipe_endpoint_p95_is_under_budget(client: TestClient) -> None:
    headers = _auth(client, "google-dev")
    ids = _product_ids(client, 60)
    for warmup in ids[:5]:
        client.post(
            "/v1/me/swipes", json={"product_id": warmup, "direction": "left"}, headers=headers
        )

    timings = []
    for i, product_id in enumerate(ids[5:]):
        direction = "right" if i % 2 else "left"
        started = time.perf_counter()
        response = client.post(
            "/v1/me/swipes",
            json={"product_id": product_id, "direction": direction},
            headers=headers,
        )
        timings.append((time.perf_counter() - started) * 1000)
        assert response.status_code == 200

    p95 = statistics.quantiles(timings, n=20)[-1]
    assert p95 < SWIPE_P95_BUDGET_MS, f"swipe p95 {p95:.1f} ms"


# ---------- deck refill ----------


def _session_with_deck(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(
        "/v1/stylist/sessions",
        json={"entry": "search", "value": "t-shirt for men under 1500"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_deck_refill_returns_fresh_cards_and_is_never_cached(client: TestClient) -> None:
    headers = _auth(client)
    session = _session_with_deck(client, headers)
    held = [c["product_id"] for c in session["ui"]["components"][0]["props"]["cards"]]

    response = client.get(
        f"/v1/stylist/sessions/{session['session_id']}/deck",
        params={"exclude": held, "limit": 5},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    cards = response.json()["cards"]
    assert len(cards) == 5
    assert not {c["product_id"] for c in cards} & set(held)


def test_swiped_cards_never_come_back_in_a_refill(client: TestClient) -> None:
    headers = _auth(client)
    session = _session_with_deck(client, headers)
    first = session["ui"]["components"][0]["props"]["cards"][0]["product_id"]
    client.post(
        "/v1/me/swipes",
        json={"product_id": first, "direction": "left", "session_id": session["session_id"]},
        headers=headers,
    )

    cards = client.get(
        f"/v1/stylist/sessions/{session['session_id']}/deck", headers=headers
    ).json()["cards"]

    assert first not in {c["product_id"] for c in cards}


def test_deck_refill_while_asking_is_409(client: TestClient) -> None:
    headers = _auth(client)
    session = client.post(
        "/v1/stylist/sessions", json={"entry": "occasion_tile", "value": "party"}, headers=headers
    ).json()

    response = client.get(f"/v1/stylist/sessions/{session['session_id']}/deck", headers=headers)

    assert (response.status_code, response.json()["code"]) == (409, "no_deck")


def test_deck_refill_of_another_users_session_is_404(client: TestClient) -> None:
    session = _session_with_deck(client, _auth(client))

    response = client.get(
        f"/v1/stylist/sessions/{session['session_id']}/deck", headers=_auth(client, "google-dev")
    )

    assert response.status_code == 404


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 21}, {"exclude": "nope"}])
def test_deck_refill_validates_its_query(client: TestClient, params: dict[str, Any]) -> None:
    headers = _auth(client)
    session = _session_with_deck(client, headers)

    response = client.get(
        f"/v1/stylist/sessions/{session['session_id']}/deck", params=params, headers=headers
    )

    assert response.status_code == 422


def test_onboarding_entry_starts_style_dna(client: TestClient) -> None:
    response = client.post(
        "/v1/stylist/sessions", json={"entry": "onboarding"}, headers=_auth(client)
    )

    assert response.status_code == 201
    assert response.json()["ui"]["components"][0]["id"] == "q_fit"
