import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from stylesense.api.auth import Claims
from stylesense.api.dependencies import ContainerDep
from stylesense.api.rate_limit import rate_limited_user
from stylesense.genui.actions import ActionRequest
from stylesense.genui.envelope import ErrorEvent, RenderEvent, UiEnvelope, UiEvent, to_sse
from stylesense.genui.versioning import HEADER, negotiate
from stylesense.modules.stylist.schemas import DeckRefill, SessionCreate, SessionView

router = APIRouter(
    prefix="/stylist", tags=["stylist"], dependencies=[Depends(rate_limited_user("api.per_user"))]
)

SSE = "text/event-stream"
KEEPALIVE_S = 15  # proxies (e.g. Cloudflare) drop connections that go quiet
MAX_EXCLUDE = 50  # cards the app already holds


def client_version(request: Request) -> int:
    return negotiate(request.headers.get(HEADER))


GenUIVersion = Annotated[int, Depends(client_version)]


class ActionResult(BaseModel):
    """Non-streaming response: the turn's final screen (and the error, if the turn failed)."""

    turn_id: int
    ui: UiEnvelope | None
    error: dict[str, Any] | None = None


@router.post("/sessions", status_code=status.HTTP_201_CREATED, summary="Start a stylist session")
async def start_session(
    body: SessionCreate, claims: Claims, container: ContainerDep, version: GenUIVersion
) -> SessionView:
    return await container.stylist.start(claims.user_id, body, client_version=version)


@router.get("/sessions/{session_id}", summary="Current screen (resume after a dropped stream)")
async def get_session(
    session_id: uuid.UUID, claims: Claims, container: ContainerDep, version: GenUIVersion
) -> SessionView:
    return await container.stylist.snapshot(session_id, claims.user_id, client_version=version)


@router.get(
    "/sessions/{session_id}/deck",
    summary="More cards for the current deck (prefetch), skipping swiped and held cards",
    responses={409: {"description": "The session isn't showing products"}},
)
async def refill_deck(
    session_id: uuid.UUID,
    claims: Claims,
    container: ContainerDep,
    exclude: Annotated[list[uuid.UUID], Query(max_length=MAX_EXCLUDE)] = [],  # noqa: B006
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> JSONResponse:
    refill: DeckRefill = await container.stylist.deck(
        session_id, claims.user_id, exclude=exclude, limit=limit
    )
    # Personal and changes with every swipe: never cache.
    return JSONResponse(refill.model_dump(mode="json"), headers={"Cache-Control": "no-store"})


@router.post(
    "/sessions/{session_id}/actions",
    response_model=ActionResult,
    summary="Send a tap/swipe/text; streams the next screen as SSE when Accept: text/event-stream",
    responses={200: {"content": {SSE: {}}}, 409: {"description": "Stale turn or session busy"}},
)
async def act(
    *,
    session_id: uuid.UUID,
    body: ActionRequest,
    request: Request,
    claims: Claims,
    container: ContainerDep,
    version: GenUIVersion,
) -> Response:
    events = await container.stylist.act(session_id, claims.user_id, body, client_version=version)
    if SSE in request.headers.get("accept", ""):
        return StreamingResponse(
            _frames(events, turn_id=body.turn_id + 1),
            media_type=SSE,
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )
    collected = [e async for e in events]
    renders = [e for e in collected if isinstance(e, RenderEvent)]
    errors = [e for e in collected if isinstance(e, ErrorEvent)]
    result = ActionResult(
        turn_id=body.turn_id + 1,
        ui=renders[-1].envelope if renders else None,
        error=errors[0].problem if errors else None,
    )
    return JSONResponse(result.model_dump(mode="json"), headers={"Cache-Control": "no-store"})


async def _frames(events: AsyncIterator[UiEvent], *, turn_id: int) -> AsyncIterator[str]:
    sequence = 0
    pending = asyncio.ensure_future(anext(events))
    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=KEEPALIVE_S)
            if not done:
                yield ": keep-alive\n\n"  # SSE comment: ignored by clients, keeps proxies happy
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                return
            sequence += 1
            yield to_sse(event, event_id=f"{turn_id}.{sequence}")
            pending = asyncio.ensure_future(anext(events))
    finally:
        pending.cancel()
