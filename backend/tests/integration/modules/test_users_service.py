import asyncio
import uuid
from collections.abc import Callable
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from stylesense.guards.outbox import OutboxEnvelope, OutboxMessage
from stylesense.modules.auth.ports import VerifiedIdentity
from stylesense.modules.users.exceptions import (
    AccountDeletedError,
    AccountSuspendedError,
    EmailInUseError,
)
from stylesense.modules.users.models import AccountDeletion, AuthIdentity, User, UserDevice
from stylesense.modules.users.schemas import (
    ConsentInput,
    ConsentKind,
    DeletionChannel,
    DeviceRegistration,
    Platform,
    ProfileUpdate,
    PurgeOutcome,
    Role,
    UserStatus,
)
from stylesense.modules.users.service import PurgeNotDueError
from tests.integration.modules.conftest import ADMIN_EMAIL, Services

PRIYA = VerifiedIdentity(provider="google", subject="g-1", email="priya@example.com", name="Priya")


async def _count(svc: Services, model: type, **where: object) -> int:
    async with svc.sessions() as s:
        stmt = select(func.count()).select_from(model).filter_by(**where)
        return int((await s.execute(stmt)).scalar_one())


async def _set_status(svc: Services, user_id: uuid.UUID, status: str) -> None:
    async with svc.sessions() as s, s.begin():
        user = await s.get(User, user_id)
        assert user is not None
        user.status = status


# ---------- sign-in / account creation ----------


async def test_first_sign_in_creates_user_and_identity(svc: Services) -> None:
    user, created = await svc.users.sign_in(PRIYA)

    assert created is True
    assert (user.email, user.display_name, user.role, user.status) == (
        "priya@example.com",
        "Priya",
        Role.USER,
        UserStatus.ACTIVE,
    )
    assert await _count(svc, AuthIdentity, provider="google", subject="g-1") == 1


async def test_returning_user_is_found_by_subject_not_email(svc: Services) -> None:
    first, _ = await svc.users.sign_in(PRIYA)
    renamed = VerifiedIdentity(provider="google", subject="g-1", email="priya.new@example.com")

    again, created = await svc.users.sign_in(renamed)

    assert created is False
    assert again.id == first.id


async def test_existing_display_name_is_not_overwritten(svc: Services) -> None:
    user, _ = await svc.users.sign_in(PRIYA)
    await svc.users.update_profile(user.id, ProfileUpdate(display_name="Pri"))

    again, _ = await svc.users.sign_in(PRIYA)

    assert again.display_name == "Pri"


async def test_concurrent_first_sign_ins_create_exactly_one_user(svc: Services) -> None:
    results = await asyncio.gather(*(svc.users.sign_in(PRIYA) for _ in range(5)))

    assert len({user.id for user, _ in results}) == 1
    assert sum(created for _, created in results) == 1
    assert await _count(svc, User) == 1


async def test_allow_listed_email_becomes_admin(svc: Services) -> None:
    founder = VerifiedIdentity(provider="google", subject="g-9", email=ADMIN_EMAIL)

    user, _ = await svc.users.sign_in(founder)

    assert user.role is Role.ADMIN


async def test_admin_removed_from_allow_list_is_demoted_on_next_sign_in(
    make_services: Callable[..., Services],
) -> None:
    founder = VerifiedIdentity(provider="google", subject="g-9", email=ADMIN_EMAIL)
    await make_services().users.sign_in(founder)

    user, _ = await make_services(admin_emails=()).users.sign_in(founder)

    assert user.role is Role.USER


async def test_same_email_with_a_different_google_account_is_rejected(svc: Services) -> None:
    await svc.users.sign_in(PRIYA)
    impostor = VerifiedIdentity(provider="google", subject="g-other", email="Priya@Example.com")

    with pytest.raises(EmailInUseError) as err:
        await svc.users.sign_in(impostor)
    assert err.value.status_code == 409


@pytest.mark.parametrize(
    ("status", "error"),
    [(UserStatus.DELETING, AccountDeletedError), (UserStatus.SUSPENDED, AccountSuspendedError)],
)
async def test_inactive_accounts_cannot_sign_in(
    svc: Services, status: UserStatus, error: type[Exception]
) -> None:
    user, _ = await svc.users.sign_in(PRIYA)
    await _set_status(svc, user.id, status)

    with pytest.raises(error):
        await svc.users.sign_in(PRIYA)


# ---------- profile ----------


async def test_get_active_rejects_unknown_user(svc: Services) -> None:
    with pytest.raises(AccountDeletedError):
        await svc.users.get_active(uuid.uuid4())


async def test_update_profile_changes_only_given_fields(svc: Services) -> None:
    user, _ = await svc.users.sign_in(PRIYA)

    updated = await svc.users.update_profile(user.id, ProfileUpdate(locale="hi-IN"))

    assert (updated.locale, updated.display_name) == ("hi-IN", "Priya")


# ---------- devices ----------


async def test_registering_a_device_twice_updates_one_row(svc: Services) -> None:
    user, _ = await svc.users.sign_in(PRIYA)
    install = uuid.uuid4()

    await svc.users.register_device(
        user.id, install, DeviceRegistration(platform=Platform.ANDROID, app_version="0.1.0")
    )
    device = await svc.users.register_device(
        user.id,
        install,
        DeviceRegistration(platform=Platform.ANDROID, app_version="0.2.0", push_token="fcm-1"),
    )

    assert (device.app_version, device.has_push_token) == ("0.2.0", True)
    assert await _count(svc, UserDevice, user_id=user.id) == 1


async def test_push_token_moves_when_the_phone_switches_accounts(svc: Services) -> None:
    priya, _ = await svc.users.sign_in(PRIYA)
    ravi, _ = await svc.users.sign_in(
        VerifiedIdentity(provider="google", subject="g-2", email="ravi@example.com")
    )
    reg = DeviceRegistration(
        platform=Platform.ANDROID, app_version="0.1.0", push_token="fcm-shared"
    )

    await svc.users.register_device(priya.id, uuid.uuid4(), reg)
    await svc.users.register_device(ravi.id, uuid.uuid4(), reg)

    assert await _count(svc, UserDevice, push_token="fcm-shared") == 1
    assert await _count(svc, UserDevice, user_id=ravi.id, push_token="fcm-shared") == 1


async def test_removing_a_device_is_idempotent_and_scoped_to_its_owner(svc: Services) -> None:
    priya, _ = await svc.users.sign_in(PRIYA)
    ravi, _ = await svc.users.sign_in(
        VerifiedIdentity(provider="google", subject="g-2", email="ravi@example.com")
    )
    install = uuid.uuid4()
    await svc.users.register_device(
        priya.id, install, DeviceRegistration(platform=Platform.IOS, app_version="0.1.0")
    )

    await svc.users.remove_device(ravi.id, install)  # someone else's device: no effect
    assert await _count(svc, UserDevice, user_id=priya.id) == 1

    await svc.users.remove_device(priya.id, install)
    await svc.users.remove_device(priya.id, install)
    assert await _count(svc, UserDevice, user_id=priya.id) == 0


# ---------- consents ----------


async def test_consents_are_append_only_and_latest_wins(svc: Services) -> None:
    user, _ = await svc.users.sign_in(PRIYA)
    await svc.users.record_consent(
        user.id, ConsentInput(kind=ConsentKind.MARKETING_PUSH, version="1", granted=True)
    )
    svc.clock.advance(timedelta(seconds=1))
    await svc.users.record_consent(
        user.id, ConsentInput(kind=ConsentKind.MARKETING_PUSH, version="1", granted=False)
    )
    await svc.users.record_consent(
        user.id, ConsentInput(kind=ConsentKind.TERMS, version="2026-10", granted=True)
    )

    current = {c.kind: c.granted for c in await svc.users.current_consents(user.id)}

    assert current == {ConsentKind.MARKETING_PUSH: False, ConsentKind.TERMS: True}


# ---------- deletion & purge ----------


async def test_deletion_request_schedules_a_purge_and_blocks_the_account(svc: Services) -> None:
    user, _ = await svc.users.sign_in(PRIYA)

    receipt = await svc.users.request_deletion(user.id, DeletionChannel.APP)

    assert receipt.purge_after == svc.clock.now() + timedelta(days=30)
    with pytest.raises(AccountDeletedError):
        await svc.users.get_active(user.id)
    async with svc.sessions() as s:
        msg = await s.scalar(select(OutboxMessage).where(OutboxMessage.topic == "users.purge"))
    assert msg is not None
    assert msg.payload == {"user_id": str(user.id)}
    assert msg.available_at == receipt.purge_after


async def test_repeated_deletion_request_is_idempotent(svc: Services) -> None:
    user, _ = await svc.users.sign_in(PRIYA)

    first = await svc.users.request_deletion(user.id, DeletionChannel.APP)
    svc.clock.advance(timedelta(days=1))
    second = await svc.users.request_deletion(user.id, DeletionChannel.WEB)

    assert first == second
    assert await _count(svc, OutboxMessage, topic="users.purge") == 1
    assert await _count(svc, AccountDeletion) == 1


async def test_purge_waits_for_the_grace_period_then_removes_everything(svc: Services) -> None:
    user, _ = await svc.users.sign_in(PRIYA)
    await svc.users.register_device(
        user.id, uuid.uuid4(), DeviceRegistration(platform=Platform.ANDROID, app_version="0.1.0")
    )
    await svc.users.request_deletion(user.id, DeletionChannel.APP)

    assert await svc.users.purge(user.id) is PurgeOutcome.NOT_DUE
    svc.clock.advance(timedelta(days=30))
    assert await svc.users.purge(user.id) is PurgeOutcome.PURGED

    assert await _count(svc, User) == 0
    assert await _count(svc, AuthIdentity) == 0
    assert await _count(svc, UserDevice) == 0
    async with svc.sessions() as s:
        record = await s.scalar(select(AccountDeletion))
    assert record is not None
    assert record.purged_at == svc.clock.now()


async def test_purge_is_idempotent_and_never_touches_active_accounts(svc: Services) -> None:
    active, _ = await svc.users.sign_in(PRIYA)

    assert await svc.users.purge(active.id) is PurgeOutcome.NOTHING_TO_DO
    assert await _count(svc, User) == 1
    assert await svc.users.purge(uuid.uuid4()) is PurgeOutcome.NOTHING_TO_DO


async def test_purge_handler_retries_when_fired_early(svc: Services) -> None:
    user, _ = await svc.users.sign_in(PRIYA)
    await svc.users.request_deletion(user.id, DeletionChannel.APP)
    envelope = OutboxEnvelope(uuid.uuid4(), "users.purge", {"user_id": str(user.id)}, attempt=1)

    with pytest.raises(PurgeNotDueError):
        await svc.users.handle_purge(envelope)

    svc.clock.advance(timedelta(days=30))
    await svc.users.handle_purge(envelope)
    await svc.users.handle_purge(envelope)  # redelivery is harmless
    assert await _count(svc, User) == 0
