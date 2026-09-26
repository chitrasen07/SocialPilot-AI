import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import SessionDep, require_role
from app.models import ConversationStatus, OrganizationMember, Role
from app.schemas.conversations import (
    ConversationDetail,
    ConversationList,
    ConversationListItem,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
    MessagePage,
)
from app.services import conversations as service

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

Viewer = Annotated[OrganizationMember, Depends(require_role(Role.VIEWER))]
Agent = Annotated[OrganizationMember, Depends(require_role(Role.AGENT))]
MessageLimit = Annotated[int, Query(ge=1, le=100)]


@router.get("")
async def list_conversations(
    membership: Viewer,
    session: SessionDep,
    status: ConversationStatus | None = None,
    customer_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> ConversationList:
    rows, has_more = await service.list_conversations(
        session,
        membership.organization_id,
        status=status,
        customer_id=customer_id,
        limit=limit,
        offset=offset,
    )
    return ConversationList(
        items=[ConversationListItem.from_row(row) for row in rows], has_more=has_more
    )


async def _message_page(
    session: SessionDep,
    membership: OrganizationMember,
    conversation_id: uuid.UUID,
    limit: int,
    before: str | None,
) -> MessagePage:
    messages, next_cursor = await service.list_messages(
        session, membership.organization_id, conversation_id, limit=limit, before=before
    )
    return MessagePage(items=[MessageOut.from_model(m) for m in messages], next_cursor=next_cursor)


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    membership: Viewer,
    session: SessionDep,
    limit: MessageLimit = 50,
) -> ConversationDetail:
    conversation = await service.get_conversation(
        session, membership.organization_id, conversation_id
    )
    page = await _message_page(session, membership, conversation_id, limit, None)
    return ConversationDetail(
        **ConversationOut.model_validate(conversation).model_dump(), messages=page
    )


@router.patch("/{conversation_id}")
async def update_conversation(
    conversation_id: uuid.UUID, body: ConversationUpdate, membership: Agent, session: SessionDep
) -> ConversationOut:
    conversation = await service.update_status(
        session, membership.organization_id, conversation_id, body.status
    )
    return ConversationOut.model_validate(conversation)


@router.get("/{conversation_id}/messages")
async def list_messages(
    conversation_id: uuid.UUID,
    membership: Viewer,
    session: SessionDep,
    limit: MessageLimit = 50,
    before: Annotated[str | None, Query(max_length=200)] = None,
) -> MessagePage:
    return await _message_page(session, membership, conversation_id, limit, before)
