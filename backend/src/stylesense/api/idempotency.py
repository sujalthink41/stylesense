from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Header, Request, Response
from pydantic import TypeAdapter

from stylesense.bootstrap.container import Container
from stylesense.guards.idempotency import fingerprint, validate_key
from stylesense.platform.errors import AppError

REPLAYED_HEADER = "Idempotent-Replayed"


class IdempotencyKeyRequiredError(AppError):
    status_code = 400
    code = "idempotency_key_required"
    title = "This operation requires an Idempotency-Key header"


def IdempotencyKey(  # noqa: N802  # FastAPI dependency, reads like a type at call sites
    key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if key is None:
        raise IdempotencyKeyRequiredError
    return validate_key(key)


async def run_idempotent[T](
    request: Request,
    response: Response,
    container: Container,
    *,
    key: str,
    principal: str,
    operation: Callable[[], Awaitable[T]],
    adapter: TypeAdapter[T],
) -> T:
    """Run a write at most once per (principal, route, key); replays return the stored result."""
    route = getattr(request.scope.get("route"), "path", request.url.path)
    outcome = await container.idempotency.run(
        scope=f"{principal}:{request.method} {route}",
        key=key,
        fingerprint=fingerprint(request.method, route, await request.body()),
        operation=operation,
        adapter=adapter,
    )
    if outcome.replayed:
        response.headers[REPLAYED_HEADER] = "true"
    return outcome.value
