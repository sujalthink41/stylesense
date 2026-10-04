"""Distributed locks on Redis: one holder across all instances, safe expiry, owner-only release."""

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis

from stylesense.platform.errors import ConflictError

# Compare-and-act scripts: only the token that took the lock may release or extend it.
_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""
_EXTEND = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('PEXPIRE', KEYS[1], ARGV[2]) end
return 0
"""

_POLL_S = 0.02


class LockNotAcquiredError(ConflictError):
    code = "lock_not_acquired"
    title = "Resource is busy"


class Lock:
    def __init__(self, redis: Redis, key: str, token: str) -> None:
        self._redis = redis
        self.key = key
        self._token = token

    async def release(self) -> bool:
        return bool(await self._redis.eval(_RELEASE, 1, self.key, self._token))

    async def extend(self, ttl_s: float) -> bool:
        ttl_ms = _to_ms(ttl_s)
        return bool(await self._redis.eval(_EXTEND, 1, self.key, self._token, ttl_ms))


class LockManager:
    """Locks expire after `ttl_s` so a crashed holder can't block others forever.

    Keep the protected work shorter than the TTL, or `extend` it while working.
    """

    def __init__(self, redis: Redis, *, prefix: str = "lock:") -> None:
        self._redis = redis
        self._prefix = prefix

    async def acquire(self, name: str, *, ttl_s: float, wait_s: float = 0) -> Lock | None:
        key = f"{self._prefix}{name}"
        token = uuid.uuid4().hex
        ttl_ms = _to_ms(ttl_s)
        deadline = time.monotonic() + wait_s
        while True:
            if await self._redis.set(key, token, nx=True, px=ttl_ms):
                return Lock(self._redis, key, token)
            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(_POLL_S)

    @asynccontextmanager
    async def hold(self, name: str, *, ttl_s: float, wait_s: float = 0) -> AsyncIterator[Lock]:
        lock = await self.acquire(name, ttl_s=ttl_s, wait_s=wait_s)
        if lock is None:
            raise LockNotAcquiredError(f"lock '{name}' is held by another worker")
        try:
            yield lock
        finally:
            await lock.release()


def _to_ms(seconds: float) -> int:
    if seconds <= 0:
        raise ValueError("ttl must be positive")
    return max(1, round(seconds * 1000))
