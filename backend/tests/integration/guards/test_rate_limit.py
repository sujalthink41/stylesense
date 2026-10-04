import asyncio
import uuid
from datetime import timedelta

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from redis.asyncio import Redis

from stylesense.guards.rate_limit import Algorithm, RateLimiter, RateLimitPolicy
from stylesense.infra.redis import create_redis
from tests.factories import UNREACHABLE_REDIS, make_settings
from tests.fakes.clock import FixedClock

PER_MINUTE = RateLimitPolicy(
    "test.window", limit=3, window_s=60, algorithm=Algorithm.SLIDING_WINDOW
)
BUCKET = RateLimitPolicy("test.bucket", limit=4, window_s=60, algorithm=Algorithm.TOKEN_BUCKET)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def limiter(redis: Redis, clock: FixedClock) -> RateLimiter:
    return RateLimiter(redis, clock)


async def _hits(
    limiter: RateLimiter, policy: RateLimitPolicy, n: int, subject: str = "ip:1"
) -> list[bool]:
    return [(await limiter.hit(policy, subject)).allowed for _ in range(n)]


# ---------- sliding window ----------


async def test_window_allows_up_to_limit_then_denies(limiter: RateLimiter) -> None:
    assert await _hits(limiter, PER_MINUTE, 4) == [True, True, True, False]


async def test_window_reports_remaining_and_retry_after(
    limiter: RateLimiter, clock: FixedClock
) -> None:
    first = await limiter.hit(PER_MINUTE, "ip:1")
    clock.advance(timedelta(seconds=20))
    await _hits(limiter, PER_MINUTE, 2)

    denied = await limiter.hit(PER_MINUTE, "ip:1")

    assert (first.limit, first.remaining) == (3, 2)
    assert denied.allowed is False
    assert denied.remaining == 0
    assert denied.retry_after_s == 40  # until the first hit leaves the window


async def test_window_slides_rather_than_resetting(limiter: RateLimiter, clock: FixedClock) -> None:
    await _hits(limiter, PER_MINUTE, 3)
    clock.advance(timedelta(seconds=59))
    assert (await limiter.hit(PER_MINUTE, "ip:1")).allowed is False

    clock.advance(timedelta(seconds=1))
    assert (await limiter.hit(PER_MINUTE, "ip:1")).allowed is True


async def test_denied_hits_do_not_consume_quota(limiter: RateLimiter, clock: FixedClock) -> None:
    await _hits(limiter, PER_MINUTE, 3)
    await _hits(limiter, PER_MINUTE, 10)  # hammering while blocked

    clock.advance(timedelta(seconds=60))

    assert await _hits(limiter, PER_MINUTE, 3) == [True, True, True]


async def test_subjects_and_policies_are_isolated(limiter: RateLimiter) -> None:
    await _hits(limiter, PER_MINUTE, 3, subject="ip:1")

    assert (await limiter.hit(PER_MINUTE, "ip:2")).allowed is True
    other = RateLimitPolicy("test.other", limit=1, window_s=60, algorithm=Algorithm.SLIDING_WINDOW)
    assert (await limiter.hit(other, "ip:1")).allowed is True


@settings(
    max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(gaps_ms=st.lists(st.integers(min_value=0, max_value=30_000), min_size=1, max_size=40))
async def test_never_allows_more_than_limit_in_any_window(redis: Redis, gaps_ms: list[int]) -> None:
    clock = FixedClock()
    limiter = RateLimiter(redis, clock)
    subject = uuid.uuid4().hex
    allowed_at: list[float] = []

    for gap in gaps_ms:
        clock.advance(timedelta(milliseconds=gap))
        if (await limiter.hit(PER_MINUTE, subject)).allowed:
            allowed_at.append(clock.now().timestamp())

    for i, start in enumerate(allowed_at):
        in_window = [t for t in allowed_at[i:] if t - start < PER_MINUTE.window_s]
        assert len(in_window) <= PER_MINUTE.limit


# ---------- token bucket ----------


async def test_bucket_allows_burst_up_to_capacity(limiter: RateLimiter) -> None:
    assert await _hits(limiter, BUCKET, 5) == [True, True, True, True, False]


async def test_bucket_refills_gradually(limiter: RateLimiter, clock: FixedClock) -> None:
    await _hits(limiter, BUCKET, 4)

    clock.advance(timedelta(seconds=15))  # 4 per 60 s → one token per 15 s
    assert await _hits(limiter, BUCKET, 2) == [True, False]


async def test_bucket_retry_after_is_time_to_next_token(
    limiter: RateLimiter, clock: FixedClock
) -> None:
    await _hits(limiter, BUCKET, 4)
    clock.advance(timedelta(seconds=5))

    denied = await limiter.hit(BUCKET, "ip:1")

    assert denied.retry_after_s == 10


async def test_bucket_never_exceeds_capacity_after_long_idle(
    limiter: RateLimiter, clock: FixedClock
) -> None:
    clock.advance(timedelta(days=1))

    assert await _hits(limiter, BUCKET, 5) == [True, True, True, True, False]


# ---------- concurrency & failure ----------


@pytest.mark.parametrize("policy", [PER_MINUTE, BUCKET])
async def test_concurrent_instances_never_exceed_limit(
    redis: Redis, other_redis: Redis, policy: RateLimitPolicy
) -> None:
    clock = FixedClock()
    limiters = [RateLimiter(redis, clock), RateLimiter(other_redis, clock)]

    results = await asyncio.gather(*(limiters[i % 2].hit(policy, "ip:1") for i in range(30)))

    assert sum(r.allowed for r in results) == policy.limit


async def test_fails_open_when_redis_is_down(clock: FixedClock) -> None:
    down = create_redis(make_settings(redis_url=UNREACHABLE_REDIS, redis_timeout_s=0.2))
    try:
        decision = await RateLimiter(down, clock).hit(PER_MINUTE, "ip:1")
    finally:
        await down.aclose()

    assert decision.allowed is True


async def test_can_fail_closed_when_configured(clock: FixedClock) -> None:
    down = create_redis(make_settings(redis_url=UNREACHABLE_REDIS, redis_timeout_s=0.2))
    try:
        decision = await RateLimiter(down, clock, fail_open=False).hit(PER_MINUTE, "ip:1")
    finally:
        await down.aclose()

    assert decision.allowed is False
