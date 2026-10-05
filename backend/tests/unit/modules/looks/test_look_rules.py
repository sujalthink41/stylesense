"""Complete-the-look rules. The budget rules are the CP10 exit criterion, so they're proven
over generated looks, not just examples."""

import uuid

from hypothesis import given, settings
from hypothesis import strategies as st

from stylesense.modules.looks.rules import (
    COMPLEMENTS,
    Piece,
    Slot,
    assemble,
    harmony,
    occasion_fit,
    reasons,
    slots_for,
)

ANCHOR = Piece(
    uuid.UUID(int=0), "tshirt", 49_900, frozenset({"olive", "casual", "summer"}), 4.2, 300
)
SLOTS = slots_for("tshirt", ANCHOR.tags | {"winter"})  # bottom, shoes, layer
CAPS = {
    "jeans": 200_000,
    "trousers": 150_000,
    "shorts": 100_000,
    "sneakers": 300_000,
    "jacket": 300_000,
    "hoodie": 150_000,
}
TAGS = (
    "black",
    "white",
    "navy",
    "pink",
    "red",
    "mustard",
    "summer",
    "party",
    "office",
    "casual",
    "winter",
)


def piece(category: str, price: int | None, *tags: str, rating: float = 4.2) -> Piece:
    return Piece(uuid.uuid4(), category, price, frozenset(tags), rating, 500)


pieces = st.builds(
    Piece,
    id=st.sampled_from([ANCHOR.id, *(uuid.UUID(int=i) for i in range(1, 25))]),
    category=st.sampled_from(
        ["jeans", "trousers", "shorts", "sneakers", "jacket", "hoodie", "kurta"]
    ),
    price_paise=st.none() | st.integers(min_value=100, max_value=400_000),
    tags=st.frozensets(st.sampled_from(TAGS), max_size=4),
    rating=st.none() | st.floats(min_value=1, max_value=5),
    rating_count=st.integers(min_value=0, max_value=5_000),
)
by_slot = st.fixed_dictionaries({s.name: st.lists(pieces, max_size=14) for s in SLOTS})
budgets = st.none() | st.integers(min_value=0, max_value=800_000)


@given(by_slot, budgets)
def test_a_look_never_exceeds_the_remaining_budget(
    candidates: dict[str, list[Piece]], remaining: int | None
) -> None:
    look = assemble(ANCHOR, SLOTS, candidates, remaining_paise=remaining, caps=CAPS)

    total = sum(p.piece.price_paise or 0 for p in look)
    assert remaining is None or total <= remaining


@given(by_slot, budgets)
def test_every_piece_is_buyable_capped_distinct_and_fits_its_slot(
    candidates: dict[str, list[Piece]], remaining: int | None
) -> None:
    look = assemble(ANCHOR, SLOTS, candidates, remaining_paise=remaining, caps=CAPS)

    slot_of = {s.name: s for s in SLOTS}
    assert len({p.slot for p in look}) == len(look)  # one piece per slot
    assert len({p.piece.id for p in look}) == len(look)  # never the same product twice
    for pick in look:
        assert pick.piece.id != ANCHOR.id
        assert pick.piece.price_paise is not None
        assert pick.piece.price_paise <= CAPS[pick.piece.category]
        assert pick.piece.category in slot_of[pick.slot].categories
        assert occasion_fit(ANCHOR.occasions, pick.piece.occasions) > 0  # no register clash


@settings(max_examples=500)
@given(by_slot, budgets)
def test_a_look_fills_every_slot_it_can_afford(
    candidates: dict[str, list[Piece]], remaining: int | None
) -> None:
    """If the cheapest eligible piece of an empty slot still fits, the look isn't maximal."""
    look = assemble(ANCHOR, SLOTS, candidates, remaining_paise=remaining, caps=CAPS)
    spent = sum(p.piece.price_paise or 0 for p in look)
    used = {p.piece.id for p in look} | {ANCHOR.id}
    filled = {p.slot for p in look}

    for slot in SLOTS:
        if slot.name in filled:
            continue
        affordable = [
            c
            for c in candidates[slot.name]
            if c.price_paise is not None
            and c.id not in used
            and c.category in slot.categories
            and c.price_paise <= CAPS[c.category]
            and occasion_fit(ANCHOR.occasions, c.occasions) > 0
            and (remaining is None or spent + c.price_paise <= remaining)
        ]
        assert not affordable


@given(by_slot, budgets)
def test_assembly_is_deterministic(
    candidates: dict[str, list[Piece]], remaining: int | None
) -> None:
    reversed_candidates = {k: list(reversed(v)) for k, v in candidates.items()}

    first = assemble(ANCHOR, SLOTS, candidates, remaining_paise=remaining, caps=CAPS)
    second = assemble(ANCHOR, SLOTS, reversed_candidates, remaining_paise=remaining, caps=CAPS)

    assert [p.piece.id for p in first] == [p.piece.id for p in second]


def test_a_tight_budget_trades_the_best_pieces_for_ones_that_fit() -> None:
    jeans, cheap_jeans = piece("jeans", 150_000, "navy"), piece("jeans", 70_000, "black")
    sneakers = piece("sneakers", 100_000, "white")

    look = assemble(
        ANCHOR,
        slots_for("tshirt", ANCHOR.tags),
        {"bottom": [jeans, cheap_jeans], "shoes": [sneakers]},
        remaining_paise=180_000,
        caps=CAPS,
    )

    assert {p.piece.id for p in look} == {cheap_jeans.id, sneakers.id}


def test_no_budget_left_means_no_look() -> None:
    look = assemble(
        ANCHOR, SLOTS, {"bottom": [piece("jeans", 100, "navy")]}, remaining_paise=0, caps=CAPS
    )

    assert look == []


def test_layers_only_for_cold_occasions() -> None:
    assert [s.name for s in slots_for("tshirt", {"summer"})] == ["bottom", "shoes"]
    assert [s.name for s in slots_for("tshirt", {"winter"})] == ["bottom", "shoes", "layer"]
    assert slots_for("socks") == []


def test_every_anchor_category_has_complements_from_known_categories() -> None:
    known = set(COMPLEMENTS)
    for category, slots in COMPLEMENTS.items():
        for slot in slots:
            assert category not in slot.categories
            assert set(slot.categories) <= known


def test_neutrals_go_with_anything_and_bold_colours_clash() -> None:
    assert harmony(frozenset({"pink"}), frozenset({"black"})) == 1.0
    assert harmony(frozenset({"white"}), frozenset({"red"})) == 0.8
    assert harmony(frozenset({"red"}), frozenset({"green"})) < harmony(
        frozenset({"red"}), frozenset({"navy"})
    )


def test_shared_occasions_match_and_formal_never_meets_casual() -> None:
    assert occasion_fit(frozenset({"party"}), frozenset({"party", "casual"})) == 1.0
    assert occasion_fit(frozenset({"summer"}), frozenset({"college"})) == 0.7
    assert occasion_fit(frozenset({"office"}), frozenset({"wedding"})) == 0.7
    assert occasion_fit(frozenset({"summer"}), frozenset({"office"})) == 0.0
    assert occasion_fit(frozenset(), frozenset({"sports"})) == 0.5


def test_a_summer_tee_skips_formal_trousers_for_casual_jeans() -> None:
    tee = Piece(uuid.UUID(int=0), "tshirt", 49_900, frozenset({"red", "summer"}))
    formal = piece("trousers", 130_000, "white", "office")
    casual = piece("jeans", 140_000, "grey", "college")

    [pick] = assemble(
        tee,
        [Slot("bottom", ("jeans", "trousers"))],
        {"bottom": [formal, casual]},
        remaining_paise=None,
        caps=CAPS,
    )

    assert pick.piece == casual


def test_reasons_explain_colour_and_occasion() -> None:
    anchor = Piece(uuid.uuid4(), "tshirt", 49_900, frozenset({"pink", "party"}))

    chips = reasons(anchor, piece("jeans", 99_900, "black", "party", rating=4.5))

    assert chips == ["Neutral with your pink", "Also party-ready", "Rated 4.5★"]


def test_matching_beats_clashing_when_both_fit() -> None:
    clash = piece("jeans", 90_000, "red", "sports")
    match = piece("jeans", 90_000, "navy", "summer")

    [pick] = assemble(
        ANCHOR,
        [Slot("bottom", ("jeans",))],
        {"bottom": [clash, match]},
        remaining_paise=None,
        caps=CAPS,
    )

    assert pick.piece == match
