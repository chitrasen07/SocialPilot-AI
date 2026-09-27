import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.ai.errors import ai_rate_limited
from app.ai.orchestrator import AIOrchestrator
from app.api.deps import SessionDep, require_role
from app.core.config import Settings
from app.core.errors import AppError
from app.knowledge.citations import KnowledgeSource
from app.models import AIReplyDraft, Customer, Message, MessageAIAnalysis, OrganizationMember, Role
from app.models.intelligence import FeedbackAction
from app.services import ai_data, draft_review
from app.services.feedback import submit_feedback

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
    risk_level: str = "low"
    escalation_required: bool = False
    escalation_reason: str | None = None
    guardrail_results: dict[str, Any] = Field(
        default_factory=lambda: {"blocked": False, "flags": []}
    )
    edited_text: str | None = None
    review_note: str | None = None
    reviewed_at: datetime | None = None

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
            risk_level=row.risk_level.value,
            escalation_required=row.escalation_required,
            escalation_reason=row.escalation_reason,
            guardrail_results=row.guardrail_results or {"blocked": False, "flags": []},
            edited_text=row.edited_text,
            review_note=row.review_note,
            reviewed_at=row.reviewed_at,
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
    personality: str
    brand_voice: str
    custom_instructions: str
    preferred_terms: list[str]
    forbidden_terms: list[str]
    emoji_policy: str
    response_length: str
    language_mode: str
    require_review_for_refunds: bool
    require_review_for_payment_issues: bool
    require_review_for_high_risk: bool
    require_review_for_unsupported_claims: bool
    updated_at: datetime | None
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
    personality: (
        Literal["professional", "friendly", "casual", "premium", "playful", "custom"] | None
    ) = None
    brand_voice: str | None = Field(default=None, max_length=2000)
    custom_instructions: str | None = Field(default=None, max_length=4000)
    preferred_terms: list[str] | None = Field(default=None, max_length=40)
    forbidden_terms: list[str] | None = Field(default=None, max_length=40)
    emoji_policy: Literal["none", "minimal", "moderate", "match_customer"] | None = None
    response_length: Literal["short", "medium", "long"] | None = None
    language_mode: Literal["auto", "english", "hindi", "hinglish", "telugu"] | None = None
    require_review_for_refunds: bool | None = None
    require_review_for_payment_issues: bool | None = None
    require_review_for_high_risk: bool | None = None
    require_review_for_unsupported_claims: bool | None = None


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
    if "brand_voice" in updates:
        updates["brand_voice"] = _plain(updates["brand_voice"], 2000)
    if "custom_instructions" in updates:
        updates["custom_instructions"] = _plain(updates["custom_instructions"], 4000)
    if "preferred_terms" in updates:
        updates["preferred_terms"] = _terms(updates["preferred_terms"])
    if "forbidden_terms" in updates:
        updates["forbidden_terms"] = _terms(updates["forbidden_terms"])
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
        personality=current.personality,
        brand_voice=current.brand_voice,
        custom_instructions=current.custom_instructions,
        preferred_terms=current.preferred_terms,
        forbidden_terms=current.forbidden_terms,
        emoji_policy=current.emoji_policy,
        response_length=current.response_length,
        language_mode=current.language_mode,
        require_review_for_refunds=current.require_review_for_refunds,
        require_review_for_payment_issues=current.require_review_for_payment_issues,
        require_review_for_high_risk=current.require_review_for_high_risk,
        require_review_for_unsupported_claims=current.require_review_for_unsupported_claims,
        updated_at=current.updated_at,
        configured=configured,
    )


class ReviewNote(BaseModel):
    review_note: str | None = Field(default=None, max_length=1000)


class EditDraft(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class EscalateDraft(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


class FeedbackIn(BaseModel):
    action: Literal["approved", "edited", "rejected"]
    final_text: str | None = Field(default=None, max_length=4000)
    reason: str | None = Field(default=None, max_length=500)


class FeedbackOut(BaseModel):
    id: uuid.UUID
    draft_id: uuid.UUID
    action: str
    created_at: datetime


class QueueItem(DraftOut):
    customer_name: str
    message_preview: str


class QueuePage(BaseModel):
    items: list[QueueItem]
    has_more: bool


@router.get("/review-queue")
async def review_queue(
    membership: Viewer,
    session: SessionDep,
    review_filter: Literal["all", "review_required", "high", "medium", "low", "escalated"] = Query(
        default="all", alias="filter"
    ),
    limit: int = Query(default=20, ge=1, le=100),
) -> QueuePage:
    rows, has_more = await draft_review.list_queue(
        session,
        membership.organization_id,
        review_filter=review_filter,
        limit=limit,
    )
    return QueuePage(
        items=[_queue_item(draft, customer, message) for draft, customer, message in rows],
        has_more=has_more,
    )


@router.post("/drafts/{draft_id}/approve")
async def approve_draft(
    draft_id: uuid.UUID, request: Request, membership: Agent, session: SessionDep
) -> DraftOut:
    draft = await draft_review.approve(
        session, membership.organization_id, draft_id, membership.user_id, _settings(request)
    )
    return DraftOut.from_model(draft)


@router.post("/drafts/{draft_id}/reject")
async def reject_draft(
    draft_id: uuid.UUID, body: ReviewNote, membership: Agent, session: SessionDep
) -> DraftOut:
    draft = await draft_review.reject(
        session, membership.organization_id, draft_id, membership.user_id, body.review_note
    )
    return DraftOut.from_model(draft)


@router.post("/drafts/{draft_id}/edit")
async def edit_draft(
    draft_id: uuid.UUID, body: EditDraft, request: Request, membership: Agent, session: SessionDep
) -> DraftOut:
    draft = await draft_review.edit(
        session,
        membership.organization_id,
        draft_id,
        membership.user_id,
        _plain(body.text, 4000),
        _settings(request),
    )
    return DraftOut.from_model(draft)


@router.post("/drafts/{draft_id}/escalate")
async def escalate_draft(
    draft_id: uuid.UUID, body: EscalateDraft, membership: Agent, session: SessionDep
) -> DraftOut:
    reason = _plain(body.reason, 200) if body.reason else None
    draft = await draft_review.escalate(
        session, membership.organization_id, draft_id, membership.user_id, reason
    )
    return DraftOut.from_model(draft)


@router.post("/drafts/{draft_id}/feedback", status_code=201)
async def create_feedback(
    draft_id: uuid.UUID, body: FeedbackIn, membership: Agent, session: SessionDep
) -> FeedbackOut:
    reason = _plain(body.reason, 500) if body.reason else None
    final_text = _plain(body.final_text, 4000) if body.final_text else None
    row = await submit_feedback(
        session,
        membership.organization_id,
        draft_id,
        action=FeedbackAction(body.action),
        final_text=final_text,
        reason=reason,
    )
    return FeedbackOut(
        id=row.id, draft_id=row.draft_id, action=row.action.value, created_at=row.created_at
    )


def _queue_item(draft: AIReplyDraft, customer: Customer, message: Message) -> QueueItem:
    base = DraftOut.from_model(draft)
    name = customer.display_name or customer.username or customer.instagram_user_id
    preview = (message.content or "").strip().replace("\n", " ")
    return QueueItem(**base.model_dump(), customer_name=name, message_preview=preview[:180])


def _plain(value: str, limit: int) -> str:
    cleaned = value.replace("\x00", "").replace("<<<", "").replace(">>>", "").strip()
    if len(cleaned) > limit:
        raise AppError("INVALID_SETTINGS", f"Use {limit} characters or fewer.", 400)
    return cleaned


def _terms(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values:
        term = " ".join(item.replace("\x00", "").split())
        if not term:
            continue
        if len(term) > 40:
            raise AppError("INVALID_SETTINGS", "Each term must be 40 characters or fewer.", 400)
        key = term.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(term)
    if len(cleaned) > 40:
        raise AppError("INVALID_SETTINGS", "Use 40 terms or fewer.", 400)
    return cleaned
