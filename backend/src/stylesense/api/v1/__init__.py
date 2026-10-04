"""Versioned public API. Every route under /v1 inherits the per-IP rate limit."""

from fastapi import APIRouter, Depends

from stylesense.api.rate_limit import rate_limited

router = APIRouter(prefix="/v1", dependencies=[Depends(rate_limited("api.per_ip"))])
