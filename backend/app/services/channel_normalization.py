"""Turns any channel payload into the same customer, conversation, and message rows."""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import ChannelProvider, InboundMessage
from app.db.base import utcnow
from app.models import (
    ACTIVE_CONVERSATION_STATUSES,
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageType,
    SenderType,
)
from app.models.channel import (
    ChannelType,
    ConversationChannel,
    ConversationPriority,
)
from app.services.automation import on_customer_message

logger = logging.getLogger("socialpilot.channels")


async def ensure_channel(
    session: AsyncSession, organization_id: uuid.UUID, channel_type: ChannelType
) -> uuid.UUID:
    existing = await session.scalar(
        select(ConversationChannel.id).where(
            ConversationChannel.organization_id == organization_id,
            ConversationChannel.channel_type == channel_type,
        )
    )
    if existing is not None:
        return existing
    created = await session.scalar(
        insert(ConversationChannel)
        .values(organization_id=organization_id, channel_type=channel_type)
        .on_conflict_do_nothing(index_elements=["organization_id", "channel_type"])
        .returning(ConversationChannel.id)
    )
    if created is not None:
        return created
    again = await session.scalar(
        select(ConversationChannel.id).where(
            ConversationChannel.organization_id == organization_id,
            ConversationChannel.channel_type == channel_type,
        )
    )
    if again is None:
        raise RuntimeError("could not resolve a channel")
    return again


async def ingest(
    session: AsyncSession,
    organization_id: uuid.UUID,
    provider: ChannelProvider,
    inbound: InboundMessage,
    *,
    prepare_draft: bool = False,
) -> Message | None:
    """Stores one inbound message. A draft may be prepared. Nothing is sent."""
    if inbound.sender_is_business or not inbound.sender_id:
        return None
    channel_id = await ensure_channel(session, organization_id, provider.channel)
    profile = provider.get_customer_profile(inbound.sender_id, {})
    customer_id = await _customer(session, organization_id, provider.channel, profile)
    conversation_id = await _conversation(
        session, organization_id, customer_id, channel_id, provider.channel
    )
    message_id = await session.scalar(
        insert(Message)
        .values(
            organization_id=organization_id,
            conversation_id=conversation_id,
            customer_id=customer_id,
            external_message_id=f"{provider.channel.value}:{inbound.external_id}",
            sender_type=SenderType.CUSTOMER,
            content=inbound.text,
            message_type=MessageType.TEXT,
            sent_at=inbound.occurred_at if inbound.occurred_at.tzinfo else datetime.now(UTC),
            channel_id=channel_id,
            channel_type=provider.channel,
            sender_identifier=inbound.sender_id[:255],
            receiver_identifier=(inbound.recipient_id or "")[:255] or None,
        )
        .on_conflict_do_nothing(index_elements=["organization_id", "external_message_id"])
        .returning(Message.id)
    )
    if message_id is None:
        return None
    await session.execute(
        Conversation.__table__.update()
        .where(Conversation.id == conversation_id)
        .values(
            last_message_at=inbound.occurred_at,
            channel_id=channel_id,
            channel_type=provider.channel,
        )
    )
    await session.commit()
    await on_customer_message(
        session,
        organization_id,
        customer_id,
        conversation_id,
        message_id,
        inbound.text,
    )
    from app.services.intelligence_engine import observe_customer_message

    await observe_customer_message(
        session,
        organization_id,
        customer_id,
        conversation_id,
        message_id,
        inbound.text,
    )
    if prepare_draft:
        await _draft(session, organization_id, message_id)
    message = await session.get(Message, message_id)
    return message


async def _customer(
    session: AsyncSession,
    organization_id: uuid.UUID,
    channel_type: ChannelType,
    profile,
) -> uuid.UUID:
    existing = await session.scalar(
        select(Customer.id).where(
            Customer.organization_id == organization_id,
            Customer.channel_type == channel_type,
            Customer.external_user_id == profile.external_id,
        )
    )
    if existing is not None:
        return existing
    now = utcnow()
    created = await session.scalar(
        insert(Customer)
        .values(
            organization_id=organization_id,
            channel_type=channel_type,
            external_user_id=profile.external_id[:255],
            display_name=profile.display_name,
            username=profile.username,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(
            index_elements=["organization_id", "channel_type", "external_user_id"],
            index_where=text("instagram_account_id IS NULL"),
        )
        .returning(Customer.id)
    )
    if created is not None:
        return created
    again = await session.scalar(
        select(Customer.id).where(
            Customer.organization_id == organization_id,
            Customer.channel_type == channel_type,
            Customer.external_user_id == profile.external_id,
        )
    )
    if again is None:
        raise RuntimeError("could not resolve a customer")
    return again


async def _conversation(
    session: AsyncSession,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    channel_id: uuid.UUID,
    channel_type: ChannelType,
) -> uuid.UUID:
    existing = await session.scalar(
        select(Conversation.id).where(
            Conversation.customer_id == customer_id,
            Conversation.status.in_(ACTIVE_CONVERSATION_STATUSES),
        )
    )
    if existing is not None:
        return existing
    created = await session.scalar(
        insert(Conversation)
        .values(
            organization_id=organization_id,
            customer_id=customer_id,
            channel_id=channel_id,
            channel_type=channel_type,
            status=ConversationStatus.OPEN,
            priority=ConversationPriority.MEDIUM,
        )
        .returning(Conversation.id)
    )
    if created is None:
        raise RuntimeError("could not open a conversation")
    return created


async def _draft(session: AsyncSession, organization_id: uuid.UUID, message_id: uuid.UUID) -> None:
    from app.ai.factory import build_ai
    from app.ai.orchestrator import AIOrchestrator
    from app.core.config import get_settings
    from app.core.errors import AppError

    settings = get_settings()
    built = build_ai(settings)
    if built is None:
        return
    provider, embeddings = built
    orchestrator = AIOrchestrator(provider, embeddings, settings)
    try:
        await orchestrator.generate_reply(session, organization_id, message_id)
    except AppError:
        logger.info("channel_draft_skipped")
