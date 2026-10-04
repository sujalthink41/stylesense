import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

import structlog
from prometheus_client import CollectorRegistry, Counter, Histogram

from stylesense.guards.locks import LockManager

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PeriodicTask:
    """`run` returns True when more work is waiting, so the loop continues without sleeping."""

    name: str
    interval_s: float
    run: Callable[[], Awaitable[bool]]
    exclusive: bool = False  # cron-style: at most one instance across all workers

    def __post_init__(self) -> None:
        if self.interval_s <= 0:
            raise ValueError("interval_s must be positive")


class _Metrics:
    def __init__(self, registry: CollectorRegistry | None) -> None:
        registry = registry or CollectorRegistry()
        self.runs = Counter(
            "worker_task_runs", "Worker task iterations", ["task", "outcome"], registry=registry
        )
        self.duration = Histogram(
            "worker_task_duration_seconds",
            "Worker task iteration time",
            ["task"],
            registry=registry,
        )


class Worker:
    def __init__(
        self,
        tasks: Sequence[PeriodicTask],
        *,
        locks: LockManager | None,
        heartbeat: Callable[[], None] | None = None,
        registry: CollectorRegistry | None = None,
        shutdown_grace_s: float = 20,
    ) -> None:
        if locks is None and any(t.exclusive for t in tasks):
            raise ValueError("exclusive tasks need locks")
        self._tasks = tasks
        self._locks = locks
        self._heartbeat = heartbeat
        self._metrics = _Metrics(registry)
        self._grace_s = shutdown_grace_s

    async def run(self, stop: asyncio.Event) -> None:
        loops = [asyncio.create_task(self._loop(t, stop), name=t.name) for t in self._tasks]
        await stop.wait()
        # Graceful: let in-flight iterations finish, then cancel anything still stuck.
        _, stuck = await asyncio.wait(loops, timeout=self._grace_s)
        for task in stuck:
            logger.warning("worker_task_cancelled_on_shutdown", task=task.get_name())
            task.cancel()
        await asyncio.gather(*stuck, return_exceptions=True)

    async def _loop(self, task: PeriodicTask, stop: asyncio.Event) -> None:
        while not stop.is_set():
            more = await self._iterate(task)
            if more:
                await asyncio.sleep(0)  # yield, then keep draining
                continue
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=task.interval_s)

    async def _iterate(self, task: PeriodicTask) -> bool:
        started = time.perf_counter()
        try:
            if task.exclusive:
                more = await self._run_exclusive(task)
            else:
                more = await task.run()
        except Exception:
            logger.exception("worker_task_failed", task=task.name)
            self._metrics.runs.labels(task.name, "error").inc()
            return False
        self._metrics.runs.labels(task.name, "ok").inc()
        self._metrics.duration.labels(task.name).observe(time.perf_counter() - started)
        if self._heartbeat:
            self._heartbeat()
        return more

    async def _run_exclusive(self, task: PeriodicTask) -> bool:
        assert self._locks is not None  # noqa: S101  # guaranteed by __init__
        # TTL outlives a normal run but frees the lock soon if this worker dies mid-run.
        lock = await self._locks.acquire(f"task:{task.name}", ttl_s=max(30, task.interval_s * 2))
        if lock is None:
            return False  # another worker is on it
        try:
            return await task.run()
        finally:
            await lock.release()
