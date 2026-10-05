from collections.abc import Sequence

from stylesense.ai.gateway.gateway import LLMGateway
from stylesense.ai.gateway.types import ModelRef
from stylesense.modules.catalog.ports import EMBEDDING_DIMENSIONS


class GatewayEmbedder:
    """Catalog Embedder backed by a provider model through the gateway (metered, budgeted,
    circuit-broken). `model` is the full ref, so switching models re-embeds the catalog.
    """

    def __init__(
        self,
        gateway: LLMGateway,
        ref: ModelRef,
        *,
        dimensions: int = EMBEDDING_DIMENSIONS,
        batch_size: int = 128,
    ) -> None:
        self._gateway = gateway
        self._ref = ref
        self.model = str(ref)
        self.dimensions = dimensions
        self._batch_size = batch_size

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = await self._gateway.embed(self._ref, texts[start : start + self._batch_size])
            vectors.extend(batch)
        if any(len(v) != self.dimensions for v in vectors):
            # Loud on purpose: a mismatched model would corrupt similarity search.
            raise ValueError(
                f"{self.model} returned vectors that aren't {self.dimensions}-dimensional"
            )
        return vectors
