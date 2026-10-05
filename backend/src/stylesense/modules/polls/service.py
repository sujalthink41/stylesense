"""Ask-friends polls: the owner shares `/p/{slug}`; friends vote without signing in.

Anti-abuse, in layers:
  1. one vote per voter token per poll: a unique key (the final word, even under races);
  2. per IP per poll: at most `VOTES_PER_POLL_PER_IP` new votes a day (CGNAT-friendly);
  3. per IP overall: `votes.per_ip` at the API edge.
Voter tokens and IPs are stored only as keyed hashes. Results stay hidden from a voter
until they vote, so early votes don't sway later ones.
"""

import uuid
from collections import Counter
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from stylesense.guards.rate_limit import (
    Algorithm,
    RateLimitedError,
    RateLimiter,
    RateLimitPolicy,
)
from stylesense.infra.database import UnitOfWork
from stylesense.modules.catalog.exceptions import ProductNotFoundError
from stylesense.modules.catalog.service import CatalogService
from stylesense.modules.polls.exceptions import (
    AlreadyVotedError,
    InvalidOptionError,
    PollClosedError,
    PollIdTakenError,
    PollLimitError,
    PollNotFoundError,
)
from stylesense.modules.polls.models import Poll, PollOption, PollVote
from stylesense.modules.polls.schemas import (
    OptionView,
    PollCreate,
    PollView,
    PublicPoll,
)
from stylesense.platform.clock import Clock
from stylesense.platform.ids import new_id
from stylesense.platform.slugs import Pseudonymizer, new_slug

logger = structlog.get_logger(__name__)

MAX_OPEN_POLLS = 20
VOTES_PER_POLL_PER_IP = 25
PER_POLL_IP = RateLimitPolicy(
    "votes.per_poll_ip",
    limit=VOTES_PER_POLL_PER_IP,
    window_s=86_400,
    algorithm=Algorithm.SLIDING_WINDOW,
)
_SLUG_ATTEMPTS = 5


class PollsService:
    def __init__(
        self,
        uow: Callable[[], UnitOfWork],
        *,
        catalog: CatalogService,
        limiter: RateLimiter,
        hasher: Pseudonymizer,
        clock: Clock,
        public_url: str,
    ) -> None:
        self._uow = uow
        self._catalog = catalog
        self._limiter = limiter
        self._hash = hasher
        self._clock = clock
        self._public_url = public_url.rstrip("/")

    # ---------- owner ----------

    async def create(self, user_id: uuid.UUID, body: PollCreate) -> tuple[PollView, bool]:
        products = await self._catalog.summaries(body.product_ids)
        if len(products) != len(body.product_ids):
            raise ProductNotFoundError
        now = self._clock.now()
        async with self._uow() as uow:
            s = uow.session
            if body.id is not None and (existing := await s.get(Poll, body.id)) is not None:
                if existing.user_id != user_id:
                    raise PollIdTakenError
                return await self._owner_view(s, existing), False
            open_polls = await s.scalar(
                select(func.count()).where(
                    Poll.user_id == user_id, Poll.closed_at.is_(None), Poll.closes_at > now
                )
            )
            if (open_polls or 0) >= MAX_OPEN_POLLS:
                raise PollLimitError
            poll = await self._insert(
                s,
                id=body.id or new_id(),
                user_id=user_id,
                question=" ".join(body.question.split()),
                closes_at=now + timedelta(hours=body.closes_in_hours),
                created_at=now,
            )
            s.add_all(
                PollOption(poll_id=poll.id, product_id=pid, position=i)
                for i, pid in enumerate(body.product_ids, start=1)
            )
            await s.flush()
            view = await self._owner_view(s, poll)
        logger.info("poll_created", poll_id=str(poll.id), options=len(body.product_ids))
        return view, True

    async def get(self, user_id: uuid.UUID, poll_id: uuid.UUID) -> PollView:
        async with self._uow() as uow:
            poll = await uow.session.get(Poll, poll_id)
            if poll is None or poll.user_id != user_id:
                raise PollNotFoundError
            return await self._owner_view(uow.session, poll)

    async def list_mine(self, user_id: uuid.UUID, *, limit: int = 50) -> list[PollView]:
        async with self._uow() as uow:
            polls = (
                await uow.session.scalars(
                    select(Poll)
                    .where(Poll.user_id == user_id)
                    .order_by(Poll.created_at.desc())
                    .limit(limit)
                )
            ).all()
            return [await self._owner_view(uow.session, p) for p in polls]

    async def close(self, user_id: uuid.UUID, poll_id: uuid.UUID) -> PollView:
        """Idempotent."""
        async with self._uow() as uow:
            poll = await uow.session.get(Poll, poll_id, with_for_update=True)
            if poll is None or poll.user_id != user_id:
                raise PollNotFoundError
            if poll.closed_at is None:
                poll.closed_at = self._clock.now()
            return await self._owner_view(uow.session, poll)

    # ---------- public ----------

    async def public(self, slug: str, *, voter_token: str | None) -> PublicPoll:
        async with self._uow() as uow:
            poll = await self._by_slug(uow.session, slug)
            mine = await self._vote_of(uow.session, poll, voter_token)
            return await self._public_view(uow.session, poll, mine)

    async def vote(
        self, slug: str, option_id: uuid.UUID, *, voter_token: str, ip: str
    ) -> PublicPoll:
        voter, ip_hash = self._hash(voter_token), self._hash(ip)
        async with self._uow() as uow:
            s = uow.session
            poll = await self._by_slug(s, slug)
            if not self._is_open(poll):
                raise PollClosedError
            if option_id not in set(await self._option_ids(s, poll)):
                raise InvalidOptionError
            mine = await s.scalar(
                select(PollVote.option_id).where(
                    PollVote.poll_id == poll.id, PollVote.voter_hash == voter
                )
            )
            if mine is None:
                decision = await self._limiter.hit(PER_POLL_IP, f"{poll.id}:{ip_hash}")
                if not decision.allowed:
                    raise RateLimitedError.from_decision(decision)
                await s.execute(
                    insert(PollVote)
                    .values(poll_id=poll.id, option_id=option_id, voter_hash=voter, ip_hash=ip_hash)
                    .on_conflict_do_nothing(constraint="uq_poll_votes_once")
                )
                # Re-read: under a race the other request's vote is the one that counts.
                mine = await s.scalar(
                    select(PollVote.option_id).where(
                        PollVote.poll_id == poll.id, PollVote.voter_hash == voter
                    )
                )
            if mine != option_id:
                raise AlreadyVotedError(your_vote=str(mine))
            return await self._public_view(s, poll, mine)  # same vote again = harmless replay

    # ---------- helpers ----------

    async def _insert(self, s: AsyncSession, **values: Any) -> Poll:
        for _ in range(_SLUG_ATTEMPTS):
            poll_id = await s.scalar(
                insert(Poll)
                .values(slug=new_slug(), **values)
                .on_conflict_do_nothing(index_elements=["slug"])
                .returning(Poll.id)
            )
            if poll_id is not None:
                poll = await s.get(Poll, poll_id)
                assert poll is not None  # noqa: S101
                return poll
        raise RuntimeError("could not allocate a poll slug")  # ~impossible at 62**8

    def _is_open(self, poll: Poll) -> bool:
        return poll.closed_at is None and self._clock.now() < poll.closes_at

    async def _by_slug(self, s: AsyncSession, slug: str) -> Poll:
        poll: Poll | None = await s.scalar(select(Poll).where(Poll.slug == slug))
        if poll is None:
            raise PollNotFoundError
        return poll

    async def _vote_of(self, s: AsyncSession, poll: Poll, token: str | None) -> uuid.UUID | None:
        if not token:
            return None
        vote: uuid.UUID | None = await s.scalar(
            select(PollVote.option_id).where(
                PollVote.poll_id == poll.id, PollVote.voter_hash == self._hash(token)
            )
        )
        return vote

    async def _option_ids(self, s: AsyncSession, poll: Poll) -> list[uuid.UUID]:
        rows = await s.scalars(
            select(PollOption.id).where(PollOption.poll_id == poll.id).order_by(PollOption.position)
        )
        return list(rows.all())

    async def _options(self, s: AsyncSession, poll: Poll, *, with_votes: bool) -> list[OptionView]:
        options = (
            await s.scalars(
                select(PollOption)
                .where(PollOption.poll_id == poll.id)
                .order_by(PollOption.position)
            )
        ).all()
        counts: Counter[uuid.UUID] = Counter()
        if with_votes:
            rows = await s.execute(
                select(PollVote.option_id, func.count())
                .where(PollVote.poll_id == poll.id)
                .group_by(PollVote.option_id)
            )
            counts.update({row[0]: row[1] for row in rows.all()})
        products = await self._catalog.summaries([o.product_id for o in options])
        return [
            OptionView(
                option_id=o.id,
                product=products[o.product_id],
                votes=counts[o.id] if with_votes else None,
            )
            for o in options
            if o.product_id in products
        ]

    async def _owner_view(self, s: AsyncSession, poll: Poll) -> PollView:
        options = await self._options(s, poll, with_votes=True)
        return PollView(
            id=poll.id,
            slug=poll.slug,
            url=f"{self._public_url}/p/{poll.slug}",
            question=poll.question,
            status="open" if self._is_open(poll) else "closed",
            closes_at=poll.closes_at,
            total_votes=sum(o.votes or 0 for o in options),
            options=options,
            created_at=poll.created_at,
        )

    async def _public_view(self, s: AsyncSession, poll: Poll, mine: uuid.UUID | None) -> PublicPoll:
        is_open = self._is_open(poll)
        reveal = mine is not None or not is_open
        options = await self._options(s, poll, with_votes=reveal)
        return PublicPoll(
            slug=poll.slug,
            question=poll.question,
            status="open" if is_open else "closed",
            closes_at=poll.closes_at,
            options=options,
            total_votes=sum(o.votes or 0 for o in options) if reveal else None,
            your_vote=mine,
        )
