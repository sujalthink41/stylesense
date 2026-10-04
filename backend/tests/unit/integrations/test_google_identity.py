import base64
import hashlib
import hmac
import json
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from stylesense.integrations.google_identity import GoogleIdTokenVerifier
from stylesense.modules.auth.exceptions import (
    EmailNotVerifiedError,
    InvalidIdentityTokenError,
    SignInUnavailableError,
)

ANDROID = "android-client.apps.googleusercontent.com"
WEB = "web-client.apps.googleusercontent.com"
GOOGLE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ATTACKER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _Key:
    def __init__(self, key: Any) -> None:
        self.key = key


class FakeGoogleKeys:
    """Stands in for Google's JWKS endpoint."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error

    def get_signing_key_from_jwt(self, _token: str) -> _Key:
        if self._error:
            raise self._error
        return _Key(GOOGLE_KEY.public_key())


def _claims(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": ANDROID,
        "sub": "110169484474386276334",
        "email": "priya@example.com",
        "email_verified": True,
        "name": "Priya",
        "picture": "https://lh3.googleusercontent.com/a/x",
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


def _token(key: rsa.RSAPrivateKey = GOOGLE_KEY, **overrides: Any) -> str:
    return jwt.encode(_claims(**overrides), key, algorithm="RS256", headers={"kid": "k1"})


def _verifier(**kwargs: Any) -> GoogleIdTokenVerifier:
    return GoogleIdTokenVerifier(client_ids=[ANDROID, WEB], keys=FakeGoogleKeys(**kwargs))


async def test_valid_token_yields_identity() -> None:
    identity = await _verifier().verify(_token())

    assert identity.provider == "google"
    assert identity.subject == "110169484474386276334"
    assert identity.email == "priya@example.com"
    assert (identity.name, identity.picture_url) == (
        "Priya",
        "https://lh3.googleusercontent.com/a/x",
    )


@pytest.mark.parametrize("audience", [ANDROID, WEB])
async def test_accepts_every_configured_client(audience: str) -> None:
    assert (await _verifier().verify(_token(aud=audience))).email == "priya@example.com"


@pytest.mark.parametrize("issuer", ["accounts.google.com", "https://accounts.google.com"])
async def test_accepts_both_google_issuer_forms(issuer: str) -> None:
    assert (await _verifier().verify(_token(iss=issuer))).subject


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "someone-elses-app.apps.googleusercontent.com"},
        {"iss": "https://evil.example"},
        {"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200},
        {"sub": None},
        {"email": None},
    ],
    ids=["wrong-audience", "wrong-issuer", "expired", "no-subject", "no-email"],
)
async def test_rejects_invalid_claims(overrides: dict[str, Any]) -> None:
    with pytest.raises(InvalidIdentityTokenError):
        await _verifier().verify(_token(**overrides))


async def test_rejects_token_signed_by_someone_else() -> None:
    with pytest.raises(InvalidIdentityTokenError):
        await _verifier().verify(_token(key=ATTACKER_KEY))


async def test_rejects_algorithm_confusion_with_public_key_as_hmac_secret() -> None:
    public_pem = GOOGLE_KEY.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # Built by hand: PyJWT itself refuses to sign HMAC with a public key, attackers don't.
    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    signing_input = f"{header}.{b64(json.dumps(_claims()).encode())}"
    signature = hmac.new(public_pem, signing_input.encode(), hashlib.sha256).digest()
    forged = f"{signing_input}.{b64(signature)}"

    with pytest.raises(InvalidIdentityTokenError):
        await _verifier().verify(forged)


async def test_rejects_unverified_email() -> None:
    with pytest.raises(EmailNotVerifiedError):
        await _verifier().verify(_token(email_verified=False))


@pytest.mark.parametrize("garbage", ["", "not.a.jwt", "x" * 10])
async def test_rejects_garbage(garbage: str) -> None:
    with pytest.raises(InvalidIdentityTokenError):
        await _verifier().verify(garbage)


async def test_unknown_signing_key_is_invalid_token() -> None:
    verifier = _verifier(error=jwt.PyJWKClientError("Unable to find a signing key"))

    with pytest.raises(InvalidIdentityTokenError):
        await verifier.verify(_token())


async def test_google_keys_unreachable_is_503_not_401() -> None:
    verifier = _verifier(error=jwt.PyJWKClientConnectionError("network down"))

    with pytest.raises(SignInUnavailableError) as err:
        await verifier.verify(_token())
    assert err.value.status_code == 503


async def test_not_configured_means_sign_in_unavailable() -> None:
    verifier = GoogleIdTokenVerifier(client_ids=[], keys=FakeGoogleKeys())

    with pytest.raises(SignInUnavailableError):
        await verifier.verify(_token())


def test_email_is_normalised_to_lowercase() -> None:
    assert GoogleIdTokenVerifier.normalise_email("  Priya@Example.COM ") == "priya@example.com"
