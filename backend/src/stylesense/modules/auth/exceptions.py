from typing import Any

from stylesense.platform.errors import ForbiddenError, ServiceUnavailableError, UnauthorizedError


class _BearerChallengeError(UnauthorizedError):
    """401s carry WWW-Authenticate so clients know to (re)authenticate."""

    def __init__(self, detail: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            detail, headers={"WWW-Authenticate": f'Bearer error="{self.code}"'}, **kwargs
        )


class AuthenticationRequiredError(_BearerChallengeError):
    code = "authentication_required"
    title = "Sign in to continue"


class TokenExpiredError(_BearerChallengeError):
    code = "token_expired"
    title = "Access token expired; refresh it"


class InvalidTokenError(_BearerChallengeError):
    code = "invalid_token"
    title = "Access token is invalid"


class InvalidRefreshTokenError(_BearerChallengeError):
    code = "invalid_refresh_token"
    title = "Session expired; sign in again"


class RefreshTokenReusedError(_BearerChallengeError):
    code = "refresh_token_reused"
    title = "Session revoked for your security; sign in again"


class InvalidIdentityTokenError(_BearerChallengeError):
    code = "invalid_id_token"
    title = "Google sign-in could not be verified"


class EmailNotVerifiedError(ForbiddenError):
    code = "email_not_verified"
    title = "Verify your Google account email first"


class InsufficientRoleError(ForbiddenError):
    code = "insufficient_role"
    title = "You don't have access to this"


class SignInUnavailableError(ServiceUnavailableError):
    code = "sign_in_unavailable"
    title = "Sign-in is temporarily unavailable"
