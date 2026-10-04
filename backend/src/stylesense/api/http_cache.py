"""Conditional GETs: the client sends back the ETag it has; unchanged data costs a 304, no body."""

import hashlib

from fastapi import Request, Response
from pydantic import BaseModel


def etag_response(request: Request, model: BaseModel, *, max_age_s: int) -> Response:
    body = model.model_dump_json().encode()
    etag = f'W/"{hashlib.sha256(body).hexdigest()[:32]}"'
    headers = {"ETag": etag, "Cache-Control": f"private, max-age={max_age_s}"}
    if etag in _client_etags(request):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


def _client_etags(request: Request) -> set[str]:
    header = request.headers.get("If-None-Match", "")
    return {tag.strip() for tag in header.split(",") if tag.strip()}
