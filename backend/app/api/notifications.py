"""In-app notifications for the signed-in member. These are not emails or Instagram messages."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import SessionDep, require_role
from app.models import OrganizationMember, Role
from app.models.automation import Notification
from app.services import automation as service

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

Viewer = Annotated[OrganizationMember, Depends(require_role(Role.VIEWER))]


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    message: str
    read: bool
    created_at: datetime


class NotificationList(BaseModel):
    items: list[NotificationOut]
    unread_count: int


def _out(row: Notification) -> NotificationOut:
    return NotificationOut(
        id=row.id,
        type=row.type.value,
        title=row.title,
        message=row.message,
        read=row.read,
        created_at=row.created_at,
    )


@router.get("")
async def list_notifications(membership: Viewer, session: SessionDep) -> NotificationList:
    rows, unread = await service.list_notifications(
        session, membership.organization_id, membership.user_id
    )
    return NotificationList(items=[_out(row) for row in rows], unread_count=unread)


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: uuid.UUID, membership: Viewer, session: SessionDep
) -> NotificationOut:
    row = await service.mark_read(
        session, membership.organization_id, membership.user_id, notification_id
    )
    return _out(row)
