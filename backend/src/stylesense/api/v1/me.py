import uuid

from fastapi import APIRouter, Depends, status

from stylesense.api.auth import Claims
from stylesense.api.dependencies import ContainerDep
from stylesense.api.rate_limit import rate_limited_user
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
