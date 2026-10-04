from collections.abc import AsyncIterator

import pytest
import structlog
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.testclient import TestClient
from starlette.requests import Request

from stylesense.platform.errors import NotFoundError, register_error_handlers
from stylesense.platform.observability.context import current_request_id
from stylesense.platform.observability.middleware import (
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
    _request_id,
)
from tests.unit.platform.observability.conftest import LogReader


def _app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware, quiet_paths=frozenset({"/healthz"}))

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, str | None]:
        structlog.get_logger("test").info("loading_item")
        return {"request_id": current_request_id()}

    @app.get("/missing")
    async def missing() -> None:
        raise NotFoundError

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    async def plain(_: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    app.add_route("/plain/{name}", plain)  # Starlette route, like FastAPI's /docs
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_app(), raise_server_exceptions=False)


def test_generates_request_id_and_returns_it(client: TestClient) -> None:
    response = client.get("/items/1")

    rid = response.headers[REQUEST_ID_HEADER]
    assert len(rid) == 32
    assert response.json()["request_id"] == rid


def test_propagates_valid_inbound_request_id(client: TestClient) -> None:
    response = client.get("/items/1", headers={REQUEST_ID_HEADER: "mobile-abc_123.x"})

    assert response.headers[REQUEST_ID_HEADER] == "mobile-abc_123.x"


@pytest.mark.parametrize(
    "bad",
    ["short", "a" * 65, "has space inside", "semi;colon-injection", 'quote"-injection'],
)
def test_replaces_unsafe_inbound_request_id(client: TestClient, bad: str) -> None:
    response = client.get("/items/1", headers={REQUEST_ID_HEADER: bad})

    assert response.headers[REQUEST_ID_HEADER] != bad
    assert len(response.headers[REQUEST_ID_HEADER]) == 32


def test_replaces_non_ascii_request_id_bytes() -> None:
    scope = {"type": "http", "headers": [(b"x-request-id", "emoji-😀-request".encode())]}

    assert len(_request_id(scope)) == 32


def test_each_request_gets_its_own_id(client: TestClient) -> None:
    first = client.get("/items/1").headers[REQUEST_ID_HEADER]
    second = client.get("/items/1").headers[REQUEST_ID_HEADER]

    assert first != second


def test_context_does_not_leak_after_request(client: TestClient) -> None:
    client.get("/items/1")

    assert current_request_id() is None


def test_logs_inside_handler_carry_request_id(client: TestClient, json_logs: LogReader) -> None:
    rid = client.get("/items/1").headers[REQUEST_ID_HEADER]

    handler_log = next(r for r in json_logs() if r["event"] == "loading_item")
    assert handler_log["request_id"] == rid


def test_access_log_uses_route_template_not_raw_path(
    client: TestClient, json_logs: LogReader
) -> None:
    client.get("/items/secret-42?email=a@b.co")

    access = next(r for r in json_logs() if r["event"] == "http_request")
    assert access["route"] == "/items/{item_id}"
    assert access["method"] == "GET"
    assert access["status"] == 200
    assert isinstance(access["duration_ms"], float)
    assert "secret-42" not in str(access)
    assert "a@b.co" not in str(access)


@pytest.mark.parametrize(
    ("path", "status", "level"),
    [("/missing", 404, "warning"), ("/boom", 500, "error")],
)
def test_access_log_level_follows_status(
    client: TestClient, json_logs: LogReader, path: str, status: int, level: str
) -> None:
    client.get(path)

    access = next(r for r in json_logs() if r["event"] == "http_request")
    assert (access["status"], access["level"]) == (status, level)


def test_plain_starlette_routes_use_their_template(
    client: TestClient, json_logs: LogReader
) -> None:
    client.get("/plain/secret-name")

    access = next(r for r in json_logs() if r["event"] == "http_request")
    assert access["route"] == "/plain/{name}"


def test_unmatched_route_is_labelled_generically(client: TestClient, json_logs: LogReader) -> None:
    client.get("/random/scanner/path")

    access = next(r for r in json_logs() if r["event"] == "http_request")
    assert access["route"] == "<unmatched>"


def test_quiet_paths_are_not_access_logged(client: TestClient, json_logs: LogReader) -> None:
    response = client.get("/healthz")

    assert REQUEST_ID_HEADER in response.headers
    assert not [r for r in json_logs() if r["event"] == "http_request"]


def test_problem_responses_include_request_id(client: TestClient) -> None:
    response = client.get("/missing")

    assert response.json()["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_unhandled_error_response_still_has_request_id(client: TestClient) -> None:
    response = client.get("/boom")

    assert response.status_code == 500
    assert response.json()["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_error_after_streaming_started_is_not_masked_with_a_second_response() -> None:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    async def chunks() -> AsyncIterator[bytes]:
        yield b"first"
        raise RuntimeError("stream broke")

    @app.get("/stream")
    async def stream() -> StreamingResponse:
        return StreamingResponse(chunks())

    client = TestClient(app)
    with pytest.raises(RuntimeError, match="stream broke"):
        client.get("/stream")
