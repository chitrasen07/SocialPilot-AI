import enum
import uuid
from typing import Any

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, string_enum


class AnalysisStatus(enum.StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class DraftStatus(enum.StrEnum):
    GENERATED = "generated"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class GuardrailStatus(enum.StrEnum):
    PASSED = "passed"
    BLOCKED = "blocked"


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
