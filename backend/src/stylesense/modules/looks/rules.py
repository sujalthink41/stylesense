"""Complete the look, in plain code: which categories go together, which colours and occasions
match, and the best affordable combination. Pure (no I/O), so the budget rules are provable.

    score(piece) = 0.45 · colour harmony + 0.30 · occasion fit + 0.25 · rating confidence
    look = argmax Σ (1 + score) over one optional piece per slot, s.t. Σ price ≤ remaining
"""

import itertools
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

NEUTRALS = frozenset({"black", "white", "navy", "beige", "grey", "off-white", "olive", "brown"})
COLORS = NEUTRALS | {"maroon", "sky blue", "mustard", "pink", "red", "green", "lavender"}
CASUAL = frozenset({"casual", "summer", "college", "sports", "travel", "winter"})
DRESSY = frozenset({"office", "wedding", "festive", "party", "date night"})
OCCASIONS = CASUAL | DRESSY
COLD = frozenset({"winter", "travel"})

W_HARMONY, W_OCCASION, W_RATING = 0.45, 0.30, 0.25
FILL_BONUS = 1.0  # a fuller look beats a slightly better-matched smaller one
CANDIDATES_PER_SLOT = 6  # brute force stays tiny: at most (6 + 3 + 1) ** 3 combinations
_CONFIDENT_RATINGS = 200


@dataclass(frozen=True, slots=True)
class Slot:
    name: str
    categories: tuple[str, ...]
    only_when: frozenset[str] = frozenset()  # e.g. a layer only for cold occasions


_SHOES = Slot("shoes", ("sneakers",))
_LAYER = Slot("layer", ("jacket", "hoodie"), only_when=COLD)
_BOTTOM = Slot("bottom", ("jeans", "trousers", "shorts"))
_TOP = Slot("top", ("tshirt", "shirt", "top"))

COMPLEMENTS: dict[str, tuple[Slot, ...]] = {
    "tshirt": (_BOTTOM, _SHOES, _LAYER),
    "shirt": (Slot("bottom", ("trousers", "jeans")), _SHOES, Slot("layer", ("jacket",), COLD)),
    "top": (_BOTTOM, _SHOES, Slot("layer", ("jacket",), COLD)),
    "kurta": (Slot("bottom", ("trousers", "jeans")), _SHOES),
    "hoodie": (Slot("bottom", ("jeans", "trousers")), _SHOES),
    "dress": (_SHOES, Slot("layer", ("jacket",), COLD)),
    "jacket": (_TOP, Slot("bottom", ("jeans", "trousers")), _SHOES),
    "jeans": (_TOP, _SHOES, _LAYER),
    "trousers": (Slot("top", ("shirt", "tshirt", "top")), _SHOES),
    "shorts": (Slot("top", ("tshirt", "top")), _SHOES),
    "sneakers": (_TOP, _BOTTOM),
}


@dataclass(frozen=True, slots=True)
class Piece:
    id: uuid.UUID
    category: str
    price_paise: int | None
    tags: frozenset[str] = field(default_factory=frozenset)
    rating: float | None = None
    rating_count: int = 0

    @property
    def colors(self) -> frozenset[str]:
        return self.tags & COLORS

    @property
    def occasions(self) -> frozenset[str]:
        return self.tags & OCCASIONS


@dataclass(frozen=True, slots=True)
class Pick:
    slot: str
    piece: Piece
    score: float


def slots_for(category: str, context: Iterable[str] = ()) -> list[Slot]:
    """Slots to fill for an anchor; `context` = anchor tags plus the session's occasion."""
    context = set(context)
    return [s for s in COMPLEMENTS.get(category, ()) if not s.only_when or s.only_when & context]


def harmony(anchor: frozenset[str], other: frozenset[str]) -> float:
    """Neutrals go with anything; one bold colour against neutrals pops; two bolds clash."""
    if not other or other <= NEUTRALS:
        return 1.0
    if not anchor or anchor <= NEUTRALS:
        return 0.8
    return 0.4 if other & anchor else 0.2


def occasion_fit(anchor: frozenset[str], other: frozenset[str]) -> float:
    """Same occasion fits best; same register (casual vs dressy) is fine; mixing registers
    (formal trousers with a summer tee) is the clash to avoid."""
    if not anchor or not other:
        return 0.5  # nothing to go on: neutral
    if anchor & other:
        return 1.0
    if (anchor <= CASUAL and other & CASUAL) or (anchor <= DRESSY and other & DRESSY):
        return 0.7
    return 0.0


def score(anchor: Piece, piece: Piece) -> float:
    rating = 0.0
    if piece.rating is not None:
        quality = min(1.0, max(0.0, (piece.rating - 3.0) / 2.0))
        rating = quality * min(1.0, piece.rating_count / _CONFIDENT_RATINGS)
    return (
        W_HARMONY * harmony(anchor.colors, piece.colors)
        + W_OCCASION * occasion_fit(anchor.occasions, piece.occasions)
        + W_RATING * rating
    )


def assemble(
    anchor: Piece,
    slots: Sequence[Slot],
    candidates: Mapping[str, Sequence[Piece]],
    *,
    remaining_paise: int | None,
    caps: Mapping[str, int],
) -> list[Pick]:
    """Best look within budget: at most one piece per slot, never the anchor or a repeat,
    never a casual/dressy clash, each piece under its category cap, and the total never
    above `remaining_paise`."""
    options: list[list[Pick | None]] = []
    for slot in slots:
        eligible = [
            Pick(slot.name, p, score(anchor, p))
            for p in candidates.get(slot.name, ())
            if _buyable(p, anchor, slot, caps, remaining_paise)
            and occasion_fit(anchor.occasions, p.occasions) > 0  # a clash is worse than nothing
        ]
        eligible = _unique(sorted(eligible, key=lambda pick: (-pick.score, str(pick.piece.id))))
        # The best matches, plus the cheapest few so a tight budget still finds a fit (as many
        # as there are slots: other slots can take at most all but one of them).
        cheapest = sorted(
            eligible, key=lambda pick: (pick.piece.price_paise or 0, str(pick.piece.id))
        )
        shortlist = _unique(eligible[:CANDIDATES_PER_SLOT] + cheapest[: len(slots)])
        options.append([*shortlist, None])

    best: tuple[float, tuple[str, ...]] | None = None
    best_look: list[Pick] = []
    for combo in itertools.product(*options):
        look = [p for p in combo if p is not None]
        ids = [str(p.piece.id) for p in look]
        if len(set(ids)) != len(ids):
            continue  # the same product can't fill two slots
        total = sum(p.piece.price_paise or 0 for p in look)
        if remaining_paise is not None and total > remaining_paise:
            continue
        key = (sum(FILL_BONUS + p.score for p in look), tuple(sorted(ids)))
        # Higher value wins; on equal value the lexicographically smallest ids (deterministic).
        if best is None or key[0] > best[0] or (key[0] == best[0] and key[1] < best[1]):
            best, best_look = key, look
    return best_look


def _buyable(
    piece: Piece,
    anchor: Piece,
    slot: Slot,
    caps: Mapping[str, int],
    remaining: int | None,
) -> bool:
    if piece.id == anchor.id or piece.price_paise is None or piece.category not in slot.categories:
        return False
    if piece.price_paise > caps.get(piece.category, piece.price_paise):
        return False
    return remaining is None or piece.price_paise <= remaining


def _unique(picks: list[Pick]) -> list[Pick]:
    seen: set[uuid.UUID] = set()
    out = []
    for pick in picks:
        if pick.piece.id not in seen:
            seen.add(pick.piece.id)
            out.append(pick)
    return out


def reasons(anchor: Piece, piece: Piece) -> list[str]:
    """Short chips: why this piece goes with the anchor."""
    out: list[str] = []
    bold = sorted(anchor.colors - NEUTRALS)
    if piece.colors and piece.colors <= NEUTRALS:
        out.append(f"Neutral with your {bold[0]}" if bold else "Easy neutral")
    elif bold == [] and piece.colors:
        out.append(f"{sorted(piece.colors)[0].title()} adds colour")
    shared = sorted(anchor.occasions & piece.occasions)
    if shared:
        out.append(f"Also {shared[0]}-ready")
    if piece.rating is not None and piece.rating >= 4.0:  # noqa: PLR2004
        out.append(f"Rated {piece.rating:.1f}★")
    return [r[:40] for r in out][:3]
