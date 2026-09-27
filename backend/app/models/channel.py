"""Channel records shared by every inbox. Credentials stay encrypted and are not returned."""

import enum
import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, string_enum


class ChannelType(enum.StrEnum):
    INSTAGRAM = "instagram"
    WHATSAPP = "whatsapp"
    MESSENGER = "messenger"
    EMAIL = "email"
    WEBCHAT = "webchat"


class ChannelStatus(enum.StrEnum):
    CONNECTED = "connected"
    PENDING = "pending"
    DISCONNECTED = "disconnected"


class ChannelProviderName(enum.StrEnum):
    META = "meta"
    MOCK = "mock"
    WIDGET = "widget"
    EMAIL = "email"


class ConversationPriority(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConversationChannel(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "conversation_channels"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "channel_type", name="uq_conversation_channels_org_type"
        ),
        Index("ix_conversation_channels_organization_id", "organization_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    channel_type: Mapped[ChannelType] = mapped_column(string_enum(ChannelType, "channel_type", 16))


class ChannelSettings(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "channel_settings"
    __table_args__ = (Index("ix_channel_settings_organization_id", "organization_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversation_channels.id", ondelete="CASCADE")
    )
    provider: Mapped[ChannelProviderName] = mapped_column(
        string_enum(ChannelProviderName, "channel_provider", 16)
    )
    status: Mapped[ChannelStatus] = mapped_column(
        string_enum(ChannelStatus, "channel_status"), default=ChannelStatus.PENDING
    )
    display_name: Mapped[str] = mapped_column(String(120), default="")
    # Fernet ciphertext. API responses never include this value.
    webhook_secret: Mapped[str | None] = mapped_column(Text)


class ChannelAnalytics(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "channel_analytics"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "day", "channel_type", name="uq_channel_analytics_org_day_channel"
        ),
        Index("ix_channel_analytics_organization_id_day", "organization_id", "day"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    day: Mapped[date] = mapped_column(Date)
    channel_type: Mapped[ChannelType] = mapped_column(
        string_enum(ChannelType, "analytics_channel", 16)
    )
    total_messages: Mapped[int] = mapped_column(Integer, default=0)
    total_conversations: Mapped[int] = mapped_column(Integer, default=0)
    ai_generated: Mapped[int] = mapped_column(Integer, default=0)
    approved: Mapped[int] = mapped_column(Integer, default=0)
