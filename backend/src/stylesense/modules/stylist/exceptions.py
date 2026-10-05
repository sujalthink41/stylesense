from stylesense.platform.errors import ConflictError, NotFoundError


class SessionNotFoundError(NotFoundError):
    code = "session_not_found"
    title = "Stylist session not found"


class StaleTurnError(ConflictError):
    """The app acted on an old screen (double tap, retry, second device). Fetch the session."""

    code = "stale_turn"
    title = "The screen has moved on; refresh to continue"

    def __init__(self, current_turn: int) -> None:
        super().__init__(extra={"current_turn": current_turn})


class SessionBusyError(ConflictError):
    code = "session_busy"
    title = "Still working on your last request"

    def __init__(self, current_turn: int) -> None:
        super().__init__(extra={"current_turn": current_turn}, headers={"Retry-After": "1"})


class SessionEndedError(ConflictError):
    code = "session_ended"
    title = "This session has ended; start a new one"
