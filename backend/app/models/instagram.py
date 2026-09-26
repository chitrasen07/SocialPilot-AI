import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, deferred, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, string_enum


class ConnectionStatus(enum.StrEnum):
    CONNECTED = "connected"
    NEEDS_REAUTH = "needs_reauth"
    DISCONNECTED = "disconnected"


class InstagramAccount(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "instagram_accounts"
    __table_args__ = (
        UniqueConstraint("organization_id", "instagram_account_id"),
        # An Instagram account can be actively connected to at most one organization.
        Index(
            "uq_instagram_accounts_active_account",
            "instagram_account_id",
            unique=True,
            postgresql_where=text("connection_status <> 'disconnected'"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    # Instagram professional account ID (IG ID); matches `entry[].id` in webhook payloads.
    instagram_account_id: Mapped[str] = mapped_column(String(64))
    username: Mapped[str] = mapped_column(String(64))
    account_type: Mapped[str | None] = mapped_column(String(32))
    connection_status: Mapped[ConnectionStatus] = mapped_column(
        string_enum(ConnectionStatus, "instagram_connection_status")
    )
    # Fernet ciphertext (see app.core.crypto). Deferred so ordinary queries never load it.
    access_token_ciphertext: Mapped[str | None] = deferred(mapped_column(Text))
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_webhook_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InstagramEventType(enum.StrEnum):
    MESSAGE = "message"
    COMMENT = "comment"


class InstagramEvent(UUIDPrimaryKey, Timestamps, Base):
    """A normalized, organization-scoped event extracted from a webhook delivery."""

    __tablename__ = "instagram_events"
    __table_args__ = (
        UniqueConstraint("instagram_account_id", "event_type", "external_id"),
        Index("ix_instagram_events_organization_id_occurred_at", "organization_id", "occurred_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    instagram_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instagram_accounts.id", ondelete="CASCADE")
    )
    event_type: Mapped[InstagramEventType] = mapped_column(
        string_enum(InstagramEventType, "instagram_event_type")
    )
    # Meta's ID for the message (`mid`) or comment (`id`); makes processing idempotent.
    external_id: Mapped[str] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
