import pytest

from stylesense.modules.stylist.brands import find_brand
from stylesense.modules.stylist.tasks import UnderstandOutput
from stylesense.modules.stylist.understanding import parse_request, unknown_words


@pytest.mark.parametrize(
    ("text", "brand"),
    [
        ("asics shoes for mens", "ASICS"),
        ("ASICS Gel running shoes", "ASICS"),
        ("red tape sneakers", "Red Tape"),
        ("us polo tshirt", "U.S. Polo Assn."),
        ("levis 511 jeans", "Levi's"),
        ("nb sneakers", "New Balance"),
        ("jeans from only", "Only"),
        ("only black jeans under 1000", None),  # an everyday word, not the brand
        ("black jeans for men", None),  # "ck jeans" must not match inside "black jeans"
        ("women kurta", None),
    ],
)
def test_brands_are_found_by_their_store_spelling(text: str, brand: str | None) -> None:
    assert find_brand(text) == brand


def test_a_clear_brand_search_is_fully_understood_by_rules() -> None:
    slots = parse_request("asics shoes for mens")

    assert (slots.brand, slots.category, slots.gender, slots.keywords) == (
        "ASICS",
        "sneakers",
        "men",
        [],
    )
    assert unknown_words("asics shoes for mens") == []  # nothing left for the AI: no tokens spent


def test_leftover_words_become_keywords() -> None:
    assert parse_request("asics gel running shoes for men").keywords == ["gel"]
    assert parse_request("comfy kurti for office not too flashy").keywords == ["comfy", "flashy"]
    assert parse_request("hmm not sure yet").keywords == []


def test_a_null_list_from_an_open_model_still_parses() -> None:
    out = UnderstandOutput.model_validate_json(
        '{"brand": null, "category": "top", "colors": null,'
        ' "gender": "women", "occasion": "sports"}'
    )

    assert (out.category, out.colors) == ("top", [])
