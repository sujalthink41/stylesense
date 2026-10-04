from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    provider: str
    subject: str  # provider's stable user id; emails can change, this can't
    email: str
    name: str | None = None
    picture_url: str | None = None


class IdentityVerifier(Protocol):
    """Proves who the user is from a provider-issued token.

    Raises InvalidIdentityTokenError, EmailNotVerifiedError or SignInUnavailableError.
    """

    async def verify(self, id_token: str) -> VerifiedIdentity: ...
