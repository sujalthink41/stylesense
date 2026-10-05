"""Everything the app can send back: taps, swipes, text. Validated before any turn runs."""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_Id = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")]


class _Action(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ChipSelect(_Action):
    type: Literal["chip_select"] = "chip_select"
    component_id: _Id
    option_ids: list[_Id] = Field(min_length=1, max_length=12)


class SliderSet(_Action):
    type: Literal["slider_set"] = "slider_set"
    component_id: _Id
    min_paise: int = Field(ge=0)
    max_paise: int = Field(ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> "SliderSet":
        if self.min_paise > self.max_paise:
            raise ValueError("min_paise must not exceed max_paise")
        return self


class Swipe(_Action):
    type: Literal["swipe"] = "swipe"
    component_id: _Id
    product_id: uuid.UUID
    direction: Literal["left", "right", "super"]


class CardOpen(_Action):
    type: Literal["card_open"] = "card_open"
    component_id: _Id
    product_id: uuid.UUID


class TextInput(_Action):
    type: Literal["text_input"] = "text_input"
    text: str = Field(min_length=1, max_length=500)


class Shortcut(_Action):
    type: Literal["shortcut"] = "shortcut"
    value: _Id


class Back(_Action):
    type: Literal["back"] = "back"


class Restart(_Action):
    type: Literal["restart"] = "restart"


Action = Annotated[
    ChipSelect | SliderSet | Swipe | CardOpen | TextInput | Shortcut | Back | Restart,
    Field(discriminator="type"),
]


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: int = Field(ge=1)  # the turn the app is looking at; stale turns are rejected
    action: Action
