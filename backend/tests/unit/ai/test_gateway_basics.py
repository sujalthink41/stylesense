from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from stylesense.ai.gateway.pricing import ModelPrice
from stylesense.ai.gateway.tokens import IMAGE_TOKENS, estimate_tokens
from stylesense.ai.gateway.types import Message, ModelRef, Usage

PRICE = ModelPrice(
    input_usd_per_mtok=Decimal("0.40"),
    cached_input_usd_per_mtok=Decimal("0.10"),
    output_usd_per_mtok=Decimal("1.60"),
)


def test_model_ref_round_trips() -> None:
    ref = ModelRef.parse("openai:some-model-2026")

    assert (ref.provider, ref.model, str(ref)) == (
        "openai",
        "some-model-2026",
        "openai:some-model-2026",
    )


def test_model_ref_keeps_colons_inside_the_model_name() -> None:
    assert ModelRef.parse("ollama:llama3:8b").model == "llama3:8b"


@pytest.mark.parametrize("bad", ["openai", ":model", "openai:", ""])
def test_model_ref_rejects_malformed_refs(bad: str) -> None:
    with pytest.raises(ValueError, match="provider:model"):
        ModelRef.parse(bad)


def test_cost_is_in_whole_micro_dollars_and_bills_cached_tokens_cheaper() -> None:
    usage = Usage(input_tokens=10_000, cached_input_tokens=4_000, output_tokens=500)

    # 6,000 x 0.40 + 4,000 x 0.10 + 500 x 1.60 = 2,400 + 400 + 800 micro-USD
    assert PRICE.cost_micro_usd(usage) == 3_600


def test_cost_rounds_up_so_budgets_are_never_undercounted() -> None:
    assert PRICE.cost_micro_usd(Usage(input_tokens=1)) == 1


@given(
    inp=st.integers(min_value=0, max_value=10**7),
    cached=st.integers(min_value=0, max_value=10**7),
    out=st.integers(min_value=0, max_value=10**6),
)
def test_cost_is_never_negative_even_with_inconsistent_usage(
    inp: int, cached: int, out: int
) -> None:
    assert PRICE.cost_micro_usd(Usage(inp, cached, out)) >= 0


def test_token_estimate_is_conservative() -> None:
    text = "Suggest a breathable summer t-shirt under five hundred rupees for college."

    estimate = estimate_tokens([Message("user", text)])

    assert estimate >= len(text) // 4 + 4  # at or above the usual ~4 chars/token


def test_token_estimate_grows_with_every_message() -> None:
    one = estimate_tokens([Message("system", "rules")])
    two = estimate_tokens([Message("system", "rules"), Message("user", "hi")])

    assert two > one


def test_images_are_counted_in_the_token_estimate() -> None:
    text_only = estimate_tokens([Message("user", "hi")])
    with_image = estimate_tokens([Message("user", "hi", images=("https://img.test/a.jpg",))])

    assert with_image - text_only == IMAGE_TOKENS


def test_vision_tasks_send_the_image_field_as_images_not_text() -> None:
    from pydantic import BaseModel  # noqa: PLC0415

    from stylesense.ai.gateway.tasks import TaskSpec  # noqa: PLC0415

    class In(BaseModel):
        note: str
        image_urls: list[str]

    class Out(BaseModel):
        ok: bool

    spec = TaskSpec("t.vision", "v1", "Look.", In, Out, image_field="image_urls")

    _, user = spec.messages(In(note="hello", image_urls=["https://img.test/a.jpg"]))

    assert user.images == ("https://img.test/a.jpg",)
    assert "img.test" not in user.content
    assert "hello" in user.content
