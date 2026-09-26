import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.models import OrganizationMember, Role


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str | None
    avatar_url: str | None
    email_verified: bool
    created_at: datetime
    last_login_at: datetime | None


class OrganizationOut(BaseModel):
    """An organization as seen by the current user, including their role in it."""

    id: uuid.UUID
    name: str
    slug: str
    role: Role
    created_at: datetime

    @classmethod
    def from_membership(cls, membership: OrganizationMember) -> "OrganizationOut":
        org = membership.organization
        return cls(
            id=org.id, name=org.name, slug=org.slug, role=membership.role, created_at=org.created_at
        )


class OrganizationList(BaseModel):
    items: list[OrganizationOut]


class OrganizationUpdate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class MeResponse(BaseModel):
    user: UserOut
    organizations: list[OrganizationOut]


class SyncResponse(MeResponse):
    is_new_user: bool
