from fastapi import APIRouter, Depends, Response, status

from stylesense.api.dependencies import ContainerDep
from stylesense.api.rate_limit import rate_limited
from stylesense.modules.auth.schemas import (
    GoogleSignInRequest,
    RefreshRequest,
    SignInResult,
    TokenPair,
)

router = APIRouter(
    prefix="/auth", tags=["auth"], dependencies=[Depends(rate_limited("auth.per_ip"))]
)

NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}  # tokens must never be cached


@router.post("/google", summary="Sign in with a Google ID token")
async def sign_in_with_google(
    body: GoogleSignInRequest, response: Response, container: ContainerDep
) -> SignInResult:
    response.headers.update(NO_STORE)
    return await container.auth.sign_in_with_google(
        body.id_token, installation_id=body.installation_id
    )


@router.post("/refresh", summary="Exchange a refresh token for a new token pair")
async def refresh(body: RefreshRequest, response: Response, container: ContainerDep) -> TokenPair:
    response.headers.update(NO_STORE)
    return await container.auth.refresh(body.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="End this session")
async def logout(body: RefreshRequest, container: ContainerDep) -> None:
    await container.auth.logout(body.refresh_token)
