import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import MessageAnalysis, Usage
from app.core.config import Settings
from app.core.errors import AppError
from app.db.base import utcnow
from app.models import (
    AIReplyDraft,
    AnalysisStatus,
    DraftStatus,
    GuardrailStatus,
    Message,
    MessageAIAnalysis,
    OrganizationAISettings,
)


@dataclass(frozen=True)
class EffectiveAISettings:
    enabled: bool
    provider: str
    model: str
    temperature: float
    max_output_tokens: int
    max_context_messages: int
    memory_top_k: int
    auto_analysis_enabled: bool
    knowledge_enabled: bool
    knowledge_top_k: int
    knowledge_max_distance: float


def defaults_from(settings: Settings) -> EffectiveAISettings:
    model = settings.gemini_model if settings.ai_provider == "gemini" else "mock"
    return EffectiveAISettings(
        enabled=True,
        provider=settings.ai_provider,
        model=model,
        temperature=settings.ai_temperature,
        max_output_tokens=settings.ai_max_output_tokens,
        max_context_messages=settings.ai_max_context_messages,
        memory_top_k=settings.ai_memory_top_k,
        auto_analysis_enabled=False,
        knowledge_enabled=True,
        knowledge_top_k=settings.knowledge_retrieval_top_k,
        knowledge_max_distance=settings.knowledge_retrieval_max_distance,
    )


async def get_message(
    session: AsyncSession, organization_id: uuid.UUID, message_id: uuid.UUID
) -> Message:
    message = await session.scalar(
        select(Message).where(Message.id == message_id, Message.organization_id == organization_id)
    )
    if message is None:
        raise AppError("MESSAGE_NOT_FOUND", "Message not found.", 404)
    return message


async def get_analysis(
    session: AsyncSession, organization_id: uuid.UUID, message_id: uuid.UUID
) -> MessageAIAnalysis | None:
    return await session.scalar(
        select(MessageAIAnalysis).where(
            MessageAIAnalysis.message_id == message_id,
            MessageAIAnalysis.organization_id == organization_id,
        )
    )


async def save_analysis(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    message_id: uuid.UUID,
    analysis: MessageAnalysis,
    provider: str,
    model: str,
    usage: Usage,
    latency_ms: int,
) -> MessageAIAnalysis:
    values = {
        "id": uuid.uuid4(),
        "organization_id": organization_id,
        "message_id": message_id,
        "language": analysis.language.value,
        "language_confidence": analysis.language.confidence,
        "intent": analysis.intent.value,
        "intent_confidence": analysis.intent.confidence,
        "sentiment": analysis.sentiment.value,
        "sentiment_confidence": analysis.sentiment.confidence,
        "emotion": analysis.emotion.value,
        "emotion_confidence": analysis.emotion.confidence,
        "purchase_intent": analysis.purchase_intent.value,
        "purchase_intent_confidence": analysis.purchase_intent.confidence,
        "provider": provider,
        "model": model,
        "processing_status": AnalysisStatus.COMPLETED,
        "latency_ms": latency_ms,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
    }
    row = await session.scalar(
        insert(MessageAIAnalysis)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["message_id"])
        .returning(MessageAIAnalysis)
    )
    await session.commit()
    if row is not None:
        return row
    existing = await get_analysis(session, organization_id, message_id)
    assert existing is not None
    return existing


async def latest_draft(
    session: AsyncSession, organization_id: uuid.UUID, message_id: uuid.UUID
) -> AIReplyDraft | None:
    return await session.scalar(
        select(AIReplyDraft)
        .where(
            AIReplyDraft.message_id == message_id,
            AIReplyDraft.organization_id == organization_id,
        )
        .order_by(AIReplyDraft.created_at.desc())
    )


async def save_draft(
    session: AsyncSession,
    *,
    message: Message,
    reply_text: str | None,
    provider: str,
    model: str,
    status: DraftStatus,
    guardrail_status: GuardrailStatus,
    usage: Usage,
    latency_ms: int,
    sources: list[dict] | None = None,
) -> AIReplyDraft:
    draft = AIReplyDraft(
        organization_id=message.organization_id,
        message_id=message.id,
        conversation_id=message.conversation_id,
        customer_id=message.customer_id,
        reply_text=reply_text,
        provider=provider,
        model=model,
        status=status,
        guardrail_status=guardrail_status,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        latency_ms=latency_ms,
        sources=sources,
    )
    session.add(draft)
    await session.commit()
    return draft


async def effective_settings(
    session: AsyncSession, organization_id: uuid.UUID, settings: Settings
) -> EffectiveAISettings:
    base = defaults_from(settings)
    stored = await session.scalar(
        select(OrganizationAISettings).where(
            OrganizationAISettings.organization_id == organization_id
        )
    )
    if stored is None:
        return base
    return EffectiveAISettings(
        enabled=stored.enabled,
        provider=base.provider,
        model=stored.model or base.model,
        temperature=stored.temperature,
        max_output_tokens=stored.max_output_tokens,
        max_context_messages=stored.max_context_messages,
        memory_top_k=stored.memory_top_k,
        auto_analysis_enabled=stored.auto_analysis_enabled,
        knowledge_enabled=stored.knowledge_enabled,
        knowledge_top_k=stored.knowledge_top_k,
        knowledge_max_distance=stored.knowledge_max_distance,
    )


async def upsert_settings(
    session: AsyncSession,
    organization_id: uuid.UUID,
    settings: Settings,
    updates: dict,
) -> OrganizationAISettings:
    current = await effective_settings(session, organization_id, settings)
    values = {
        "organization_id": organization_id,
        "provider": current.provider,
        "model": current.model,
        "enabled": current.enabled,
        "temperature": current.temperature,
        "max_output_tokens": current.max_output_tokens,
        "max_context_messages": current.max_context_messages,
        "memory_top_k": current.memory_top_k,
        "auto_analysis_enabled": current.auto_analysis_enabled,
        "knowledge_enabled": current.knowledge_enabled,
        "knowledge_top_k": current.knowledge_top_k,
        "knowledge_max_distance": current.knowledge_max_distance,
    }
    values.update(updates)
    await session.execute(
        insert(OrganizationAISettings)
        .values(id=uuid.uuid4(), **values)
        .on_conflict_do_update(
            index_elements=["organization_id"],
            set_={key: values[key] for key in values if key != "organization_id"}
            | {"updated_at": utcnow()},
        )
    )
    await session.commit()
    stored = await session.scalar(
        select(OrganizationAISettings).where(
            OrganizationAISettings.organization_id == organization_id
        )
    )
    assert stored is not None
    return stored
