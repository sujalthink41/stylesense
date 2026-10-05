from email.utils import parsedate_to_datetime

import httpx2 as httpx

_SERVER_ERROR = 500
_RETRYABLE_CLIENT_STATUSES = {408, 409, 429}


def retry_after_s(response: httpx.Response | None) -> float | None:
    """Seconds to wait from `retry-after-ms` / `retry-after` (seconds or HTTP date)."""
    if response is None:
        return None
    if (ms := response.headers.get("retry-after-ms")) is not None:
        seconds = _as_float(ms)
        return seconds / 1000 if seconds is not None else None
    value = response.headers.get("retry-after")
    if value is None:
        return None
    seconds = _as_float(value)
    return seconds if seconds is not None else _seconds_until(value, response.headers.get("date"))


def _as_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _seconds_until(http_date: str, server_date: str | None) -> float | None:
    try:
        when = parsedate_to_datetime(http_date)
        now = parsedate_to_datetime(server_date) if server_date else None
    except (TypeError, ValueError):
        return None
    return max(0.0, (when - now).total_seconds()) if now else None


def is_retryable_status(status: int) -> bool:
    return status >= _SERVER_ERROR or status in _RETRYABLE_CLIENT_STATUSES
