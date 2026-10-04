from typing import Any, cast

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.transport import Transport
from sentry_sdk.types import Event, Hint

from stylesense.platform.config import Settings
from stylesense.platform.observability.redaction import scrub

# Only fields that can carry user data; metadata like `release` must stay intact.
_USER_DATA_FIELDS = (
    "message",
    "logentry",
    "exception",
    "request",
    "extra",
    "breadcrumbs",
    "user",
    "contexts",
)


def _scrub_event(event: Event, _hint: Hint) -> Event:
    return cast("Event", {k: scrub(v) if k in _USER_DATA_FIELDS else v for k, v in event.items()})


def _scrub_breadcrumb(crumb: dict[str, Any], _hint: Any) -> dict[str, Any]:
    scrubbed: dict[str, Any] = scrub(crumb)
    return scrubbed


def configure_error_reporting(
    settings: Settings, *, transport: type[Transport] | None = None
) -> bool:
    """Send unexpected errors to GlitchTip (Sentry protocol). No DSN means disabled."""
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env.value,
        release=f"{settings.name}@{settings.version}",
        send_default_pii=False,
        traces_sample_rate=None,  # tracing is OpenTelemetry's job
        before_send=_scrub_event,
        before_breadcrumb=_scrub_breadcrumb,
        # Logs become breadcrumbs only; events are captured explicitly to avoid duplicates.
        integrations=[LoggingIntegration(event_level=None)],
        transport=transport,
    )
    return True


def report_exception(exc: BaseException, *, request_id: str | None) -> None:
    sentry_sdk.capture_exception(exc, tags={"request_id": request_id})
