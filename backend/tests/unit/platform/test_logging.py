import json
import logging

import pytest
import structlog

from stylesense.platform.logging import configure_logging


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
