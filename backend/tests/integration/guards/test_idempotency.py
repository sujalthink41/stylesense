import asyncio

import pytest
from pydantic import BaseModel, TypeAdapter
from redis.asyncio import Redis

from stylesense.guards.idempotency import (
    IdempotencyGuard,
    IdempotencyInProgressError,
    IdempotencyKeyReusedError,
    IdempotentOutcome,
)
from stylesense.infra.redis import create_redis
from stylesense.platform.errors import ServiceUnavailableError
from tests.factories import UNREACHABLE_REDIS, make_settings


class Order(BaseModel):
    id: int
    total_paise: int


ORDER = TypeAdapter(Order)


class CreateOrder:
    """Fake side-effecting operation that counts how often it really ran."""

    def __init__(
        self, delay: float = 0, error: Exception | None = None, total_paise: int = 49_900
    ) -> None:
        self.calls = 0
        self._delay = delay
        self._error = error
        self._total = total_paise

    async def __call__(self) -> Order:
        self.calls += 1
        await asyncio.sleep(self._delay)
        if self._error:
            raise self._error
        return Order(id=self.calls, total_paise=self._total)


async def _run(
    guard: IdempotencyGuard, op: CreateOrder, *, key: str = "key-0001", fp: str = "fp-a"
) -> IdempotentOutcome[Order]:
    return await guard.run(
        scope="user:1:POST /orders", key=key, fingerprint=fp, operation=op, adapter=ORDER
    )


async def test_first_call_executes_and_repeat_replays_stored_result(redis: Redis) -> None:
    guard, op = IdempotencyGuard(redis), CreateOrder()

    first = await _run(guard, op)
    second = await _run(guard, op)

    assert op.calls == 1
    assert (first.value, first.replayed) == (Order(id=1, total_paise=49_900), False)
    assert (second.value, second.replayed) == (first.value, True)


async def test_same_key_with_different_request_is_rejected(redis: Redis) -> None:
    guard, op = IdempotencyGuard(redis), CreateOrder()
    await _run(guard, op, fp="fp-a")

    with pytest.raises(IdempotencyKeyReusedError) as err:
        await _run(guard, op, fp="fp-b")

    assert err.value.status_code == 422
    assert op.calls == 1


async def test_concurrent_duplicates_across_instances_execute_once(
    redis: Redis, other_redis: Redis
) -> None:
    guards = [IdempotencyGuard(redis), IdempotencyGuard(other_redis)]
    op = CreateOrder(delay=0.1)

    results = await asyncio.gather(
        *(_run(guards[i % 2], op) for i in range(10)), return_exceptions=True
    )

    assert op.calls == 1
    successes = [r for r in results if not isinstance(r, BaseException)]
    in_progress = [r for r in results if isinstance(r, IdempotencyInProgressError)]
    assert len(successes) == 1
    assert len(in_progress) == 9
    assert in_progress[0].headers["Retry-After"] == "1"


async def test_retry_after_completion_replays_for_every_instance(
    redis: Redis, other_redis: Redis
) -> None:
    op = CreateOrder()
    await _run(IdempotencyGuard(redis), op)

    replay = await _run(IdempotencyGuard(other_redis), op)

    assert replay.replayed is True
    assert op.calls == 1


async def test_failed_operation_releases_key_so_client_can_retry(redis: Redis) -> None:
    guard = IdempotencyGuard(redis)
    with pytest.raises(RuntimeError):
        await _run(guard, CreateOrder(error=RuntimeError("payment gateway down")))

    retry = CreateOrder()
    outcome = await _run(guard, retry)

    assert (retry.calls, outcome.replayed) == (1, False)


async def test_in_progress_request_with_different_body_is_rejected(redis: Redis) -> None:
    guard = IdempotencyGuard(redis)
    slow = asyncio.create_task(_run(guard, CreateOrder(delay=0.1), fp="fp-a"))
    await asyncio.sleep(0.02)

    with pytest.raises(IdempotencyKeyReusedError):
        await _run(guard, CreateOrder(), fp="fp-b")
    await slow


async def test_scopes_isolate_identical_keys(redis: Redis) -> None:
    guard, op = IdempotencyGuard(redis), CreateOrder()

    await guard.run(scope="user:1", key="key-0001", fingerprint="fp", operation=op, adapter=ORDER)
    other = await guard.run(
        scope="user:2", key="key-0001", fingerprint="fp", operation=op, adapter=ORDER
    )

    assert (op.calls, other.replayed) == (2, False)


async def test_stored_results_expire(redis: Redis) -> None:
    guard, op = IdempotencyGuard(redis, result_ttl_s=0.1), CreateOrder()
    await _run(guard, op)
    await asyncio.sleep(0.2)

    outcome = await _run(guard, op)

    assert (op.calls, outcome.replayed) == (2, False)


async def test_owner_that_outlived_its_lock_does_not_overwrite_new_owner(redis: Redis) -> None:
    guard = IdempotencyGuard(redis, lock_ttl_s=0.05)
    stale = asyncio.create_task(_run(guard, CreateOrder(delay=0.15, total_paise=1)))
    await asyncio.sleep(0.1)  # stale owner's lock has expired; a retry takes over
    fresh = asyncio.create_task(
        _run(IdempotencyGuard(redis, lock_ttl_s=5), CreateOrder(delay=0.2, total_paise=2))
    )
    await stale  # finishes first, but no longer owns the key

    fresh_result = await fresh
    replay = await _run(IdempotencyGuard(redis), CreateOrder())

    assert replay.replayed is True
    assert replay.value == fresh_result.value
    assert replay.value.total_paise == 2


async def test_redis_outage_fails_closed() -> None:
    down = create_redis(make_settings(redis_url=UNREACHABLE_REDIS, redis_timeout_s=0.2))
    op = CreateOrder()
    try:
        with pytest.raises(ServiceUnavailableError):
            await _run(IdempotencyGuard(down), op)
    finally:
        await down.aclose()

    assert op.calls == 0  # never run a side effect we can't protect
