"""Domain error taxonomy rendered as RFC 9457 problem+json."""

import logging
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, ClassVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from stylesense.platform.observability.context import current_request_id

PROBLEM_JSON = "application/problem+json"

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base for all expected errors. Subclass and override the class attributes."""

    status_code: ClassVar[int] = 500
    code: ClassVar[str] = "internal_error"
    title: ClassVar[str] = "Internal server error"

    def __init__(
        self,
        detail: str | None = None,
        *,
        extra: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        self.extra = dict(extra or {})
        self.headers = dict(headers or {})


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    title = "Authentication required"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    title = "Not allowed"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    title = "Resource not found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    title = "Conflict with current state"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
    title = "Service temporarily unavailable"

    def __init__(self, detail: str | None = None, *, retry_after_s: int | None = None) -> None:
        headers = {"Retry-After": str(retry_after_s)} if retry_after_s is not None else None
        super().__init__(detail, headers=headers)


def problem_response(
    instance: str,
    *,
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    extra: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"/problems/{code}",
        "title": title,
        "status": status,
    }
    if detail:
        body["detail"] = detail
    body["instance"] = instance
    body["code"] = code
    if request_id := current_request_id():
        body["request_id"] = request_id
    body.update(extra or {})
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


def unexpected_error_response(instance: str) -> JSONResponse:
    return problem_response(instance, status=500, code=AppError.code, title=AppError.title)


def _code_for(status: int) -> str:
    return HTTPStatus(status).phrase.lower().replace(" ", "_").replace("-", "_")


async def _handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101  # narrowed by registration
    return problem_response(
        request.url.path,
        status=exc.status_code,
        code=exc.code,
        title=exc.title,
        detail=exc.detail,
        extra=exc.extra,
        headers=exc.headers,
    )


async def _handle_http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    phrase = HTTPStatus(exc.status_code).phrase
    return problem_response(
        request.url.path,
        status=exc.status_code,
        code=_code_for(exc.status_code),
        title=phrase,
        headers=exc.headers,
    )


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    # Drop `input`/`ctx`: echoing user input back can leak PII into logs and clients.
    errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return problem_response(
        request.url.path,
        status=422,
        code="validation_error",
        title="Request validation failed",
        extra={"errors": errors},
    )


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", extra={"path": request.url.path}, exc_info=exc)
    return unexpected_error_response(request.url.path)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected)
