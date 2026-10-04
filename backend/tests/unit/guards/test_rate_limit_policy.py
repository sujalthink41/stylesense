import pytest

from stylesense.guards.rate_limit import (
    DEFAULT_POLICIES,
    Algorithm,
    RateLimitDecision,
    RateLimitedError,
    RateLimitPolicy,
)


@pytest.mark.parametrize(("limit", "window"), [(0, 60), (5, 0), (-1, 60)])
def test_policy_rejects_non_positive_values(limit: int, window: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        RateLimitPolicy("x", limit=limit, window_s=window, algorithm=Algorithm.SLIDING_WINDOW)


def test_default_policies_are_keyed_by_their_name() -> None:
    assert DEFAULT_POLICIES
    assert all(name == p.name for name, p in DEFAULT_POLICIES.items())


def test_rate_limited_error_carries_standard_headers() -> None:
    decision = RateLimitDecision(allowed=False, limit=60, remaining=0, retry_after_s=12)

    error = RateLimitedError.from_decision(decision)

    assert error.status_code == 429
    assert error.code == "rate_limited"
    assert error.headers == {
        "Retry-After": "12",
        "X-RateLimit-Limit": "60",
        "X-RateLimit-Remaining": "0",
    }
