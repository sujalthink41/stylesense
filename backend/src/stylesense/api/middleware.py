from starlette.types import ASGIApp, Receive, Scope, Send

from stylesense.guards.bulkhead import Bulkhead, BulkheadFullError
from stylesense.platform.errors import problem_response


class LoadSheddingMiddleware:
    """Caps in-flight requests per instance; beyond that, fail fast with 503 + Retry-After
    instead of queueing until everything times out.
    """

    def __init__(self, app: ASGIApp, *, bulkhead: Bulkhead, exempt_paths: frozenset[str]) -> None:
        self.app = app
        self._bulkhead = bulkhead
        self._exempt = exempt_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in self._exempt:
            await self.app(scope, receive, send)
            return
        try:
            async with self._bulkhead.slot():
                await self.app(scope, receive, send)
        except BulkheadFullError as exc:
            response = problem_response(
                scope["path"],
                status=exc.status_code,
                code=exc.code,
                title=exc.title,
                headers=exc.headers,
            )
            await response(scope, receive, send)
