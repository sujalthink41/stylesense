import asyncio
import uuid
from collections.abc import Callable
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from stylesense.modules.auth.exceptions import (
    EmailNotVerifiedError,
    InvalidIdentityTokenError,
    InvalidRefreshTokenError,
    RefreshTokenReusedError,
)
from stylesense.modules.auth.models import RefreshToken
from stylesense.modules.users.exceptions import AccountDeletedError
from stylesense.modules.users.schemas import DeletionChannel, Role
from tests.integration.modules.conftest import ADMIN_EMAIL, Services


def _google(
    svc: Services,
    token: str = "google-token-priya",
    email: str = "priya@example.com",
    subject: str = "g-1",
) -> str:
    return svc.verifier.register(token, subject=subject, email=email)


async def _tokens_in_db(svc: Services) -> list[RefreshToken]:
    async with svc.sessions() as s:
        return list((await s.scalars(select(RefreshToken))).all())


# ---------- sign-in ----------


async def test_sign_in_issues_tokens_for_the_user(svc: Services) -> None:
    result = await svc.auth.sign_in_with_google(_google(svc))

    claims = svc.tokens.decode(result.tokens.access_token)
    assert result.is_new_user is True
    assert claims.user_id == result.user.id
    assert claims.role == "user"
    assert result.tokens.access_token_expires_in == 900
    assert result.tokens.refresh_token_expires_in == 30 * 86_400


async def test_refresh_tokens_are_stored_only_as_hashes(svc: Services) -> None:
    result = await svc.auth.sign_in_with_google(_google(svc))

    [row] = await _tokens_in_db(svc)
    assert result.tokens.refresh_token.encode() not in row.token_hash
    assert len(row.token_hash) == 32


async def test_admin_role_is_carried_in_the_access_token(svc: Services) -> None:
    token = _google(svc, token="google-founder", email=ADMIN_EMAIL, subject="g-9")

    result = await svc.auth.sign_in_with_google(token)

    assert svc.tokens.decode(result.tokens.access_token).role == Role.ADMIN


async def test_signing_in_again_on_the_same_install_replaces_the_old_session(svc: Services) -> None:
    install = uuid.uuid4()
    first = await svc.auth.sign_in_with_google(_google(svc), installation_id=install)

    await svc.auth.sign_in_with_google(_google(svc), installation_id=install)

    with pytest.raises(InvalidRefreshTokenError):
        await svc.auth.refresh(first.tokens.refresh_token)


async def test_sessions_on_other_installs_are_untouched(svc: Services) -> None:
    phone = await svc.auth.sign_in_with_google(_google(svc), installation_id=uuid.uuid4())

    await svc.auth.sign_in_with_google(_google(svc), installation_id=uuid.uuid4())

    assert await svc.auth.refresh(phone.tokens.refresh_token)


@pytest.mark.parametrize("error", [InvalidIdentityTokenError(), EmailNotVerifiedError()])
async def test_verifier_errors_propagate_and_create_nothing(
    svc: Services, error: Exception
) -> None:
    token = svc.verifier.fail("bad-google-token", error)

    with pytest.raises(type(error)):
        await svc.auth.sign_in_with_google(token)
    assert await _tokens_in_db(svc) == []


# ---------- refresh rotation ----------


async def test_refresh_rotates_to_a_new_token(svc: Services) -> None:
    first = await svc.auth.sign_in_with_google(_google(svc))

    second = await svc.auth.refresh(first.tokens.refresh_token)

    assert second.refresh_token != first.tokens.refresh_token
    assert (
        svc.tokens.decode(second.access_token).session_id
        == svc.tokens.decode(first.tokens.access_token).session_id
    )


async def test_parallel_refreshes_within_grace_both_succeed(svc: Services) -> None:
    first = await svc.auth.sign_in_with_google(_google(svc))

    a, b = await asyncio.gather(
        svc.auth.refresh(first.tokens.refresh_token), svc.auth.refresh(first.tokens.refresh_token)
    )

    assert a.refresh_token != b.refresh_token
    assert await svc.auth.refresh(a.refresh_token)  # family still alive
    assert await svc.auth.refresh(b.refresh_token)


async def test_reuse_after_grace_revokes_the_whole_session(svc: Services) -> None:
    stolen = (await svc.auth.sign_in_with_google(_google(svc))).tokens.refresh_token
    legit = await svc.auth.refresh(stolen)  # real app rotates
    svc.clock.advance(timedelta(seconds=31))

    with pytest.raises(RefreshTokenReusedError):
        await svc.auth.refresh(stolen)  # attacker replays the old token

    with pytest.raises(InvalidRefreshTokenError):
        await svc.auth.refresh(legit.refresh_token)  # descendant revoked too
    assert all(t.revoked_at is not None for t in await _tokens_in_db(svc))


async def test_zero_grace_treats_any_reuse_as_theft(make_services: Callable[..., Services]) -> None:
    svc = make_services(grace_s=0)
    token = (await svc.auth.sign_in_with_google(_google(svc))).tokens.refresh_token
    await svc.auth.refresh(token)
    svc.clock.advance(timedelta(milliseconds=1))

    with pytest.raises(RefreshTokenReusedError):
        await svc.auth.refresh(token)


async def test_expired_refresh_token_is_rejected(svc: Services) -> None:
    token = (await svc.auth.sign_in_with_google(_google(svc))).tokens.refresh_token
    svc.clock.advance(timedelta(days=30))

    with pytest.raises(InvalidRefreshTokenError):
        await svc.auth.refresh(token)


@pytest.mark.parametrize("token", ["", "made-up-token", "x" * 43])
async def test_unknown_refresh_token_is_rejected(svc: Services, token: str) -> None:
    with pytest.raises(InvalidRefreshTokenError):
        await svc.auth.refresh(token)


async def test_refresh_picks_up_role_changes(make_services: Callable[..., Services]) -> None:
    svc = make_services()
    founder = svc.verifier.register("g-founder", subject="g-9", email=ADMIN_EMAIL)
    token = (await svc.auth.sign_in_with_google(founder)).tokens.refresh_token
    demoted = make_services(admin_emails=())
    demoted.verifier.register("g-founder", subject="g-9", email=ADMIN_EMAIL)
    await demoted.users.sign_in(await demoted.verifier.verify("g-founder"))

    pair = await svc.auth.refresh(token)

    assert svc.tokens.decode(pair.access_token).role == Role.USER


# ---------- logout & deletion ----------


async def test_logout_revokes_the_session_and_is_idempotent(svc: Services) -> None:
    token = (await svc.auth.sign_in_with_google(_google(svc))).tokens.refresh_token

    await svc.auth.logout(token)
    await svc.auth.logout(token)
    await svc.auth.logout("never-issued")

    with pytest.raises(InvalidRefreshTokenError):
        await svc.auth.refresh(token)


async def test_deleting_the_account_ends_every_session(svc: Services) -> None:
    phone = await svc.auth.sign_in_with_google(_google(svc), installation_id=uuid.uuid4())
    tablet = await svc.auth.sign_in_with_google(_google(svc), installation_id=uuid.uuid4())

    receipt = await svc.auth.delete_account(phone.user.id, DeletionChannel.APP)

    assert receipt.purge_after == svc.clock.now() + timedelta(days=30)
    for session in (phone, tablet):
        with pytest.raises(InvalidRefreshTokenError):
            await svc.auth.refresh(session.tokens.refresh_token)


async def test_refresh_for_a_deleted_account_fails_and_revokes(svc: Services) -> None:
    session = await svc.auth.sign_in_with_google(_google(svc))
    await svc.users.request_deletion(session.user.id, DeletionChannel.WEB)  # tokens not revoked yet

    with pytest.raises(AccountDeletedError):
        await svc.auth.refresh(session.tokens.refresh_token)
    with pytest.raises(InvalidRefreshTokenError):
        await svc.auth.refresh(session.tokens.refresh_token)


async def test_prune_removes_only_long_expired_tokens(svc: Services) -> None:
    await svc.auth.sign_in_with_google(_google(svc))
    svc.clock.advance(timedelta(days=36))
    await svc.auth.sign_in_with_google(_google(svc))

    assert await svc.auth.prune_expired(older_than=timedelta(days=7)) == 0
    svc.clock.advance(timedelta(days=2))
    assert await svc.auth.prune_expired(older_than=timedelta(days=7)) == 1
    async with svc.sessions() as s:
        assert (await s.execute(select(func.count()).select_from(RefreshToken))).scalar_one() == 1
