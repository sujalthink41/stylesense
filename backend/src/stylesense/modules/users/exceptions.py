from stylesense.platform.errors import ConflictError, ForbiddenError, UnauthorizedError


class AccountDeletedError(UnauthorizedError):
    """401 so the app drops its tokens; the account is gone or being purged."""

    code = "account_deleted"
    title = "This account has been deleted"


class AccountSuspendedError(ForbiddenError):
    code = "account_suspended"
    title = "This account is suspended"


class EmailInUseError(ConflictError):
    code = "email_in_use"
    title = "This email belongs to a different Google account"
