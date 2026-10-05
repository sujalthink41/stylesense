from stylesense.platform.errors import AppError, ServiceUnavailableError


class AIUnavailableError(ServiceUnavailableError):
    """No configured model could answer. Callers catch this and fall back to rule-based logic."""

    code = "ai_unavailable"
    title = "Smart suggestions are temporarily unavailable"


class AIBudgetExhaustedError(AIUnavailableError):
    code = "ai_budget_exhausted"


class AIQuotaExceededError(AppError):
    status_code = 429
    code = "ai_quota_exceeded"
    title = "You've hit the limit for AI features; try again later"


class AIInputTooLargeError(AppError):
    status_code = 413
    code = "ai_input_too_large"
    title = "That request is too large for the assistant"
