import enum
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, string_enum, utcnow


class DeliveryStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class WebhookDelivery(UUIDPrimaryKey, Timestamps, Base):
    """A raw, signature-verified webhook request, stored before acknowledging it.

    PostgreSQL is the source of truth for processing state; the Redis queue only wakes
    workers, so lost queue messages are recovered by the sweeper.
    """

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        Index(
            "ix_webhook_deliveries_due",
            "next_attempt_at",
            postgresql_where=text("status IN ('pending', 'processing')"),
        ),
    )

    source: Mapped[str] = mapped_column(String(32))
    # SHA-256 of the raw body: Meta retries resend identical bodies, so duplicates collapse.
    payload_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    # Cleared once processed; normalized events keep only what later phases need.
    # none_as_null: Python None must become SQL NULL, not the JSON value `null`.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    status: Mapped[DeliveryStatus] = mapped_column(
        string_enum(DeliveryStatus, "webhook_delivery_status"), default=DeliveryStatus.PENDING
    )
    attempts: Mapped[int] = mapped_column(default=0)
    # When pending: earliest retry time. When processing: when the claim expires.
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_error: Mapped[str | None] = mapped_column(String(500))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
