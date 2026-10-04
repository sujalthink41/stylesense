import json
import logging

import pytest
import structlog

from stylesense.platform.logging import _console_exception_formatter, configure_logging


def _last_json_line(text: str) -> dict[str, object]:
    line = text.strip().splitlines()[-1]
    parsed: dict[str, object] = json.loads(line)
    return parsed


def test_structlog_emits_json_with_level_and_timestamp(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="INFO", json_logs=True)

    structlog.get_logger("test").info("order_placed", order_id="o1")

    record = _last_json_line(capsys.readouterr().out)
    assert record["event"] == "order_placed"
    assert record["order_id"] == "o1"
    assert record["level"] == "info"
    assert "timestamp" in record


def test_stdlib_logs_are_rendered_as_json_too(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="INFO", json_logs=True)

    logging.getLogger("uvicorn.error").warning("worker_restarted")

    record = _last_json_line(capsys.readouterr().out)
    assert record["event"] == "worker_restarted"
    assert record["level"] == "warning"


def test_respects_level(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="WARNING", json_logs=True)

    structlog.get_logger("test").info("too_quiet")

    assert "too_quiet" not in capsys.readouterr().out


def test_exceptions_are_rendered_as_structured_field(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="INFO", json_logs=True)

    def fail() -> None:
        raise ValueError("bad")

    try:
        fail()
    except ValueError:
        structlog.get_logger("test").exception("failed")

    record = _last_json_line(capsys.readouterr().out)
    assert "ValueError" in str(record["exception"])


def test_exception_logs_never_include_local_variables(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level="INFO", json_logs=True)

    def fail() -> None:
        api_token = "tok-super-secret-value"  # noqa: F841  # a local that must never be logged
        raise ValueError("bad")

    try:
        fail()
    except ValueError:
        structlog.get_logger("test").exception("failed")

    out = capsys.readouterr().out
    assert "tok-super-secret-value" not in out
    assert '"locals"' not in out


def test_console_falls_back_to_plain_tracebacks_without_rich(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("importlib.util.find_spec", lambda _name: None)

    assert _console_exception_formatter() is structlog.dev.plain_traceback
