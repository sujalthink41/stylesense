from typing import ClassVar

from stylesense.platform.errors import AppError, ConflictError, NotFoundError


class BoardNotFoundError(NotFoundError):
    code = "board_not_found"
    title = "Board not found"


class VersionConflictError(AppError):
    """Someone (another device) changed the board since the app last read it."""

    status_code: ClassVar[int] = 412
    code: ClassVar[str] = "version_conflict"
    title: ClassVar[str] = "This board changed elsewhere; refresh and try again"

    def __init__(self, current_version: int) -> None:
        super().__init__(
            extra={"current_version": current_version}, headers={"ETag": f'"{current_version}"'}
        )


class BoardIdTakenError(ConflictError):
    code = "board_id_taken"
    title = "That board id is already in use"


class WishlistIsPermanentError(ConflictError):
    code = "wishlist_permanent"
    title = "The wishlist can't be deleted or renamed"


class BoardLimitError(ConflictError):
    code = "board_limit"
    title = "Too many boards; delete one first"


class ItemLimitError(ConflictError):
    code = "item_limit"
    title = "This board is full"


class InvalidOrderError(AppError):
    status_code: ClassVar[int] = 422
    code: ClassVar[str] = "invalid_order"
    title: ClassVar[str] = "The new order must list every item on the board exactly once"
