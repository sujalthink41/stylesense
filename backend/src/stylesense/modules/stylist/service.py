"""Turn engine: validate → claim turn (CAS) → run flow in the background → stream → persist.

The flow runs in its own task and talks to the HTTP stream through a queue, so a client that
disconnects mid-stream never aborts or corrupts a turn; it resumes from the snapshot.
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator, Callable, Mapping
from datetime import timedelta
from typing import Any

import structlog

from stylesense.genui.actions import ActionRequest, Restart
from stylesense.genui.components import (
    InfoBanner,
    InfoBannerProps,
    Suggestion,
    SuggestionBar,
    SuggestionBarProps,
)
from stylesense.genui.envelope import (
    DoneEvent,
    ErrorEvent,
    LoadingEvent,
    RenderEvent,
    UiEnvelope,
    UiEvent,
)
from stylesense.genui.validation import validate_action
from stylesense.genui.versioning import adapt
from stylesense.infra.database import UnitOfWork
from stylesense.modules.stylist.exceptions import (
    SessionBusyError,
    SessionEndedError,
    SessionNotFoundError,
    StaleTurnError,
)
from stylesense.modules.stylist.flows.base import Entry, Flow, Progress, Rendered, TurnContext
from stylesense.modules.stylist.models import SessionEvent, StylistSession
from stylesense.modules.stylist.repository import StylistRepository
from stylesense.modules.stylist.schemas import SessionCreate, SessionView
from stylesense.platform.clock import Clock
from stylesense.platform.ids import new_id

logger = structlog.get_logger(__name__)

_FAILURE_PROBLEM = {
    "type": "/problems/turn_failed",
    "title": "Something went wrong on our side",
    "status": 500,
    "code": "turn_failed",
}


class StylistService:
    def __init__(
        self,
        uow: Callable[[], UnitOfWork],
        *,
        flows: Mapping[str, Flow],
        default_flow: str,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._flows = flows
        self._default_flow = default_flow
        self._clock = clock
        self._turns: set[asyncio.Task[None]] = set()

    async def start(
        self, user_id: uuid.UUID, request: SessionCreate, *, client_version: int
    ) -> SessionView:
        flow = self._flows[self._default_flow]
        session_id = new_id()
        rendered = await flow.start(
            TurnContext(session_id, user_id, turn_id=1), Entry(request.entry, request.value)
        )
        envelope = UiEnvelope(session_id=session_id, turn_id=1, components=rendered.components)
        now = self._clock.now()
        async with self._uow() as uow:
            repo = StylistRepository(uow.session)
            repo.add(
                StylistSession(
                    id=session_id,
                    user_id=user_id,
                    flow=flow.name,
                    entry=request.entry,
                    status="active",
                    turn_id=1,
                    state=rendered.state,
                    envelope=envelope.model_dump(mode="json"),
                    last_activity_at=now,
                )
            )
            await repo.flush()  # the event row references the session: insert the session first
            repo.add(_event(session_id, 1, "render", envelope.model_dump(mode="json")))
        logger.info("stylist_session_started", session_id=str(session_id), entry=request.entry)
        return SessionView(
            session_id=session_id, turn_id=1, status="active", ui=adapt(envelope, client_version)
        )

    async def snapshot(
        self, session_id: uuid.UUID, user_id: uuid.UUID, *, client_version: int
    ) -> SessionView:
        session = await self._load(session_id, user_id)
        envelope = UiEnvelope.model_validate(session.envelope)
        return SessionView(
            session_id=session.id,
            turn_id=envelope.turn_id,
            status=session.status,
            ui=adapt(envelope, client_version),
        )

    async def act(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        request: ActionRequest,
        *,
        client_version: int,
    ) -> AsyncGenerator[UiEvent]:
        """Raises 404/409/422 *before* any event, so the API can answer with a proper status."""
        session = await self._load(session_id, user_id)
        self._check_turn(session, request.turn_id)
        screen = UiEnvelope.model_validate(session.envelope)
        validate_action(screen, request.action)

        async with self._uow() as uow:
            claimed = await StylistRepository(uow.session).claim_turn(
                session_id, user_id, request.turn_id, self._clock.now()
            )
        if claimed is None:  # lost a race with a concurrent action on the same turn
            self._check_turn(await self._load(session_id, user_id), request.turn_id)
            raise StaleTurnError(current_turn=request.turn_id + 1)

        events: asyncio.Queue[UiEvent] = asyncio.Queue()
        ctx = TurnContext(session_id, user_id, turn_id=claimed.turn_id)
        task = asyncio.create_task(
            self._run_turn(
                session=claimed,
                ctx=ctx,
                screen=screen,
                request=request,
                client_version=client_version,
                events=events,
            ),
            name=f"stylist-turn-{session_id}-{ctx.turn_id}",
        )
        self._turns.add(task)
        task.add_done_callback(self._turns.discard)
        return _drain(events)

    async def prune_events(self, *, older_than: timedelta) -> int:
        async with self._uow() as uow:
            return await StylistRepository(uow.session).prune_events(self._clock.now() - older_than)

    async def wait_for_turns(self) -> None:
        """Let in-flight turns finish (graceful shutdown, tests)."""
        if self._turns:
            await asyncio.gather(*self._turns, return_exceptions=True)

    async def _run_turn(
        self,
        *,
        session: StylistSession,
        ctx: TurnContext,
        screen: UiEnvelope,
        request: ActionRequest,
        client_version: int,
        events: asyncio.Queue[UiEvent],
    ) -> None:
        log = logger.bind(
            session_id=str(ctx.session_id), turn_id=ctx.turn_id, action=request.action.type
        )
        flow = self._flows[session.flow]
        try:
            rendered = await _final_screen(
                flow=flow,
                ctx=ctx,
                state=session.state,
                screen=screen,
                request=request,
                events=events,
            )
            envelope = UiEnvelope(
                session_id=ctx.session_id, turn_id=ctx.turn_id, components=rendered.components
            )
            await self._complete(ctx, request, rendered.state, envelope, ended=rendered.ended)
            await events.put(RenderEvent(envelope=adapt(envelope, client_version)))
            log.info("stylist_turn_rendered", components=[c.type for c in envelope.components])
        except Exception:
            log.exception("stylist_turn_failed")
            fallback = _failure_screen(ctx)
            await self._complete(ctx, request, session.state, fallback, ended=False, failed=True)
            await events.put(ErrorEvent(problem=_FAILURE_PROBLEM))
            await events.put(RenderEvent(envelope=adapt(fallback, client_version)))
        finally:
            await events.put(DoneEvent(turn_id=ctx.turn_id))

    async def _complete(
        self,
        ctx: TurnContext,
        request: ActionRequest,
        state: Mapping[str, Any],
        envelope: UiEnvelope,
        *,
        ended: bool,
        failed: bool = False,
    ) -> None:
        payload = envelope.model_dump(mode="json")
        async with self._uow() as uow:
            repo = StylistRepository(uow.session)
            await repo.complete_turn(
                ctx.session_id,
                ctx.turn_id,
                state=dict(state),
                envelope=payload,
                status="ended" if ended else "active",
                now=self._clock.now(),
            )
            repo.add(
                _event(
                    ctx.session_id, ctx.turn_id, "action", request.action.model_dump(mode="json")
                )
            )
            repo.add(_event(ctx.session_id, ctx.turn_id, "error" if failed else "render", payload))

    async def _load(self, session_id: uuid.UUID, user_id: uuid.UUID) -> StylistSession:
        async with self._uow() as uow:
            # Owner-scoped: another user's session id looks exactly like a missing one.
            session = await StylistRepository(uow.session).get(session_id, user_id)
        if session is None or session.envelope is None:
            raise SessionNotFoundError
        return session

    @staticmethod
    def _check_turn(session: StylistSession, turn_id: int) -> None:
        if session.status == "ended":
            raise SessionEndedError
        if session.status == "busy":
            raise SessionBusyError(current_turn=session.turn_id)
        if session.turn_id != turn_id:
            raise StaleTurnError(current_turn=session.turn_id)


async def _final_screen(
    *,
    flow: Flow,
    ctx: TurnContext,
    state: Mapping[str, Any],
    screen: UiEnvelope,
    request: ActionRequest,
    events: asyncio.Queue[UiEvent],
) -> Rendered:
    """Forward progress to the stream; return the flow's single final screen."""
    rendered: Rendered | None = None
    async for output in flow.act(ctx, state, screen, request.action):
        if isinstance(output, Progress):
            await events.put(LoadingEvent(turn_id=ctx.turn_id, components=output.components))
        else:
            rendered = output
    if rendered is None:
        raise RuntimeError(f"flow '{flow.name}' produced no screen")
    return rendered


async def _drain(events: asyncio.Queue[UiEvent]) -> AsyncGenerator[UiEvent]:
    while True:
        event = await events.get()
        yield event
        if isinstance(event, DoneEvent):
            return


def _event(session_id: uuid.UUID, turn_id: int, kind: str, payload: dict[str, Any]) -> SessionEvent:
    return SessionEvent(session_id=session_id, turn_id=turn_id, kind=kind, payload=payload)


def _failure_screen(ctx: TurnContext) -> UiEnvelope:
    return UiEnvelope(
        session_id=ctx.session_id,
        turn_id=ctx.turn_id,
        components=[
            InfoBanner(
                id="failed",
                props=InfoBannerProps(
                    tone="warning", text="That didn't work on our side. Let's try again."
                ),
            ),
            SuggestionBar(
                id="next",
                props=SuggestionBarProps(
                    suggestions=[Suggestion(id="restart", label="Start over", action=Restart())]
                ),
            ),
        ],
    )
