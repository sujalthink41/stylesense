from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Time source; inject it instead of calling datetime.now() directly."""

    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
