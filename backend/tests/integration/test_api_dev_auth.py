"""Developer sign-in: the Expo Go stand-in for Google, never available unless enabled."""

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis.asyncio import Redis

from stylesense.main import create_app, openapi_json
from stylesense.platform.config import Settings
from tests.factories import make_settings


def _client(settings: Settings, *, enabled: bool) -> TestClient:
    return TestClient(create_app(settings.model_copy(update={"dev_sign_in_enabled": enabled})))


@pytest.fixture(autouse=True)
def fresh_limits(settings: Settings) -> Iterator[None]:
    yield
    import asyncio  # noqa: PLC0415

    async def flush() -> None:
        redis = Redis.from_url(str(settings.redis_url))
        await redis.flushdb()
        await redis.aclose()

    asyncio.run(flush())


def test_dev_sign_in_is_404_unless_enabled(settings: Settings, migrated: None) -> None:
    with _client(settings, enabled=False) as client:
        response = client.post("/v1/auth/dev", json={"email": "dev@example.com"})

    assert (response.status_code, response.json()["code"]) == (404, "not_found")


def test_dev_sign_in_issues_a_real_session(settings: Settings, migrated: None) -> None:
    with _client(settings, enabled=True) as client:
        first = client.post("/v1/auth/dev", json={"email": "  Dev@Example.com "})
        again = client.post("/v1/auth/dev", json={"email": "dev@example.com"})
        me = client.get(
            "/v1/me", headers={"Authorization": f"Bearer {first.json()['tokens']['access_token']}"}
        )

    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-store"
    assert (first.json()["is_new_user"], again.json()["is_new_user"]) == (True, False)
    assert me.json()["email"] == "dev@example.com"


@pytest.mark.parametrize("body", [{}, {"email": "not-an-email"}, {"email": "a@b.co", "x": 1}])
def test_dev_sign_in_validates_its_input(
    settings: Settings, migrated: None, body: dict[str, object]
) -> None:
    with _client(settings, enabled=True) as client:
        assert client.post("/v1/auth/dev", json=body).status_code == 422


def test_dev_sign_in_can_never_be_enabled_in_production() -> None:
    with pytest.raises(ValidationError, match="developer sign-in"):
        make_settings(env="production", google_client_ids=["web"], dev_sign_in_enabled=True)


def test_openapi_export_needs_no_environment_and_covers_the_api() -> None:
    schema = json.loads(openapi_json())

    assert schema["openapi"].startswith("3.")
    for path in ("/v1/auth/google", "/v1/auth/dev", "/v1/stylist/sessions", "/v1/boards"):
        assert path in schema["paths"]
