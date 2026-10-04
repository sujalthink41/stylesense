import asyncio

import pytest
from redis.asyncio import Redis

from stylesense.guards.locks import LockManager, LockNotAcquiredError


async def test_only_one_holder_at_a_time_across_instances(redis: Redis, other_redis: Redis) -> None:
    first, second = LockManager(redis), LockManager(other_redis)

    async with first.hold("cron:feed", ttl_s=5):
        with pytest.raises(LockNotAcquiredError):
            async with second.hold("cron:feed", ttl_s=5):
                pass


async def test_lock_is_released_after_the_block(redis: Redis) -> None:
    locks = LockManager(redis)

    async with locks.hold("job", ttl_s=5):
        pass

    async with locks.hold("job", ttl_s=5):
        pass


async def test_lock_is_released_when_the_block_fails(redis: Redis) -> None:
    locks = LockManager(redis)

    with pytest.raises(RuntimeError):
        async with locks.hold("job", ttl_s=5):
            raise RuntimeError

    async with locks.hold("job", ttl_s=5):
        pass


async def test_expired_lock_can_be_taken_and_old_owner_cannot_release_it(
    redis: Redis, other_redis: Redis
) -> None:
    stale = await LockManager(redis).acquire("job", ttl_s=0.05)
    assert stale is not None
    await asyncio.sleep(0.1)

    fresh = await LockManager(other_redis).acquire("job", ttl_s=5)
    assert fresh is not None

    assert await stale.release() is False  # must not delete the new owner's lock
    assert await redis.exists("lock:job") == 1


async def test_owner_can_extend_but_others_cannot(redis: Redis, other_redis: Redis) -> None:
    lock = await LockManager(redis).acquire("job", ttl_s=0.2)
    assert lock is not None

    assert await lock.extend(5) is True
    await asyncio.sleep(0.3)
    assert await LockManager(other_redis).acquire("job", ttl_s=5) is None


async def test_waits_for_lock_up_to_a_limit(redis: Redis, other_redis: Redis) -> None:
    holder = await LockManager(redis).acquire("job", ttl_s=0.1)
    assert holder is not None

    waited = await LockManager(other_redis).acquire("job", ttl_s=5, wait_s=0.5)

    assert waited is not None


async def test_wait_gives_up_after_limit(redis: Redis, other_redis: Redis) -> None:
    assert await LockManager(redis).acquire("job", ttl_s=5) is not None

    assert await LockManager(other_redis).acquire("job", ttl_s=5, wait_s=0.1) is None


async def test_concurrent_contenders_produce_exactly_one_winner(
    redis: Redis, other_redis: Redis
) -> None:
    managers = [LockManager(redis), LockManager(other_redis)] * 5

    results = await asyncio.gather(*(m.acquire("job", ttl_s=5) for m in managers))

    assert sum(r is not None for r in results) == 1


async def test_rejects_non_positive_ttl(redis: Redis) -> None:
    with pytest.raises(ValueError, match="ttl"):
        await LockManager(redis).acquire("job", ttl_s=0)
