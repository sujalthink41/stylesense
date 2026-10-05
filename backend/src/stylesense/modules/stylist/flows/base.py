import uuid
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from stylesense.genui.actions import Action
from stylesense.genui.components import Component
from stylesense.genui.envelope import UiEnvelope


@dataclass(frozen=True, slots=True)
class Entry:
    kind: str  # occasion_tile | search | photo | feed
    value: str | None


@dataclass(frozen=True, slots=True)
class TurnContext:
    session_id: uuid.UUID
    user_id: uuid.UUID
    turn_id: int  # the turn being rendered


@dataclass(frozen=True, slots=True)
class Progress:
    """Interim UI (skeletons) while a slow step runs."""

    components: list[Component]


@dataclass(frozen=True, slots=True)
class Rendered:
    """A turn's final UI plus the flow state to persist with it."""

    components: list[Component]
    state: dict[str, Any]
    ended: bool = False


class Flow(Protocol):
    name: str

    async def start(self, ctx: TurnContext, entry: Entry) -> Rendered: ...

    def act(
        self, ctx: TurnContext, state: Mapping[str, Any], screen: UiEnvelope, action: Action
    ) -> AsyncIterator[Progress | Rendered]:
        """Yield any Progress, then exactly one Rendered as the last item."""
        ...
