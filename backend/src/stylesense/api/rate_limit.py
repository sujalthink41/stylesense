from fastapi import Request, Response

from stylesense.api.dependencies import ContainerDep
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
        policy = DEFAULT_POLICIES[self.policy_name]
        decision = await container.rate_limiter.hit(policy, f"ip:{client_ip(request)}")
        if not decision.allowed:
            raise RateLimitedError.from_decision(decision)
        response.headers["X-RateLimit-Limit"] = str(decision.limit)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
