from collections.abc import Iterator, Sequence

import pytest
from fastapi.testclient import TestClient

from stylesense.api.dependencies import get_health_checks
from stylesense.bootstrap.container import build_container
from stylesense.main import create_app
from stylesense.platform.health import HealthCheck
from tests.factories import make_settings
from tests.fakes.health import StubHealthCheck


def _client(checks: Sequence[HealthCheck], **settings: object) -> TestClient:
    app = create_app(make_settings(**settings))
    app.dependency_overrides[get_health_checks] = lambda: checks
    return TestClient(app)


@pytest.fixture
def healthy() -> Iterator[TestClient]:
    with _client([StubHealthCheck("postgres"), StubHealthCheck("redis")]) as client:
        yield client


def test_liveness_never_touches_dependencies() -> None:
    hanging = StubHealthCheck("postgres", hang=True)
    with _client([hanging]) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert hanging.calls == 0


def test_readiness_ok_when_all_dependencies_up(healthy: TestClient) -> None:
    response = healthy.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert {c["name"] for c in body["checks"]} == {"postgres", "redis"}


def test_readiness_503_when_a_dependency_is_down() -> None:
    checks = [StubHealthCheck("postgres", error=OSError()), StubHealthCheck("redis")]
    with _client(checks) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    down = next(c for c in body["checks"] if c["name"] == "postgres")
    assert (down["ok"], down["error"]) == (False, "OSError")


def test_readiness_503_when_a_dependency_hangs() -> None:
    with _client([StubHealthCheck("postgres", hang=True)], readiness_timeout_s=0.05) as client:
        response = client.get("/readyz")

    assert response.status_code == 503


def test_probes_are_never_cached(healthy: TestClient) -> None:
    for path in ("/healthz", "/readyz"):
        assert healthy.get(path).headers["cache-control"] == "no-store"


def test_docs_available_outside_production(healthy: TestClient) -> None:
    assert healthy.get("/docs").status_code == 200
    assert healthy.get("/openapi.json").status_code == 200


def test_docs_hidden_in_production() -> None:
    with _client([], env="production") as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_unknown_route_returns_problem_json(healthy: TestClient) -> None:
    response = healthy.get("/v1/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


def test_container_is_built_on_startup_and_closed_on_shutdown() -> None:
    app = create_app(make_settings())

    with TestClient(app):
        container = app.state.container
        assert container.settings.env.value == "test"
        assert not container.closed

    assert container.closed


async def test_container_close_is_idempotent() -> None:
    container = build_container(make_settings())
    await container.aclose()
    await container.aclose()

    assert container.closed


def test_cors_allows_only_configured_origins() -> None:
    with _client([], cors_origins=["https://admin.stylesense.app"]) as client:
        allowed = client.options(
            "/healthz",
            headers={
                "Origin": "https://admin.stylesense.app",
                "Access-Control-Request-Method": "GET",
            },
        )
        denied = client.options(
            "/healthz",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
        )

    assert allowed.headers["access-control-allow-origin"] == "https://admin.stylesense.app"
    assert "access-control-allow-origin" not in denied.headers
