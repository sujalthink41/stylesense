from fastapi.testclient import TestClient

from stylesense.main import create_app
from stylesense.platform.config import Settings


def test_readyz_is_ok_against_real_dependencies(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert {c["name"]: c["ok"] for c in response.json()["checks"]} == {
        "postgres": True,
        "redis": True,
    }
