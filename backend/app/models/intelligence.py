"""Customer intelligence, suggestions, segments, analytics, and draft feedback.

These rows are organization-scoped. They are not model training data and they are not sent.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, string_enum


class SuggestionStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SuggestionCategory(enum.StrEnum):
    PREFERENCE = "preference"
    COMMUNICATION = "communication"
    SHOPPING = "shopping"


class SegmentName(enum.StrEnum):
    NEW = "new_customer"
    RETURNING = "returning_customer"
    HIGH_INTENT = "high_intent_buyer"
    PRICE_SENSITIVE = "price_sensitive"
    PRODUCT_EXPLORER = "product_explorer"
    SUPPORT = "support_customer"


class FeedbackAction(enum.StrEnum):
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"


class CustomerIntelligence(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "customer_intelligence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            ondelete="CASCADE",
            name="fk_customer_intelligence_customer_org",
        ),
        UniqueConstraint(
            "organization_id", "customer_id", name="uq_customer_intelligence_org_customer"
        ),
        Index("ix_customer_intelligence_organization_id", "organization_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    customer_id: Mapped[uuid.UUID]
    summary: Mapped[str] = mapped_column(Text, default="")
    preferences: Mapped[list[str]] = mapped_column(JSONB, default=list)
    interests: Mapped[list[str]] = mapped_column(JSONB, default=list)
    frequent_products: Mapped[list[str]] = mapped_column(JSONB, default=list)
    buying_intent: Mapped[str] = mapped_column(String(16), default="unknown")
    communication_style: Mapped[str] = mapped_column(String(32), default="unknown")
    language_preference: Mapped[str] = mapped_column(String(16), default="unknown")
    previous_issues: Mapped[list[str]] = mapped_column(JSONB, default=list)
    sentiment_trend: Mapped[str] = mapped_column(String(16), default="unknown")


class MemorySuggestion(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "memory_suggestions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            ondelete="CASCADE",
            name="fk_memory_suggestions_customer_org",
        ),
        Index(
            "ix_memory_suggestions_organization_id_customer_id", "organization_id", "customer_id"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    customer_id: Mapped[uuid.UUID]
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[SuggestionCategory] = mapped_column(
        string_enum(SuggestionCategory, "suggestion_category", 24)
    )
    status: Mapped[SuggestionStatus] = mapped_column(
        string_enum(SuggestionStatus, "suggestion_status"), default=SuggestionStatus.PENDING
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class CustomerSegment(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "customer_segments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            ondelete="CASCADE",
            name="fk_customer_segments_customer_org",
        ),
        UniqueConstraint(
            "organization_id",
            "customer_id",
            "segment",
            name="uq_customer_segments_org_customer_segment",
        ),
        Index("ix_customer_segments_organization_id", "organization_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    customer_id: Mapped[uuid.UUID]
    segment: Mapped[SegmentName] = mapped_column(string_enum(SegmentName, "segment_name", 32))
    confidence: Mapped[float] = mapped_column(Float)


class ConversationAnalytics(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "conversation_analytics"
    __table_args__ = (
        UniqueConstraint("organization_id", "day", name="uq_conversation_analytics_org_day"),
        Index("ix_conversation_analytics_organization_id_day", "organization_id", "day"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    day: Mapped[date] = mapped_column(Date)
    total_messages: Mapped[int] = mapped_column(Integer, default=0)
    total_conversations: Mapped[int] = mapped_column(Integer, default=0)
    ai_generated: Mapped[int] = mapped_column(Integer, default=0)
    approved: Mapped[int] = mapped_column(Integer, default=0)
    edited: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    escalated: Mapped[int] = mapped_column(Integer, default=0)


class AIFeedback(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "ai_feedback"
    __table_args__ = (
        Index("ix_ai_feedback_organization_id", "organization_id"),
        Index("ix_ai_feedback_draft_id", "draft_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    draft_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_reply_drafts.id", ondelete="CASCADE")
    )
    original_text: Mapped[str | None] = mapped_column(Text)
    final_text: Mapped[str | None] = mapped_column(Text)
    action: Mapped[FeedbackAction] = mapped_column(string_enum(FeedbackAction, "feedback_action"))
    reason: Mapped[str | None] = mapped_column(Text)
