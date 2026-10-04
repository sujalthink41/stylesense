from typing import Any

import pytest
from pydantic import TypeAdapter
from redis.exceptions import ConnectionError as RedisConnectionError

from stylesense.guards.idempotency import IdempotencyGuard, IdempotencyInProgressError

INT = TypeAdapter(int)


class ScriptedRedis:
    """Just enough of the Redis API to force rare races and partial outages."""

    def __init__(
        self, *, claim: bool, existing: str | None = None, eval_fails: bool = False
    ) -> None:
        self._claim = claim
        self._existing = existing
        self._eval_fails = eval_fails

    async def set(self, *_: Any, **__: Any) -> bool:
        return self._claim

    async def get(self, _key: str) -> str | None:
        return self._existing

    async def eval(self, *_: Any) -> int:
        if self._eval_fails:
            raise RedisConnectionError("connection reset")
        return 1


async def _answer() -> int:
    return 42


async def test_key_vanishing_between_claim_and_read_is_treated_as_in_progress() -> None:
    guard = IdempotencyGuard(ScriptedRedis(claim=False, existing=None))  # type: ignore[arg-type]

    with pytest.raises(IdempotencyInProgressError):
        await guard.run(scope="s", key="key-0001", fingerprint="fp", operation=_answer, adapter=INT)


async def test_result_store_failure_after_success_still_returns_the_result() -> None:
    guard = IdempotencyGuard(ScriptedRedis(claim=True, eval_fails=True))  # type: ignore[arg-type]

    outcome = await guard.run(
        scope="s", key="key-0001", fingerprint="fp", operation=_answer, adapter=INT
    )

    assert (outcome.value, outcome.replayed) == (42, False)
