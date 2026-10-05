import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import text

from stylesense.ai.gateway.models import LlmUsage
from stylesense.bootstrap.container import Container, build_container
from stylesense.main import create_app
from stylesense.platform.config import Settings
from tests.fakes.identity import FakeIdentityVerifier

ADMIN = "founder@stylesense.app"
PRICE = {
    "input_usd_per_mtok": "0.40",
    "cached_input_usd_per_mtok": "0.10",
    "output_usd_per_mtok": "1.60",
}
ROUTE = {
    "targets": ["openai:chat-small", "anthropic:chat-backup"],
    "max_output_tokens": 400,
    "timeout_s": 15,
}


@pytest.fixture
def client(settings: Settings, migrated: None) -> Iterator[TestClient]:
    verifier = FakeIdentityVerifier()
    verifier.register("google-admin", subject="g-admin", email=ADMIN)
    verifier.register("google-user", subject="g-user", email="user@example.com")
    app = create_app(
        settings.model_copy(update={"admin_emails": [ADMIN]}),
        container_factory=lambda s, **kw: build_container(s, verifier=verifier, **kw),
    )
    with TestClient(app) as c:
        container: Container = app.state.container

        async def reset() -> None:
            redis = Redis.from_url(str(settings.redis_url))
            await redis.flushdb()
            await redis.aclose()
            async with container.engine.begin() as conn:
                await conn.execute(
                    text("TRUNCATE users, llm_models, llm_task_configs, llm_usage CASCADE")
                )

        c.portal.call(reset)  # type: ignore[union-attr]
        yield c


def _auth(client: TestClient, token: str) -> dict[str, str]:
    body = client.post("/v1/auth/google", json={"id_token": token}).json()
    return {"Authorization": f"Bearer {body['tokens']['access_token']}"}


@pytest.fixture
def admin(client: TestClient) -> dict[str, str]:
    return _auth(client, "google-admin")


def test_regular_users_cannot_touch_ai_config(client: TestClient) -> None:
    headers = _auth(client, "google-user")

    assert client.get("/v1/admin/ai/tasks", headers=headers).status_code == 403
    assert client.put("/v1/admin/ai/tasks/x", json=ROUTE, headers=headers).status_code == 403
    assert client.get("/v1/admin/ai/tasks").status_code == 401


def test_admin_sets_prices_and_routing(client: TestClient, admin: dict[str, str]) -> None:
    price = client.put("/v1/admin/ai/models/openai/chat-small", json=PRICE, headers=admin)
    route = client.put("/v1/admin/ai/tasks/stylist.explain", json=ROUTE, headers=admin)

    assert price.status_code == 200
    assert price.json()["output_usd_per_mtok"] == "1.600000"
    assert route.status_code == 200
    assert route.json()["targets"] == ["openai:chat-small", "anthropic:chat-backup"]
    assert [t["task"] for t in client.get("/v1/admin/ai/tasks", headers=admin).json()] == [
        "stylist.explain"
    ]


def test_upserts_replace_previous_values(client: TestClient, admin: dict[str, str]) -> None:
    client.put("/v1/admin/ai/tasks/stylist.explain", json=ROUTE, headers=admin)

    client.put(
        "/v1/admin/ai/tasks/stylist.explain", json={**ROUTE, "enabled": False}, headers=admin
    )

    [task] = client.get("/v1/admin/ai/tasks", headers=admin).json()
    assert task["enabled"] is False


@pytest.mark.parametrize(
    "body",
    [
        {**ROUTE, "targets": []},
        {**ROUTE, "targets": ["no-colon"]},
        {**ROUTE, "targets": ["openai:a", "openai:a"]},
        {**ROUTE, "temperature": 5},
        {**ROUTE, "timeout_s": 0},
        {**ROUTE, "surprise": True},
    ],
)
def test_invalid_routing_is_422(
    client: TestClient, admin: dict[str, str], body: dict[str, Any]
) -> None:
    assert (
        client.put("/v1/admin/ai/tasks/stylist.explain", json=body, headers=admin).status_code
        == 422
    )


def test_unknown_provider_is_rejected(client: TestClient, admin: dict[str, str]) -> None:
    response = client.put(
        "/v1/admin/ai/tasks/stylist.explain",
        json={**ROUTE, "targets": ["madeup:model"]},
        headers=admin,
    )

    assert (response.status_code, response.json()["code"]) == (422, "invalid_ai_config")


def test_negative_price_is_422(client: TestClient, admin: dict[str, str]) -> None:
    body = {**PRICE, "input_usd_per_mtok": "-1"}

    assert client.put("/v1/admin/ai/models/openai/x", json=body, headers=admin).status_code == 422


def test_usage_report_aggregates_cost_and_outcomes(
    client: TestClient, admin: dict[str, str]
) -> None:
    container: Container = client.app.state.container  # type: ignore[attr-defined]

    async def seed_usage() -> None:
        call = uuid.uuid4()
        async with container.session_factory() as s, s.begin():
            for outcome, cost, latency in (
                ("error", 0, 900),
                ("ok", 1_400, 1_200),
                ("cache_hit", 0, 0),
            ):
                s.add(
                    LlmUsage(
                        call_id=call,
                        task="stylist.explain",
                        provider="openai",
                        model="chat-small",
                        prompt_version="v1",
                        input_tokens=1_000 if cost else 0,
                        output_tokens=100 if cost else 0,
                        cost_micro_usd=cost,
                        latency_ms=latency,
                        outcome=outcome,
                    )
                )

    client.portal.call(seed_usage)  # type: ignore[union-attr]

    [row] = client.get("/v1/admin/ai/usage", params={"days": 1}, headers=admin).json()

    assert (row["attempts"], row["ok"], row["errors"], row["cache_hits"]) == (3, 1, 1, 1)
    assert row["cost_usd"] == "0.0014"
    assert row["input_tokens"] == 1_000


def test_status_reports_budget_and_providers(client: TestClient, admin: dict[str, str]) -> None:
    status = client.get("/v1/admin/ai/status", headers=admin).json()

    assert status["providers"] == []  # no API keys in tests
    assert status["embedding_model"] == "hashing"
    assert status["spent_today_usd"] == "0"
    assert status["daily_budget_usd"] == "2.00"
