import asyncio
from collections.abc import Awaitable, Callable


class SingleFlight[T]:
    """Coalesce concurrent calls with the same key into one execution (per process).

    Not a cache: once the shared call finishes, the next call runs again.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[T]] = {}

    @property
    def in_flight(self) -> int:
        return len(self._tasks)

    async def do(self, key: str, fn: Callable[[], Awaitable[T]]) -> T:
        task = self._tasks.get(key)
        if task is None:
            task = asyncio.ensure_future(fn())
            self._tasks[key] = task
            task.add_done_callback(lambda _: self._tasks.pop(key, None))
        # Shield: one caller cancelling must not cancel the work others are waiting on.
        return await asyncio.shield(task)
