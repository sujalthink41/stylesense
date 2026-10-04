from collections.abc import Iterator
from typing import Any

import pytest
import sentry_sdk
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

from stylesense.platform.errors import NotFoundError, register_error_handlers
from stylesense.platform.observability.error_reporting import configure_error_reporting
from stylesense.platform.observability.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from tests.factories import make_settings

FAKE_DSN = "http://public@glitchtip.invalid/1"


class CapturingTransport(Transport):
    events: list[dict[str, Any]] = []  # noqa: RUF012  # shared on purpose: SDK instantiates it

    def capture_envelope(self, envelope: Envelope) -> None:
        for item in envelope.items:
            if item.type == "event" and item.payload.json is not None:
                CapturingTransport.events.append(item.payload.json)


@pytest.fixture
def events() -> Iterator[list[dict[str, Any]]]:
    CapturingTransport.events = []
    configure_error_reporting(
        make_settings(sentry_dsn=FAKE_DSN, version="1.2.3"), transport=CapturingTransport
    )
    yield CapturingTransport.events
    sentry_sdk.get_client().close()
    sentry_sdk.init()  # back to a disabled client


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("failed for user a@b.co with token=abc")

    @app.get("/missing")
    async def missing() -> None:
        raise NotFoundError

    return TestClient(app, raise_server_exceptions=False)


def test_disabled_without_dsn() -> None:
    assert configure_error_reporting(make_settings()) is False


def test_unhandled_error_is_reported_once_with_context(
    events: list[dict[str, Any]], client: TestClient
) -> None:
    response = client.get("/boom")
    sentry_sdk.flush()

    assert len(events) == 1
    event = events[0]
    assert event["environment"] == "test"
    assert event["release"] == "stylesense@1.2.3"
    assert event["tags"]["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_reported_event_is_scrubbed(events: list[dict[str, Any]], client: TestClient) -> None:
    client.get("/boom", headers={"Authorization": "Bearer secret-token"})
    sentry_sdk.flush()

    payload = str(events[0])
    assert "a@b.co" not in payload
    assert "secret-token" not in payload


def test_expected_errors_are_not_reported(events: list[dict[str, Any]], client: TestClient) -> None:
    client.get("/missing")
    sentry_sdk.flush()

    assert events == []
