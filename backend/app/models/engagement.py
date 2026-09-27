"""Engagement intelligence. These rows describe commercial conversation signals.

They are not model training data, they are not sent to a customer, and they do not store
inferred sensitive attributes.
"""

import enum
import uuid

from sqlalchemy import (
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, string_enum


class ConversationStage(enum.StrEnum):
    DISCOVERY = "discovery"
    PRODUCT_INTEREST = "product_interest"
    PRICING = "pricing"
    NEGOTIATION = "negotiation"
    PURCHASE_INTENT = "purchase_intent"
    SUPPORT = "support"
    COMPLAINT = "complaint"
    RESOLVED = "resolved"


class Urgency(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class JourneyStage(enum.StrEnum):
    VISITOR = "visitor"
    LEAD = "lead"
    INTERESTED = "interested"
    QUALIFIED = "qualified"
    CUSTOMER = "customer"
    REPEAT_CUSTOMER = "repeat_customer"
    INACTIVE = "inactive"


class ConversationIntelligence(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "conversation_intelligence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["conversations.id", "conversations.organization_id"],
            ondelete="CASCADE",
            name="fk_conversation_intelligence_conversation_org",
        ),
        UniqueConstraint(
            "organization_id",
            "conversation_id",
            name="uq_conversation_intelligence_org_conversation",
        ),
        Index("ix_conversation_intelligence_organization_id", "organization_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    conversation_id: Mapped[uuid.UUID]
    stage: Mapped[ConversationStage] = mapped_column(
        string_enum(ConversationStage, "engagement_stage", 32)
    )
    intent: Mapped[str] = mapped_column(String(32), default="unknown")
    urgency: Mapped[Urgency] = mapped_column(string_enum(Urgency, "engagement_urgency"))
    buying_probability: Mapped[float] = mapped_column(Float, default=0)
    churn_probability: Mapped[float] = mapped_column(Float, default=0)
    customer_goal: Mapped[str] = mapped_column(Text, default="")
    recommended_action: Mapped[str] = mapped_column(Text, default="")


class CustomerJourney(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "customer_journey"
    __table_args__ = (
        ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            ondelete="CASCADE",
            name="fk_customer_journey_customer_org",
        ),
        Index("ix_customer_journey_organization_id_customer_id", "organization_id", "customer_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    customer_id: Mapped[uuid.UUID]
    current_stage: Mapped[JourneyStage] = mapped_column(
        string_enum(JourneyStage, "journey_stage", 32)
    )
    previous_stage: Mapped[JourneyStage | None] = mapped_column(
        string_enum(JourneyStage, "journey_previous_stage", 32)
    )
    changed_reason: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0)


class CustomerScore(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "customer_scores"
    __table_args__ = (
        ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            ondelete="CASCADE",
            name="fk_customer_scores_customer_org",
        ),
        UniqueConstraint("organization_id", "customer_id", name="uq_customer_scores_org_customer"),
        Index("ix_customer_scores_organization_id", "organization_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    customer_id: Mapped[uuid.UUID]
    lead_score: Mapped[int] = mapped_column(Integer, default=0)
    score_reason: Mapped[str] = mapped_column(Text, default="")


class CustomerRecommendation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "customer_recommendations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            ondelete="CASCADE",
            name="fk_customer_recommendations_customer_org",
        ),
        Index(
            "ix_customer_recommendations_organization_id_customer_id",
            "organization_id",
            "customer_id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    customer_id: Mapped[uuid.UUID]
    product_name: Mapped[str] = mapped_column(String(120))
    reason: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0)


class AIResponseScore(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "ai_response_scores"
    __table_args__ = (
        UniqueConstraint("draft_id", name="uq_ai_response_scores_draft_id"),
        Index("ix_ai_response_scores_organization_id", "organization_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    draft_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_reply_drafts.id", ondelete="CASCADE")
    )
    clarity_score: Mapped[int] = mapped_column(Integer)
    helpfulness_score: Mapped[int] = mapped_column(Integer)
    brand_score: Mapped[int] = mapped_column(Integer)
    conversion_score: Mapped[int] = mapped_column(Integer)


class LearningMetric(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "learning_metrics"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "personality",
            "response_length",
            "language_mode",
            "emoji_policy",
            name="uq_learning_metrics_style",
        ),
        Index("ix_learning_metrics_organization_id", "organization_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    personality: Mapped[str] = mapped_column(String(32))
    response_length: Mapped[str] = mapped_column(String(16))
    language_mode: Mapped[str] = mapped_column(String(16))
    emoji_policy: Mapped[str] = mapped_column(String(32))
    accepted: Mapped[int] = mapped_column(Integer, default=0)
    edited: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
