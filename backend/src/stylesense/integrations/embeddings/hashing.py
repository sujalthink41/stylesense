"""Feature-hashing embedder: deterministic, offline, free.

Words and word pairs are hashed into a fixed-size signed vector, then L2-normalised, so items
sharing vocabulary (category, colour, fabric, fit…) end up close in cosine distance. It captures
shared *words*, not meaning; a model-based embedder replaces it in CP6 (ADR 0007).
"""

import hashlib
import itertools
import math
import re
from collections.abc import Sequence

from stylesense.modules.catalog.ports import EMBEDDING_DIMENSIONS

_WORD = re.compile(r"[a-z0-9]+")
_BIGRAM_WEIGHT = 0.5


class HashingEmbedder:
    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self.dimensions = dimensions
        self.model = f"hashing-v1-{dimensions}"

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        words = _WORD.findall(text.lower())
        features = [(w, 1.0) for w in words]
        features += [(f"{a} {b}", _BIGRAM_WEIGHT) for a, b in itertools.pairwise(words)]
        for feature, weight in features:
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0  # signed hashing cancels collision bias
            vector[index] += sign * weight
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector] if norm else vector
