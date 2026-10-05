"""Versioned public API. Every route under /v1 inherits the per-IP rate limit."""

from fastapi import APIRouter, Depends

from stylesense.api.rate_limit import rate_limited
from stylesense.api.v1 import admin_ai, app_config, auth, catalog, me, stylist

router = APIRouter(prefix="/v1", dependencies=[Depends(rate_limited("api.per_ip"))])
router.include_router(auth.router)
router.include_router(me.router)
router.include_router(app_config.router)
router.include_router(catalog.router)
router.include_router(stylist.router)
router.include_router(admin_ai.router)
