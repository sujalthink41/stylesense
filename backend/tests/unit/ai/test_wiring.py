from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from stylesense.ai.gateway.types import ModelRef
from stylesense.bootstrap.container import build_container
from stylesense.integrations.embeddings.gateway import GatewayEmbedder
from stylesense.integrations.embeddings.hashing import HashingEmbedder
from tests.factories import make_settings


class FakeGateway:
    def __init__(self, dimensions: int) -> None:
        self.batches: list[int] = []
        self._dimensions = dimensions

    async def embed(self, ref: ModelRef, texts: Sequence[str]) -> list[list[float]]:
        self.batches.append(len(texts))
        return [[0.0] * self._dimensions for _ in texts]


async def test_gateway_embedder_batches_requests() -> None:
    gateway = FakeGateway(dimensions=8)
    embedder = GatewayEmbedder(gateway, ModelRef("openai", "e"), dimensions=8, batch_size=3)  # type: ignore[arg-type]

    vectors = await embedder.embed([f"t{i}" for i in range(7)])

    assert len(vectors) == 7
    assert gateway.batches == [3, 3, 1]
    assert embedder.model == "openai:e"


async def test_gateway_embedder_rejects_wrong_dimensions() -> None:
    embedder = GatewayEmbedder(FakeGateway(dimensions=4), ModelRef("openai", "e"), dimensions=8)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="8-dimensional"):
        await embedder.embed(["x"])


@pytest.mark.parametrize(
    "value", ["hashing", "openai:text-embedding-3-small", "ollama:nomic:latest"]
)
def test_embedding_model_setting_accepts_valid_refs(value: str) -> None:
    assert make_settings(embedding_model=value).embedding_model == value


@pytest.mark.parametrize("value", ["openai", "OpenAI:x", "openai:", ""])
def test_embedding_model_setting_rejects_malformed_refs(value: str) -> None:
    with pytest.raises(ValidationError, match="embedding_model"):
        make_settings(embedding_model=value)


def test_api_keys_never_appear_in_settings_output() -> None:
    settings = make_settings(openai_api_key="sk-live-very-secret")

    assert "sk-live-very-secret" not in repr(settings)
    assert "sk-live-very-secret" not in str(settings.model_dump())


async def test_providers_are_registered_only_when_keys_are_set() -> None:
    bare = build_container(make_settings())
    keyed = build_container(make_settings(openai_api_key="sk-x", anthropic_api_key="sk-ant-x"))
    try:
        assert bare.llm_providers == ()
        assert keyed.llm_providers == ("anthropic", "openai")
    finally:
        await bare.aclose()
        await keyed.aclose()


async def test_embedder_follows_the_embedding_model_setting() -> None:
    hashing = build_container(make_settings())
    model = build_container(make_settings(openai_api_key="sk-x", embedding_model="openai:emb"))
    try:
        assert isinstance(hashing.catalog._embedder, HashingEmbedder)
        assert isinstance(model.catalog._embedder, GatewayEmbedder)
    finally:
        await hashing.aclose()
        await model.aclose()


def test_blank_api_keys_mean_no_provider() -> None:
    settings = make_settings(openai_api_key="", anthropic_api_key="   ")

    assert (settings.openai_api_key, settings.anthropic_api_key) == (None, None)
