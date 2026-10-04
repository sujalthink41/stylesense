"""PII and secret scrubbing for anything that leaves the process (logs, error reports)."""

import re
from collections.abc import Mapping, MutableMapping
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEYS = frozenset(
    {"authorization", "cookie", "set-cookie", "api_key", "apikey", "x-api-key", "email", "phone"}
)
_SENSITIVE_SUFFIXES = ("password", "passwd", "secret", "token", "otp")

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"), f"Bearer {REDACTED}"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), REDACTED),
    (
        re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)(\s*[=:]\s*)\S+"),
        rf"\1\2{REDACTED}",
    ),
    # TLD must start with a letter, so versions like "pkg@1.2.3" are not mistaken for emails.
    (
        re.compile(r"[^\s@<>()\[\]:;,\"]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z][A-Za-z0-9-]*[A-Za-z0-9]"),
        REDACTED,
    ),
    # Indian mobile numbers; lookarounds avoid clipping longer digit runs (ids, timestamps).
    (re.compile(r"(?<![\d+])(?:\+91[ -]?)?[6-9]\d{9}(?!\d)"), REDACTED),
)


def _is_sensitive(key: str) -> bool:
    k = key.lower()
    return k in _SENSITIVE_KEYS or k.endswith(_SENSITIVE_SUFFIXES)


def _scrub_text(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def scrub(value: Any) -> Any:
    """Return a scrubbed deep copy; the input is never mutated."""
    if isinstance(value, str):
        return _scrub_text(value)
    if isinstance(value, Mapping):
        return {
            k: REDACTED if isinstance(k, str) and _is_sensitive(k) else scrub(v)
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return type(value)(scrub(v) for v in value)
    return value


def redact_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    scrubbed: dict[str, Any] = scrub(event_dict)
    return scrubbed
