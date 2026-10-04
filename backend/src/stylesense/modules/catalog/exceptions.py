from stylesense.platform.errors import AppError, NotFoundError


class ProductNotFoundError(NotFoundError):
    code = "product_not_found"
    title = "Product not found"


class OfferNotFoundError(NotFoundError):
    code = "offer_not_found"
    title = "This offer is no longer available"


class InvalidCursorError(AppError):
    status_code = 400
    code = "invalid_cursor"
    title = "Pagination cursor is invalid"
