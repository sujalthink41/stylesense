import pytest

from stylesense.guards.idempotency import InvalidIdempotencyKeyError, fingerprint, validate_key


@pytest.mark.parametrize("key", ["abcdefgh", "018f2a3b-7c4d-7e8f-9a0b-1c2d3e4f5a6b", "A_b-9" * 5])
def test_accepts_well_formed_keys(key: str) -> None:
    assert validate_key(key) == key


@pytest.mark.parametrize(
    "key", ["", "short", "x" * 129, "has space here", "semi;colon-key", "ünïcode-key"]
)
def test_rejects_malformed_keys(key: str) -> None:
    with pytest.raises(InvalidIdempotencyKeyError) as err:
        validate_key(key)

    assert err.value.status_code == 400


def test_fingerprint_is_deterministic_and_order_sensitive() -> None:
    assert fingerprint("POST", "/orders", b'{"a":1}') == fingerprint("POST", "/orders", b'{"a":1}')
    assert fingerprint("POST", "/orders", b'{"a":1}') != fingerprint("/orders", "POST", b'{"a":1}')
    assert len(fingerprint("x")) == 64


def test_fingerprint_parts_cannot_collide_by_concatenation() -> None:
    assert fingerprint("ab", "c") != fingerprint("a", "bc")
