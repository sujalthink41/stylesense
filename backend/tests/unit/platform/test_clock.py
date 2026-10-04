from datetime import UTC, timedelta

from stylesense.platform.clock import Clock, SystemClock
from tests.fakes.clock import FixedClock


def test_system_clock_returns_timezone_aware_utc() -> None:
    now = SystemClock().now()

    assert now.tzinfo is UTC


def test_fixed_clock_satisfies_clock_protocol_and_advances() -> None:
    clock: Clock = FixedClock()
    start = clock.now()

    assert isinstance(clock, FixedClock)
    clock.advance(timedelta(minutes=5))

    assert clock.now() - start == timedelta(minutes=5)
