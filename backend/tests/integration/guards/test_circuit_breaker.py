import asyncio
from datetime import timedelta

import pytest
from redis.asyncio import Redis

from stylesense.guards.circuit_breaker import BreakerState, CircuitBreaker
from stylesense.infra.redis import create_redis
from tests.factories import UNREACHABLE_REDIS, make_settings
from tests.fakes.clock import FixedClock


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


def _breaker(redis: Redis, clock: FixedClock, name: str = "openai:model-a") -> CircuitBreaker:
    return CircuitBreaker(redis, clock, name=name, failure_threshold=3, window_s=30, cooldown_s=60)


async def _fail(breaker: CircuitBreaker, times: int) -> None:
    for _ in range(times):
        await breaker.record_failure()


async def test_starts_closed_and_allows_calls(redis: Redis, clock: FixedClock) -> None:
    breaker = _breaker(redis, clock)

    assert await breaker.allow() is True
    assert await breaker.state() is BreakerState.CLOSED


async def test_opens_after_threshold_failures_in_the_window(
    redis: Redis, clock: FixedClock
) -> None:
    breaker = _breaker(redis, clock)

    await _fail(breaker, 2)
    assert await breaker.allow() is True
    await _fail(breaker, 1)

    assert await breaker.allow() is False
    assert await breaker.state() is BreakerState.OPEN


async def test_failures_outside_the_window_do_not_add_up(redis: Redis, clock: FixedClock) -> None:
    breaker = _breaker(redis, clock)

    await _fail(breaker, 2)
    clock.advance(timedelta(seconds=31))
    await _fail(breaker, 2)

    assert await breaker.state() is BreakerState.CLOSED


async def test_success_resets_the_failure_count(redis: Redis, clock: FixedClock) -> None:
    breaker = _breaker(redis, clock)

    await _fail(breaker, 2)
    await breaker.record_success()
    await _fail(breaker, 2)

    assert await breaker.state() is BreakerState.CLOSED


async def test_after_cooldown_exactly_one_probe_is_let_through(
    redis: Redis, other_redis: Redis, clock: FixedClock
) -> None:
    await _fail(_breaker(redis, clock), 3)
    clock.advance(timedelta(seconds=60))
    instances = [_breaker(redis, clock), _breaker(other_redis, clock)] * 5

    allowed = await asyncio.gather(*(b.allow() for b in instances))

    assert sum(allowed) == 1
    assert await instances[0].state() is BreakerState.HALF_OPEN


async def test_successful_probe_closes_the_breaker(redis: Redis, clock: FixedClock) -> None:
    breaker = _breaker(redis, clock)
    await _fail(breaker, 3)
    clock.advance(timedelta(seconds=60))
    assert await breaker.allow() is True

    await breaker.record_success()

    assert await breaker.state() is BreakerState.CLOSED
    assert await breaker.allow() is True


async def test_failed_probe_reopens_for_another_cooldown(redis: Redis, clock: FixedClock) -> None:
    breaker = _breaker(redis, clock)
    await _fail(breaker, 3)
    clock.advance(timedelta(seconds=60))
    assert await breaker.allow() is True

    await breaker.record_failure()

    assert await breaker.allow() is False
    clock.advance(timedelta(seconds=59))
    assert await breaker.allow() is False
    clock.advance(timedelta(seconds=1))
    assert await breaker.allow() is True


async def test_state_is_shared_across_instances(
    redis: Redis, other_redis: Redis, clock: FixedClock
) -> None:
    await _fail(_breaker(redis, clock), 3)

    assert await _breaker(other_redis, clock).allow() is False


async def test_breakers_are_independent_per_name(redis: Redis, clock: FixedClock) -> None:
    await _fail(_breaker(redis, clock, "openai:model-a"), 3)

    assert await _breaker(redis, clock, "anthropic:model-b").allow() is True


async def test_redis_outage_fails_open(clock: FixedClock) -> None:
    down = create_redis(make_settings(redis_url=UNREACHABLE_REDIS, redis_timeout_s=0.2))
    try:
        breaker = _breaker(down, clock)
        assert await breaker.allow() is True
        await breaker.record_failure()  # must not raise
        await breaker.record_success()
    finally:
        await down.aclose()
