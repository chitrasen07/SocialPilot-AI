"""Human follow-up tasks. Completing a task does not message the customer."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import SessionDep, require_role
from app.core.errors import AppError
from app.db.base import utcnow
from app.models import Conversation, Customer, OrganizationMember, Role
from app.models.automation import Task, TaskPriority, TaskStatus
from app.services import automation as service

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

Viewer = Annotated[OrganizationMember, Depends(require_role(Role.VIEWER))]
Agent = Annotated[OrganizationMember, Depends(require_role(Role.AGENT))]


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    customer_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    priority: Literal["low", "medium", "high"] = "medium"
    assigned_to: uuid.UUID | None = None


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    status: Literal["open", "in_progress", "completed", "cancelled"] | None = None
    priority: Literal["low", "medium", "high"] | None = None
    assigned_to: uuid.UUID | None = None


class TaskOut(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID | None
    conversation_id: uuid.UUID | None
    title: str
    description: str
    status: str
    priority: str
    assigned_to: uuid.UUID | None
    created_at: datetime
    completed_at: datetime | None


class TaskList(BaseModel):
    items: list[TaskOut]


def _out(task: Task) -> TaskOut:
    return TaskOut(
        id=task.id,
        customer_id=task.customer_id,
        conversation_id=task.conversation_id,
        title=task.title,
        description=task.description,
        status=task.status.value,
        priority=task.priority.value,
        assigned_to=task.assigned_to,
        created_at=task.created_at,
        completed_at=task.completed_at,
    )


async def _owns(
    session,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID | None,
    conversation_id: uuid.UUID | None,
) -> None:
    if customer_id is not None:
        found = await session.scalar(
            select(Customer.id).where(
                Customer.id == customer_id, Customer.organization_id == organization_id
            )
        )
        if found is None:
            raise AppError("CUSTOMER_NOT_FOUND", "Customer not found.", 404)
    if conversation_id is not None:
        found = await session.scalar(
            select(Conversation.id).where(
                Conversation.id == conversation_id,
                Conversation.organization_id == organization_id,
            )
        )
        if found is None:
            raise AppError("CONVERSATION_NOT_FOUND", "Conversation not found.", 404)


@router.get("")
async def list_tasks(
    membership: Viewer,
    session: SessionDep,
    status: Literal["open", "in_progress", "completed", "cancelled"] | None = None,
    priority: Literal["low", "medium", "high"] | None = None,
    assigned: Literal["me"] | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> TaskList:
    rows = await service.list_tasks(
        session,
        membership.organization_id,
        status=TaskStatus(status) if status else None,
        priority=TaskPriority(priority) if priority else None,
        assigned_to=membership.user_id if assigned == "me" else None,
        limit=limit,
    )
    return TaskList(items=[_out(row) for row in rows])


@router.post("", status_code=201)
async def create_task(body: TaskIn, membership: Agent, session: SessionDep) -> TaskOut:
    await _owns(session, membership.organization_id, body.customer_id, body.conversation_id)
    if body.assigned_to is not None and not membership.role.at_least(Role.ADMIN):
        if body.assigned_to != membership.user_id:
            raise AppError("TASK_FORBIDDEN", "You can only assign a task to yourself.", 403)
    task = Task(
        organization_id=membership.organization_id,
        customer_id=body.customer_id,
        conversation_id=body.conversation_id,
        title=body.title.strip(),
        description=body.description.strip(),
        status=TaskStatus.OPEN,
        priority=TaskPriority(body.priority),
        assigned_to=body.assigned_to,
    )
    saved = await service.save_task(session, task)
    return _out(saved)


@router.patch("/{task_id}")
async def update_task(
    task_id: uuid.UUID, body: TaskPatch, membership: Agent, session: SessionDep
) -> TaskOut:
    task = await service.get_task(session, membership.organization_id, task_id)
    admin = membership.role.at_least(Role.ADMIN)
    if not admin and task.assigned_to not in {None, membership.user_id}:
        raise AppError("TASK_FORBIDDEN", "This task is assigned to someone else.", 403)
    if body.assigned_to is not None and not admin and body.assigned_to != membership.user_id:
        raise AppError("TASK_FORBIDDEN", "You can only assign a task to yourself.", 403)
    if body.title is not None:
        task.title = body.title.strip()
    if body.description is not None:
        task.description = body.description.strip()
    if body.priority is not None:
        task.priority = TaskPriority(body.priority)
    if body.assigned_to is not None:
        task.assigned_to = body.assigned_to
    if body.status is not None:
        task.status = TaskStatus(body.status)
        task.completed_at = utcnow() if task.status == TaskStatus.COMPLETED else None
    saved = await service.save_task(session, task)
    return _out(saved)
