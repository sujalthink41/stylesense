"""Actions must match what the server rendered: no tapping chips that weren't offered."""

from typing import Any

from stylesense.genui.actions import (
    Action,
    Back,
    CardOpen,
    ChipSelect,
    Restart,
    Shortcut,
    SliderSet,
    Swipe,
    TextInput,
)
from stylesense.genui.components import (
    BudgetSlider,
    ChipQuestion,
    CompleteTheLook,
    EmptyState,
    ImageChoiceGrid,
    ProductCard,
    ProductCarousel,
    ProductSwipeDeck,
    SuggestionBar,
    TextInputBar,
)
from stylesense.genui.envelope import UiEnvelope
from stylesense.platform.errors import AppError


class InvalidActionError(AppError):
    status_code = 422
    code = "invalid_action"
    title = "That action doesn't match the current screen"


def validate_action(envelope: UiEnvelope, action: Action) -> None:
    match action:
        case Back() | Restart():
            return
        case ChipSelect():
            _check_chips(_choice(envelope, action.component_id), action)
        case SliderSet():
            props = _component(envelope, action.component_id, BudgetSlider).props
            if action.min_paise < props.min_paise or action.max_paise > props.max_paise:
                raise InvalidActionError("budget is outside the slider's range")
        case Swipe():
            deck = _component(envelope, action.component_id, ProductSwipeDeck)
            _check_product(action.product_id, [c.product_id for c in deck.props.cards])
        case CardOpen():
            _check_product(action.product_id, _products_in(envelope, action.component_id))
        case TextInput():
            if not any(
                isinstance(c, TextInputBar)
                or (isinstance(c, ChipQuestion) and c.props.allow_custom)
                for c in envelope.components
            ):
                raise InvalidActionError("free text isn't accepted on this screen")
        case Shortcut():
            if action.value not in _offered_shortcuts(envelope):
                raise InvalidActionError(f"shortcut '{action.value}' isn't offered here")


def _component[C](envelope: UiEnvelope, component_id: str, kind: type[C]) -> C:
    for component in envelope.components:
        if component.id == component_id:
            if not isinstance(component, kind):
                raise InvalidActionError(f"'{component_id}' doesn't accept this action")
            return component
    raise InvalidActionError(f"no component '{component_id}' on this screen")


def _choice(envelope: UiEnvelope, component_id: str) -> ChipQuestion | ImageChoiceGrid:
    component = _component(envelope, component_id, object)
    if not isinstance(component, ChipQuestion | ImageChoiceGrid):
        raise InvalidActionError(f"'{component_id}' doesn't accept this action")
    return component


def _check_chips(question: ChipQuestion | ImageChoiceGrid, action: ChipSelect) -> None:
    offered = {o.id for o in question.props.options}
    chosen = action.option_ids
    if len(set(chosen)) != len(chosen):
        raise InvalidActionError("an option was selected twice")
    if not set(chosen) <= offered:
        raise InvalidActionError("an option that wasn't offered was selected")
    if len(chosen) > question.props.max_select:
        raise InvalidActionError(f"select at most {question.props.max_select}")


def _products_in(envelope: UiEnvelope, component_id: str) -> list[Any]:
    component = _component(envelope, component_id, object)
    match component:
        case ProductSwipeDeck():
            return [c.product_id for c in component.props.cards]
        case ProductCard():
            return [component.props.product_id]
        case CompleteTheLook() | ProductCarousel():
            return [i.product_id for i in component.props.items]
    raise InvalidActionError(f"'{component_id}' has no products to open")


def _check_product(product_id: Any, available: list[Any]) -> None:
    if product_id not in available:
        raise InvalidActionError("that product isn't on this screen")


def _offered_shortcuts(envelope: UiEnvelope) -> set[str]:
    values: set[str] = set()
    for component in envelope.components:
        suggestions = []
        if isinstance(component, SuggestionBar):
            suggestions = component.props.suggestions
        elif isinstance(component, EmptyState):
            suggestions = component.props.recovery
        values.update(s.action.value for s in suggestions if isinstance(s.action, Shortcut))
    return values
