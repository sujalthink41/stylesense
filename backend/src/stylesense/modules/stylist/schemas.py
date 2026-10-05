import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from stylesense.genui.envelope import UiEnvelope


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry: Literal["occasion_tile", "search", "photo", "feed"]
    value: str | None = Field(default=None, min_length=1, max_length=100)


class SessionView(BaseModel):
    """Everything needed to (re)draw a session; also the resume point after a dropped stream."""

    session_id: uuid.UUID
    turn_id: int
    status: Literal["active", "busy", "ended"]
    ui: UiEnvelope
