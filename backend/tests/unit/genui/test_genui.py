import json
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from stylesense.genui.actions import (
    ActionRequest,
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
    BudgetSliderProps,
    ChipOption,
    ChipQuestion,
    ChipQuestionProps,
    ComparedOffer,
    InfoBanner,
    ProductCardProps,
    ProductSwipeDeck,
    ProductSwipeDeckProps,
    Suggestion,
    SuggestionBar,
    SuggestionBarProps,
    TextInputBar,
    TextInputBarProps,
)
from stylesense.genui.envelope import DoneEvent, RenderEvent, UiEnvelope, to_sse
from stylesense.genui.schema import contract_json
from stylesense.genui.validation import InvalidActionError, validate_action
from stylesense.genui.versioning import (
    InvalidGenUIVersionError,
    UnsupportedGenUIVersionError,
    adapt,
    negotiate,
)

SESSION = uuid.UUID("018f2a3b-7c4d-7e8f-9a0b-1c2d3e4f5a6b")
P1, P2 = uuid.uuid4(), uuid.uuid4()
CONTRACT_FILE = Path(__file__).resolve().parents[3] / "contracts" / "genui.schema.json"

QUESTION = ChipQuestion(
    id="category",
    props=ChipQuestionProps(
        question="What are you shopping for?",
        options=[ChipOption(id="tshirt", label="T-shirts"), ChipOption(id="jeans", label="Jeans")],
    ),
)
SLIDER = BudgetSlider(
    id="budget",
    props=BudgetSliderProps(
        label="Budget",
        min_paise=0,
        max_paise=500_000,
        step_paise=10_000,
        default_min_paise=0,
        default_max_paise=100_000,
    ),
)
DECK = ProductSwipeDeck(
    id="deck",
    props=ProductSwipeDeckProps(
        cards=[
            ProductCardProps(product_id=P1, title="Tee", brand="Kalaa", price_paise=49_900),
            ProductCardProps(product_id=P2, title="Jeans", brand="Kalaa", price_paise=99_900),
        ]
    ),
)
BAR = SuggestionBar(
    id="next",
    props=SuggestionBarProps(
        suggestions=[Suggestion(id="more", label="Show more", action=Shortcut(value="more"))]
    ),
)


def _envelope(*components: object) -> UiEnvelope:
    return UiEnvelope(session_id=SESSION, turn_id=1, components=list(components))


# ---------- component contracts ----------


def test_chip_options_must_be_unique() -> None:
    with pytest.raises(ValidationError, match="unique"):
        ChipQuestionProps(
            question="Pick", options=[ChipOption(id="a", label="A"), ChipOption(id="a", label="B")]
        )


def test_single_choice_cannot_allow_multiple_selections() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        ChipQuestionProps(
            question="Pick",
            options=[ChipOption(id="a", label="A"), ChipOption(id="b", label="B")],
            max_select=2,
        )


@pytest.mark.parametrize("bad_id", ["Upper", "has space", "", "-leading", "x" * 41])
def test_component_ids_are_restricted(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        InfoBanner(id=bad_id, props={"text": "hi"})


def test_slider_defaults_must_sit_inside_its_range() -> None:
    with pytest.raises(ValidationError, match="min <= default_min"):
        BudgetSliderProps(
            label="Budget",
            min_paise=10_000,
            max_paise=50_000,
            step_paise=1_000,
            default_min_paise=0,
            default_max_paise=20_000,
        )


def test_buy_links_must_go_through_the_tracked_redirect() -> None:
    with pytest.raises(ValidationError):
        ComparedOffer(
            offer_id=uuid.uuid4(),
            store="amazon",
            store_name="Amazon",
            price_paise=1,
            mrp_paise=None,
            discount_percent=0,
            in_stock=True,
            is_best=True,
            buy_path="https://evil.example",
        )


def test_unknown_props_are_rejected() -> None:
    with pytest.raises(ValidationError):
        InfoBanner(id="x", props={"text": "hi", "html": "<script>"})


def test_envelope_round_trips_through_json_by_type() -> None:
    envelope = _envelope(QUESTION, SLIDER, DECK, BAR)

    assert UiEnvelope.model_validate_json(envelope.model_dump_json()) == envelope


# ---------- actions ----------


@pytest.mark.parametrize(
    "payload",
    [
        {"turn_id": 0, "action": {"type": "back"}},
        {"turn_id": 1, "action": {"type": "teleport"}},
        {
            "turn_id": 1,
            "action": {"type": "slider_set", "component_id": "b", "min_paise": 5, "max_paise": 1},
        },
        {"turn_id": 1, "action": {"type": "text_input", "text": "x" * 501}},
        {"turn_id": 1, "action": {"type": "chip_select", "component_id": "c", "option_ids": []}},
        {"turn_id": 1, "action": {"type": "back"}, "extra": True},
    ],
)
def test_malformed_action_requests_are_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ActionRequest.model_validate(payload)


def test_actions_parse_by_type() -> None:
    request = ActionRequest.model_validate(
        {
            "turn_id": 3,
            "action": {"type": "chip_select", "component_id": "category", "option_ids": ["jeans"]},
        }
    )

    assert isinstance(request.action, ChipSelect)


# ---------- action vs screen ----------


@pytest.mark.parametrize(
    "action",
    [
        ChipSelect(component_id="category", option_ids=["jeans"]),
        SliderSet(component_id="budget", min_paise=0, max_paise=200_000),
        Swipe(component_id="deck", product_id=P1, direction="right"),
        CardOpen(component_id="deck", product_id=P2),
        Shortcut(value="more"),
        Back(),
        Restart(),
    ],
)
def test_actions_matching_the_screen_are_accepted(action: object) -> None:
    validate_action(_envelope(QUESTION, SLIDER, DECK, BAR), action)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("action", "message"),
    [
        (ChipSelect(component_id="category", option_ids=["dress"]), "wasn't offered"),
        (ChipSelect(component_id="category", option_ids=["jeans", "tshirt"]), "at most 1"),
        (ChipSelect(component_id="category", option_ids=["jeans", "jeans"]), "twice"),
        (ChipSelect(component_id="missing", option_ids=["jeans"]), "no component"),
        (ChipSelect(component_id="budget", option_ids=["jeans"]), "doesn't accept"),
        (SliderSet(component_id="budget", min_paise=0, max_paise=900_000), "outside"),
        (
            Swipe(component_id="deck", product_id=uuid.uuid4(), direction="left"),
            "isn't on this screen",
        ),
        (CardOpen(component_id="category", product_id=P1), "no products"),
        (Shortcut(value="secret-admin-mode"), "isn't offered"),
        (TextInput(text="hello"), "free text"),
    ],
)
def test_actions_not_matching_the_screen_are_rejected(action: object, message: str) -> None:
    with pytest.raises(InvalidActionError, match=message) as err:
        validate_action(_envelope(QUESTION, SLIDER, DECK, BAR), action)  # type: ignore[arg-type]
    assert err.value.status_code == 422


def test_free_text_is_accepted_when_the_screen_offers_it() -> None:
    bar = TextInputBar(id="ask", props=TextInputBarProps())

    validate_action(_envelope(QUESTION, bar), TextInput(text="linen shirt for a beach trip"))


# ---------- versioning ----------


@pytest.mark.parametrize(("raw", "expected"), [(None, 1), ("1", 1), (" 1 ", 1), ("2", 2), ("7", 2)])
def test_negotiates_a_renderable_version(raw: str | None, expected: int) -> None:
    assert negotiate(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "1.5", "-2", "0"])
def test_garbage_versions_are_400(raw: str) -> None:
    with pytest.raises(InvalidGenUIVersionError):
        negotiate(raw)


def test_apps_older_than_the_minimum_must_update(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("stylesense.genui.versioning.MIN_SUPPORTED_VERSION", 2)

    with pytest.raises(UnsupportedGenUIVersionError) as err:
        negotiate("1")
    assert err.value.status_code == 426


def test_components_newer_than_the_app_become_update_prompts() -> None:
    introduced = {
        "chip_question": 1,
        "budget_slider": 2,
        "product_swipe_deck": 1,
        "suggestion_bar": 1,
    }

    adapted = adapt(_envelope(QUESTION, SLIDER), client_version=1, introduced=introduced)

    assert [c.type for c in adapted.components] == ["chip_question", "info_banner"]
    assert adapted.components[1].id == "budget"  # same slot, so the layout doesn't jump
    assert (
        adapt(_envelope(QUESTION, SLIDER), client_version=2, introduced=introduced)
        .components[1]
        .type
        == "budget_slider"
    )


# ---------- wire format & contract ----------


def test_sse_frames_are_well_formed() -> None:
    frame = to_sse(DoneEvent(turn_id=4), event_id="4.2")

    assert frame == 'id: 4.2\nevent: done\ndata: {"event":"done","turn_id":4}\n\n'


def test_render_event_carries_the_whole_envelope() -> None:
    frame = to_sse(RenderEvent(envelope=_envelope(QUESTION)), event_id="1.1")
    data = json.loads(frame.split("data: ", 1)[1])

    assert data["envelope"]["components"][0]["type"] == "chip_question"


def test_committed_contract_matches_the_code() -> None:
    # If this fails, run `make contracts` and commit the result: the app's types depend on it.
    assert CONTRACT_FILE.read_text(encoding="utf-8") == contract_json()
