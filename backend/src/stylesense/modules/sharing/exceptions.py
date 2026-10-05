from typing import ClassVar

from stylesense.platform.errors import AppError, NotFoundError


class ShareNotFoundError(NotFoundError):
    code = "share_not_found"
    title = "Share link not found"


class ShareGoneError(AppError):
    """The owner revoked the link or deleted what it pointed to."""

    status_code: ClassVar[int] = 410
    code: ClassVar[str] = "share_gone"
    title: ClassVar[str] = "This link is no longer available"
