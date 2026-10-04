import importlib.util
import logging
import sys
from typing import TextIO

import structlog
from structlog.typing import ExceptionRenderer, Processor

from stylesense.platform.observability.redaction import redact_processor
from stylesense.platform.observability.tracing import add_trace_context


def configure_logging(*, level: str, json_logs: bool, stream: TextIO | None = None) -> None:
    """Route structlog and stdlib logging through one pipeline (JSON in deployed envs)."""
    out = stream or sys.stdout
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        add_trace_context,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]
    # Never render stack-frame locals: they routinely hold tokens, bodies and PII.
    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(
            colors=out.isatty(),
            exception_formatter=_console_exception_formatter(),
        )
    )
    final: list[Processor] = [structlog.stdlib.ProcessorFormatter.remove_processors_meta]
    if json_logs:
        final.append(
            structlog.processors.ExceptionRenderer(
                structlog.tracebacks.ExceptionDictTransformer(show_locals=False)
            )
        )
    # Last step before rendering, so tracebacks and bound context are scrubbed too.
    final.append(redact_processor)
    final.append(renderer)

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    handler = logging.StreamHandler(out)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(foreign_pre_chain=shared, processors=final)
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Uvicorn installs its own handlers; let records propagate to ours instead.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = []
        uv_logger.propagate = True


def _console_exception_formatter() -> ExceptionRenderer:
    # rich is a dev-only nicety; production images don't ship it.
    if importlib.util.find_spec("rich") is None:
        return structlog.dev.plain_traceback
    return structlog.dev.RichTracebackFormatter(show_locals=False)
