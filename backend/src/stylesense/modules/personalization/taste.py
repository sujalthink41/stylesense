"""Taste learning in plain code (no LLM): a unit taste vector and per-tag affinity counters.

    like:  taste = normalize((1 - a) * taste + a * item)   a = 0.20 (right), 0.35 (super)
    skip:  taste = normalize(taste - b * item)             b = 0.05 (a skip is a weak signal)

Affinity counts +1 / +2 / -1 per tag, capped, so one binge can't dominate forever.
"""

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Literal

Direction = Literal["left", "right", "super"]

LIKE_RATE: dict[str, float] = {"right": 0.20, "super": 0.35}
SKIP_RATE = 0.05
AFFINITY_STEP: dict[str, int] = {"right": 1, "super": 2, "left": -1}
AFFINITY_CAP = 20
MAX_TAGS = 200
_AFFINITY_SCALE = 8.0  # summed affinity at which the score is ~0.96 (tanh)
_EPSILON = 1e-9


def normalize(vector: Sequence[float]) -> list[float] | None:
    norm = math.sqrt(math.fsum(x * x for x in vector))
    return None if norm < _EPSILON else [x / norm for x in vector]


def update_vector(
    taste: Sequence[float] | None, item: Sequence[float], direction: Direction
) -> list[float] | None:
    unit = normalize(item)
    if unit is None:
        return list(taste) if taste is not None else None
    if direction == "left":
        if taste is None:
            return None  # a dislike alone says nothing about what the user wants
        return normalize([t - SKIP_RATE * x for t, x in zip(taste, unit, strict=True)]) or list(
            taste
        )
    if taste is None:
        return unit
    rate = LIKE_RATE[direction]
    blended = [(1 - rate) * t + rate * x for t, x in zip(taste, unit, strict=True)]
    return normalize(blended) or unit


def blend(
    taste: Sequence[float] | None, seed: Sequence[float], weight: float
) -> list[float] | None:
    """Mix a seed (e.g. from Style DNA picks) into an existing taste without erasing it."""
    unit = normalize(seed)
    if unit is None or taste is None:
        return unit if taste is None else list(taste)
    return normalize([(1 - weight) * t + weight * s for t, s in zip(taste, unit, strict=True)])


def mean(vectors: Sequence[Sequence[float]]) -> list[float] | None:
    units = [u for v in vectors if (u := normalize(v)) is not None]
    if not units:
        return None
    return normalize([math.fsum(column) for column in zip(*units, strict=True)])


def update_affinity(affinity: Mapping[str, int], tags: Iterable[str], step: int) -> dict[str, int]:
    updated = dict(affinity)
    for tag in set(tags):
        value = max(-AFFINITY_CAP, min(AFFINITY_CAP, updated.get(tag, 0) + step))
        if value:
            updated[tag] = value
        else:
            updated.pop(tag, None)
    if len(updated) > MAX_TAGS:  # keep the strongest signals
        strongest = sorted(updated.items(), key=lambda kv: (-abs(kv[1]), kv[0]))[:MAX_TAGS]
        updated = dict(strongest)
    return updated


def affinity_score(affinity: Mapping[str, int], tags: Iterable[str]) -> float:
    """0..1, 0.5 = neutral."""
    total = sum(affinity.get(tag, 0) for tag in set(tags))
    return 0.5 + 0.5 * math.tanh(total / _AFFINITY_SCALE)
