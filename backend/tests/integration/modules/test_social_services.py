import asyncio
import uuid
from datetime import timedelta

import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stylesense.guards.rate_limit import RateLimitedError, RateLimiter
from stylesense.infra.database import UnitOfWork
from stylesense.integrations.embeddings.hashing import HashingEmbedder
from stylesense.modules.boards.schemas import BoardCreate
from stylesense.modules.boards.service import BoardsService
from stylesense.modules.catalog.exceptions import ProductNotFoundError
from stylesense.modules.catalog.models import Product
from stylesense.modules.catalog.service import CatalogService
from stylesense.modules.polls.exceptions import (
    AlreadyVotedError,
    InvalidOptionError,
    PollClosedError,
    PollIdTakenError,
    PollLimitError,
    PollNotFoundError,
)
from stylesense.modules.polls.models import PollVote
from stylesense.modules.polls.schemas import PollCreate, PollView
from stylesense.modules.polls.service import MAX_OPEN_POLLS, VOTES_PER_POLL_PER_IP, PollsService
from stylesense.modules.sharing.exceptions import ShareGoneError, ShareNotFoundError
from stylesense.modules.sharing.schemas import ShareCreate
from stylesense.modules.sharing.service import SharingService
from stylesense.modules.users.models import User
from stylesense.platform.slugs import Pseudonymizer
from tests.fakes.clock import FixedClock

PUBLIC = "https://stylesense.example"
TOKEN = "voter-token-0123456789"


class Services:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], redis: Redis) -> None:
        def uow() -> UnitOfWork:
            return UnitOfWork(sessions)

        self.clock = FixedClock()
        catalog = CatalogService(uow, clock=self.clock, embedder=HashingEmbedder())
        self.boards = BoardsService(uow, catalog=catalog, clock=self.clock)
        self.sharing = SharingService(
            uow, catalog=catalog, boards=self.boards, clock=self.clock, public_url=PUBLIC
        )
        self.polls = PollsService(
            uow,
            catalog=catalog,
            limiter=RateLimiter(redis, self.clock, prefix=f"t{uuid.uuid4().hex}:"),
            hasher=Pseudonymizer.derive("s" * 32, "poll-voters"),
            clock=self.clock,
            public_url=PUBLIC,
        )


@pytest.fixture
async def svc(catalog_sessions: async_sessionmaker[AsyncSession], redis: Redis) -> Services:
    return Services(catalog_sessions, redis)


async def _products(sessions: async_sessionmaker[AsyncSession], n: int) -> list[uuid.UUID]:
    async with sessions() as s:
        return list((await s.scalars(select(Product.id).order_by(Product.id).limit(n))).all())


async def _user(sessions: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with sessions() as s, s.begin():
        user = User(email=f"{uuid.uuid4().hex}@example.com")
        s.add(user)
    return user.id


# ---------- shares ----------


async def test_sharing_the_same_look_twice_returns_the_same_link(
    svc: Services, catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    ids = await _products(catalog_sessions, 3)
    body = ShareCreate(kind="look", title="Goa trip", product_ids=ids)

    first, created = await svc.sharing.create(user_id, body)
    again, created_again = await svc.sharing.create(user_id, body)
    reordered, _ = await svc.sharing.create(
        user_id, ShareCreate(kind="look", title="Goa trip", product_ids=ids[::-1])
    )

    assert (created, created_again) == (True, False)
    assert first.slug == again.slug != reordered.slug  # order is part of a look
    assert first.url == f"{PUBLIC}/l/{first.slug}"


async def test_concurrent_identical_shares_mint_one_link(
    svc: Services, catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    [product] = await _products(catalog_sessions, 1)
    body = ShareCreate(kind="product", product_ids=[product])

    results = await asyncio.gather(*(svc.sharing.create(user_id, body) for _ in range(8)))

    assert len({share.slug for share, _ in results}) == 1


async def test_opening_a_share_shows_live_products_and_counts_views(
    svc: Services, catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    ids = await _products(catalog_sessions, 2)
    share, _ = await svc.sharing.create(user_id, ShareCreate(kind="look", product_ids=ids))

    await svc.sharing.open(share.slug)
    page = await svc.sharing.open(share.slug)

    assert [p.id for p in page.products] == ids
    assert (await svc.sharing.list_mine(user_id))[0].views == 2


async def test_revoked_links_are_gone_and_resharing_revives_them(
    svc: Services, catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    [product] = await _products(catalog_sessions, 1)
    body = ShareCreate(kind="product", product_ids=[product])
    share, _ = await svc.sharing.create(user_id, body)

    await svc.sharing.revoke(user_id, share.slug)
    await svc.sharing.revoke(user_id, share.slug)  # idempotent

    with pytest.raises(ShareGoneError):
        await svc.sharing.open(share.slug)
    assert await svc.sharing.list_mine(user_id) == []
    revived, _ = await svc.sharing.create(user_id, body)
    assert revived.slug == share.slug
    assert (await svc.sharing.open(share.slug)).products


async def test_unknown_slugs_and_other_peoples_shares(
    svc: Services, catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    [product] = await _products(catalog_sessions, 1)
    share, _ = await svc.sharing.create(user_id, ShareCreate(kind="product", product_ids=[product]))

    with pytest.raises(ShareNotFoundError):
        await svc.sharing.open("nope1234")
    with pytest.raises(ShareNotFoundError):
        await svc.sharing.revoke(await _user(catalog_sessions), share.slug)


async def test_board_shares_follow_the_live_board_until_it_is_deleted(
    svc: Services, catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    a, b = await _products(catalog_sessions, 2)
    board, _ = await svc.boards.create(user_id, BoardCreate(name="Wedding"))
    await svc.boards.add_item(user_id, board.id, a)
    share, _ = await svc.sharing.create(user_id, ShareCreate(kind="board", board_id=board.id))

    await svc.boards.add_item(user_id, board.id, b)
    page = await svc.sharing.open(share.slug)
    assert (page.title, [p.id for p in page.products]) == ("Wedding", [a, b])

    await svc.boards.delete(user_id, board.id)
    with pytest.raises(ShareGoneError):
        await svc.sharing.open(share.slug)


async def test_sharing_needs_real_products_and_your_own_board(
    svc: Services, catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    board, _ = await svc.boards.create(user_id, BoardCreate(name="Private"))

    with pytest.raises(ProductNotFoundError):
        await svc.sharing.create(
            user_id, ShareCreate(kind="look", product_ids=[uuid.uuid4(), uuid.uuid4()])
        )
    with pytest.raises(ShareNotFoundError):
        await svc.sharing.create(
            await _user(catalog_sessions), ShareCreate(kind="board", board_id=board.id)
        )


# ---------- polls ----------


async def _poll(
    svc: Services, sessions: async_sessionmaker[AsyncSession], user: uuid.UUID
) -> PollView:
    poll, _ = await svc.polls.create(user, PollCreate(product_ids=await _products(sessions, 3)))
    return poll


async def test_a_friend_votes_once_and_then_sees_results(
    svc: Services, catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    poll = await _poll(svc, catalog_sessions, user_id)
    choice = poll.options[1].option_id

    before = await svc.polls.public(poll.slug, voter_token=TOKEN)
    after = await svc.polls.vote(poll.slug, choice, voter_token=TOKEN, ip="1.2.3.4")

    assert (before.total_votes, before.options[0].votes, before.your_vote) == (None, None, None)
    assert (after.total_votes, after.your_vote) == (1, choice)
    assert [o.votes for o in after.options] == [0, 1, 0]
    owner = await svc.polls.get(user_id, poll.id)
    assert owner.total_votes == 1


async def test_concurrent_duplicate_votes_count_once(
    svc: Services, catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    poll = await _poll(svc, catalog_sessions, user_id)
    choice = poll.options[0].option_id

    results = await asyncio.gather(
        *(svc.polls.vote(poll.slug, choice, voter_token=TOKEN, ip="1.2.3.4") for _ in range(12)),
        return_exceptions=True,
    )

    assert not [r for r in results if isinstance(r, Exception)]
    async with catalog_sessions() as s:
        votes = await s.scalar(
            select(func.count()).select_from(PollVote).where(PollVote.poll_id == poll.id)
        )
    assert votes == 1


async def test_a_second_vote_for_another_option_is_refused(
    svc: Services, catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    poll = await _poll(svc, catalog_sessions, user_id)
    first, second = (o.option_id for o in poll.options[:2])
    await svc.polls.vote(poll.slug, first, voter_token=TOKEN, ip="1.2.3.4")

    with pytest.raises(AlreadyVotedError) as caught:
        await svc.polls.vote(poll.slug, second, voter_token=TOKEN, ip="5.6.7.8")

    assert caught.value.extra == {"your_vote": str(first)}


async def test_one_network_can_only_cast_so_many_votes_per_poll(
    svc: Services, catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    poll = await _poll(svc, catalog_sessions, user_id)
    choice = poll.options[0].option_id
    for i in range(VOTES_PER_POLL_PER_IP):
        await svc.polls.vote(poll.slug, choice, voter_token=f"device-token-{i:08d}", ip="9.9.9.9")

    with pytest.raises(RateLimitedError):
        await svc.polls.vote(poll.slug, choice, voter_token="device-token-extra1", ip="9.9.9.9")
    await svc.polls.vote(poll.slug, choice, voter_token="device-token-extra1", ip="8.8.8.8")


async def test_votes_are_stored_without_raw_tokens_or_ips(
    svc: Services, catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    poll = await _poll(svc, catalog_sessions, user_id)
    await svc.polls.vote(poll.slug, poll.options[0].option_id, voter_token=TOKEN, ip="1.2.3.4")

    async with catalog_sessions() as s:
        vote = await s.scalar(select(PollVote).where(PollVote.poll_id == poll.id))
    assert vote is not None
    assert TOKEN not in vote.voter_hash
    assert "1.2.3.4" not in vote.ip_hash


async def test_closed_polls_refuse_votes_but_show_results(
    svc: Services, catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    poll = await _poll(svc, catalog_sessions, user_id)
    await svc.polls.close(user_id, poll.id)
    await svc.polls.close(user_id, poll.id)  # idempotent

    with pytest.raises(PollClosedError):
        await svc.polls.vote(poll.slug, poll.options[0].option_id, voter_token=TOKEN, ip="1.1.1.1")
    page = await svc.polls.public(poll.slug, voter_token=None)
    assert (page.status, page.total_votes) == ("closed", 0)


async def test_polls_close_on_their_own(
    svc: Services, catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    poll, _ = await svc.polls.create(
        user_id, PollCreate(product_ids=await _products(catalog_sessions, 2), closes_in_hours=1)
    )

    svc.clock.advance(timedelta(hours=1, seconds=1))

    with pytest.raises(PollClosedError):
        await svc.polls.vote(poll.slug, poll.options[0].option_id, voter_token=TOKEN, ip="1.1.1.1")
    assert (await svc.polls.get(user_id, poll.id)).status == "closed"


async def test_votes_must_name_an_option_of_this_poll(
    svc: Services, catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    poll = await _poll(svc, catalog_sessions, user_id)
    other = await _poll(svc, catalog_sessions, user_id)

    with pytest.raises(InvalidOptionError):
        await svc.polls.vote(poll.slug, other.options[0].option_id, voter_token=TOKEN, ip="1.1.1.1")


async def test_poll_creation_is_idempotent_and_owner_scoped(
    svc: Services, catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    body = PollCreate(id=uuid.uuid4(), product_ids=await _products(catalog_sessions, 2))

    first, created = await svc.polls.create(user_id, body)
    again, created_again = await svc.polls.create(user_id, body)

    assert (created, created_again) == (True, False)
    assert first.slug == again.slug
    assert first.url == f"{PUBLIC}/p/{first.slug}"
    with pytest.raises(PollNotFoundError):
        await svc.polls.get(await _user(catalog_sessions), first.id)


async def test_polls_need_real_products(svc: Services, user_id: uuid.UUID) -> None:
    with pytest.raises(ProductNotFoundError):
        await svc.polls.create(user_id, PollCreate(product_ids=[uuid.uuid4(), uuid.uuid4()]))


async def test_unknown_poll_slug(svc: Services) -> None:
    with pytest.raises(PollNotFoundError):
        await svc.polls.public("unknown1", voter_token=None)


async def test_my_polls_newest_first_and_ids_cannot_be_borrowed(
    svc: Services, catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    first = await _poll(svc, catalog_sessions, user_id)
    svc.clock.advance(timedelta(minutes=1))
    second = await _poll(svc, catalog_sessions, user_id)

    mine = await svc.polls.list_mine(user_id)

    assert [p.id for p in mine] == [second.id, first.id]
    with pytest.raises(PollIdTakenError):
        await svc.polls.create(
            await _user(catalog_sessions),
            PollCreate(id=first.id, product_ids=await _products(catalog_sessions, 2)),
        )


async def test_open_polls_are_capped_per_user(
    svc: Services, catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    ids = await _products(catalog_sessions, 2)
    for _ in range(MAX_OPEN_POLLS):
        await svc.polls.create(user_id, PollCreate(product_ids=ids))

    with pytest.raises(PollLimitError):
        await svc.polls.create(user_id, PollCreate(product_ids=ids))
    await svc.polls.close(user_id, (await svc.polls.list_mine(user_id))[0].id)
    await svc.polls.create(user_id, PollCreate(product_ids=ids))  # closing one frees a slot
