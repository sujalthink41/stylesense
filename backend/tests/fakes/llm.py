import asyncio
from collections import defaultdict, deque
from collections.abc import Sequence

from stylesense.ai.gateway.types import ChatCall, ChatOutput, Usage

Scripted = ChatOutput | Exception | float  # float = hang for that many seconds


class FakeChatProvider:
    """Scriptable provider: queue outcomes per model; records every call it receives."""

    def __init__(self, name: str = "fake") -> None:
        self.name = name
        self.calls: list[tuple[str, ChatCall]] = []
        self._scripts: dict[str, deque[Scripted]] = defaultdict(deque)
        self._default: dict[str, ChatOutput] = {}

    def reply(
        self, model: str, text: str, *, input_tokens: int = 1_000, output_tokens: int = 100
    ) -> None:
        self._scripts[model].append(ChatOutput(text, Usage(input_tokens, 0, output_tokens)))

    def fail(self, model: str, error: Exception, times: int = 1) -> None:
        for _ in range(times):
            self._scripts[model].append(error)

    def hang(self, model: str, seconds: float) -> None:
        self._scripts[model].append(seconds)

    def always(self, model: str, text: str) -> None:
        self._default[model] = ChatOutput(text, Usage(1_000, 0, 100))

    def calls_to(self, model: str) -> int:
        return sum(1 for m, _ in self.calls if m == model)

    async def chat(self, model: str, call: ChatCall) -> ChatOutput:
        self.calls.append((model, call))
        await asyncio.sleep(0)
        script = self._scripts[model]
        if not script:
            if model in self._default:
                return self._default[model]
            raise AssertionError(f"no scripted reply for {model}")
        outcome = script.popleft()
        if isinstance(outcome, float):
            await asyncio.sleep(outcome)
            raise AssertionError("hung call should have timed out")  # noqa: TRY004
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeEmbeddingProvider:
    def __init__(self, name: str = "fake", dimensions: int = 1536) -> None:
        self.name = name
        self.dimensions = dimensions
        self.calls = 0
        self.error: Exception | None = None

    async def embed(
        self, model: str, texts: Sequence[str], *, timeout_s: float
    ) -> tuple[list[list[float]], Usage]:
        self.calls += 1
        if self.error:
            raise self.error
        vectors = [
            [1.0 if i == len(t) % self.dimensions else 0.0 for i in range(self.dimensions)]
            for t in texts
        ]
        return vectors, Usage(input_tokens=sum(len(t) for t in texts))


class RecordingSleep:
    """Replaces asyncio.sleep in retry backoff so tests run instantly and can assert delays."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)
