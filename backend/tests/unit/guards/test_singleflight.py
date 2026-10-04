import asyncio

import pytest

from stylesense.guards.singleflight import SingleFlight


class Counter:
    def __init__(self, delay: float = 0.05, error: Exception | None = None) -> None:
        self.calls = 0
        self._delay = delay
        self._error = error

    async def __call__(self) -> str:
        self.calls += 1
        await asyncio.sleep(self._delay)
        if self._error:
            raise self._error
        return f"result-{self.calls}"


async def test_concurrent_callers_share_one_execution() -> None:
    flight: SingleFlight[str] = SingleFlight()
    work = Counter()

    results = await asyncio.gather(*(flight.do("k", work) for _ in range(10)))

    assert work.calls == 1
    assert set(results) == {"result-1"}


async def test_different_keys_run_independently() -> None:
    flight: SingleFlight[str] = SingleFlight()
    work = Counter()

    await asyncio.gather(flight.do("a", work), flight.do("b", work))

    assert work.calls == 2


async def test_sequential_calls_are_not_cached() -> None:
    flight: SingleFlight[str] = SingleFlight()
    work = Counter(delay=0)

    first = await flight.do("k", work)
    second = await flight.do("k", work)

    assert (first, second) == ("result-1", "result-2")


async def test_error_reaches_every_waiter_and_is_not_cached() -> None:
    flight: SingleFlight[str] = SingleFlight()
    failing = Counter(error=ValueError("boom"))

    results = await asyncio.gather(
        *(flight.do("k", failing) for _ in range(3)), return_exceptions=True
    )

    assert failing.calls == 1
    assert all(isinstance(r, ValueError) for r in results)
    assert await flight.do("k", Counter(delay=0)) == "result-1"


async def test_cancelling_one_waiter_does_not_cancel_the_shared_work() -> None:
    flight: SingleFlight[str] = SingleFlight()
    work = Counter(delay=0.1)

    impatient = asyncio.create_task(flight.do("k", work))
    patient = asyncio.create_task(flight.do("k", work))
    await asyncio.sleep(0.01)
    impatient.cancel()

    assert await patient == "result-1"
    with pytest.raises(asyncio.CancelledError):
        await impatient


async def test_key_is_released_after_completion() -> None:
    flight: SingleFlight[str] = SingleFlight()

    await flight.do("k", Counter(delay=0))

    assert flight.in_flight == 0
