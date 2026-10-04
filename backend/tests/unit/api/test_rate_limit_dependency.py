import pytest
from starlette.requests import Request

from stylesense.api.rate_limit import client_ip, rate_limited


def test_client_ip_falls_back_when_transport_has_no_peer() -> None:
    request = Request({"type": "http", "headers": [], "client": None})

    assert client_ip(request) == "unknown"


def test_unknown_policy_is_rejected_at_startup() -> None:
    with pytest.raises(ValueError, match="unknown rate limit policy"):
        rate_limited("does.not.exist")
