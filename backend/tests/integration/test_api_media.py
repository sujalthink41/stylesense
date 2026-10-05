import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import select, text, update

from stylesense.bootstrap.container import Container, build_container
from stylesense.guards.outbox import OutboxMessage, OutboxRelay
from stylesense.integrations.sources.mock import MockSource
from stylesense.main import create_app
from stylesense.modules.catalog.models import Product
from stylesense.modules.tryon.service import TOPIC
from stylesense.platform.config import Settings
from tests.fakes.identity import FakeIdentityVerifier
from tests.fakes.media import FakeMediaStore, ScriptedTryOn


def _app(settings: Settings, **overrides: Any) -> Any:
    verifier = FakeIdentityVerifier()
    verifier.register("google-zoya", subject="g-31", email="zoya@example.com")
    verifier.register("google-arjun", subject="g-32", email="arjun@example.com")
    return create_app(
        settings,
        container_factory=lambda s, **kw: build_container(s, verifier=verifier, **overrides, **kw),
    )


@pytest.fixture(scope="module")
def store() -> FakeMediaStore:
    return FakeMediaStore()


@pytest.fixture(scope="module")
def provider() -> ScriptedTryOn:
    return ScriptedTryOn()


@pytest.fixture(scope="module")
def client(
    settings: Settings, migrated: None, store: FakeMediaStore, provider: ScriptedTryOn
) -> Iterator[TestClient]:
    with TestClient(_app(settings, media_store=store, tryon_provider=provider)) as c:
        container: Container = c.app.state.container  # type: ignore[attr-defined]

        async def seed() -> None:
            async with container.engine.begin() as conn:
                await conn.execute(text("TRUNCATE users, products CASCADE"))
                await conn.execute(update(OutboxMessage).values(status="done"))
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


def _auth(client: TestClient, token: str = "google-zoya") -> dict[str, str]:
    body = client.post("/v1/auth/google", json={"id_token": token}).json()
    return {"Authorization": f"Bearer {body['tokens']['access_token']}"}


def _product(client: TestClient) -> str:
    container: Container = client.app.state.container  # type: ignore[attr-defined]

    async def first() -> str:
        async with container.session_factory() as s:
            return str(await s.scalar(select(Product.id).order_by(Product.id).limit(1)))

    return client.portal.call(first)  # type: ignore[union-attr]


def _ready_selfie(client: TestClient, store: FakeMediaStore, headers: dict[str, str]) -> str:
    upload = client.post("/v1/uploads", json={"kind": "selfie"}, headers=headers).json()
    store.simulate_upload(upload["upload"]["fields"]["public_id"])
    assert client.post(f"/v1/uploads/{upload['id']}/confirm", headers=headers).status_code == 200
    return str(upload["id"])


def _work(client: TestClient) -> None:
    container: Container = client.app.state.container  # type: ignore[attr-defined]
    relay = OutboxRelay(
        container.session_factory,
        {TOPIC: container.tryon.handle},
        clock=container.clock,
        base_backoff_s=0,
    )
    client.portal.call(relay.run_batch)  # type: ignore[union-attr]


# ---------- uploads ----------


def test_upload_lifecycle_over_http(client: TestClient, store: FakeMediaStore) -> None:
    headers = _auth(client)

    created = client.post("/v1/uploads", json={"kind": "photo_search"}, headers=headers)
    upload = created.json()
    early = client.post(f"/v1/uploads/{upload['id']}/confirm", headers=headers)
    store.simulate_upload(upload["upload"]["fields"]["public_id"])
    confirmed = client.post(f"/v1/uploads/{upload['id']}/confirm", headers=headers)

    assert created.status_code == 201
    assert upload["upload"]["url"].startswith("https://")
    assert (early.status_code, early.json()["code"]) == (409, "upload_missing")
    assert (confirmed.status_code, confirmed.json()["status"]) == (200, "ready")
    assert confirmed.json()["url"]
    assert (
        client.get(f"/v1/uploads/{upload['id']}", headers=_auth(client, "google-arjun")).status_code
        == 404
    )
    assert client.delete(f"/v1/uploads/{upload['id']}", headers=headers).status_code == 204
    assert client.get(f"/v1/uploads/{upload['id']}", headers=headers).json()["status"] == "deleted"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/v1/uploads", {"kind": "video"}),
        ("post", "/v1/uploads", {}),
        ("post", "/v1/tryon", {"selfie_upload_id": "x", "product_id": str(uuid.uuid4())}),
        (
            "post",
            "/v1/reports",
            {"target_kind": "user", "target_id": str(uuid.uuid4()), "reason": "spam"},
        ),
        (
            "post",
            "/v1/reports",
            {"target_kind": "tryon", "target_id": str(uuid.uuid4()), "reason": "meh"},
        ),
    ],
)
def test_media_input_is_validated(
    client: TestClient, method: str, path: str, body: dict[str, Any]
) -> None:
    headers = {**_auth(client), "Idempotency-Key": f"key-{uuid.uuid4().hex}"}

    assert client.request(method.upper(), path, json=body, headers=headers).status_code == 422


def test_media_needs_sign_in(client: TestClient) -> None:
    assert client.post("/v1/uploads", json={"kind": "selfie"}).status_code == 401
    assert client.get(f"/v1/tryon/{uuid.uuid4()}").status_code == 401


# ---------- try-on ----------


def test_try_on_over_http_double_tap_and_progress_stream(
    client: TestClient, store: FakeMediaStore, provider: ScriptedTryOn
) -> None:
    headers = _auth(client)
    body = {
        "selfie_upload_id": _ready_selfie(client, store, headers),
        "product_id": _product(client),
    }

    no_key = client.post("/v1/tryon", json=body, headers=headers)
    first = client.post(
        "/v1/tryon", json=body, headers={**headers, "Idempotency-Key": "tap-000001"}
    )
    replay = client.post(
        "/v1/tryon", json=body, headers={**headers, "Idempotency-Key": "tap-000001"}
    )
    second_tap = client.post(
        "/v1/tryon", json=body, headers={**headers, "Idempotency-Key": "tap-000002"}
    )
    job_id = first.json()["id"]

    assert (no_key.status_code, no_key.json()["code"]) == (400, "idempotency_key_required")
    assert (first.status_code, first.json()["status"]) == (202, "queued")
    assert replay.headers["idempotent-replayed"] == "true"
    assert (second_tap.status_code, second_tap.json()["id"]) == (200, job_id)  # same job

    calls_before = len(provider.calls)
    _work(client)
    assert len(provider.calls) == calls_before + 1  # paid once

    with client.stream("GET", f"/v1/tryon/{job_id}/events", headers=headers) as stream:
        assert stream.headers["content-type"].startswith("text/event-stream")
        frames = [line for line in stream.iter_lines() if line.startswith("data: ")]
    assert len(frames) == 1
    assert '"status":"done"' in frames[0]
    done = client.get(f"/v1/tryon/{job_id}", headers=headers).json()
    assert done["result_url"]


def test_reporting_a_try_on_hides_its_result(client: TestClient, store: FakeMediaStore) -> None:
    headers = _auth(client)
    body = {
        "selfie_upload_id": _ready_selfie(client, store, headers),
        "product_id": _product(client),
    }
    job = client.post(
        "/v1/tryon", json=body, headers={**headers, "Idempotency-Key": f"k-{uuid.uuid4().hex}"}
    ).json()
    _work(client)
    report = {"target_kind": "tryon", "target_id": job["id"], "reason": "inappropriate"}

    first = client.post("/v1/reports", json=report, headers=headers)
    again = client.post("/v1/reports", json=report, headers=headers)

    assert (first.status_code, again.status_code) == (201, 200)
    assert client.get(f"/v1/tryon/{job['id']}", headers=headers).json()["result_url"] is None


def test_others_cannot_see_or_retry_my_try_on(client: TestClient, store: FakeMediaStore) -> None:
    headers = _auth(client)
    body = {
        "selfie_upload_id": _ready_selfie(client, store, headers),
        "product_id": _product(client),
    }
    job = client.post(
        "/v1/tryon", json=body, headers={**headers, "Idempotency-Key": f"k-{uuid.uuid4().hex}"}
    ).json()
    other = _auth(client, "google-arjun")

    assert client.get(f"/v1/tryon/{job['id']}", headers=other).status_code == 404
    assert client.post(f"/v1/tryon/{job['id']}/retry", headers=other).status_code == 404
    assert client.get(f"/v1/tryon/{job['id']}/events", headers=other).status_code == 404


# ---------- not configured ----------


def test_without_storage_or_provider_media_reports_unavailable(
    settings: Settings, migrated: None
) -> None:
    with TestClient(_app(settings)) as c:  # test settings carry no Cloudinary keys
        headers = _auth(c)
        upload = c.post("/v1/uploads", json={"kind": "selfie"}, headers=headers)
        tryon = c.post(
            "/v1/tryon",
            json={"selfie_upload_id": str(uuid.uuid4()), "product_id": str(uuid.uuid4())},
            headers={**headers, "Idempotency-Key": "k-unavailable"},
        )

    assert (upload.status_code, upload.json()["code"]) == (503, "media_unavailable")
    assert (tryon.status_code, tryon.json()["code"]) == (503, "tryon_unavailable")
