import pytest

from stylesense.platform.health import run_checks
from tests.fakes.health import StubHealthCheck


async def test_all_checks_passing_is_ok() -> None:
    report = await run_checks([StubHealthCheck("db"), StubHealthCheck("cache")], timeout_s=1)

    assert report.ok is True
    assert [(c.name, c.ok, c.error) for c in report.checks] == [
        ("db", True, None),
        ("cache", True, None),
    ]


async def test_failing_check_reports_only_error_type() -> None:
    failing = StubHealthCheck("db", error=ConnectionRefusedError("10.0.0.5:5432 password=x"))

    report = await run_checks([failing, StubHealthCheck("cache")], timeout_s=1)

    assert report.ok is False
    db = report.checks[0]
    assert (db.ok, db.error) == (False, "ConnectionRefusedError")


async def test_hanging_check_times_out_without_blocking_others() -> None:
    cache = StubHealthCheck("cache")

    report = await run_checks([StubHealthCheck("db", hang=True), cache], timeout_s=0.05)

    assert report.ok is False
    assert report.checks[0].error == "TimeoutError"
    assert report.checks[1].ok is True
    assert cache.calls == 1


async def test_no_checks_is_ok() -> None:
    assert (await run_checks([], timeout_s=1)).ok is True


async def test_records_non_negative_duration() -> None:
    report = await run_checks([StubHealthCheck("db")], timeout_s=1)

    assert report.checks[0].duration_ms >= 0


async def test_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValueError, match="timeout"):
        await run_checks([StubHealthCheck("db")], timeout_s=0)
