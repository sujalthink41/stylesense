"""What the server sends: a UI envelope per turn, streamed as Server-Sent Events."""

import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from stylesense.genui.components import Component


class UiEnvelope(BaseModel):
    """One turn's UI. `turn_id` is what the app must echo back with its next action."""

    model_config = ConfigDict(frozen=True)

    session_id: uuid.UUID
    turn_id: int = Field(ge=1)
    mode: Literal["replace", "append"] = "replace"
    components: list[Component] = Field(min_length=1, max_length=20)


class RenderEvent(BaseModel):
    event: Literal["ui.render"] = "ui.render"
    envelope: UiEnvelope


class LoadingEvent(BaseModel):
    """Skeletons to show while the turn is being computed (e.g. waiting on AI)."""

    event: Literal["ui.loading"] = "ui.loading"
    turn_id: int
    components: list[Component] = Field(min_length=1, max_length=5)


class ErrorEvent(BaseModel):
    event: Literal["error"] = "error"
    problem: dict[str, Any]  # RFC 9457 problem body


class DoneEvent(BaseModel):
    event: Literal["done"] = "done"
    turn_id: int


UiEvent = Annotated[
    RenderEvent | LoadingEvent | ErrorEvent | DoneEvent, Field(discriminator="event")
]


def to_sse(event: RenderEvent | LoadingEvent | ErrorEvent | DoneEvent, *, event_id: str) -> str:
    """One SSE frame. JSON never contains raw newlines, so a single `data:` line is safe."""
    return f"id: {event_id}\nevent: {event.event}\ndata: {event.model_dump_json()}\n\n"
