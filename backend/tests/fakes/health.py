import asyncio


class StubHealthCheck:
    """Health check whose outcome is scripted: ok, raise, or hang."""

    def __init__(self, name: str, *, error: Exception | None = None, hang: bool = False) -> None:
        self.name = name
        self._error = error
        self._hang = hang
        self.calls = 0

    async def check(self) -> None:
        self.calls += 1
        if self._hang:
            await asyncio.Event().wait()
        if self._error is not None:
            raise self._error
