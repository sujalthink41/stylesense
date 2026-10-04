from stylesense.modules.auth.exceptions import InvalidIdentityTokenError
from stylesense.modules.auth.ports import VerifiedIdentity


class FakeIdentityVerifier:
    """Maps opaque test tokens to identities; anything else is an invalid token."""

    def __init__(self) -> None:
        self._identities: dict[str, VerifiedIdentity | Exception] = {}

    def register(
        self, token: str, *, subject: str, email: str, name: str | None = "Test User"
    ) -> str:
        self._identities[token] = VerifiedIdentity(
            provider="google", subject=subject, email=email, name=name
        )
        return token

    def fail(self, token: str, error: Exception) -> str:
        self._identities[token] = error
        return token

    async def verify(self, id_token: str) -> VerifiedIdentity:
        outcome = self._identities.get(id_token)
        if outcome is None:
            raise InvalidIdentityTokenError
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
