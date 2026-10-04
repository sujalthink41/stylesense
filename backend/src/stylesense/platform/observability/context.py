import structlog


def current_request_id() -> str | None:
    value = structlog.contextvars.get_contextvars().get("request_id")
    return value if isinstance(value, str) else None
