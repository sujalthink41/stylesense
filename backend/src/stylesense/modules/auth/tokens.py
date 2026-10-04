"""Our own tokens: short-lived signed access JWTs and opaque, hashed refresh tokens."""

import hashlib
import secrets
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pydantic import SecretStr

from stylesense.modules.auth.exceptions import InvalidTokenError, TokenExpiredError
from stylesense.platform.clock import Clock

AUDIENCE = "stylesense-api"
_ALGORITHM = "HS256"
_REQUIRED_CLAIMS = ["sub", "sid", "role", "iss", "aud", "iat", "exp", "jti"]


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID  # refresh-token family: logout/theft revokes the whole session
    role: str
    expires_at: datetime


class AccessTokenCodec:
    def __init__(
        self,
        *,
        secret: SecretStr,
        previous_secrets: Sequence[SecretStr],
        issuer: str,
        ttl_s: int,
        clock: Clock,
    ) -> None:
        self._signing_key = secret.get_secret_value()
        # Verify with old keys too, so rotating the secret doesn't log everyone out.
        self._verify_keys = [self._signing_key, *(s.get_secret_value() for s in previous_secrets)]
        self._issuer = issuer
        self._ttl = timedelta(seconds=ttl_s)
        self._clock = clock

    @property
    def ttl_s(self) -> int:
        return int(self._ttl.total_seconds())

    def issue(self, *, user_id: uuid.UUID, session_id: uuid.UUID, role: str) -> str:
        now = self._clock.now()
        payload = {
            "sub": str(user_id),
            "sid": str(session_id),
            "role": role,
            "iss": self._issuer,
            "aud": AUDIENCE,
            "iat": int(now.timestamp()),
            "exp": int((now + self._ttl).timestamp()),
            "jti": uuid.uuid4().hex,
        }
        return jwt.encode(payload, self._signing_key, algorithm=_ALGORITHM)

    def decode(self, token: str) -> AccessClaims:
        payload = self._verified_payload(token)
        expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
        # Expiry is checked against the injected clock, not the OS clock.
        if self._clock.now() >= expires_at:
            raise TokenExpiredError
        try:
            return AccessClaims(
                user_id=uuid.UUID(payload["sub"]),
                session_id=uuid.UUID(payload["sid"]),
                role=str(payload["role"]),
                expires_at=expires_at,
            )
        except (ValueError, TypeError) as exc:
            raise InvalidTokenError from exc

    def _verified_payload(self, token: str) -> dict[str, Any]:
        for key in self._verify_keys:
            try:
                payload: dict[str, Any] = jwt.decode(
                    token,
                    key,
                    algorithms=[_ALGORITHM],  # pinned: blocks alg=none and algorithm confusion
                    audience=AUDIENCE,
                    issuer=self._issuer,
                    options={"verify_exp": False, "require": _REQUIRED_CLAIMS},
                )
            except jwt.InvalidSignatureError:
                continue
            except jwt.PyJWTError as exc:
                raise InvalidTokenError from exc
            return payload
        raise InvalidTokenError


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits of entropy


def hash_refresh_token(token: str) -> bytes:
    # Tokens are high-entropy random, so a fast hash is enough (no salt or KDF needed).
    return hashlib.sha256(token.encode()).digest()
