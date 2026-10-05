from typing import ClassVar

from stylesense.platform.errors import AppError, ConflictError, NotFoundError


class PollNotFoundError(NotFoundError):
    code = "poll_not_found"
    title = "Poll not found"


class PollClosedError(ConflictError):
    code = "poll_closed"
    title = "Voting has closed"


class AlreadyVotedError(ConflictError):
    code = "already_voted"
    title = "You've already voted in this poll"

    def __init__(self, your_vote: str) -> None:
        super().__init__(extra={"your_vote": your_vote})


class InvalidOptionError(AppError):
    status_code: ClassVar[int] = 422
    code: ClassVar[str] = "invalid_option"
    title: ClassVar[str] = "That option isn't part of this poll"


class PollLimitError(ConflictError):
    code = "poll_limit"
    title = "Too many open polls; close one first"


class PollIdTakenError(ConflictError):
    code = "poll_id_taken"
    title = "That poll id is already in use"
