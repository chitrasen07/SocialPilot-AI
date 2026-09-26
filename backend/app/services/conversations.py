import base64
import binascii
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, true, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.errors import AppError
from app.models import Conversation, ConversationStatus, Message

logger = logging.getLogger("socialpilot.conversations")


@dataclass(frozen=True)
class MessagePreview:
    content: str | None
    sender_type: str
    message_type: str
    sent_at: datetime


@dataclass(frozen=True)
class ConversationRow:
    conversation: Conversation
    last_message: MessagePreview | None


async def list_conversations(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    status: ConversationStatus | None,
    customer_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[ConversationRow], bool]:
    """Most recent activity first, each with its latest message. Returns (rows, has_more)."""
    latest = (
        select(Message.content, Message.sender_type, Message.message_type, Message.sent_at)
        .where(Message.conversation_id == Conversation.id)
        .order_by(Message.sent_at.desc(), Message.id.desc())
        .limit(1)
        .lateral("latest")
    )
    query = (
        select(Conversation, latest)
        .outerjoin(latest, true())
        .options(joinedload(Conversation.customer))
        .where(Conversation.organization_id == organization_id)
    )
    if status is not None:
        query = query.where(Conversation.status == status)
    if customer_id is not None:
        query = query.where(Conversation.customer_id == customer_id)
    rows = (
        await session.execute(
            query.order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.id.desc())
            .limit(limit + 1)
            .offset(offset)
        )
    ).all()
    items = [
        ConversationRow(
            conversation,
            MessagePreview(content, sender_type, message_type, sent_at) if sent_at else None,
        )
        for conversation, content, sender_type, message_type, sent_at in rows[:limit]
    ]
    return items, len(rows) > limit


async def get_conversation(
    session: AsyncSession, organization_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation:
    conversation = await session.scalar(
        select(Conversation)
        .options(joinedload(Conversation.customer))
        .where(
            Conversation.id == conversation_id,
            Conversation.organization_id == organization_id,
        )
    )
    if conversation is None:
        raise AppError("CONVERSATION_NOT_FOUND", "Conversation not found.", 404)
    return conversation


async def update_status(
    session: AsyncSession,
    organization_id: uuid.UUID,
    conversation_id: uuid.UUID,
    status: ConversationStatus,
) -> Conversation:
    conversation = await get_conversation(session, organization_id, conversation_id)
    if conversation.status == status:
        return conversation
    conversation.status = status
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        # uq_conversations_active_customer: reopening while a newer thread is active.
        raise AppError(
            "CONVERSATION_ALREADY_ACTIVE",
            "This customer already has an active conversation.",
            409,
        ) from exc
    logger.info(
        "conversation_status_changed",
        extra={"fields": {"conversation_id": str(conversation.id), "status": str(status)}},
    )
    return conversation


def encode_cursor(message: Message) -> str:
    raw = f"{message.sent_at.isoformat()}|{message.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        sent_at, message_id = raw.split("|", 1)
        return datetime.fromisoformat(sent_at), uuid.UUID(message_id)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise AppError("INVALID_CURSOR", "The pagination cursor is invalid.", 400) from exc


async def list_messages(
    session: AsyncSession,
    organization_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    limit: int,
    before: str | None,
) -> tuple[list[Message], str | None]:
    """The newest `limit` messages older than the cursor, returned oldest-first.

    Returns (messages, cursor for the next older page or None).
    """
    await get_conversation(session, organization_id, conversation_id)
    query = select(Message).where(
        Message.organization_id == organization_id,
        Message.conversation_id == conversation_id,
    )
    if before:
        query = query.where(tuple_(Message.sent_at, Message.id) < _decode_cursor(before))
    rows = list(
        await session.scalars(
            query.order_by(Message.sent_at.desc(), Message.id.desc()).limit(limit + 1)
        )
    )
    page = rows[:limit]
    next_cursor = encode_cursor(page[-1]) if len(rows) > limit else None
    page.reverse()
    return page, next_cursor
