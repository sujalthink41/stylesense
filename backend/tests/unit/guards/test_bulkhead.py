import asyncio

import pytest

from stylesense.guards.bulkhead import Bulkhead, BulkheadFullError


async def _hold(bulkhead: Bulkhead, release: asyncio.Event) -> None:
    async with bulkhead.slot():
        await release.wait()


async def test_allows_up_to_capacity_concurrently() -> None:
    bulkhead = Bulkhead("llm", max_concurrent=2, max_waiting=0)
    release = asyncio.Event()

    tasks = [asyncio.create_task(_hold(bulkhead, release)) for _ in range(2)]
    await asyncio.sleep(0)

    assert bulkhead.active == 2
    release.set()
    await asyncio.gather(*tasks)
    assert bulkhead.active == 0


async def test_rejects_immediately_when_full_and_no_queue() -> None:
    bulkhead = Bulkhead("llm", max_concurrent=1, max_waiting=0, retry_after_s=3)
    release = asyncio.Event()
    holder = asyncio.create_task(_hold(bulkhead, release))
    await asyncio.sleep(0)

    with pytest.raises(BulkheadFullError) as err:
        async with bulkhead.slot():
            pass

    assert err.value.status_code == 503
    assert err.value.headers["Retry-After"] == "3"
    release.set()
    await holder


async def test_queues_up_to_max_waiting_then_rejects() -> None:
    bulkhead = Bulkhead("llm", max_concurrent=1, max_waiting=1)
    release = asyncio.Event()
    holder = asyncio.create_task(_hold(bulkhead, release))
    await asyncio.sleep(0)
    waiter = asyncio.create_task(_hold(bulkhead, release))
    await asyncio.sleep(0)

    assert bulkhead.waiting == 1
    with pytest.raises(BulkheadFullError):
        async with bulkhead.slot():
            pass

    release.set()
    await asyncio.gather(holder, waiter)
    assert (bulkhead.active, bulkhead.waiting) == (0, 0)


async def test_waiter_gives_up_after_timeout() -> None:
    bulkhead = Bulkhead("llm", max_concurrent=1, max_waiting=5, wait_timeout_s=0.02)
    release = asyncio.Event()
    holder = asyncio.create_task(_hold(bulkhead, release))
    await asyncio.sleep(0)

    with pytest.raises(BulkheadFullError):
        async with bulkhead.slot():
            pass

    assert bulkhead.waiting == 0
    release.set()
    await holder


async def test_slot_is_released_when_work_fails() -> None:
    bulkhead = Bulkhead("llm", max_concurrent=1, max_waiting=0)

    with pytest.raises(RuntimeError):
        async with bulkhead.slot():
            raise RuntimeError

    async with bulkhead.slot():
        assert bulkhead.active == 1


async def test_cancelled_waiter_frees_its_queue_place() -> None:
    bulkhead = Bulkhead("llm", max_concurrent=1, max_waiting=1)
    release = asyncio.Event()
    holder = asyncio.create_task(_hold(bulkhead, release))
    await asyncio.sleep(0)
    waiter = asyncio.create_task(_hold(bulkhead, release))
    await asyncio.sleep(0)

    waiter.cancel()
    await asyncio.gather(waiter, return_exceptions=True)

    assert bulkhead.waiting == 0
    release.set()
    await holder


@pytest.mark.parametrize(
    ("concurrent", "waiting", "timeout"), [(0, 0, 1.0), (1, -1, 1.0), (1, 0, 0.0)]
)
def test_rejects_invalid_configuration(concurrent: int, waiting: int, timeout: float) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        Bulkhead("x", max_concurrent=concurrent, max_waiting=waiting, wait_timeout_s=timeout)
