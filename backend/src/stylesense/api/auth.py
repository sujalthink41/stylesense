"""Request authentication: Bearer access token → claims. No DB hit; the JWT is self-contained."""

from collections.abc import Awaitable, Callable
from typing import Annotated

import structlog
from fastapi import Depends, Request

from stylesense.api.dependencies import ContainerDep
from stylesense.modules.auth.exceptions import (
    AuthenticationRequiredError,
    InsufficientRoleError,
    InvalidTokenError,
    TokenExpiredError,
)
from stylesense.modules.auth.tokens import AccessClaims
from stylesense.modules.users.schemas import Role


def authenticate(request: Request, container: ContainerDep) -> AccessClaims:
    header = request.headers.get("Authorization")
    if not header:
        raise AuthenticationRequiredError
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise InvalidTokenError
    claims = container.token_codec.decode(token.strip())
    structlog.contextvars.bind_contextvars(user_id=str(claims.user_id))
    return claims


Claims = Annotated[AccessClaims, Depends(authenticate)]


def authenticate_optional(request: Request, container: ContainerDep) -> AccessClaims | None:
    """For public routes that personalise when they can (e.g. click attribution)."""
    if not request.headers.get("Authorization"):
        return None
    try:
        return authenticate(request, container)
    except (InvalidTokenError, TokenExpiredError):
        return None


OptionalClaims = Annotated[AccessClaims | None, Depends(authenticate_optional)]


def require_role(*roles: Role) -> Callable[[AccessClaims], Awaitable[AccessClaims]]:
    allowed = {r.value for r in roles}

    async def check(claims: Claims) -> AccessClaims:
        if claims.role not in allowed:
            raise InsufficientRoleError
        return claims

    return check
