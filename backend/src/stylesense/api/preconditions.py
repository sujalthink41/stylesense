"""Optimistic locking over HTTP: `ETag: "<version>"` out, `If-Match: "<version>"` back in."""

from typing import Annotated, ClassVar

from fastapi import Header, Response

from stylesense.platform.errors import AppError


class PreconditionRequiredError(AppError):
    status_code: ClassVar[int] = 428
    code: ClassVar[str] = "precondition_required"
    title: ClassVar[str] = "Send If-Match with the version you're editing"


class InvalidPreconditionError(AppError):
    status_code: ClassVar[int] = 400
    code: ClassVar[str] = "invalid_if_match"
    title: ClassVar[str] = 'If-Match must be a version, e.g. "3"'


def etag(version: int) -> str:
    return f'"{version}"'


def set_version(response: Response, version: int) -> None:
    response.headers["ETag"] = etag(version)


def IfMatch(  # noqa: N802  # FastAPI dependency
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> int:
    """The version the client last saw. Required: editing blind is how updates get lost."""
    if if_match is None:
        raise PreconditionRequiredError
    raw = if_match.strip().removeprefix("W/").strip('"')
    if not raw.isdigit():
        raise InvalidPreconditionError
    return int(raw)
