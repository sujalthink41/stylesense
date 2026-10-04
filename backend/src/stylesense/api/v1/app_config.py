from fastapi import APIRouter, Response
from pydantic import BaseModel

from stylesense.api.dependencies import SettingsDep

router = APIRouter(prefix="/app", tags=["app"])


class AppConfig(BaseModel):
    min_supported_version: str  # older builds must show a blocking "please update" screen
    latest_version: str  # older builds may show a soft "update available" prompt


@router.get("/config", summary="Public app configuration (force-update thresholds)")
async def app_config(response: Response, settings: SettingsDep) -> AppConfig:
    response.headers["Cache-Control"] = "public, max-age=300"
    return AppConfig(
        min_supported_version=settings.min_supported_app_version,
        latest_version=settings.latest_app_version,
    )
