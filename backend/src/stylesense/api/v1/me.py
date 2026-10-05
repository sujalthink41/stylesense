import uuid

from fastapi import APIRouter, Depends, status

from stylesense.api.auth import Claims
from stylesense.api.dependencies import ContainerDep
from stylesense.api.rate_limit import rate_limited_user
from stylesense.modules.personalization.schemas import (
    StyleOptions,
    StyleProfileUpdate,
    StyleProfileView,
    SwipeInput,
    SwipeReceipt,
)
from stylesense.modules.users.schemas import (
    ConsentInput,
    ConsentRecord,
    DeletionChannel,
    DeletionReceipt,
    Device,
    DeviceRegistration,
    ProfileUpdate,
    UserProfile,
)

router = APIRouter(
    prefix="/me", tags=["me"], dependencies=[Depends(rate_limited_user("api.per_user"))]
)


@router.get("", summary="Profile of the signed-in user")
async def get_me(claims: Claims, container: ContainerDep) -> UserProfile:
    return await container.users.get_active(claims.user_id)


@router.patch("", summary="Update profile fields")
async def update_me(body: ProfileUpdate, claims: Claims, container: ContainerDep) -> UserProfile:
    return await container.users.update_profile(claims.user_id, body)


@router.delete(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Delete my account (data purged after the grace period)",
)
async def delete_me(claims: Claims, container: ContainerDep) -> DeletionReceipt:
    return await container.auth.delete_account(claims.user_id, DeletionChannel.APP)


@router.put(
    "/devices/{installation_id}",
    summary="Register or update this device (idempotent upsert by installation id)",
)
async def put_device(
    installation_id: uuid.UUID, body: DeviceRegistration, claims: Claims, container: ContainerDep
) -> Device:
    return await container.users.register_device(claims.user_id, installation_id, body)


@router.delete("/devices/{installation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    installation_id: uuid.UUID, claims: Claims, container: ContainerDep
) -> None:
    await container.users.remove_device(claims.user_id, installation_id)


@router.get("/consents", summary="Current answer per consent kind")
async def list_consents(claims: Claims, container: ContainerDep) -> list[ConsentRecord]:
    return await container.users.current_consents(claims.user_id)


@router.post("/consents", status_code=status.HTTP_201_CREATED, summary="Record a consent answer")
async def record_consent(
    body: ConsentInput, claims: Claims, container: ContainerDep
) -> ConsentRecord:
    return await container.users.record_consent(claims.user_id, body)


# ---------- Style DNA & swipes ----------


@router.get("/style-profile", summary="My Style DNA and what my swipes taught the stylist")
async def get_style_profile(claims: Claims, container: ContainerDep) -> StyleProfileView:
    return await container.personalization.profile(claims.user_id)


@router.put("/style-profile", summary="Save Style DNA (full replace; idempotent)")
async def put_style_profile(
    body: StyleProfileUpdate, claims: Claims, container: ContainerDep
) -> StyleProfileView:
    return await container.personalization.update_profile(claims.user_id, body)


@router.get("/style-profile/options", summary="What onboarding offers: styles and sizes")
async def style_options(claims: Claims, container: ContainerDep) -> StyleOptions:
    return container.personalization.options()


# Own router: swipes are frequent, so they get their own budget instead of api.per_user.
swipes_router = APIRouter(
    prefix="/me", tags=["me"], dependencies=[Depends(rate_limited_user("swipes.per_user"))]
)


@swipes_router.post(
    "/swipes", summary="Record a swipe; replays of the same swipe are ignored (safe to retry)"
)
async def swipe(body: SwipeInput, claims: Claims, container: ContainerDep) -> SwipeReceipt:
    return await container.personalization.record_swipe(claims.user_id, body)
