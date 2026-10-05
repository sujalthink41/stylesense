import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from stylesense.api.auth import Claims
from stylesense.api.dependencies import ContainerDep
from stylesense.api.preconditions import IfMatch, set_version
from stylesense.api.rate_limit import rate_limited_user
from stylesense.modules.boards.schemas import (
    BoardCreate,
    BoardSummary,
    BoardUpdate,
    BoardView,
    ItemAdd,
    ItemOrder,
    ItemReceipt,
)

router = APIRouter(
    prefix="/boards", tags=["boards"], dependencies=[Depends(rate_limited_user("api.per_user"))]
)

# A board id, or "wishlist" for the user's wishlist (created on first use).
BoardRef = Annotated[
    str, Path(pattern=r"^(wishlist|[0-9a-fA-F]{8}-[0-9a-fA-F-]{27})$", max_length=36)
]
Version = Annotated[int, Depends(IfMatch)]


@router.get("", summary="My boards (the wishlist always comes first)")
async def list_boards(claims: Claims, container: ContainerDep) -> list[BoardSummary]:
    return await container.boards.list_boards(claims.user_id)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create an outfit board; replaying with the same client id returns it (200)",
)
async def create_board(
    body: BoardCreate, claims: Claims, container: ContainerDep, response: Response
) -> BoardView:
    board, created = await container.boards.create(claims.user_id, body)
    if not created:
        response.status_code = status.HTTP_200_OK
    set_version(response, board.version)
    return board


@router.get("/{board_id}", summary="A board with its items; ETag = version")
async def get_board(
    board_id: BoardRef, claims: Claims, container: ContainerDep, response: Response
) -> BoardView:
    board = await container.boards.get(claims.user_id, board_id)
    set_version(response, board.version)
    return board


@router.patch(
    "/{board_id}",
    summary="Rename or set the cover (If-Match required)",
    responses={412: {"description": "Changed elsewhere"}, 428: {"description": "No If-Match"}},
)
async def update_board(
    *,
    board_id: BoardRef,
    body: BoardUpdate,
    version: Version,
    claims: Claims,
    container: ContainerDep,
    response: Response,
) -> BoardView:
    board = await container.boards.update(claims.user_id, board_id, body, expected_version=version)
    set_version(response, board.version)
    return board


@router.delete("/{board_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a board")
async def delete_board(board_id: BoardRef, claims: Claims, container: ContainerDep) -> None:
    await container.boards.delete(claims.user_id, board_id)


@router.put(
    "/{board_id}/items/{product_id}",
    summary="Save a product to a board (idempotent: saving twice keeps one)",
)
async def add_item(
    *,
    board_id: BoardRef,
    product_id: uuid.UUID,
    claims: Claims,
    container: ContainerDep,
    response: Response,
    body: ItemAdd | None = None,
) -> ItemReceipt:
    receipt = await container.boards.add_item(
        claims.user_id, board_id, product_id, note=body.note if body else None
    )
    set_version(response, receipt.version)
    return receipt


@router.delete(
    "/{board_id}/items/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a product (idempotent)",
)
async def remove_item(
    board_id: BoardRef,
    product_id: uuid.UUID,
    claims: Claims,
    container: ContainerDep,
    response: Response,
) -> None:
    set_version(response, await container.boards.remove_item(claims.user_id, board_id, product_id))


@router.put(
    "/{board_id}/order",
    summary="Reorder items: list every product id once (If-Match required)",
    responses={412: {"description": "Changed elsewhere"}, 428: {"description": "No If-Match"}},
)
async def reorder(
    *,
    board_id: BoardRef,
    body: ItemOrder,
    version: Version,
    claims: Claims,
    container: ContainerDep,
    response: Response,
) -> BoardView:
    board = await container.boards.reorder(
        claims.user_id, board_id, body.product_ids, expected_version=version
    )
    set_version(response, board.version)
    return board
