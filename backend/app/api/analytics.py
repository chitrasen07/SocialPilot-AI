"""Organization analytics derived from messages, drafts, and feedback."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.deps import SessionDep, require_role
from app.models import OrganizationMember, Role
from app.services import analytics as analytics_service

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

Viewer = Annotated[OrganizationMember, Depends(require_role(Role.VIEWER))]


@router.get("/overview")
async def overview(membership: Viewer, session: SessionDep) -> dict[str, Any]:
    return await analytics_service.overview(session, membership.organization_id)


@router.get("/customers")
async def customers(membership: Viewer, session: SessionDep) -> dict[str, Any]:
    return await analytics_service.customer_metrics(session, membership.organization_id)


@router.get("/channels")
async def channels(membership: Viewer, session: SessionDep) -> dict[str, Any]:
    return await analytics_service.channel_metrics(session, membership.organization_id)


@router.get("/ai-performance")
async def ai_performance(membership: Viewer, session: SessionDep) -> dict[str, Any]:
    return await analytics_service.ai_performance(session, membership.organization_id)
