from fastapi import APIRouter

from app.api.deps import CurrentUser, IdentityDep, SessionDep
from app.schemas.accounts import MeResponse, OrganizationOut, SyncResponse, UserOut
from app.services.accounts import list_memberships, sync_user

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/sync")
async def sync(identity: IdentityDep, session: SessionDep) -> SyncResponse:
    user, is_new = await sync_user(session, identity)
    memberships = await list_memberships(session, user.id)
    return SyncResponse(
        user=UserOut.model_validate(user),
        organizations=[OrganizationOut.from_membership(m) for m in memberships],
        is_new_user=is_new,
    )


@router.get("/me")
async def me(user: CurrentUser, session: SessionDep) -> MeResponse:
    memberships = await list_memberships(session, user.id)
    return MeResponse(
        user=UserOut.model_validate(user),
        organizations=[OrganizationOut.from_membership(m) for m in memberships],
    )
