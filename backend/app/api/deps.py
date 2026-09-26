import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.errors import AppError
from app.core.firebase import TokenVerifier, VerifiedIdentity
from app.db.session import get_session
from app.models import OrganizationMember, Role, User

ORGANIZATION_HEADER = "x-organization-id"

_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_identity(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> VerifiedIdentity:
    if credentials is None:
        raise AppError("AUTHENTICATION_REQUIRED", "Authentication is required.", 401)
    verifier: TokenVerifier | None = request.app.state.token_verifier
    if verifier is None:
        raise AppError(
            "AUTH_NOT_CONFIGURED", "Authentication is not configured on this server.", 503
        )
    identity = await verifier.verify(credentials.credentials)
    if not identity.email or not identity.email_verified:
        raise AppError("EMAIL_NOT_VERIFIED", "Verify your email address to continue.", 403)
    return identity


IdentityDep = Annotated[VerifiedIdentity, Depends(get_identity)]


async def get_current_user(identity: IdentityDep, session: SessionDep) -> User:
    user = await session.scalar(select(User).where(User.firebase_uid == identity.uid))
    if user is None:
        raise AppError("USER_NOT_FOUND", "Complete sign-in before using the API.", 404)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_membership(
    request: Request, user: CurrentUser, session: SessionDep
) -> OrganizationMember:
    """Resolves the active organization from the `{organization_id}` path parameter or the
    X-Organization-Id header, and requires the caller to be a member of it."""
    raw_id = request.path_params.get("organization_id") or request.headers.get(ORGANIZATION_HEADER)
    if not raw_id:
        raise AppError("ORGANIZATION_REQUIRED", "An organization must be specified.", 400)
    try:
        organization_id = uuid.UUID(raw_id)
    except ValueError as exc:
        raise AppError("INVALID_ORGANIZATION_ID", "The organization ID is invalid.", 400) from exc

    membership = await session.scalar(
        select(OrganizationMember)
        .options(joinedload(OrganizationMember.organization))
        .where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user.id,
        )
    )
    if membership is None:
        raise AppError(
            "ORGANIZATION_ACCESS_DENIED", "You do not have access to this organization.", 403
        )
    return membership


CurrentMembership = Annotated[OrganizationMember, Depends(get_current_membership)]


def require_role(minimum: Role) -> Callable[..., Awaitable[OrganizationMember]]:
    async def dependency(membership: CurrentMembership) -> OrganizationMember:
        if not membership.role.at_least(minimum):
            raise AppError(
                "INSUFFICIENT_ROLE",
                f"This action requires the {minimum.value} role or higher.",
                403,
            )
        return membership

    return dependency
