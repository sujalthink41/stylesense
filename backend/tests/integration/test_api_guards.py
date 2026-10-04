from collections.abc import Iterator
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, TypeAdapter
from redis.asyncio import Redis

from stylesense.api.dependencies import ContainerDep
from stylesense.api.idempotency import IdempotencyKey, run_idempotent
from stylesense.api.rate_limit import rate_limited
from stylesense.api.v1 import router as v1_router
from stylesense.main import create_app
from stylesense.platform.config import Settings


class OrderIn(BaseModel):
    total_paise: int


class OrderOut(BaseModel):
    id: int
    total_paise: int


class Ledger:
    def __init__(self) -> None:
        self.created = 0


@pytest.fixture
def ledger() -> Ledger:
    return Ledger()


@pytest.fixture
def client(settings: Settings, ledger: Ledger) -> Iterator[TestClient]:
    async def flush() -> None:
        redis = Redis.from_url(str(settings.redis_url))
        await redis.flushdb()
        await redis.aclose()

    router = APIRouter(dependencies=[Depends(rate_limited("api.per_ip"))])

    @router.get("/ping")
    async def ping() -> dict[str, str]:
        return {"pong": "ok"}

    @router.post("/orders", status_code=status.HTTP_201_CREATED)
    async def create_order(
        body: OrderIn,
        request: Request,
        response: Response,
        container: ContainerDep,
        key: Annotated[str, Depends(IdempotencyKey)],
    ) -> OrderOut:
        async def create() -> OrderOut:
            ledger.created += 1
            return OrderOut(id=ledger.created, total_paise=body.total_paise)

        return await run_idempotent(
            request,
            response,
            container,
            key=key,
            principal="ip:test",
            operation=create,
            adapter=TypeAdapter(OrderOut),
        )

    app = create_app(settings)
    app.include_router(router, prefix="/t")
    with TestClient(app) as c:
        c.portal.call(flush)  # type: ignore[union-attr]
        yield c


def test_v1_router_is_rate_limited_per_ip() -> None:
    assert any(
        getattr(d.dependency, "policy_name", None) == "api.per_ip" for d in v1_router.dependencies
    )


def test_rate_limit_headers_on_success(client: TestClient) -> None:
    response = client.get("/t/ping")

    assert response.headers["x-ratelimit-limit"] == "60"
    assert response.headers["x-ratelimit-remaining"] == "59"


def test_exceeding_the_limit_returns_429_problem(client: TestClient) -> None:
    for _ in range(60):
        assert client.get("/t/ping").status_code == 200

    response = client.get("/t/ping")

    assert response.status_code == 429
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "rate_limited"
    assert int(response.headers["retry-after"]) >= 1


def test_idempotent_create_replays_instead_of_duplicating(
    client: TestClient, ledger: Ledger
) -> None:
    headers = {"Idempotency-Key": "order-key-0001"}

    first = client.post("/t/orders", json={"total_paise": 49_900}, headers=headers)
    second = client.post("/t/orders", json={"total_paise": 49_900}, headers=headers)

    assert ledger.created == 1
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json() == {"id": 1, "total_paise": 49_900}
    assert "idempotent-replayed" not in first.headers
    assert second.headers["idempotent-replayed"] == "true"


def test_reusing_key_with_different_body_is_422(client: TestClient, ledger: Ledger) -> None:
    headers = {"Idempotency-Key": "order-key-0002"}
    client.post("/t/orders", json={"total_paise": 100}, headers=headers)

    response = client.post("/t/orders", json={"total_paise": 999}, headers=headers)

    assert response.status_code == 422
    assert response.json()["code"] == "idempotency_key_reused"
    assert ledger.created == 1


@pytest.mark.parametrize("headers", [{}, {"Idempotency-Key": "bad key"}])
def test_missing_or_malformed_key_is_400(
    client: TestClient, ledger: Ledger, headers: dict[str, str]
) -> None:
    response = client.post("/t/orders", json={"total_paise": 1}, headers=headers)

    assert response.status_code == 400
    assert response.json()["code"] in {"idempotency_key_required", "invalid_idempotency_key"}
    assert ledger.created == 0
