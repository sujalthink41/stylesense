import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from stylesense.platform.errors import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    UnauthorizedError,
    register_error_handlers,
)

PROBLEM_JSON = "application/problem+json"


class Item(BaseModel):
    name: str
    price_paise: int


class OutOfStockError(ConflictError):
    code = "out_of_stock"
    title = "Item is out of stock"


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/not-found")
    async def not_found() -> None:
        raise NotFoundError("Product 42 does not exist")

    @app.get("/custom")
    async def custom() -> None:
        raise OutOfStockError(extra={"product_id": "p1"})

    @app.get("/unavailable")
    async def unavailable() -> None:
        raise ServiceUnavailableError(retry_after_s=30)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("db password is hunter2")

    @app.post("/items")
    async def create(item: Item) -> Item:
        return item

    return TestClient(app, raise_server_exceptions=False)


def test_app_error_renders_problem_json(client: TestClient) -> None:
    response = client.get("/not-found")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json() == {
        "type": "/problems/not_found",
        "title": "Resource not found",
        "status": 404,
        "detail": "Product 42 does not exist",
        "instance": "/not-found",
        "code": "not_found",
    }


def test_subclassed_error_uses_its_own_code_and_extra_fields(client: TestClient) -> None:
    body = client.get("/custom").json()

    assert body["status"] == 409
    assert body["code"] == "out_of_stock"
    assert body["title"] == "Item is out of stock"
    assert body["product_id"] == "p1"
    assert "detail" not in body


def test_service_unavailable_sets_retry_after_header(client: TestClient) -> None:
    response = client.get("/unavailable")

    assert response.status_code == 503
    assert response.headers["retry-after"] == "30"


def test_unhandled_exception_is_500_without_leaking_internals(client: TestClient) -> None:
    response = client.get("/boom")

    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "internal_error"
    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text


def test_unknown_route_is_problem_json_404(client: TestClient) -> None:
    response = client.get("/nope")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "not_found"


def test_wrong_method_is_problem_json_405(client: TestClient) -> None:
    response = client.delete("/items")

    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"


def test_validation_error_lists_fields_without_echoing_input(client: TestClient) -> None:
    response = client.post("/items", json={"name": "secret-name", "price_paise": "lots"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["errors"] == [
        {
            "loc": ["body", "price_paise"],
            "msg": "Input should be a valid integer, unable to parse string as an integer",
            "type": "int_parsing",
        }
    ]
    assert "lots" not in response.text


def test_malformed_json_body_is_422(client: TestClient) -> None:
    response = client.post(
        "/items", content=b"{not json", headers={"content-type": "application/json"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


@pytest.mark.parametrize(
    ("error_cls", "status", "code"),
    [
        (UnauthorizedError, 401, "unauthorized"),
        (ForbiddenError, 403, "forbidden"),
        (NotFoundError, 404, "not_found"),
        (ConflictError, 409, "conflict"),
        (ServiceUnavailableError, 503, "service_unavailable"),
        (AppError, 500, "internal_error"),
    ],
)
def test_error_taxonomy(error_cls: type[AppError], status: int, code: str) -> None:
    assert error_cls.status_code == status
    assert error_cls.code == code
