import re
import time
import uuid

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from stylesense.platform.errors import unexpected_error_response
from stylesense.platform.observability.error_reporting import report_exception
from stylesense.platform.observability.metrics import HttpMetrics

_SERVER_ERROR = 500
_CLIENT_ERROR = 400

REQUEST_ID_HEADER = "X-Request-ID"
UNMATCHED_ROUTE = "<unmatched>"

_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{8,64}")

logger = structlog.get_logger("stylesense.http")


def _request_id(scope: Scope) -> str:
    # Accept a caller's id only if it's safe to put in logs and headers.
    inbound = Headers(scope=scope).get(REQUEST_ID_HEADER)
    if inbound and _SAFE_REQUEST_ID.fullmatch(inbound):
        return inbound
    return uuid.uuid4().hex


def _route_template(scope: Scope) -> str:
    # Templates, not raw paths: keeps ids/PII out of logs and metric labels bounded.
    path = getattr(scope.get("route"), "path", None)
    if isinstance(path, str):
        return path
    # Plain Starlette routes (e.g. /docs) don't record themselves in the scope.
    for route in getattr(scope.get("app"), "routes", ()):
        match, _ = route.matches(scope)
        if match is Match.FULL and isinstance(getattr(route, "path", None), str):
            return str(route.path)
    return UNMATCHED_ROUTE


class RequestContextMiddleware:
    """Pure ASGI (safe for SSE streaming): request id, access log, RED metrics, last-resort 500."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        metrics: HttpMetrics | None = None,
        quiet_paths: frozenset[str] = frozenset(),
        unmetered_paths: frozenset[str] = frozenset({"/metrics"}),
    ) -> None:
        self.app = app
        self._metrics = metrics
        self._quiet = quiet_paths
        self._unmetered = unmetered_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id(scope)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        method: str = scope["method"]
        path: str = scope["path"]
        metrics = None if path in self._unmetered else self._metrics
        status = 500
        response_started = False
        started = time.perf_counter()
        if metrics:
            metrics.started(method)

        async def send_with_id(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception as exc:
            status = 500
            logger.exception("unhandled_error")
            report_exception(exc, request_id=request_id)
            if response_started:
                raise
            await unexpected_error_response(path)(scope, receive, send_with_id)
        finally:
            seconds = time.perf_counter() - started
            route = _route_template(scope)
            if metrics:
                metrics.finished(method, route, status, seconds)
            if path not in self._quiet:
                self._access_log(method, route, status, seconds)
            structlog.contextvars.clear_contextvars()

    @staticmethod
    def _access_log(method: str, route: str, status: int, seconds: float) -> None:
        if status >= _SERVER_ERROR:
            level = "error"
        elif status >= _CLIENT_ERROR:
            level = "warning"
        else:
            level = "info"
        getattr(logger, level)(
            "http_request",
            method=method,
            route=route,
            status=status,
            duration_ms=round(seconds * 1000, 2),
        )
