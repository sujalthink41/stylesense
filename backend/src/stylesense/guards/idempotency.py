"""Idempotency keys: a retried or double-submitted request runs its side effect at most once.

Flow per (scope, key):
  absent   → claim it as `pending` (SET NX), run the operation, store the result as `done`
  pending  → 409 + Retry-After (same request still running) or 422 (different request)
  done     → replay the stored result (same request) or 422 (key reused for another request)
"""

import hashlib
import json
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import structlog
from pydantic import TypeAdapter
from redis.asyncio import Redis
from redis.exceptions import RedisError

from stylesense.platform.errors import AppError, ConflictError, ServiceUnavailableError

logger = structlog.get_logger(__name__)

_VALID_KEY = re.compile(r"[A-Za-z0-9_-]{8,128}")

# Store the result only if this attempt still owns the key (its lock may have expired).
_COMPLETE = """
local current = redis.call('GET', KEYS[1])
if not current then return 0 end
if cjson.decode(current)['owner'] ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[1], ARGV[2], 'PX', ARGV[3])
return 1
"""
_RELEASE = """
local current = redis.call('GET', KEYS[1])
if current and cjson.decode(current)['owner'] == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""


class InvalidIdempotencyKeyError(AppError):
    status_code = 400
    code = "invalid_idempotency_key"
    title = "Idempotency-Key must be 8-128 characters of A-Z, a-z, 0-9, '_' or '-'"


class IdempotencyKeyReusedError(AppError):
    status_code = 422
    code = "idempotency_key_reused"
    title = "Idempotency-Key was already used for a different request"


class IdempotencyInProgressError(ConflictError):
    code = "request_in_progress"
    title = "The original request is still being processed"

    def __init__(self) -> None:
        super().__init__(headers={"Retry-After": "1"})


@dataclass(frozen=True, slots=True)
class IdempotentOutcome[T]:
    value: T
    replayed: bool


def validate_key(key: str) -> str:
    if not _VALID_KEY.fullmatch(key):
        raise InvalidIdempotencyKeyError
    return key


def fingerprint(*parts: str | bytes) -> str:
    """Stable hash of what the request *is*, to detect a key reused for a different request."""
    digest = hashlib.sha256()
    for part in parts:
        data = part.encode() if isinstance(part, str) else part
        digest.update(len(data).to_bytes(8, "big"))  # length prefix: ("ab","c") != ("a","bc")
        digest.update(data)
    return digest.hexdigest()


class IdempotencyGuard:
    def __init__(
        self,
        redis: Redis,
        *,
        lock_ttl_s: float = 60,
        result_ttl_s: float = 86_400,
        prefix: str = "idem:",
    ) -> None:
        self._redis = redis
        self._lock_ttl_ms = round(lock_ttl_s * 1000)
        self._result_ttl_ms = round(result_ttl_s * 1000)
        self._prefix = prefix

    async def run[T](
        self,
        *,
        scope: str,
        key: str,
        fingerprint: str,
        operation: Callable[[], Awaitable[T]],
        adapter: TypeAdapter[T],
    ) -> IdempotentOutcome[T]:
        redis_key = f"{self._prefix}{scope}:{validate_key(key)}"
        owner = uuid.uuid4().hex
        pending = json.dumps({"state": "pending", "owner": owner, "fp": fingerprint})
        try:
            claimed = await self._redis.set(redis_key, pending, nx=True, px=self._lock_ttl_ms)
            if not claimed:
                return self._existing(await self._redis.get(redis_key), fingerprint, adapter)
        except RedisError as exc:
            # Fail closed: running a side effect we can't deduplicate is worse than a 503.
            raise ServiceUnavailableError("idempotency store unavailable", retry_after_s=1) from exc

        try:
            value = await operation()
        except BaseException:
            await self._safe_eval(_RELEASE, redis_key, owner)
            raise

        done = json.dumps(
            {
                "state": "done",
                "owner": owner,
                "fp": fingerprint,
                "result": adapter.dump_python(value, mode="json"),
            }
        )
        if not await self._safe_eval(_COMPLETE, redis_key, owner, done, self._result_ttl_ms):
            logger.warning("idempotency_ownership_lost", scope=scope)
        return IdempotentOutcome(value=value, replayed=False)

    @staticmethod
    def _existing[T](
        raw: str | bytes | None, fingerprint: str, adapter: TypeAdapter[T]
    ) -> IdempotentOutcome[T]:
        if raw is None:  # expired between SET NX and GET: treat as still in flight
            raise IdempotencyInProgressError
        record = json.loads(raw)
        if record["fp"] != fingerprint:
            raise IdempotencyKeyReusedError
        if record["state"] == "pending":
            raise IdempotencyInProgressError
        return IdempotentOutcome(value=adapter.validate_python(record["result"]), replayed=True)

    async def _safe_eval(self, script: str, key: str, *args: str | int) -> bool:
        # The operation already happened; a cache hiccup here must not turn success into an error.
        try:
            return bool(await self._redis.eval(script, 1, key, *args))
        except RedisError as exc:
            logger.warning("idempotency_store_write_failed", error=type(exc).__name__)
            return False
