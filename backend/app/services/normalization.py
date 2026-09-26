"""Turns stored Instagram message events into customers, conversations and messages.

Runs inside the webhook delivery transaction. Every step is idempotent and safe under
concurrent workers because each one is arbitrated by a database unique constraint, never by
a read-then-write check alone.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, literal_column, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.integrations.instagram.webhooks import NormalizedEvent
from app.models import (
    ACTIVE_CONVERSATION_STATUSES,
    Conversation,
    Customer,
    InstagramAccount,
    Message,
    MessageType,
    SenderType,
)

logger = logging.getLogger("socialpilot.normalization")

_MEDIA_TYPES = {MessageType.IMAGE, MessageType.VIDEO, MessageType.AUDIO}
# Matches the predicate of uq_conversations_active_customer.
_ACTIVE_PREDICATE = text("status IN ('open', 'pending')")


async def normalize_message_event(
    session: AsyncSession, account: InstagramAccount, event: NormalizedEvent
) -> None:
    item = event.payload
    message: dict[str, Any] = item.get("message") or {}
    sender_id = str((item.get("sender") or {}).get("id") or "")
    recipient_id = str((item.get("recipient") or {}).get("id") or "")

    # Echoes are messages the business account sent; the customer is then the recipient.
    from_business = bool(message.get("is_echo")) or sender_id == account.instagram_account_id
    customer_user_id = recipient_id if from_business else sender_id
    log_fields = {"organization_id": str(account.organization_id), "event_type": "message"}
    if not customer_user_id:
        logger.warning("instagram_event_skipped", extra={"fields": log_fields})
        return

    if message.get("is_deleted"):
        await _mark_deleted(session, account.organization_id, event.external_id)
        logger.info("instagram_event_normalized", extra={"fields": log_fields})
        return

    if await _message_exists(session, account.organization_id, event.external_id):
        logger.info("message_duplicate", extra={"fields": log_fields})
        return

    customer_id = await _upsert_customer(session, account, customer_user_id)
    conversation_id = await _active_conversation(session, account, customer_id)
    message_id = await session.scalar(
        insert(Message)
        .values(
            organization_id=account.organization_id,
            conversation_id=conversation_id,
            customer_id=customer_id,
            instagram_account_id=account.id,
            external_message_id=event.external_id,
            sender_type=SenderType.BUSINESS if from_business else SenderType.CUSTOMER,
            content=message.get("text"),
            message_type=_message_type(message),
            meta=_message_metadata(message),
            sent_at=event.occurred_at,
        )
        .on_conflict_do_nothing(index_elements=["organization_id", "external_message_id"])
        .returning(Message.id)
    )
    if message_id is None:
        logger.info("message_duplicate", extra={"fields": log_fields})
        return

    await _touch_conversation(session, conversation_id, event.occurred_at)
    logger.info(
        "message_created",
        extra={"fields": {**log_fields, "message_id": str(message_id)}},
    )
    logger.info("instagram_event_normalized", extra={"fields": log_fields})


async def _message_exists(
    session: AsyncSession, organization_id: uuid.UUID, external_message_id: str
) -> bool:
    """Cheap fast path for redeliveries; the unique constraint remains the real guard."""
    found = await session.scalar(
        select(Message.id).where(
            Message.organization_id == organization_id,
            Message.external_message_id == external_message_id,
        )
    )
    return found is not None


async def _upsert_customer(
    session: AsyncSession, account: InstagramAccount, instagram_user_id: str
) -> uuid.UUID:
    now = utcnow()
    statement = insert(Customer).values(
        organization_id=account.organization_id,
        instagram_account_id=account.id,
        instagram_user_id=instagram_user_id,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    row = (
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=["organization_id", "instagram_account_id", "instagram_user_id"],
                set_={"updated_at": now},
            ).returning(Customer.id, literal_column("xmax = 0").label("inserted"))
        )
    ).one()
    if row.inserted:
        logger.info(
            "customer_created",
            extra={
                "fields": {
                    "organization_id": str(account.organization_id),
                    "customer_id": str(row.id),
                }
            },
        )
    return row.id


async def _active_conversation(
    session: AsyncSession, account: InstagramAccount, customer_id: uuid.UUID
) -> uuid.UUID:
    # The retry covers an agent closing the conversation between our insert and select.
    for _ in range(3):
        created = await session.scalar(
            insert(Conversation)
            .values(
                organization_id=account.organization_id,
                customer_id=customer_id,
                instagram_account_id=account.id,
            )
            .on_conflict_do_nothing(index_elements=["customer_id"], index_where=_ACTIVE_PREDICATE)
            .returning(Conversation.id)
        )
        if created is not None:
            logger.info(
                "conversation_created",
                extra={
                    "fields": {
                        "organization_id": str(account.organization_id),
                        "conversation_id": str(created),
                    }
                },
            )
            return created
        existing = await session.scalar(
            select(Conversation.id).where(
                Conversation.customer_id == customer_id,
                Conversation.status.in_(ACTIVE_CONVERSATION_STATUSES),
            )
        )
        if existing is not None:
            return existing
    raise RuntimeError("could not resolve an active conversation")


async def _touch_conversation(
    session: AsyncSession, conversation_id: uuid.UUID, sent_at: datetime
) -> None:
    # GREATEST keeps last_message_at correct when webhooks arrive out of order.
    await session.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(
            last_message_at=func.greatest(
                func.coalesce(Conversation.last_message_at, sent_at), sent_at
            ),
            updated_at=utcnow(),
        )
    )


async def _mark_deleted(
    session: AsyncSession, organization_id: uuid.UUID, external_message_id: str
) -> None:
    """The customer unsent the message: drop its content, keep the thread position."""
    await session.execute(
        update(Message)
        .where(
            Message.organization_id == organization_id,
            Message.external_message_id == external_message_id,
        )
        .values(content=None, meta={"deleted": True}, updated_at=utcnow())
    )


def _message_type(message: dict[str, Any]) -> MessageType:
    attachments = message.get("attachments") or []
    if attachments:
        kind = attachments[0].get("type") if isinstance(attachments[0], dict) else None
        return MessageType(kind) if kind in _MEDIA_TYPES else MessageType.UNKNOWN
    return MessageType.TEXT if message.get("text") else MessageType.UNKNOWN


def _message_metadata(message: dict[str, Any]) -> dict[str, Any] | None:
    meta: dict[str, Any] = {}
    attachments = [a for a in message.get("attachments") or [] if isinstance(a, dict)]
    if attachments:
        meta["attachments"] = [
            {"type": a.get("type"), "url": (a.get("payload") or {}).get("url")} for a in attachments
        ]
    if reply_to := message.get("reply_to"):
        meta["reply_to"] = reply_to
    return meta or None
