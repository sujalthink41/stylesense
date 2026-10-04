import asyncio

import httpx2
from fastapi import FastAPI

from stylesense.api.middleware import LoadSheddingMiddleware
from stylesense.guards.bulkhead import Bulkhead
from stylesense.platform.errors import register_error_handlers


def _app(release: asyncio.Event) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(
        LoadSheddingMiddleware,
        bulkhead=Bulkhead("http", max_concurrent=1, max_waiting=0, retry_after_s=2),
        exempt_paths=frozenset({"/healthz"}),
    )

    @app.get("/slow")
    async def slow() -> dict[str, str]:
        await release.wait()
        return {"ok": "yes"}

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


async def test_sheds_excess_requests_with_503_and_retry_after() -> None:
    release = asyncio.Event()
    transport = httpx2.ASGITransport(app=_app(release))
    async with httpx2.AsyncClient(transport=transport, base_url="http://t") as client:
        busy = asyncio.create_task(client.get("/slow"))
        await asyncio.sleep(0.05)

        shed = await client.get("/slow")
        release.set()
        ok = await busy

    assert ok.status_code == 200
    assert shed.status_code == 503
    assert shed.headers["retry-after"] == "2"
    assert shed.headers["content-type"] == "application/problem+json"
    assert shed.json()["code"] == "capacity_exceeded"


async def test_probes_are_never_shed() -> None:
    release = asyncio.Event()
    transport = httpx2.ASGITransport(app=_app(release))
    async with httpx2.AsyncClient(transport=transport, base_url="http://t") as client:
        busy = asyncio.create_task(client.get("/slow"))
        await asyncio.sleep(0.05)

        probe = await client.get("/healthz")
        release.set()
        await busy

    assert probe.status_code == 200
