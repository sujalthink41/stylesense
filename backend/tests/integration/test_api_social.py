import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import select, text

from stylesense.bootstrap.container import Container, build_container
from stylesense.guards.rate_limit import DEFAULT_POLICIES
from stylesense.integrations.sources.mock import MockSource
from stylesense.main import create_app
from stylesense.modules.catalog.models import Product
from stylesense.platform.config import Settings
from tests.fakes.identity import FakeIdentityVerifier


@pytest.fixture(scope="module")
def client(settings: Settings, migrated: None) -> Iterator[TestClient]:
    verifier = FakeIdentityVerifier()
    verifier.register("google-meera", subject="g-21", email="meera@example.com")
    verifier.register("google-kabir", subject="g-22", email="kabir@example.com")
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


def _auth(client: TestClient, token: str = "google-meera") -> dict[str, str]:
    body = client.post("/v1/auth/google", json={"id_token": token}).json()
    return {"Authorization": f"Bearer {body['tokens']['access_token']}"}


def _products(client: TestClient, n: int) -> list[str]:
    container: Container = client.app.state.container  # type: ignore[attr-defined]

    async def ids() -> list[str]:
        async with container.session_factory() as s:
            rows = await s.scalars(select(Product.id).order_by(Product.id).limit(n))
            return [str(i) for i in rows.all()]

    return client.portal.call(ids)  # type: ignore[union-attr]


def _voter(i: int = 0) -> dict[str, str]:
    return {"X-Voter-Token": f"voter-token-{i:010d}"}


# ---------- boards ----------


def test_board_lifecycle_with_optimistic_locking(client: TestClient) -> None:
    headers = _auth(client)
    body = {"id": str(uuid.uuid4()), "name": "Diwali"}

    created = client.post("/v1/boards", json=body, headers=headers)
    replay = client.post("/v1/boards", json=body, headers=headers)
    assert (created.status_code, replay.status_code) == (201, 200)
    board = created.json()
    path = f"/v1/boards/{board['id']}"
    assert created.headers["etag"] == '"1"'

    no_precondition = client.patch(path, json={"name": "Diwali 2026"}, headers=headers)
    renamed = client.patch(
        path, json={"name": "Diwali 2026"}, headers={**headers, "If-Match": '"1"'}
    )
    stale = client.patch(path, json={"name": "Old"}, headers={**headers, "If-Match": '"1"'})

    assert (no_precondition.status_code, no_precondition.json()["code"]) == (
        428,
        "precondition_required",
    )
    assert (renamed.status_code, renamed.headers["etag"]) == (200, '"2"')
    assert (stale.status_code, stale.json()["code"]) == (412, "version_conflict")
    assert stale.json()["current_version"] == 2
    assert stale.headers["etag"] == '"2"'

    assert client.delete(path, headers=headers).status_code == 204
    assert client.get(path, headers=headers).status_code == 404


def test_saving_items_is_idempotent_and_reorder_needs_the_version(client: TestClient) -> None:
    headers = _auth(client)
    a, b = _products(client, 2)

    first = client.put(f"/v1/boards/wishlist/items/{a}", headers=headers)
    again = client.put(f"/v1/boards/wishlist/items/{a}", headers=headers)
    client.put(f"/v1/boards/wishlist/items/{b}", json={"note": "for mom"}, headers=headers)
    wishlist = client.get("/v1/boards/wishlist", headers=headers)

    assert (first.json()["added"], again.json()["added"]) == (True, False)
    assert [i["product"]["id"] for i in wishlist.json()["items"]] == [a, b]
    assert wishlist.json()["items"][1]["note"] == "for mom"

    reordered = client.put(
        "/v1/boards/wishlist/order",
        json={"product_ids": [b, a]},
        headers={**headers, "If-Match": wishlist.headers["etag"]},
    )
    assert [i["product"]["id"] for i in reordered.json()["items"]] == [b, a]
    assert client.delete(f"/v1/boards/wishlist/items/{a}", headers=headers).status_code == 204
    assert client.delete(f"/v1/boards/wishlist/items/{a}", headers=headers).status_code == 204


def test_boards_are_private(client: TestClient) -> None:
    board = client.post("/v1/boards", json={"name": "Mine"}, headers=_auth(client)).json()
    other = _auth(client, "google-kabir")

    assert client.get(f"/v1/boards/{board['id']}", headers=other).status_code == 404
    assert client.delete(f"/v1/boards/{board['id']}", headers=other).status_code == 204  # no-op
    assert client.get(f"/v1/boards/{board['id']}", headers=_auth(client)).status_code == 200
    assert client.get("/v1/boards").status_code == 401


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/v1/boards/not-a-board", None),
        ("post", "/v1/boards", {"name": "   "}),
        ("post", "/v1/boards", {"name": "x" * 61}),
        ("put", f"/v1/boards/wishlist/items/{uuid.uuid4()}", {"note": "x" * 201}),
    ],
)
def test_board_input_is_validated(
    client: TestClient, method: str, path: str, body: dict[str, Any] | None
) -> None:
    response = client.request(method.upper(), path, json=body, headers=_auth(client))

    assert response.status_code == 422


# ---------- shares ----------


def test_share_link_round_trip_without_sign_in(client: TestClient) -> None:
    headers = _auth(client)
    ids = _products(client, 2)
    body = {"kind": "look", "title": "Date night", "product_ids": ids}

    created = client.post("/v1/shares", json=body, headers=headers)
    again = client.post("/v1/shares", json=body, headers=headers)
    slug = created.json()["slug"]
    page = client.get(f"/v1/public/shares/{slug}")

    assert (created.status_code, again.status_code, again.json()["slug"]) == (201, 200, slug)
    assert created.json()["url"].endswith(f"/l/{slug}")
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    assert [p["id"] for p in page.json()["products"]] == ids
    assert "user_id" not in page.text  # nothing about the owner
    assert "meera" not in page.text

    assert client.delete(f"/v1/shares/{slug}", headers=headers).status_code == 204
    gone = client.get(f"/v1/public/shares/{slug}")
    assert (gone.status_code, gone.json()["code"]) == (410, "share_gone")


@pytest.mark.parametrize("slug", ["a", "bad slug", "x" * 40, "../etc"])
def test_malformed_slugs_are_rejected(client: TestClient, slug: str) -> None:
    assert client.get(f"/v1/public/shares/{slug}").status_code in {404, 422}


# ---------- polls ----------


def _poll(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post("/v1/polls", json={"product_ids": _products(client, 3)}, headers=headers)
    assert response.status_code == 201, response.text
    poll: dict[str, Any] = response.json()
    return poll


def test_friends_vote_without_signing_in_and_the_owner_sees_results(client: TestClient) -> None:
    headers = _auth(client)
    poll = _poll(client, headers)
    choice = poll["options"][2]["option_id"]
    page = f"/v1/public/polls/{poll['slug']}"

    before = client.get(page, headers=_voter())
    voted = client.post(f"{page}/votes", json={"option_id": choice}, headers=_voter())
    replay = client.post(f"{page}/votes", json={"option_id": choice}, headers=_voter())
    switch = client.post(
        f"{page}/votes", json={"option_id": poll["options"][0]["option_id"]}, headers=_voter()
    )

    assert before.json()["total_votes"] is None  # results hidden until you vote
    assert (voted.status_code, voted.json()["your_vote"], voted.json()["total_votes"]) == (
        200,
        choice,
        1,
    )
    assert replay.status_code == 200
    assert (switch.status_code, switch.json()["code"]) == (409, "already_voted")
    owner = client.get(f"/v1/polls/{poll['id']}", headers=headers).json()
    assert [o["votes"] for o in owner["options"]] == [0, 0, 1]
    assert poll["url"].endswith(f"/p/{poll['slug']}")


@pytest.mark.parametrize(
    "voter", [{}, {"X-Voter-Token": "short"}, {"X-Voter-Token": "has spaces in it!!"}]
)
def test_votes_need_a_well_formed_voter_token(client: TestClient, voter: dict[str, str]) -> None:
    poll = _poll(client, _auth(client))

    response = client.post(
        f"/v1/public/polls/{poll['slug']}/votes",
        json={"option_id": poll["options"][0]["option_id"]},
        headers=voter,
    )

    assert response.status_code == 422


def test_closed_polls_refuse_votes(client: TestClient) -> None:
    headers = _auth(client)
    poll = _poll(client, headers)
    client.post(f"/v1/polls/{poll['id']}/close", headers=headers)

    response = client.post(
        f"/v1/public/polls/{poll['slug']}/votes",
        json={"option_id": poll["options"][0]["option_id"]},
        headers=_voter(),
    )

    assert (response.status_code, response.json()["code"]) == (409, "poll_closed")


def test_votes_are_rate_limited_per_ip(client: TestClient) -> None:
    headers = _auth(client)
    polls = [_poll(client, headers) for _ in range(2)]
    limit = DEFAULT_POLICIES["votes.per_ip"].limit
    statuses = []
    for i in range(limit + 1):
        poll = polls[i % 2]  # spread over polls so the per-poll cap isn't what trips
        response = client.post(
            f"/v1/public/polls/{poll['slug']}/votes",
            json={"option_id": poll["options"][0]["option_id"]},
            headers=_voter(i),
        )
        statuses.append(response.status_code)

    assert statuses[:limit] == [200] * limit
    assert statuses[limit] == 429


def test_public_pages_are_rate_limited_per_ip(client: TestClient) -> None:
    poll = _poll(client, _auth(client))
    limit = DEFAULT_POLICIES["public.per_ip"].limit

    statuses = [
        client.get(f"/v1/public/polls/{poll['slug']}").status_code for _ in range(limit + 1)
    ]

    assert statuses[:limit] == [200] * limit
    assert statuses[limit] == 429


# ---------- public web pages ----------


def test_share_page_renders_products_with_tracked_store_links(client: TestClient) -> None:
    headers = _auth(client)
    ids = _products(client, 2)
    share = client.post(
        "/v1/shares",
        json={"kind": "look", "title": "Date <night>", "product_ids": ids},
        headers=headers,
    ).json()

    page = client.get(f"/l/{share['slug']}")

    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "Date &lt;night&gt;" in page.text  # escaped, never raw
    assert 'property="og:title"' in page.text
    assert page.text.count('class="card"') == 2
    assert "/v1/out/" in page.text
    assert "src=share" in page.text
    assert "meera" not in page.text

    client.delete(f"/v1/shares/{share['slug']}", headers=headers)
    gone = client.get(f"/l/{share['slug']}")
    assert gone.status_code == 410
    assert "expired" in gone.text


def test_poll_page_lists_options_and_ships_the_vote_script(client: TestClient) -> None:
    poll = _poll(client, _auth(client))

    page = client.get(f"/p/{poll['slug']}")

    assert page.status_code == 200
    assert page.text.count('class="option"') == 3
    assert "X-Voter-Token" in page.text
    assert client.get("/p/NoSuchPoll1").status_code == 404
    assert client.get("/p/bad slug").status_code in {404, 422}
