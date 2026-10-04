import uuid
from datetime import timedelta

import jwt
import pytest
from pydantic import SecretStr

from stylesense.modules.auth.exceptions import InvalidTokenError, TokenExpiredError
from stylesense.modules.auth.tokens import (
    AUDIENCE,
    AccessTokenCodec,
    hash_refresh_token,
    new_refresh_token,
)
from tests.fakes.clock import FixedClock

SECRET = "current-secret-that-is-at-least-32-chars"  # gitleaks:allow  # test fixture
OLD_SECRET = "previous-secret-that-is-at-least-32-chars"  # gitleaks:allow  # test fixture
USER_ID = uuid.UUID("018f2a3b-7c4d-7e8f-9a0b-1c2d3e4f5a6b")
FAMILY_ID = uuid.UUID("018f2a3b-0000-7000-8000-000000000001")


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


def _codec(
    clock: FixedClock, *, secret: str = SECRET, previous: tuple[str, ...] = ()
) -> AccessTokenCodec:
    return AccessTokenCodec(
        secret=SecretStr(secret),
        previous_secrets=[SecretStr(p) for p in previous],
        issuer="stylesense",
        ttl_s=900,
        clock=clock,
    )


def test_issued_token_decodes_to_the_same_claims(clock: FixedClock) -> None:
    codec = _codec(clock)

    token = codec.issue(user_id=USER_ID, session_id=FAMILY_ID, role="user")
    claims = codec.decode(token)

    assert (claims.user_id, claims.session_id, claims.role) == (USER_ID, FAMILY_ID, "user")
    assert claims.expires_at == clock.now() + timedelta(seconds=900)


def test_expired_token_is_rejected_with_specific_code(clock: FixedClock) -> None:
    codec = _codec(clock)
    token = codec.issue(user_id=USER_ID, session_id=FAMILY_ID, role="user")

    clock.advance(timedelta(seconds=900))

    with pytest.raises(TokenExpiredError) as err:
        codec.decode(token)
    assert err.value.code == "token_expired"
    assert err.value.headers["WWW-Authenticate"].startswith("Bearer")


def test_token_is_valid_until_just_before_expiry(clock: FixedClock) -> None:
    codec = _codec(clock)
    token = codec.issue(user_id=USER_ID, session_id=FAMILY_ID, role="user")

    clock.advance(timedelta(seconds=899))

    assert codec.decode(token).user_id == USER_ID


def test_tampered_payload_is_rejected(clock: FixedClock) -> None:
    codec = _codec(clock)
    header, _, signature = codec.issue(user_id=USER_ID, session_id=FAMILY_ID, role="user").split(
        "."
    )
    forged = jwt.encode({"sub": str(USER_ID), "role": "admin"}, "x" * 32, algorithm="HS256")

    with pytest.raises(InvalidTokenError):
        codec.decode(f"{header}.{forged.split('.')[1]}.{signature}")


def test_token_signed_with_unknown_secret_is_rejected(clock: FixedClock) -> None:
    stranger = _codec(clock, secret="some-other-secret-at-least-32-chars!!")
    token = stranger.issue(user_id=USER_ID, session_id=FAMILY_ID, role="admin")

    with pytest.raises(InvalidTokenError):
        _codec(clock).decode(token)


def test_alg_none_is_rejected(clock: FixedClock) -> None:
    unsigned = jwt.encode(
        {
            "sub": str(USER_ID),
            "sid": str(FAMILY_ID),
            "role": "admin",
            "iss": "stylesense",
            "aud": AUDIENCE,
            "iat": 0,
            "exp": 9_999_999_999,
            "jti": "x",
        },
        key=None,  # type: ignore[arg-type]  # deliberately unsigned
        algorithm="none",
    )

    with pytest.raises(InvalidTokenError):
        _codec(clock).decode(unsigned)


@pytest.mark.parametrize(("field", "value"), [("iss", "evil"), ("aud", "other-api")])
def test_wrong_issuer_or_audience_is_rejected(clock: FixedClock, field: str, value: str) -> None:
    now = int(clock.now().timestamp())
    claims = {
        "sub": str(USER_ID),
        "sid": str(FAMILY_ID),
        "role": "user",
        "iss": "stylesense",
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + 900,
        "jti": "x",
    }
    claims[field] = value

    with pytest.raises(InvalidTokenError):
        _codec(clock).decode(jwt.encode(claims, SECRET, algorithm="HS256"))


def test_missing_required_claim_is_rejected(clock: FixedClock) -> None:
    now = int(clock.now().timestamp())
    token = jwt.encode(
        {"sub": str(USER_ID), "iss": "stylesense", "aud": AUDIENCE, "iat": now, "exp": now + 900},
        SECRET,
        algorithm="HS256",
    )

    with pytest.raises(InvalidTokenError):
        _codec(clock).decode(token)


@pytest.mark.parametrize("garbage", ["", "not-a-jwt", "a.b.c", "Bearer x"])
def test_garbage_is_rejected(clock: FixedClock, garbage: str) -> None:
    with pytest.raises(InvalidTokenError):
        _codec(clock).decode(garbage)


def test_tokens_from_previous_secret_stay_valid_during_rotation(clock: FixedClock) -> None:
    old = _codec(clock, secret=OLD_SECRET).issue(user_id=USER_ID, session_id=FAMILY_ID, role="user")

    rotated = _codec(clock, secret=SECRET, previous=(OLD_SECRET,))

    assert rotated.decode(old).user_id == USER_ID
    new = rotated.issue(user_id=USER_ID, session_id=FAMILY_ID, role="user")
    with pytest.raises(InvalidTokenError):
        _codec(clock, secret=OLD_SECRET).decode(new)  # new tokens use the new secret only


def test_each_token_has_a_unique_id(clock: FixedClock) -> None:
    codec = _codec(clock)
    a = jwt.decode(
        codec.issue(user_id=USER_ID, session_id=FAMILY_ID, role="user"),
        options={"verify_signature": False},
    )
    b = jwt.decode(
        codec.issue(user_id=USER_ID, session_id=FAMILY_ID, role="user"),
        options={"verify_signature": False},
    )

    assert a["jti"] != b["jti"]


def test_refresh_tokens_are_long_random_and_url_safe() -> None:
    tokens = {new_refresh_token() for _ in range(100)}

    assert len(tokens) == 100
    assert all(len(t) >= 43 and t.replace("-", "").replace("_", "").isalnum() for t in tokens)


def test_refresh_token_hash_is_stable_and_not_the_token() -> None:
    token = new_refresh_token()

    assert hash_refresh_token(token) == hash_refresh_token(token)
    assert hash_refresh_token(token) != token.encode()
    assert len(hash_refresh_token(token)) == 32  # sha256 digest bytes
