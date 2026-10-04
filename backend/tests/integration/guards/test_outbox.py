import asyncio
import uuid
from collections import Counter
from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from stylesense.guards.outbox import (
    OutboxEnvelope,
    OutboxMessage,
    OutboxRelay,
    OutboxWriter,
)
from stylesense.infra.database import UnitOfWork, create_session_factory
from tests.fakes.clock import FixedClock


class Recorder:
    def __init__(self, fail_times: int = 0, delay: float = 0) -> None:
        self.seen: list[uuid.UUID] = []
        self._fail_times = fail_times
        self._delay = delay

    async def __call__(self, envelope: OutboxEnvelope) -> None:
        await asyncio.sleep(self._delay)
        if self._fail_times > 0:
            self._fail_times -= 1
            raise ConnectionError("push provider down")
        self.seen.append(envelope.id)


@pytest.fixture
async def sessions(engine: AsyncEngine, migrated: None) -> async_sessionmaker[AsyncSession]:
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE outbox_messages"))
    return create_session_factory(engine)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


def _relay(
    sessions: async_sessionmaker[AsyncSession],
    clock: FixedClock,
    handlers: dict[str, Recorder],
    **kwargs: object,
) -> OutboxRelay:
    return OutboxRelay(sessions, handlers, clock=clock, jitter=lambda: 0.0, **kwargs)  # type: ignore[arg-type]


async def _add(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock, n: int = 1, **kwargs: object
) -> None:
    writer = OutboxWriter(clock)
    async with UnitOfWork(sessions) as uow:
        for i in range(n):
            await writer.add(uow.session, "push.send", {"n": i}, **kwargs)  # type: ignore[arg-type]


async def _messages(sessions: async_sessionmaker[AsyncSession]) -> list[OutboxMessage]:
    async with sessions() as session:
        return list((await session.scalars(select(OutboxMessage))).all())


async def test_message_is_written_atomically_with_the_business_change(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    async def fail_after_writing() -> None:
        async with UnitOfWork(sessions) as uow:
            await OutboxWriter(clock).add(uow.session, "push.send", {"n": 1})
            raise RuntimeError("business change failed")

    with pytest.raises(RuntimeError):
        await fail_after_writing()

    assert await _messages(sessions) == []


async def test_dedupe_key_prevents_duplicate_messages(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    writer = OutboxWriter(clock)
    async with UnitOfWork(sessions) as uow:
        first = await writer.add(uow.session, "push.send", {}, dedupe_key="price_drop:a1:s9")
        second = await writer.add(uow.session, "push.send", {}, dedupe_key="price_drop:a1:s9")

    assert (first, second) == (True, False)
    assert len(await _messages(sessions)) == 1


async def test_relay_delivers_and_marks_done(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    handler = Recorder()
    await _add(sessions, clock, n=3)

    processed = await _relay(sessions, clock, {"push.send": handler}).run_batch()

    assert processed == 3
    assert len(handler.seen) == 3
    assert {m.status for m in await _messages(sessions)} == {"done"}


async def test_failure_is_retried_later_with_backoff(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    handler = Recorder(fail_times=1)
    relay = _relay(sessions, clock, {"push.send": handler}, base_backoff_s=10)
    await _add(sessions, clock)

    await relay.run_batch()
    [msg] = await _messages(sessions)
    assert (msg.status, msg.attempts, msg.last_error) == (
        "pending",
        1,
        "ConnectionError: push provider down",
    )
    assert msg.available_at == clock.now() + timedelta(seconds=10)

    assert await relay.run_batch() == 0  # not due yet
    clock.advance(timedelta(seconds=10))
    assert await relay.run_batch() == 1
    assert len(handler.seen) == 1


async def test_backoff_grows_exponentially_up_to_a_cap(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    relay = _relay(
        sessions, clock, {"push.send": Recorder(fail_times=10)}, base_backoff_s=1, max_backoff_s=4
    )
    await _add(sessions, clock)
    delays = []

    for _ in range(4):
        await relay.run_batch()
        [msg] = await _messages(sessions)
        delays.append((msg.available_at - clock.now()).total_seconds())
        clock.advance(timedelta(seconds=10))

    assert delays == [1, 2, 4, 4]


async def test_gives_up_after_max_attempts(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    relay = _relay(
        sessions, clock, {"push.send": Recorder(fail_times=99)}, max_attempts=3, base_backoff_s=1
    )
    await _add(sessions, clock)

    for _ in range(5):
        await relay.run_batch()
        clock.advance(timedelta(minutes=5))

    [msg] = await _messages(sessions)
    assert (msg.status, msg.attempts) == ("dead", 3)


async def test_unknown_topic_is_dead_lettered_immediately(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    await _add(sessions, clock)

    await _relay(sessions, clock, {}).run_batch()

    [msg] = await _messages(sessions)
    assert (msg.status, msg.last_error) == ("dead", "no handler for topic 'push.send'")


async def test_slow_handler_times_out_and_is_retried(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    relay = _relay(sessions, clock, {"push.send": Recorder(delay=1)}, handler_timeout_s=0.05)
    await _add(sessions, clock)

    await relay.run_batch()

    [msg] = await _messages(sessions)
    assert (msg.status, msg.last_error) == ("pending", "TimeoutError")


async def test_delayed_message_waits_until_due(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    handler = Recorder()
    relay = _relay(sessions, clock, {"push.send": handler})
    await _add(sessions, clock, delay=timedelta(minutes=5))

    assert await relay.run_batch() == 0
    clock.advance(timedelta(minutes=5))
    assert await relay.run_batch() == 1


async def test_batch_size_bounds_one_run(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    await _add(sessions, clock, n=5)

    assert await _relay(sessions, clock, {"push.send": Recorder()}, batch_size=2).run_batch() == 2


async def test_parallel_relays_deliver_each_message_exactly_once(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    handler = Recorder(delay=0.005)
    await _add(sessions, clock, n=40)
    relays = [_relay(sessions, clock, {"push.send": handler}, batch_size=100) for _ in range(4)]

    await asyncio.gather(*(r.run_batch() for r in relays))

    assert len(handler.seen) == 40
    assert max(Counter(handler.seen).values()) == 1
    assert {m.status for m in await _messages(sessions)} == {"done"}


async def test_pending_count(sessions: async_sessionmaker[AsyncSession], clock: FixedClock) -> None:
    await _add(sessions, clock, n=3)

    assert await _relay(sessions, clock, {}).pending_count() == 3
