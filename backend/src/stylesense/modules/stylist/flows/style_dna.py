"""Style DNA onboarding: one screen of looks to tap (up to 3), skippable, then saved.

Who you shop for and your sizes are never asked up front: you say them in the chat when they
matter ("for my wife", "size 9").
Answers are saved once at the end (one idempotent PUT), so abandoning midway changes nothing.
"""

import uuid
from collections.abc import AsyncIterator, Mapping
from typing import Any, Protocol

from stylesense.genui.actions import Action, Back, ChipSelect, Restart, Shortcut
from stylesense.genui.components import (
    Component,
    ImageChoice,
    ImageChoiceGrid,
    ImageChoiceGridProps,
    InfoBanner,
    InfoBannerProps,
    Suggestion,
    SuggestionBar,
    SuggestionBarProps,
)
from stylesense.genui.envelope import UiEnvelope
from stylesense.modules.personalization.schemas import (
    Sizes,
    StyleProfileUpdate,
    StyleProfileView,
)
from stylesense.modules.personalization.styles import (
    BOTTOM_SIZES,
    MAX_STYLES,
    SHOE_SIZES,
    STYLES,
    TOP_SIZES,
)
from stylesense.modules.stylist.flows.base import Entry, Progress, Rendered, TurnContext

STEPS = ("styles",)
_SKIP = Suggestion(id="skip", label="Skip", action=Shortcut(value="skip"))
_BACK = Suggestion(id="back", label="Back", action=Back())


class StyleDnaStore(Protocol):
    async def update_profile(
        self, user_id: uuid.UUID, update: StyleProfileUpdate
    ) -> StyleProfileView: ...


class StyleDnaFlow:
    name = "style_dna"

    def __init__(self, store: StyleDnaStore) -> None:
        self._store = store

    async def start(self, ctx: TurnContext, entry: Entry) -> Rendered:
        state: dict[str, Any] = {"step": 0, "answers": {}}
        return Rendered(components=_screen(state), state=state)

    async def act(
        self, ctx: TurnContext, state: Mapping[str, Any], screen: UiEnvelope, action: Action
    ) -> AsyncIterator[Progress | Rendered]:
        s: dict[str, Any] = {
            "step": state.get("step", 0),
            "answers": dict(state.get("answers", {})),
        }
        match action:
            case Restart():
                s = {"step": 0, "answers": {}}
            case Back():
                s["step"] = max(0, s["step"] - 1)
                s["answers"].pop(STEPS[s["step"]], None)
            case ChipSelect(option_ids=chosen):
                s["answers"][STEPS[s["step"]]] = chosen
                s["step"] += 1
            case Shortcut(value="skip"):
                s["step"] += 1
        if s["step"] < len(STEPS):
            yield Rendered(components=_screen(s), state=s)
            return
        view = await self._store.update_profile(ctx.user_id, _to_update(s["answers"]))
        done = InfoBanner(
            id="saved",
            props=InfoBannerProps(tone="success", text=_summary(view)),
        )
        yield Rendered(components=[done], state=s, ended=True)


def _screen(state: Mapping[str, Any]) -> list[Component]:
    question = ImageChoiceGrid(
        id="q_styles",
        props=ImageChoiceGridProps(
            question=f"Pick up to {MAX_STYLES} looks you love",
            options=[
                ImageChoice(id=key, label=style.label, image_url=style.image_url)
                for key, style in STYLES.items()
            ],
            max_select=MAX_STYLES,
        ),
    )
    actions = [_SKIP, _BACK] if state["step"] else [_SKIP]
    return [question, SuggestionBar(id="next", props=SuggestionBarProps(suggestions=actions))]


def _to_update(answers: Mapping[str, list[str]]) -> StyleProfileUpdate:
    def one(step: str) -> str | None:
        return answers[step][0] if answers.get(step) else None

    def size(step: str, offered: tuple[str, ...]) -> str | None:
        chosen = one(step)
        return next((s for s in offered if s.lower() == chosen), None)

    return StyleProfileUpdate.model_validate(
        {
            "fit_preference": one("fit"),
            "styles": answers.get("styles", []),
            "sizes": Sizes(
                top=size("top", TOP_SIZES),
                bottom=size("bottom", BOTTOM_SIZES),
                shoe=size("shoe", SHOE_SIZES),
            ),
        }
    )


def _summary(view: StyleProfileView) -> str:
    if not view.styles:
        return "Saved. Your picks will get sharper as you swipe."
    labels = ", ".join(STYLES[s].label for s in view.styles)
    return f"Saved: {labels}. Your picks will get sharper as you swipe."
