import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentMembership, CurrentUser, SessionDep, require_role
from app.models import OrganizationMember, Role
from app.schemas.accounts import OrganizationList, OrganizationOut, OrganizationUpdate
from app.services.accounts import list_memberships

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


@router.get("")
async def list_organizations(user: CurrentUser, session: SessionDep) -> OrganizationList:
    memberships = await list_memberships(session, user.id)
    return OrganizationList(items=[OrganizationOut.from_membership(m) for m in memberships])


# `organization_id` is declared so it appears in the OpenAPI schema; access is enforced by the
# membership dependency, which reads the same path parameter.
@router.get("/{organization_id}")
async def get_organization(
    organization_id: uuid.UUID, membership: CurrentMembership
) -> OrganizationOut:
    return OrganizationOut.from_membership(membership)


@router.patch("/{organization_id}")
async def update_organization(
    organization_id: uuid.UUID,
    body: OrganizationUpdate,
    membership: Annotated[OrganizationMember, Depends(require_role(Role.ADMIN))],
    session: SessionDep,
) -> OrganizationOut:
    membership.organization.name = body.name
    await session.commit()
    return OrganizationOut.from_membership(membership)
