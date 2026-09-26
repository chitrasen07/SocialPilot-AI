import re
import secrets
import uuid

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.firebase import VerifiedIdentity
from app.db.base import utcnow
from app.models import Organization, OrganizationMember, Role, User


def make_slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] or "workspace"
    return f"{base}-{secrets.token_hex(3)}"


def default_workspace_name(user: User) -> str:
    display = (user.name or user.email.split("@")[0]).strip()
    return f"{display[:80]}'s Workspace"


async def sync_user(session: AsyncSession, identity: VerifiedIdentity) -> tuple[User, bool]:
    """Creates or updates the user for a verified Firebase identity.

    New users get a personal organization with an owner membership in the same transaction.
    INSERT ... ON CONFLICT makes concurrent first logins safe: exactly one request inserts.
    """
    now = utcnow()
    profile = {
        "email": identity.email,
        "email_verified": identity.email_verified,
        "last_login_at": now,
        "updated_at": now,
    }
    # Email sign-up tokens may lack a name until the profile update propagates; keep stored values.
    optional = {"name": identity.name, "avatar_url": identity.picture}
    profile |= {key: value for key, value in optional.items() if value is not None}

    user = await session.scalar(
        insert(User)
        .values(id=uuid.uuid4(), firebase_uid=identity.uid, created_at=now, **profile)
        .on_conflict_do_nothing(index_elements=[User.firebase_uid])
        .returning(User)
    )
    is_new = user is not None
    if user is None:
        user = await session.scalar(
            update(User)
            .where(User.firebase_uid == identity.uid)
            .values(**profile)
            .returning(User)
            .execution_options(synchronize_session=False)
        )
    assert user is not None

    if is_new:
        name = default_workspace_name(user)
        organization = Organization(name=name, slug=make_slug(name))
        session.add(organization)
        await session.flush()
        session.add(
            OrganizationMember(organization_id=organization.id, user_id=user.id, role=Role.OWNER)
        )

    await session.commit()
    return user, is_new


async def list_memberships(session: AsyncSession, user_id: uuid.UUID) -> list[OrganizationMember]:
    result = await session.scalars(
        select(OrganizationMember)
        .options(joinedload(OrganizationMember.organization))
        .where(OrganizationMember.user_id == user_id)
        .order_by(OrganizationMember.created_at)
    )
    return list(result)
