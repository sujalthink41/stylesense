"""Shares and polls: owner endpoints (signed in) and public ones (anyone with the link)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Request, Response, status

from stylesense.api.auth import Claims
from stylesense.api.dependencies import ContainerDep
from stylesense.api.rate_limit import client_ip, rate_limited, rate_limited_user
from stylesense.modules.polls.schemas import PollCreate, PollView, PublicPoll, VoteInput, VoterToken
from stylesense.modules.sharing.schemas import PublicShare, ShareCreate, ShareView

owner = APIRouter(tags=["social"], dependencies=[Depends(rate_limited_user("api.per_user"))])
public = APIRouter(
    prefix="/public", tags=["public"], dependencies=[Depends(rate_limited("public.per_ip"))]
)

Slug = Annotated[str, Path(pattern=r"^[A-Za-z0-9]{6,16}$")]
# The public vote page keeps a random token (localStorage) and sends it on every call; a header
# instead of a cookie works across the web and API domains without third-party cookies.
VoterHeader = Annotated[VoterToken | None, Header(alias="X-Voter-Token")]
RequiredVoter = Annotated[VoterToken, Header(alias="X-Voter-Token")]
PUBLIC_CACHE = "public, max-age=30"


# ---------- shares ----------


@owner.post(
    "/shares",
    status_code=status.HTTP_201_CREATED,
    summary="Get a share link; sharing the same thing again returns the same link (200)",
)
async def create_share(
    body: ShareCreate, claims: Claims, container: ContainerDep, response: Response
) -> ShareView:
    share, created = await container.sharing.create(claims.user_id, body)
    if not created:
        response.status_code = status.HTTP_200_OK
    return share


@owner.get("/shares", summary="My active share links")
async def list_shares(claims: Claims, container: ContainerDep) -> list[ShareView]:
    return await container.sharing.list_mine(claims.user_id)


@owner.delete(
    "/shares/{slug}", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke a share link"
)
async def revoke_share(slug: Slug, claims: Claims, container: ContainerDep) -> None:
    await container.sharing.revoke(claims.user_id, slug)


@public.get(
    "/shares/{slug}",
    summary="What a share link shows (live prices); 410 once revoked",
    responses={410: {"description": "Revoked or deleted"}},
)
async def open_share(slug: Slug, container: ContainerDep, response: Response) -> PublicShare:
    response.headers["Cache-Control"] = "no-store"  # every open counts as a view
    return await container.sharing.open(slug)


# ---------- polls ----------


@owner.post(
    "/polls",
    status_code=status.HTTP_201_CREATED,
    summary="Ask friends: a poll of 2-4 products; replaying with the same client id returns it",
)
async def create_poll(
    body: PollCreate, claims: Claims, container: ContainerDep, response: Response
) -> PollView:
    poll, created = await container.polls.create(claims.user_id, body)
    if not created:
        response.status_code = status.HTTP_200_OK
    return poll


@owner.get("/polls", summary="My polls, newest first, with live results")
async def list_polls(claims: Claims, container: ContainerDep) -> list[PollView]:
    return await container.polls.list_mine(claims.user_id)


@owner.get("/polls/{poll_id}", summary="One of my polls, with live results")
async def get_poll(poll_id: uuid.UUID, claims: Claims, container: ContainerDep) -> PollView:
    return await container.polls.get(claims.user_id, poll_id)


@owner.post("/polls/{poll_id}/close", summary="Stop voting now (idempotent)")
async def close_poll(poll_id: uuid.UUID, claims: Claims, container: ContainerDep) -> PollView:
    return await container.polls.close(claims.user_id, poll_id)


@public.get("/polls/{slug}", summary="The vote page: results appear once you've voted")
async def public_poll(
    slug: Slug, container: ContainerDep, response: Response, voter: VoterHeader = None
) -> PublicPoll:
    response.headers["Cache-Control"] = "no-store"
    return await container.polls.public(slug, voter_token=voter)


@public.post(
    "/polls/{slug}/votes",
    summary="Vote (no sign-in). One vote per device; repeating the same vote is harmless",
    dependencies=[Depends(rate_limited("votes.per_ip"))],
    responses={409: {"description": "Already voted for another option, or closed"}},
)
async def vote(
    *, slug: Slug, body: VoteInput, voter: RequiredVoter, request: Request, container: ContainerDep
) -> PublicPoll:
    return await container.polls.vote(
        slug, body.option_id, voter_token=voter, ip=client_ip(request)
    )
