import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from stylesense.platform.errors import ServiceUnavailableError


class BulkheadFullError(ServiceUnavailableError):
    code = "capacity_exceeded"
    title = "Too busy, retry shortly"


class Bulkhead:
    """Caps concurrent work of one kind so it can't starve everything else.

    Excess callers queue (bounded) and are shed with 503 + Retry-After instead of piling up.
    """

    def __init__(
        self,
        name: str,
        *,
        max_concurrent: int,
        max_waiting: int,
        wait_timeout_s: float = 5.0,
        retry_after_s: int = 2,
    ) -> None:
        if max_concurrent < 1 or max_waiting < 0 or wait_timeout_s <= 0:
            raise ValueError("invalid bulkhead limits")
        self.name = name
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_waiting = max_waiting
        self._wait_timeout_s = wait_timeout_s
        self._retry_after_s = retry_after_s
        self.active = 0
        self.waiting = 0

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        await self._acquire()
        self.active += 1
        try:
            yield
        finally:
            self.active -= 1
            self._semaphore.release()

    async def _acquire(self) -> None:
        if not self._semaphore.locked():
            await self._semaphore.acquire()
            return
        if self.waiting >= self._max_waiting:
            raise self._full()
        self.waiting += 1
        try:
            async with asyncio.timeout(self._wait_timeout_s):
                await self._semaphore.acquire()
        except TimeoutError:
            raise self._full() from None
        finally:
            self.waiting -= 1

    def _full(self) -> BulkheadFullError:
        return BulkheadFullError(f"{self.name} is at capacity", retry_after_s=self._retry_after_s)
