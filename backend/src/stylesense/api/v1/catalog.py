import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse

from stylesense.api.auth import OptionalClaims
from stylesense.api.dependencies import ContainerDep
from stylesense.api.http_cache import etag_response
from stylesense.modules.catalog.schemas import (
    ClickSource,
    ProductDetail,
    ProductFilters,
    ProductPage,
    ProductSummary,
)

router = APIRouter(tags=["catalog"])


@router.get("/products", summary="Browse products with filters and cursor pagination")
async def list_products(
    filters: Annotated[ProductFilters, Query()], container: ContainerDep
) -> ProductPage:
    return await container.catalog.list_products(filters)


@router.get(
    "/products/{product_id}",
    response_model=ProductDetail,
    summary="Product detail with every store's offer (supports If-None-Match)",
    responses={304: {"description": "Not modified"}},
)
async def get_product(product_id: uuid.UUID, request: Request, container: ContainerDep) -> Response:
    detail = await container.catalog.get_product(product_id)
    return etag_response(request, detail, max_age_s=60)


@router.get("/products/{product_id}/similar", summary="Visually and stylistically similar items")
async def similar_products(
    product_id: uuid.UUID,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> list[ProductSummary]:
    return await container.catalog.similar(product_id, limit=limit)


@router.get(
    "/out/{offer_id}",
    status_code=302,
    response_class=RedirectResponse,
    summary="Track a Buy tap and redirect to the store",
)
async def outbound(
    offer_id: uuid.UUID,
    container: ContainerDep,
    claims: OptionalClaims,
    src: Annotated[ClickSource, Query()] = "product",
) -> RedirectResponse:
    url = await container.catalog.outbound(
        offer_id, user_id=claims.user_id if claims else None, source=src
    )
    return RedirectResponse(
        url,
        status_code=302,
        # Never cache (each tap must be counted); don't leak our URLs to the store.
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
