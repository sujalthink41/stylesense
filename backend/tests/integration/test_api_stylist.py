import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import text

from stylesense.api.v1 import stylist as stylist_api
from stylesense.bootstrap.container import Container, build_container
from stylesense.genui.envelope import DoneEvent
from stylesense.integrations.sources.mock import MockSource
from stylesense.main import create_app
from stylesense.platform.config import Settings
from tests.fakes.identity import FakeIdentityVerifier

SSE = {"Accept": "text/event-stream"}


@pytest.fixture(scope="module")
def client(settings: Settings, migrated: None) -> Iterator[TestClient]:
    verifier = FakeIdentityVerifier()
    verifier.register("google-priya", subject="g-1", email="priya@example.com")
    verifier.register("google-ravi", subject="g-2", email="ravi@example.com")
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


def _auth(client: TestClient, token: str = "google-priya") -> dict[str, str]:
    body = client.post("/v1/auth/google", json={"id_token": token}).json()
    return {"Authorization": f"Bearer {body['tokens']['access_token']}", "X-GenUI-Version": "1"}


def _start(
    client: TestClient,
    headers: dict[str, str],
    entry: str = "occasion_tile",
    value: str = "party",
) -> dict[str, Any]:
    response = client.post(
        "/v1/stylist/sessions", json={"entry": entry, "value": value}, headers=headers
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _sse_events(raw: str) -> list[tuple[str, str, dict[str, Any]]]:
    """Parse frames the way a client would: (id, event, data)."""
    events = []
    for frame in raw.strip().split("\n\n"):
        fields = dict(
            line.split(": ", 1) for line in frame.splitlines() if not line.startswith(":")
        )
        events.append((fields["id"], fields["event"], json.loads(fields["data"])))
    return events


def _act(
    client: TestClient,
    headers: dict[str, str],
    session_id: str,
    turn: int,
    action: dict[str, Any],
    **kw: Any,
) -> Any:
    return client.post(
        f"/v1/stylist/sessions/{session_id}/actions",
        json={"turn_id": turn, "action": action},
        headers={**headers, **kw.pop("extra_headers", {})},
        **kw,
    )


# ---------- happy path over the wire ----------


def test_session_starts_with_a_tappable_question(client: TestClient) -> None:
    session = _start(client, _auth(client))

    assert (session["turn_id"], session["status"]) == (1, "active")
    assert [c["type"] for c in session["ui"]["components"]] == ["chip_question", "text_input_bar"]


def test_actions_stream_the_next_screen_as_sse(client: TestClient) -> None:
    headers = _auth(client)
    session = _start(client, headers, "search", "party t-shirt for men")  # only budget missing
    slider = {
        "type": "slider_set",
        "component_id": "q_budget",
        "min_paise": 0,
        "max_paise": 100_000,
    }

    response = _act(client, headers, session["session_id"], 1, slider, extra_headers=SSE)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    events = _sse_events(response.text)
    assert [(i, e) for i, e, _ in events] == [
        ("2.1", "ui.loading"),
        ("2.2", "ui.render"),
        ("2.3", "done"),
    ]
    deck = events[1][2]["envelope"]["components"][0]
    assert deck["type"] == "product_swipe_deck"
    assert all(card["price_paise"] <= 100_000 for card in deck["props"]["cards"])


def test_json_mode_returns_the_final_screen(client: TestClient) -> None:
    headers = _auth(client)
    session = _start(client, headers)

    response = _act(
        client,
        headers,
        session["session_id"],
        1,
        {"type": "chip_select", "component_id": "q_category", "option_ids": ["jeans"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["turn_id"], body["error"]) == (2, None)
    assert body["ui"]["components"][0]["id"] == "q_gender"


def test_snapshot_resumes_where_the_user_left_off(client: TestClient) -> None:
    headers = _auth(client)
    session = _start(client, headers)
    _act(
        client,
        headers,
        session["session_id"],
        1,
        {"type": "chip_select", "component_id": "q_category", "option_ids": ["kurta"]},
    )

    snapshot = client.get(f"/v1/stylist/sessions/{session['session_id']}", headers=headers).json()

    assert (snapshot["turn_id"], snapshot["ui"]["components"][0]["id"]) == (2, "q_gender")


# ---------- protocol errors ----------


def test_double_submit_gets_409_with_the_current_turn(client: TestClient) -> None:
    headers = _auth(client)
    session = _start(client, headers)
    chip = {"type": "chip_select", "component_id": "q_category", "option_ids": ["tshirt"]}
    _act(client, headers, session["session_id"], 1, chip)

    replay = _act(client, headers, session["session_id"], 1, chip)

    assert replay.status_code == 409
    assert (replay.json()["code"], replay.json()["current_turn"]) == ("stale_turn", 2)


def test_tapping_something_not_on_screen_is_422(client: TestClient) -> None:
    headers = _auth(client)
    session = _start(client, headers)

    response = _act(
        client, headers, session["session_id"], 1, {"type": "shortcut", "value": "admin-mode"}
    )

    assert (response.status_code, response.json()["code"]) == (422, "invalid_action")


@pytest.mark.parametrize(
    "body",
    [
        {"turn_id": 1},
        {"turn_id": 1, "action": {"type": "fly"}},
        {"turn_id": "x", "action": {"type": "back"}},
    ],
)
def test_malformed_actions_are_422(client: TestClient, body: dict[str, Any]) -> None:
    headers = _auth(client)
    session = _start(client, headers)

    assert (
        client.post(
            f"/v1/stylist/sessions/{session['session_id']}/actions", json=body, headers=headers
        ).status_code
        == 422
    )


def test_other_users_get_404(client: TestClient) -> None:
    session = _start(client, _auth(client))
    intruder = _auth(client, "google-ravi")

    assert (
        client.get(f"/v1/stylist/sessions/{session['session_id']}", headers=intruder).status_code
        == 404
    )
    assert _act(client, intruder, session["session_id"], 1, {"type": "restart"}).status_code == 404


def test_requires_sign_in(client: TestClient) -> None:
    assert client.post("/v1/stylist/sessions", json={"entry": "search"}).status_code == 401


@pytest.mark.parametrize(("version", "status"), [("abc", 400), ("0", 400)])
def test_bad_genui_version_header(client: TestClient, version: str, status: int) -> None:
    headers = {**_auth(client), "X-GenUI-Version": version}

    response = client.post("/v1/stylist/sessions", json={"entry": "search"}, headers=headers)

    assert response.status_code == status


def test_unsupported_app_version_is_told_to_update(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _auth(client)
    monkeypatch.setattr("stylesense.genui.versioning.MIN_SUPPORTED_VERSION", 2)

    response = client.post("/v1/stylist/sessions", json={"entry": "search"}, headers=headers)

    assert (response.status_code, response.json()["code"]) == (426, "app_update_required")


# ---------- streaming mechanics ----------


async def test_quiet_turns_send_keep_alive_comments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stylist_api, "KEEPALIVE_S", 0.01)

    async def slow_events() -> AsyncIterator[DoneEvent]:
        await asyncio.sleep(0.05)
        yield DoneEvent(turn_id=2)

    frames = [f async for f in stylist_api._frames(slow_events(), turn_id=2)]

    assert frames[0] == ": keep-alive\n\n"
    assert frames[-1].startswith("id: 2.1\nevent: done")


def test_session_ids_are_not_guessable_into_other_sessions(client: TestClient) -> None:
    headers = _auth(client)

    assert client.get(f"/v1/stylist/sessions/{uuid.uuid4()}", headers=headers).status_code == 404
