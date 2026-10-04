from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from stylesense.api.dependencies import HealthChecksDep, SettingsDep
from stylesense.platform.health import run_checks
from stylesense.platform.observability.tracing import untraced

router = APIRouter(tags=["ops"])

NO_STORE = {"Cache-Control": "no-store"}


class LivenessOut(BaseModel):
    status: Literal["ok"] = "ok"


class CheckOut(BaseModel):
    name: str
    ok: bool
    duration_ms: float
    error: str | None


class ReadinessOut(BaseModel):
    status: Literal["ok", "unavailable"]
    checks: list[CheckOut]


@router.get("/healthz", summary="Liveness: process is up")
async def healthz(response: Response) -> LivenessOut:
    # Never check dependencies here, or a DB blip would make the orchestrator restart every pod.
    response.headers.update(NO_STORE)
    return LivenessOut()


@router.get(
    "/readyz",
    summary="Readiness: dependencies reachable",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessOut}},
)
async def readyz(
    response: Response, checks: HealthChecksDep, settings: SettingsDep
) -> ReadinessOut:
    with untraced():  # probes run every few seconds; their DB/Redis spans are pure noise
        report = await run_checks(checks, timeout_s=settings.readiness_timeout_s)
    response.headers.update(NO_STORE)
    if not report.ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessOut(
        status="ok" if report.ok else "unavailable",
        checks=[
            CheckOut(name=c.name, ok=c.ok, duration_ms=round(c.duration_ms, 2), error=c.error)
            for c in report.checks
        ],
    )
