"""Verifies Google ID tokens locally against Google's published signing keys."""

import asyncio
from collections.abc import Sequence
from typing import Any, Protocol

import jwt

from stylesense.modules.auth.exceptions import (
    EmailNotVerifiedError,
    InvalidIdentityTokenError,
    SignInUnavailableError,
)
from stylesense.modules.auth.ports import VerifiedIdentity

GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ["accounts.google.com", "https://accounts.google.com"]
_CLOCK_SKEW_S = 60  # tolerate small clock drift between Google and us


class SigningKeys(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> Any: ...


def google_signing_keys() -> SigningKeys:
    # Keys are cached in-process; Google rotates them roughly daily.
    return jwt.PyJWKClient(GOOGLE_CERTS_URL, cache_keys=True, lifespan=3_600, timeout=5)


class GoogleIdTokenVerifier:
    def __init__(self, *, client_ids: Sequence[str], keys: SigningKeys) -> None:
        self._client_ids = list(client_ids)
        self._keys = keys

    async def verify(self, id_token: str) -> VerifiedIdentity:
        if not self._client_ids:
            raise SignInUnavailableError("Google sign-in is not configured")
        key = await self._signing_key(id_token)
        try:
            # RS256 pinned: a public key must never be accepted as an HMAC secret.
            claims: dict[str, Any] = jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                audience=self._client_ids,  # only tokens minted for *our* app
                issuer=GOOGLE_ISSUERS,
                leeway=_CLOCK_SKEW_S,
                options={"require": ["iss", "aud", "sub", "exp", "iat"]},
            )
        except jwt.PyJWTError as exc:
            raise InvalidIdentityTokenError from exc

        email = claims.get("email")
        if not isinstance(email, str) or not email.strip():
            raise InvalidIdentityTokenError("Google account has no email")
        if claims.get("email_verified") is not True:
            raise EmailNotVerifiedError
        return VerifiedIdentity(
            provider="google",
            subject=str(claims["sub"]),
            email=self.normalise_email(email),
            name=claims.get("name"),
            picture_url=claims.get("picture"),
        )

    async def _signing_key(self, id_token: str) -> Any:
        try:
            # PyJWKClient does blocking HTTP on cache miss; keep it off the event loop.
            signing_key = await asyncio.to_thread(self._keys.get_signing_key_from_jwt, id_token)
        except jwt.PyJWKClientConnectionError as exc:
            raise SignInUnavailableError("could not reach Google", retry_after_s=5) from exc
        except jwt.PyJWTError as exc:
            raise InvalidIdentityTokenError from exc
        return signing_key.key

    @staticmethod
    def normalise_email(email: str) -> str:
        return email.strip().lower()
