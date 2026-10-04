from fastapi import Request, Response

from stylesense.api.auth import Claims
from stylesense.api.dependencies import ContainerDep
from stylesense.bootstrap.container import Container
from stylesense.guards.rate_limit import DEFAULT_POLICIES, RateLimitedError


def client_ip(request: Request) -> str:
    # Uvicorn's --proxy-headers already resolved the real client behind our proxy.
    return request.client.host if request.client else "unknown"


class rate_limited:  # noqa: N801  # used like a function: Depends(rate_limited("api.per_ip"))
    """Route/router dependency enforcing a named policy per client IP."""

    def __init__(self, policy_name: str) -> None:
        if policy_name not in DEFAULT_POLICIES:
            raise ValueError(f"unknown rate limit policy '{policy_name}'")
        self.policy_name = policy_name

    async def __call__(self, request: Request, response: Response, container: ContainerDep) -> None:
        await _enforce(container, response, self.policy_name, f"ip:{client_ip(request)}")


class rate_limited_user(rate_limited):  # noqa: N801
    """Per-user policy for authenticated routes (fair share regardless of IP)."""

    async def __call__(  # type: ignore[override]
        self, response: Response, container: ContainerDep, claims: Claims
    ) -> None:
        await _enforce(container, response, self.policy_name, f"user:{claims.user_id}")


async def _enforce(
    container: Container, response: Response, policy_name: str, subject: str
) -> None:
    decision = await container.rate_limiter.hit(DEFAULT_POLICIES[policy_name], subject)
    if not decision.allowed:
        raise RateLimitedError.from_decision(decision)
    response.headers["X-RateLimit-Limit"] = str(decision.limit)
    response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
