import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey, string_enum
from app.models.channel import ChannelType, ConversationPriority
from app.models.customer import Customer


class ConversationStatus(enum.StrEnum):
    OPEN = "open"
    PENDING = "pending"
    CLOSED = "closed"


ACTIVE_CONVERSATION_STATUSES = (ConversationStatus.OPEN, ConversationStatus.PENDING)


class Conversation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        # organization_id must equal the customer's organization.
        ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            ondelete="CASCADE",
            name="fk_conversations_customer_org",
        ),
        UniqueConstraint("id", "organization_id"),
        # At most one active (open/pending) conversation per customer; closed ones are history.
        # Also the arbiter that makes concurrent conversation creation safe.
        Index(
            "uq_conversations_active_customer",
            "customer_id",
            unique=True,
            postgresql_where=text("status IN ('open', 'pending')"),
        ),
        Index("ix_conversations_customer_id_last_message_at", "customer_id", "last_message_at"),
        Index(
            "ix_conversations_organization_id_last_message_at",
            "organization_id",
            text("last_message_at DESC NULLS LAST"),
        ),
        Index("ix_conversations_organization_id_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    customer_id: Mapped[uuid.UUID]
    instagram_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("instagram_accounts.id", ondelete="CASCADE"), index=True
    )
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversation_channels.id", ondelete="SET NULL")
    )
    channel_type: Mapped[ChannelType] = mapped_column(
        string_enum(ChannelType, "conversation_channel", 16), default=ChannelType.INSTAGRAM
    )
    priority: Mapped[ConversationPriority] = mapped_column(
        string_enum(ConversationPriority, "conversation_priority"),
        default=ConversationPriority.MEDIUM,
    )
    status: Mapped[ConversationStatus] = mapped_column(
        string_enum(ConversationStatus, "conversation_status"), default=ConversationStatus.OPEN
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped[Customer] = relationship(lazy="raise")


class SenderType(enum.StrEnum):
    CUSTOMER = "customer"
    BUSINESS = "business"
    SYSTEM = "system"


class MessageType(enum.StrEnum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    UNKNOWN = "unknown"


class Message(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["conversations.id", "conversations.organization_id"],
            ondelete="CASCADE",
            name="fk_messages_conversation_org",
        ),
        # Idempotency arbiter for webhook redelivery and concurrent workers.
        UniqueConstraint("organization_id", "external_message_id"),
        Index("ix_messages_conversation_id_sent_at", "conversation_id", "sent_at", "id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    conversation_id: Mapped[uuid.UUID]
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    instagram_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("instagram_accounts.id", ondelete="CASCADE"), index=True
    )
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversation_channels.id", ondelete="SET NULL")
    )
    channel_type: Mapped[ChannelType] = mapped_column(
        string_enum(ChannelType, "message_channel", 16), default=ChannelType.INSTAGRAM
    )
    sender_identifier: Mapped[str | None] = mapped_column(String(255))
    receiver_identifier: Mapped[str | None] = mapped_column(String(255))
    external_message_id: Mapped[str | None] = mapped_column(String(255))
    sender_type: Mapped[SenderType] = mapped_column(string_enum(SenderType, "sender_type"))
    content: Mapped[str | None] = mapped_column(Text)
    message_type: Mapped[MessageType] = mapped_column(string_enum(MessageType, "message_type"))
    meta: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB(none_as_null=True))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
