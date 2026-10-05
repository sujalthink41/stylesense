from stylesense.platform.errors import ConflictError, NotFoundError, ServiceUnavailableError


class TryOnNotFoundError(NotFoundError):
    code = "tryon_not_found"
    title = "Try-on not found"


class TryOnUnavailableError(ServiceUnavailableError):
    code = "tryon_unavailable"
    title = "Try-on is unavailable right now"


class TryOnNotRetryableError(ConflictError):
    code = "tryon_not_retryable"
    title = "Only a failed try-on can be retried"
