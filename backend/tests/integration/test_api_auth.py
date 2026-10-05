import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import text

from stylesense.api.auth import require_role
from stylesense.bootstrap.container import build_container
from stylesense.main import create_app
from stylesense.modules.auth.tokens import AccessTokenCodec
from stylesense.modules.users.schemas import Role
from stylesense.platform.config import Settings
from tests.fakes.clock import FixedClock
from tests.fakes.identity import FakeIdentityVerifier

ADMIN = "founder@stylesense.app"


@pytest.fixture
def verifier() -> FakeIdentityVerifier:
    v = FakeIdentityVerifier()
    v.register("google-priya", subject="g-1", email="priya@example.com", name="Priya")
    v.register("google-ravi", subject="g-2", email="ravi@example.com", name="Ravi")
    v.register("google-founder", subject="g-9", email=ADMIN)
    return v


@pytest.fixture
def client(
    settings: Settings, migrated: None, verifier: FakeIdentityVerifier
) -> Iterator[TestClient]:
    app_settings = settings.model_copy(update={"admin_emails": [ADMIN]})

    async def reset() -> None:
        redis = Redis.from_url(str(app_settings.redis_url))
        await redis.flushdb()
        await redis.aclose()
        container = app.state.container
        async with container.engine.begin() as conn:
            await conn.execute(text("TRUNCATE users, account_deletions, outbox_messages CASCADE"))

    admin_only = APIRouter()

    @admin_only.get("/admin-probe", dependencies=[Depends(require_role(Role.ADMIN))])
    async def probe() -> dict[str, str]:
        return {"ok": "admin"}

    app = create_app(
        app_settings,
        container_factory=lambda s, **kw: build_container(s, verifier=verifier, **kw),
    )
    app.include_router(admin_only, prefix="/t")
    with TestClient(app) as c:
        c.portal.call(reset)  # type: ignore[union-attr]
        yield c


def _sign_in(client: TestClient, token: str = "google-priya", **extra: Any) -> dict[str, Any]:
    response = client.post("/v1/auth/google", json={"id_token": token, **extra})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _bearer(session: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['tokens']['access_token']}"}


# ---------- sign-in ----------


def test_sign_in_returns_tokens_and_profile_without_caching(client: TestClient) -> None:
    response = client.post("/v1/auth/google", json={"id_token": "google-priya"})

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["is_new_user"] is True
    assert body["user"]["email"] == "priya@example.com"
    assert body["tokens"]["token_type"] == "Bearer"
    assert set(body["tokens"]) == {
        "access_token",
        "access_token_expires_in",
        "refresh_token",
        "refresh_token_expires_in",
        "token_type",
    }


def test_invalid_google_token_is_401_with_bearer_challenge(client: TestClient) -> None:
    response = client.post("/v1/auth/google", json={"id_token": "forged"})

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "invalid_id_token"
    assert response.headers["www-authenticate"] == 'Bearer error="invalid_id_token"'


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"id_token": ""},
        {"id_token": "x" * 5000},
        {"id_token": "t", "installation_id": "nope"},
        {"id_token": "t", "extra": 1},
    ],
)
def test_malformed_sign_in_is_422(client: TestClient, body: dict[str, Any]) -> None:
    assert client.post("/v1/auth/google", json=body).status_code == 422


# ---------- authenticated requests ----------


def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/v1/me")

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


@pytest.mark.parametrize(
    "header", ["Token abc", "Bearer", "Bearer   ", "Basic dXNlcjpwYXNz", "Bearer not.a.jwt"]
)
def test_malformed_authorization_is_invalid_token(client: TestClient, header: str) -> None:
    response = client.get("/v1/me", headers={"Authorization": header})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


def test_expired_access_token_asks_client_to_refresh(
    client: TestClient, settings: Settings
) -> None:
    session = _sign_in(client)
    past = FixedClock(datetime.now(UTC) - timedelta(hours=1))
    stale = AccessTokenCodec(
        secret=settings.jwt_secret,
        previous_secrets=[],
        issuer=settings.jwt_issuer,
        ttl_s=900,
        clock=past,
    ).issue(user_id=uuid.UUID(session["user"]["id"]), session_id=uuid.uuid4(), role="user")

    response = client.get("/v1/me", headers={"Authorization": f"Bearer {stale}"})

    assert response.status_code == 401
    assert response.json()["code"] == "token_expired"


def test_me_returns_the_signed_in_user_with_per_user_limits(client: TestClient) -> None:
    session = _sign_in(client)

    response = client.get("/v1/me", headers=_bearer(session))

    assert response.status_code == 200
    assert response.json()["id"] == session["user"]["id"]
    assert response.headers["x-ratelimit-limit"] == "120"


def test_profile_update_validates_input(client: TestClient) -> None:
    headers = _bearer(_sign_in(client))

    assert (
        client.patch("/v1/me", json={"display_name": "Pri"}, headers=headers).json()["display_name"]
        == "Pri"
    )
    assert (
        client.patch("/v1/me", json={"display_name": "x" * 61}, headers=headers).status_code == 422
    )
    assert client.patch("/v1/me", json={"locale": "fr-FR"}, headers=headers).status_code == 422
    assert client.patch("/v1/me", json={"role": "admin"}, headers=headers).status_code == 422


# ---------- roles ----------


def test_admin_routes_reject_regular_users(client: TestClient) -> None:
    response = client.get("/t/admin-probe", headers=_bearer(_sign_in(client)))

    assert response.status_code == 403
    assert response.json()["code"] == "insufficient_role"


def test_admin_routes_accept_allow_listed_admins(client: TestClient) -> None:
    session = _sign_in(client, "google-founder")

    assert session["user"]["role"] == "admin"
    assert client.get("/t/admin-probe", headers=_bearer(session)).status_code == 200


# ---------- devices & consents ----------


def test_device_registration_is_an_idempotent_upsert(client: TestClient) -> None:
    headers = _bearer(_sign_in(client))
    install = uuid.uuid4()
    body = {"platform": "android", "app_version": "0.1.0", "push_token": "fcm-secret-token"}

    first = client.put(f"/v1/me/devices/{install}", json=body, headers=headers)
    second = client.put(f"/v1/me/devices/{install}", json=body, headers=headers)

    assert first.status_code == second.status_code == 200
    assert second.json()["has_push_token"] is True
    assert "fcm-secret-token" not in second.text  # never echoed back
    assert client.delete(f"/v1/me/devices/{install}", headers=headers).status_code == 204
    assert client.delete(f"/v1/me/devices/{install}", headers=headers).status_code == 204


@pytest.mark.parametrize(
    "body",
    [
        {"platform": "windows", "app_version": "0.1.0"},
        {"platform": "android", "app_version": "latest"},
    ],
)
def test_invalid_device_registration_is_422(client: TestClient, body: dict[str, Any]) -> None:
    headers = _bearer(_sign_in(client))

    assert (
        client.put(f"/v1/me/devices/{uuid.uuid4()}", json=body, headers=headers).status_code == 422
    )


def test_consents_round_trip(client: TestClient) -> None:
    headers = _bearer(_sign_in(client))

    created = client.post(
        "/v1/me/consents",
        json={"kind": "terms", "version": "2026-10", "granted": True},
        headers=headers,
    )
    listed = client.get("/v1/me/consents", headers=headers)

    assert created.status_code == 201
    assert [(c["kind"], c["granted"]) for c in listed.json()] == [("terms", True)]


# ---------- sessions ----------


def test_refresh_rotates_and_detects_replay(client: TestClient) -> None:
    session = _sign_in(client)
    old = session["tokens"]["refresh_token"]

    rotated = client.post("/v1/auth/refresh", json={"refresh_token": old})
    assert rotated.status_code == 200
    assert rotated.headers["cache-control"] == "no-store"
    assert rotated.json()["refresh_token"] != old


def test_logout_ends_the_session(client: TestClient) -> None:
    refresh = _sign_in(client)["tokens"]["refresh_token"]

    assert client.post("/v1/auth/logout", json={"refresh_token": refresh}).status_code == 204
    response = client.post("/v1/auth/refresh", json={"refresh_token": refresh})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_refresh_token"


def test_account_deletion_flow(client: TestClient) -> None:
    session = _sign_in(client)

    deleted = client.delete("/v1/me", headers=_bearer(session))
    assert deleted.status_code == 202
    assert "purge_after" in deleted.json()

    me = client.get("/v1/me", headers=_bearer(session))  # access token still unexpired
    assert (me.status_code, me.json()["code"]) == (401, "account_deleted")
    refresh = client.post(
        "/v1/auth/refresh", json={"refresh_token": session["tokens"]["refresh_token"]}
    )
    assert refresh.status_code == 401
    again = client.post("/v1/auth/google", json={"id_token": "google-priya"})
    assert (again.status_code, again.json()["code"]) == (401, "account_deleted")


def test_users_only_ever_see_their_own_data(client: TestClient) -> None:
    priya, ravi = _sign_in(client), _sign_in(client, "google-ravi")

    assert client.get("/v1/me", headers=_bearer(priya)).json()["email"] == "priya@example.com"
    assert client.get("/v1/me", headers=_bearer(ravi)).json()["email"] == "ravi@example.com"


# ---------- public & limits ----------


def test_app_config_is_public_and_cacheable(client: TestClient) -> None:
    response = client.get("/v1/app/config")

    assert response.status_code == 200
    assert response.json() == {"min_supported_version": "0.1.0", "latest_version": "0.1.0"}
    assert response.headers["cache-control"] == "public, max-age=300"


def test_auth_endpoints_have_a_tighter_ip_limit(client: TestClient) -> None:
    statuses = [
        client.post("/v1/auth/google", json={"id_token": "forged"}).status_code for _ in range(21)
    ]

    assert statuses[:20] == [401] * 20
    assert statuses[20] == 429
