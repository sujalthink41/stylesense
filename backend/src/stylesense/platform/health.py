import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class HealthCheck(Protocol):
    """A dependency probe; `check` raises when the dependency is unhealthy."""

    name: str

    async def check(self) -> None: ...


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    ok: bool
    duration_ms: float
    # Exception type only: probe output must never leak hosts or credentials.
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    checks: tuple[CheckResult, ...]

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)


async def run_checks(checks: Sequence[HealthCheck], *, timeout_s: float) -> ReadinessReport:
    """Run all probes concurrently; each one is bounded by `timeout_s`."""
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")
    results = await asyncio.gather(*(_run_one(c, timeout_s) for c in checks))
    return ReadinessReport(checks=tuple(results))


async def _run_one(check: HealthCheck, timeout_s: float) -> CheckResult:
    started = time.perf_counter()
    error: str | None = None
    try:
        async with asyncio.timeout(timeout_s):
            await check.check()
    except Exception as exc:  # noqa: BLE001  # any failure means "not ready"
        error = type(exc).__name__
    elapsed_ms = (time.perf_counter() - started) * 1000
    return CheckResult(name=check.name, ok=error is None, duration_ms=elapsed_ms, error=error)
