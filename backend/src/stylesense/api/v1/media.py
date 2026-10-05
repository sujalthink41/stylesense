"""Photos (uploads), virtual try-on and content reports."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter

from stylesense.api.auth import Claims
from stylesense.api.dependencies import ContainerDep
from stylesense.api.idempotency import IdempotencyKey, run_idempotent
from stylesense.api.rate_limit import rate_limited_user
from stylesense.modules.tryon.schemas import ReportCreate, ReportReceipt, TryOnCreate, TryOnView
from stylesense.modules.uploads.schemas import UploadCreate, UploadView

router = APIRouter(tags=["media"], dependencies=[Depends(rate_limited_user("api.per_user"))])

SSE_KEEPALIVE_S = 15
_TRYON = TypeAdapter(tuple[TryOnView, bool])


# ---------- uploads ----------


@router.post(
    "/uploads",
    status_code=status.HTTP_201_CREATED,
    summary="Get a signed slot to upload a photo straight to storage (expires in 24 h)",
)
async def create_upload(body: UploadCreate, claims: Claims, container: ContainerDep) -> UploadView:
    return await container.uploads.create(claims.user_id, body.kind)


@router.post(
    "/uploads/{upload_id}/confirm",
    summary="After uploading: we check the stored photo and make it usable (idempotent)",
    responses={409: {"description": "Not uploaded yet"}, 422: {"description": "Rejected"}},
)
async def confirm_upload(
    upload_id: uuid.UUID, claims: Claims, container: ContainerDep
) -> UploadView:
    return await container.uploads.confirm(claims.user_id, upload_id)


@router.get("/uploads/{upload_id}", summary="A photo's status and signed view URL")
async def get_upload(upload_id: uuid.UUID, claims: Claims, container: ContainerDep) -> UploadView:
    return await container.uploads.get(claims.user_id, upload_id)


@router.delete(
    "/uploads/{upload_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a photo now"
)
async def delete_upload(upload_id: uuid.UUID, claims: Claims, container: ContainerDep) -> None:
    await container.uploads.delete(claims.user_id, upload_id)


# ---------- try-on ----------


@router.post(
    "/tryon",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a try-on (Idempotency-Key required; the same selfie + item returns its job)",
)
async def request_tryon(
    *,
    body: TryOnCreate,
    request: Request,
    response: Response,
    claims: Claims,
    container: ContainerDep,
    key: Annotated[str, Depends(IdempotencyKey)],
) -> TryOnView:
    async def start() -> tuple[TryOnView, bool]:
        return await container.tryon.request(claims.user_id, body)

    job, created = await run_idempotent(
        request,
        response,
        container,
        key=key,
        principal=f"user:{claims.user_id}",
        operation=start,
        adapter=_TRYON,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return job


@router.get("/tryon/{job_id}", summary="A try-on's status and (when done) its signed result URL")
async def get_tryon(job_id: uuid.UUID, claims: Claims, container: ContainerDep) -> TryOnView:
    return await container.tryon.get(claims.user_id, job_id)


@router.post("/tryon/{job_id}/retry", summary="Retry a failed try-on (no extra quota)")
async def retry_tryon(job_id: uuid.UUID, claims: Claims, container: ContainerDep) -> TryOnView:
    return await container.tryon.retry(claims.user_id, job_id)


@router.get(
    "/tryon/{job_id}/events",
    summary="Server-Sent Events: the job each time its status changes, until done or failed",
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def tryon_events(
    job_id: uuid.UUID, claims: Claims, container: ContainerDep
) -> StreamingResponse:
    await container.tryon.get(claims.user_id, job_id)  # a 404 must come before the stream
    return StreamingResponse(
        _frames(container.tryon.events(claims.user_id, job_id)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


async def _frames(updates: AsyncIterator[TryOnView]) -> AsyncIterator[str]:
    sequence = 0
    pending = asyncio.ensure_future(anext(updates))
    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=SSE_KEEPALIVE_S)
            if not done:
                yield ": keep-alive\n\n"
                continue
            try:
                view = pending.result()
            except StopAsyncIteration:
                return
            sequence += 1
            yield f"id: {sequence}\nevent: tryon.status\ndata: {view.model_dump_json()}\n\n"
            pending = asyncio.ensure_future(anext(updates))
    finally:
        pending.cancel()


# ---------- reports ----------


@router.post(
    "/reports",
    status_code=status.HTTP_201_CREATED,
    summary="Report a try-on result, product, share or poll (reporting twice is harmless)",
)
async def report(
    body: ReportCreate, claims: Claims, container: ContainerDep, response: Response
) -> ReportReceipt:
    receipt = await container.tryon.report(claims.user_id, body)
    if not receipt.created:
        response.status_code = status.HTTP_200_OK
    return receipt
