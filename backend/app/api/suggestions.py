"""Approve or reject a memory suggestion. Approval writes a customer memory."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.customers import SuggestionOut, _suggestion_out
from app.api.deps import SessionDep, require_role
from app.models import OrganizationMember, Role
from app.services import customer_intelligence

router = APIRouter(prefix="/api/memory-suggestions", tags=["memory-suggestions"])

Agent = Annotated[OrganizationMember, Depends(require_role(Role.AGENT))]


@router.post("/{suggestion_id}/approve")
async def approve_suggestion(
    suggestion_id: uuid.UUID, membership: Agent, session: SessionDep
) -> SuggestionOut:
    row = await customer_intelligence.review_suggestion(
        session,
        membership.organization_id,
        suggestion_id,
        membership.user_id,
        approve=True,
    )
    return _suggestion_out(row)


@router.post("/{suggestion_id}/reject")
async def reject_suggestion(
    suggestion_id: uuid.UUID, membership: Agent, session: SessionDep
) -> SuggestionOut:
    row = await customer_intelligence.review_suggestion(
        session,
        membership.organization_id,
        suggestion_id,
        membership.user_id,
        approve=False,
    )
    return _suggestion_out(row)
