from typing import ClassVar

from stylesense.platform.errors import AppError, ConflictError, NotFoundError


class UploadNotFoundError(NotFoundError):
    code = "upload_not_found"
    title = "Photo not found"


class UploadMissingError(ConflictError):
    code = "upload_missing"
    title = "Upload the photo to the URL you were given, then confirm"


class UploadNotReadyError(ConflictError):
    code = "upload_not_ready"
    title = "This photo isn't ready to use"


class UploadRejectedError(AppError):
    status_code: ClassVar[int] = 422
    code: ClassVar[str] = "upload_rejected"
    title: ClassVar[str] = "This photo can't be used"

    def __init__(self, reason: str) -> None:
        super().__init__(reason, extra={"reason": reason})


class DailyLimitError(AppError):
    status_code: ClassVar[int] = 429
    code: ClassVar[str] = "daily_limit"
    title: ClassVar[str] = "You've reached today's limit; try again tomorrow"
