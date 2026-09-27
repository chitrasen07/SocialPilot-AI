import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, string_enum


class AnalysisStatus(enum.StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class DraftStatus(enum.StrEnum):
    # `generated` is the normal draft state from Phase 5. New workflow states are added beside it.
    GENERATED = "generated"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"
    EXPIRED = "expired"


class GuardrailStatus(enum.StrEnum):
    PASSED = "passed"
    BLOCKED = "blocked"


class RiskLevel(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Personality(enum.StrEnum):
    PROFESSIONAL = "professional"
    FRIENDLY = "friendly"
    CASUAL = "casual"
    PREMIUM = "premium"
    PLAYFUL = "playful"
    CUSTOM = "custom"


class EmojiPolicy(enum.StrEnum):
    NONE = "none"
    MINIMAL = "minimal"
    MODERATE = "moderate"
    MATCH_CUSTOMER = "match_customer"


class ResponseLength(enum.StrEnum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class LanguageMode(enum.StrEnum):
    AUTO = "auto"
    ENGLISH = "english"
    HINDI = "hindi"
    HINGLISH = "hinglish"
    TELUGU = "telugu"


class MessageAIAnalysis(UUIDPrimaryKey, Timestamps, Base):
    """One structured read of a message. Raw prompts are not stored."""

    __tablename__ = "message_ai_analysis"
    __table_args__ = (
        UniqueConstraint("message_id"),
        Index("ix_message_ai_analysis_organization_id", "organization_id"),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    language: Mapped[str] = mapped_column(String(16))
    language_confidence: Mapped[float] = mapped_column(Float)
    intent: Mapped[str] = mapped_column(String(32))
    intent_confidence: Mapped[float] = mapped_column(Float)
    sentiment: Mapped[str] = mapped_column(String(16))
    sentiment_confidence: Mapped[float] = mapped_column(Float)
    emotion: Mapped[str] = mapped_column(String(24))
    emotion_confidence: Mapped[float] = mapped_column(Float)
    purchase_intent: Mapped[str] = mapped_column(String(16))
    purchase_intent_confidence: Mapped[float] = mapped_column(Float)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    processing_status: Mapped[AnalysisStatus] = mapped_column(
        string_enum(AnalysisStatus, "analysis_status")
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)


class AIReplyDraft(UUIDPrimaryKey, Timestamps, Base):
    """A draft only. Nothing here is sent to Instagram."""

    __tablename__ = "ai_reply_drafts"
    __table_args__ = (
        Index("ix_ai_reply_drafts_organization_id", "organization_id"),
        Index("ix_ai_reply_drafts_message_id", "message_id"),
        Index("ix_ai_reply_drafts_conversation_id", "conversation_id"),
        Index("ix_ai_reply_drafts_organization_id_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    reply_text: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    status: Mapped[DraftStatus] = mapped_column(string_enum(DraftStatus, "draft_status"))
    guardrail_status: Mapped[GuardrailStatus] = mapped_column(
        string_enum(GuardrailStatus, "guardrail_status")
    )
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB(none_as_null=True))
    risk_level: Mapped[RiskLevel] = mapped_column(
        string_enum(RiskLevel, "draft_risk_level"), default=RiskLevel.LOW
    )
    escalation_required: Mapped[bool] = mapped_column(default=False)
    escalation_reason: Mapped[str | None] = mapped_column(Text)
    guardrail_results: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    edited_text: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)


class OrganizationAISettings(UUIDPrimaryKey, Timestamps, Base):
    """Per-organization AI behavior. The provider API key is never stored here."""

    __tablename__ = "ai_settings"
    __table_args__ = (UniqueConstraint("organization_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(default=True)
    temperature: Mapped[float] = mapped_column(Float)
    max_output_tokens: Mapped[int] = mapped_column(Integer)
    max_context_messages: Mapped[int] = mapped_column(Integer)
    memory_top_k: Mapped[int] = mapped_column(Integer)
    auto_analysis_enabled: Mapped[bool] = mapped_column(default=False)
    knowledge_enabled: Mapped[bool] = mapped_column(default=True)
    knowledge_top_k: Mapped[int] = mapped_column(Integer, default=5)
    knowledge_max_distance: Mapped[float] = mapped_column(Float, default=0.5)
    personality: Mapped[Personality] = mapped_column(
        string_enum(Personality, "ai_personality"), default=Personality.FRIENDLY
    )
    brand_voice: Mapped[str] = mapped_column(Text, default="")
    custom_instructions: Mapped[str] = mapped_column(Text, default="")
    preferred_terms: Mapped[list[str]] = mapped_column(JSONB, default=list)
    forbidden_terms: Mapped[list[str]] = mapped_column(JSONB, default=list)
    emoji_policy: Mapped[EmojiPolicy] = mapped_column(
        string_enum(EmojiPolicy, "ai_emoji_policy"), default=EmojiPolicy.MINIMAL
    )
    response_length: Mapped[ResponseLength] = mapped_column(
        string_enum(ResponseLength, "ai_response_length"), default=ResponseLength.MEDIUM
    )
    language_mode: Mapped[LanguageMode] = mapped_column(
        string_enum(LanguageMode, "ai_language_mode"), default=LanguageMode.AUTO
    )
    require_review_for_refunds: Mapped[bool] = mapped_column(default=True)
    require_review_for_payment_issues: Mapped[bool] = mapped_column(default=True)
    require_review_for_high_risk: Mapped[bool] = mapped_column(default=True)
    require_review_for_unsupported_claims: Mapped[bool] = mapped_column(default=True)
