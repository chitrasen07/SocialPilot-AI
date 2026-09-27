"""Read-only engagement intelligence. Viewer and above. Nothing is sent."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.deps import SessionDep, require_role
from app.models import OrganizationMember, Role
from app.services.intelligence_engine import customer_insights, dashboard

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])

Viewer = Annotated[OrganizationMember, Depends(require_role(Role.VIEWER))]


@router.get("/dashboard")
async def intelligence_dashboard(membership: Viewer, session: SessionDep) -> dict[str, Any]:
    return await dashboard(session, membership.organization_id)


@router.get("/customers/{customer_id}")
async def intelligence_customer(
    customer_id: uuid.UUID, membership: Viewer, session: SessionDep
) -> dict[str, Any]:
    return await customer_insights(session, membership.organization_id, customer_id)
