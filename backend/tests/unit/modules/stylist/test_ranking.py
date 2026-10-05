import uuid

from hypothesis import given
from hypothesis import strategies as st

from stylesense.modules.catalog.schemas import ProductSummary, SearchHit
from stylesense.modules.stylist.explain import clean, rule_reasons
from stylesense.modules.stylist.ranking import rank
from stylesense.modules.stylist.slots import Slots


def _hit(
    *,
    price: int | None = 49_900,
    tags: tuple[str, ...] = (),
    brand: str = "Kalaa",
    rating: float | None = 4.2,
    count: int = 300,
    similarity: float | None = None,
    offers: int = 1,
) -> SearchHit:
    product = ProductSummary(
        id=uuid.uuid4(),
        title="Item",
        brand=brand,
        category="tshirt",
        subcategory=None,
        gender="men",
        primary_image_url=None,
        min_price_paise=price,
        rating=rating,
        rating_count=count,
        offer_count=offers,
        best_store="myntra",
        tags=list(tags),
    )
    return SearchHit(product=product, similarity=similarity)


SUMMER_LINEN = Slots(category="shirt", occasion="summer", fabric="linen", budget_max_paise=150_000)


def test_items_matching_requested_attributes_rank_first() -> None:
    plain = _hit(tags=("shirt",))
    perfect = _hit(tags=("shirt", "linen", "summer"))
    half = _hit(tags=("shirt", "linen"))

    ranked = rank([plain, half, perfect], SUMMER_LINEN, limit=3)

    assert [r.hit for r in ranked] == [perfect, half, plain]
    assert ranked[0].matched == ("linen", "summer")


def test_text_similarity_breaks_ties_between_equal_matches() -> None:
    close, far = _hit(similarity=0.9), _hit(similarity=0.1)

    assert [r.hit for r in rank([far, close], Slots(), limit=2)] == [close, far]


def test_well_rated_items_with_many_reviews_beat_few_reviews() -> None:
    trusted = _hit(rating=4.6, count=2_000)
    unproven = _hit(rating=5.0, count=3)

    assert rank([unproven, trusted], Slots(), limit=2)[0].hit == trusted


def test_one_brand_cannot_fill_the_deck() -> None:
    hits = [_hit(brand="Kalaa", rating=4.6) for _ in range(5)] + [_hit(brand="Sutra", rating=4.3)]

    top3 = [r.hit.product.brand for r in rank(hits, Slots(), limit=3)]

    assert "Sutra" in top3


def test_items_without_a_price_are_never_shown() -> None:
    assert rank([_hit(price=None)], Slots(), limit=5) == []


@given(
    prices=st.lists(st.integers(min_value=100, max_value=1_000_000), min_size=1, max_size=30),
    low=st.integers(min_value=0, max_value=200_000),
    span=st.integers(min_value=1, max_value=800_000),
)
def test_results_never_break_the_budget(prices: list[int], low: int, span: int) -> None:
    slots = Slots(budget_min_paise=low, budget_max_paise=low + span)

    for item in rank([_hit(price=p) for p in prices], slots, limit=30):
        assert low <= item.hit.product.min_price_paise <= low + span  # type: ignore[operator]


def test_limit_is_respected_and_ranking_is_deterministic() -> None:
    hits = [_hit(rating=4.0 + i / 100) for i in range(20)]

    first, second = rank(hits, Slots(), limit=5), rank(list(reversed(hits)), Slots(), limit=5)

    assert len(first) == 5
    assert [r.hit for r in first] == [r.hit for r in second]


# ---------- reasons ----------


def test_rule_reasons_explain_matches_budget_rating_and_price() -> None:
    item = rank([_hit(tags=("linen", "summer"), rating=4.4, offers=3)], SUMMER_LINEN, limit=1)[0]

    assert rule_reasons(item, SUMMER_LINEN) == ["Linen", "Made for summer", "Within ₹1,500"]


def test_reasons_are_deduped_trimmed_and_capped() -> None:
    reasons = clean(
        ["  Breathable   cotton ", "breathable cotton", "x" * 80, "Rated 4.5★", "Extra"]
    )

    assert reasons == ["Breathable cotton", "x" * 40, "Rated 4.5★"]


# ---------- taste (CP9) ----------


def test_without_taste_the_order_is_unchanged() -> None:
    hits = [_hit(tags=("linen",), rating=4.0), _hit(tags=("oversized",), rating=4.6)]

    assert [r.hit for r in rank(hits, Slots(), limit=2)] == [
        r.hit for r in rank(hits, Slots(), limit=2, affinity={})
    ]


def test_tag_affinity_lifts_liked_styles_over_better_rated_items() -> None:
    liked = _hit(tags=("oversized", "graphic print"), rating=4.1)
    plain = _hit(tags=("regular",), rating=4.6)

    ranked = rank([plain, liked], Slots(), limit=2, affinity={"oversized": 10, "graphic print": 6})

    assert ranked[0].hit == liked
    assert ranked[0].liked == ("oversized", "graphic print")


def test_disliked_tags_sink() -> None:
    neon = _hit(tags=("neon",), rating=4.6)
    other = _hit(tags=("solid",), rating=4.4)

    assert rank([neon, other], Slots(), limit=2, affinity={"neon": -10})[0].hit == other


def test_taste_vector_similarity_reorders_without_any_affinity() -> None:
    close = _hit(rating=4.2)
    far = _hit(rating=4.2)
    hits = [
        SearchHit(product=far.product, similarity=None, taste_similarity=0.1),
        SearchHit(product=close.product, similarity=None, taste_similarity=0.9),
    ]

    assert rank(hits, Slots(), limit=2)[0].hit.product == close.product


def test_requested_attributes_still_beat_taste() -> None:
    requested = _hit(tags=("linen", "summer"), rating=4.0)
    tasteful = _hit(tags=("oversized",), rating=4.0)

    ranked = rank([tasteful, requested], SUMMER_LINEN, limit=2, affinity={"oversized": 20})

    assert ranked[0].hit == requested


def test_reasons_mention_the_users_style() -> None:
    item = rank(
        [_hit(tags=("oversized",), rating=3.5)], Slots(), limit=1, affinity={"oversized": 5}
    )[0]

    assert rule_reasons(item, Slots()) == ["Your style: oversized"]


def test_vague_tags_are_learned_from_but_never_shown_as_a_reason() -> None:
    item = rank(
        [_hit(tags=("half", "olive"), rating=3.5)],
        Slots(),
        limit=1,
        affinity={"half": 9, "olive": 2},
    )[0]

    assert item.liked == ("half", "olive")
    assert rule_reasons(item, Slots()) == ["Your style: olive"]


def test_what_you_can_see_outranks_a_shared_occasion() -> None:
    # A photographed sky-blue denim jacket: the denim one beats a casual windcheater.
    wanted = Slots(category="jacket", occasion="casual", colors=["sky blue"], fabric="denim")
    windcheater = _hit(tags=("jacket", "casual"), brand="A")
    denim = _hit(tags=("jacket", "denim", "sky blue"), brand="B")

    ranked = rank([windcheater, denim], wanted, limit=2)

    assert ranked[0].hit is denim
    assert set(ranked[0].matched) == {"denim", "sky blue"}
