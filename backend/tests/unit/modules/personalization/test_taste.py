import math

from hypothesis import given
from hypothesis import strategies as st

from stylesense.modules.personalization.taste import (
    AFFINITY_CAP,
    MAX_TAGS,
    affinity_score,
    blend,
    mean,
    normalize,
    update_affinity,
    update_vector,
)

X, Y = [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]


def _cos(a: list[float], b: list[float]) -> float:
    return sum(p * q for p, q in zip(a, b, strict=True))


def test_first_like_becomes_the_taste() -> None:
    assert update_vector(None, [3.0, 0.0, 0.0], "right") == X


def test_a_dislike_alone_learns_nothing() -> None:
    assert update_vector(None, X, "left") is None


def test_likes_pull_taste_towards_the_item_and_super_pulls_harder() -> None:
    right = update_vector(X, Y, "right")
    sup = update_vector(X, Y, "super")
    assert right is not None
    assert sup is not None

    assert _cos(right, Y) > 0
    assert _cos(sup, Y) > _cos(right, Y)


def test_skips_push_taste_away_from_the_item() -> None:
    taste = normalize([1.0, 1.0, 0.0])
    assert taste is not None

    after = update_vector(taste, Y, "left")

    assert after is not None
    assert _cos(after, Y) < _cos(taste, Y)


def test_zero_vectors_never_break_the_taste() -> None:
    assert update_vector(X, [0.0, 0.0, 0.0], "right") == X
    assert update_vector(None, [0.0, 0.0, 0.0], "super") is None
    assert normalize([0.0, 0.0]) is None


def test_ten_likes_of_one_style_converge_on_it() -> None:
    taste: list[float] | None = X
    for _ in range(10):
        taste = update_vector(taste, Y, "right")

    assert taste is not None
    assert _cos(taste, Y) > 0.9


vectors = st.lists(st.floats(min_value=-10, max_value=10), min_size=3, max_size=3)


@given(taste=vectors, item=vectors, direction=st.sampled_from(["left", "right", "super"]))
def test_taste_is_always_unit_length_or_absent(
    taste: list[float], item: list[float], direction: str
) -> None:
    result = update_vector(normalize(taste), item, direction)  # type: ignore[arg-type]

    assert result is None or math.isclose(math.hypot(*result), 1.0, rel_tol=1e-6)


def test_blend_seeds_an_empty_taste_and_keeps_an_existing_one() -> None:
    assert blend(None, [0.0, 2.0, 0.0], 0.5) == Y
    mixed = blend(X, Y, 0.5)
    assert mixed is not None
    assert math.isclose(_cos(mixed, X), _cos(mixed, Y))
    assert blend(X, [0.0, 0.0, 0.0], 0.5) == X


def test_mean_ignores_zero_vectors() -> None:
    assert mean([[2.0, 0.0, 0.0], [0.0, 0.0, 0.0]]) == X
    assert mean([]) is None


def test_affinity_counts_capped_and_zero_entries_dropped() -> None:
    affinity = update_affinity({}, ["linen", "linen", "oversized"], 2)
    assert affinity == {"linen": 2, "oversized": 2}

    affinity = update_affinity(affinity, ["oversized"], -2)
    assert affinity == {"linen": 2}

    for _ in range(50):
        affinity = update_affinity(affinity, ["linen"], 1)
    assert affinity["linen"] == AFFINITY_CAP


def test_affinity_keeps_only_the_strongest_tags() -> None:
    affinity = {f"tag{i}": 1 for i in range(MAX_TAGS)}

    updated = update_affinity(affinity, ["strong"], 5)

    assert len(updated) == MAX_TAGS
    assert updated["strong"] == 5


def test_affinity_score_is_neutral_without_signal_and_bounded() -> None:
    assert affinity_score({}, ["linen"]) == 0.5
    liked = affinity_score({"linen": 20, "summer": 20}, ["linen", "summer"])
    disliked = affinity_score({"neon": -20}, ["neon"])
    assert 0.5 < liked <= 1.0
    assert 0.0 <= disliked < 0.5
