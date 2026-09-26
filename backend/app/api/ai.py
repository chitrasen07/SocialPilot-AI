import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.ai.errors import ai_rate_limited
from app.ai.orchestrator import AIOrchestrator
from app.api.deps import SessionDep, require_role
from app.core.config import Settings
from app.core.errors import AppError
from app.knowledge.citations import KnowledgeSource
from app.models import AIReplyDraft, MessageAIAnalysis, OrganizationMember, Role
from app.services import ai_data

router = APIRouter(prefix="/api/ai", tags=["ai"])

Viewer = Annotated[OrganizationMember, Depends(require_role(Role.VIEWER))]
Agent = Annotated[OrganizationMember, Depends(require_role(Role.AGENT))]
Admin = Annotated[OrganizationMember, Depends(require_role(Role.ADMIN))]


class MessageRequest(BaseModel):
    message_id: uuid.UUID


class AnalysisOut(BaseModel):
    message_id: uuid.UUID
    language: str
    language_confidence: float
    intent: str
    intent_confidence: float
    sentiment: str
    sentiment_confidence: float
    emotion: str
    emotion_confidence: float
    purchase_intent: str
    purchase_intent_confidence: float
    provider: str
    model: str
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None

    @classmethod
    def from_model(cls, row: MessageAIAnalysis) -> "AnalysisOut":
        return cls(
            message_id=row.message_id,
            language=row.language,
            language_confidence=row.language_confidence,
            intent=row.intent,
            intent_confidence=row.intent_confidence,
            sentiment=row.sentiment,
            sentiment_confidence=row.sentiment_confidence,
            emotion=row.emotion,
            emotion_confidence=row.emotion_confidence,
            purchase_intent=row.purchase_intent,
            purchase_intent_confidence=row.purchase_intent_confidence,
            provider=row.provider,
            model=row.model,
            latency_ms=row.latency_ms,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
        )


class DraftOut(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    reply_text: str | None
    status: str
    guardrail_status: str
    provider: str
    model: str
    sent: bool = False
    sources: list[KnowledgeSource] = Field(default_factory=list)

    @classmethod
    def from_model(cls, row: AIReplyDraft) -> "DraftOut":
        sources = [KnowledgeSource.model_validate(item) for item in (row.sources or [])]
        return cls(
            id=row.id,
            message_id=row.message_id,
            conversation_id=row.conversation_id,
            reply_text=row.reply_text,
            status=row.status.value,
            guardrail_status=row.guardrail_status.value,
            provider=row.provider,
            model=row.model,
            sources=sources,
        )


class MessageAIState(BaseModel):
    analysis: AnalysisOut | None
    draft: DraftOut | None


class SettingsOut(BaseModel):
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
    configured: bool


class SettingsUpdate(BaseModel):
    enabled: bool | None = None
    temperature: float | None = Field(default=None, ge=0, le=1)
    max_output_tokens: int | None = Field(default=None, ge=32, le=1024)
    max_context_messages: int | None = Field(default=None, ge=1, le=50)
    memory_top_k: int | None = Field(default=None, ge=0, le=20)
    auto_analysis_enabled: bool | None = None
    knowledge_enabled: bool | None = None
    knowledge_top_k: int | None = Field(default=None, ge=1, le=20)
    knowledge_max_distance: float | None = Field(default=None, ge=0, le=2)


def _orchestrator(request: Request) -> AIOrchestrator:
    return request.app.state.ai_orchestrator


def _settings(request: Request) -> Settings:
    return request.app.state.settings


async def _limit(request: Request, membership: OrganizationMember) -> None:
    settings: Settings = request.app.state.settings
    limit = settings.ai_requests_per_minute
    if limit <= 0:
        return
    redis = request.app.state.redis
    for key in (
        f"ai:rl:user:{membership.user_id}",
        f"ai:rl:org:{membership.organization_id}",
    ):
        try:
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 60)
        except Exception as exc:
            raise AppError("AI_UNAVAILABLE", "AI is temporarily unavailable.", 503) from exc
        if count > limit:
            raise ai_rate_limited()


@router.get("/messages/{message_id}")
async def message_state(
    message_id: uuid.UUID, membership: Viewer, session: SessionDep
) -> MessageAIState:
    await ai_data.get_message(session, membership.organization_id, message_id)
    analysis = await ai_data.get_analysis(session, membership.organization_id, message_id)
    draft = await ai_data.latest_draft(session, membership.organization_id, message_id)
    return MessageAIState(
        analysis=AnalysisOut.from_model(analysis) if analysis else None,
        draft=DraftOut.from_model(draft) if draft else None,
    )


@router.post("/analyze-message")
async def analyze_message(
    body: MessageRequest,
    request: Request,
    membership: Viewer,
    session: SessionDep,
) -> AnalysisOut:
    await _limit(request, membership)
    row = await _orchestrator(request).analyze(session, membership.organization_id, body.message_id)
    return AnalysisOut.from_model(row)


@router.post("/generate-reply")
async def generate_reply(
    body: MessageRequest,
    request: Request,
    membership: Agent,
    session: SessionDep,
) -> DraftOut:
    await _limit(request, membership)
    draft = await _orchestrator(request).generate_reply(
        session, membership.organization_id, body.message_id
    )
    return DraftOut.from_model(draft)


@router.get("/settings")
async def get_settings(membership: Admin, request: Request, session: SessionDep) -> SettingsOut:
    settings = _settings(request)
    current = await ai_data.effective_settings(session, membership.organization_id, settings)
    return _settings_out(current, settings.ai_configured)


@router.patch("/settings")
async def update_settings(
    body: SettingsUpdate, membership: Admin, request: Request, session: SessionDep
) -> SettingsOut:
    settings = _settings(request)
    updates: dict[str, Any] = {
        key: value for key, value in body.model_dump().items() if value is not None
    }
    await ai_data.upsert_settings(session, membership.organization_id, settings, updates)
    current = await ai_data.effective_settings(session, membership.organization_id, settings)
    return _settings_out(current, settings.ai_configured)


def _settings_out(current: ai_data.EffectiveAISettings, configured: bool) -> SettingsOut:
    return SettingsOut(
        enabled=current.enabled,
        provider=current.provider,
        model=current.model,
        temperature=current.temperature,
        max_output_tokens=current.max_output_tokens,
        max_context_messages=current.max_context_messages,
        memory_top_k=current.memory_top_k,
        auto_analysis_enabled=current.auto_analysis_enabled,
        knowledge_enabled=current.knowledge_enabled,
        knowledge_top_k=current.knowledge_top_k,
        knowledge_max_distance=current.knowledge_max_distance,
        configured=configured,
    )
