import pytest
from hypothesis import given
from hypothesis import strategies as st

from stylesense.modules.stylist.evals.scoring import load_golden, score
from stylesense.modules.stylist.slots import Slots
from stylesense.modules.stylist.understanding import guess_category, parse_request

# ---------- the golden set (the CP8 exit criterion) ----------


def test_rule_parser_meets_the_accuracy_bar_on_the_golden_set() -> None:
    report = score(load_golden(), parse_request)

    assert report.examples >= 50
    assert report.field_accuracy >= 0.90, report.failures
    assert report.exact_match >= 0.85, report.failures


# ---------- budgets ----------


@pytest.mark.parametrize(
    ("text", "low", "high"),
    [
        ("under 500", None, 50_000),
        ("below ₹1,499", None, 149_900),
        ("less than rs 999", None, 99_900),
        ("within 2k", None, 200_000),
        ("upto 1.5k", None, 150_000),
        ("up to Rs. 750", None, 75_000),
        ("1000 tak", None, 100_000),
        ("500 se kam", None, 50_000),
        ("500-1000", 50_000, 100_000),
        ("between 1,500 and 3,000", 150_000, 300_000),
        ("₹800 to ₹1200", 80_000, 120_000),
        ("around 1000", 70_000, 120_000),
        ("kurta 1200", None, 120_000),
    ],
)
def test_budget_phrasings(text: str, low: int | None, high: int | None) -> None:
    slots = parse_request(text)

    assert (slots.budget_min_paise, slots.budget_max_paise) == (low, high)


@pytest.mark.parametrize("text", ["size 32 jeans", "uk 9 sneakers", "jeans 32 waist", "2 tees"])
def test_sizes_and_counts_are_not_budgets(text: str) -> None:
    assert parse_request(text).budget_max_paise is None


def test_absurd_amounts_are_ignored() -> None:
    assert parse_request("tee under 5").budget_max_paise is None
    assert parse_request("tee under 9999999").budget_max_paise is None


def test_reversed_range_is_normalised() -> None:
    slots = parse_request("2000-1000 jeans")

    assert (slots.budget_min_paise, slots.budget_max_paise) == (100_000, 200_000)


# ---------- vocabulary ----------


def test_t_shirt_is_not_mistaken_for_shirt() -> None:
    assert parse_request("black t-shirt").category == "tshirt"
    assert parse_request("black shirt").category == "shirt"


def test_denim_jacket_is_a_jacket_not_jeans() -> None:
    slots = parse_request("denim jacket")

    assert (slots.category, slots.fabric) == ("jacket", "denim")


def test_her_inside_other_words_is_not_a_gender() -> None:
    assert parse_request("leather boots for weather").gender is None


def test_unknown_text_yields_empty_slots() -> None:
    assert parse_request("hmm not sure yet") == Slots()


@given(st.text(max_size=300))
def test_parser_never_crashes_on_arbitrary_input(text: str) -> None:
    slots = parse_request(text)

    if slots.budget_max_paise is not None:
        assert 0 < slots.budget_max_paise <= 10_000_000
        assert slots.budget_min_paise is None or slots.budget_min_paise <= slots.budget_max_paise


# ---------- slots ----------


def test_only_the_item_is_required_before_searching() -> None:
    assert Slots().missing() == ["category"]
    assert Slots(category="socks").missing() == []  # who it's for and budget are refinements


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("i need socks", "socks"),
        ("formal shoes for office", "formal_shoes"),
        ("track pants for gym", "joggers"),
        ("night suit for her", "nightwear"),
        ("salwar suit for mom", "kurta"),
        ("a silk saree", "saree"),
        ("laptop bag", "backpack"),
        ("smart watch for dad", "watch"),
        ("tie-dye t-shirt", "tshirt"),
        ("cap sleeve top", "top"),
        ("nehru jacket for sangeet", "blazer"),
    ],
)
def test_many_fashion_items_are_understood(text: str, category: str) -> None:
    assert parse_request(text).category == category


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("I need shocks", ("socks", "shocks")),
        ("black jens", ("jeans", "jens")),
        ("kurthi for my wife", ("kurta", "kurthi")),
        ("sneekers", ("sneakers", "sneekers")),
        ("i hate this", None),
        ("something classy", None),
    ],
)
def test_misspelt_items_are_recognised_and_ordinary_words_are_not(
    text: str, expected: tuple[str, str] | None
) -> None:
    assert guess_category(text) == expected


def test_merge_keeps_known_values_and_fills_gaps() -> None:
    known = Slots(category="tshirt", budget_max_paise=50_000)

    merged = known.merged(Slots(category="shirt", gender="men", colors=["black"]))

    assert (merged.category, merged.gender, merged.colors, merged.budget_max_paise) == (
        "shirt",
        "men",
        ["black"],
        50_000,
    )


def test_merge_never_drops_values_the_update_lacks() -> None:
    assert Slots(occasion="party").merged(Slots()).occasion == "party"
