import math

from stylesense.integrations.embeddings.hashing import HashingEmbedder


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def test_vectors_have_the_configured_size_and_unit_length() -> None:
    [vector] = await HashingEmbedder(dimensions=256).embed(["navy cotton oversized tshirt"])

    assert len(vector) == 256
    assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, rel_tol=1e-9)


async def test_same_text_always_gives_the_same_vector() -> None:
    embedder = HashingEmbedder(dimensions=256)

    [a] = await embedder.embed(["linen summer shirt"])
    [b] = await HashingEmbedder(dimensions=256).embed(["linen summer shirt"])

    assert a == b


async def test_similar_items_are_closer_than_unrelated_ones() -> None:
    tee, similar_tee, sneakers = await HashingEmbedder().embed(
        [
            "Men navy oversized cotton t-shirt, casual summer",
            "Men black oversized cotton t-shirt, casual",
            "Women white chunky sneakers, synthetic leather, sports",
        ]
    )

    assert _cosine(tee, similar_tee) > _cosine(tee, sneakers) + 0.2


async def test_text_without_any_words_yields_a_zero_vector_not_an_error() -> None:
    [vector] = await HashingEmbedder(dimensions=16).embed(["..."])

    assert vector == [0.0] * 16


async def test_batches_preserve_order() -> None:
    embedder = HashingEmbedder(dimensions=64)

    batch = await embedder.embed(["a shirt", "b jeans"])
    singles = [(await embedder.embed([t]))[0] for t in ("a shirt", "b jeans")]

    assert batch == singles


def test_model_name_identifies_algorithm_and_size() -> None:
    assert HashingEmbedder(dimensions=1536).model == "hashing-v1-1536"
