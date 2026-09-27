"""Human review of AI drafts. Approving a draft does not send it."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import ai_guardrail_blocked, draft_not_approvable, draft_not_found, draft_state
from app.ai.guardrails import evaluate_reply
from app.core.config import Settings
from app.db.base import utcnow
from app.models import (
    AIReplyDraft,
    Customer,
    DraftStatus,
    GuardrailStatus,
    KnowledgeChunk,
    Message,
    RiskLevel,
)
from app.models.intelligence import FeedbackAction
from app.services import ai_data
from app.services.feedback import record_feedback, remember_learning

_APPROVE_FROM = {DraftStatus.GENERATED, DraftStatus.REVIEW_REQUIRED, DraftStatus.EDITED}
_REJECT_FROM = {
    DraftStatus.GENERATED,
    DraftStatus.REVIEW_REQUIRED,
    DraftStatus.EDITED,
    DraftStatus.APPROVED,
}
_EDIT_FROM = {
    DraftStatus.GENERATED,
    DraftStatus.REVIEW_REQUIRED,
    DraftStatus.EDITED,
    DraftStatus.REJECTED,
}
_ESCALATE_FROM = {
    DraftStatus.GENERATED,
    DraftStatus.REVIEW_REQUIRED,
    DraftStatus.EDITED,
    DraftStatus.APPROVED,
}


async def get_draft(
    session: AsyncSession, organization_id: uuid.UUID, draft_id: uuid.UUID
) -> AIReplyDraft:
    draft = await session.scalar(
        select(AIReplyDraft).where(
            AIReplyDraft.id == draft_id,
            AIReplyDraft.organization_id == organization_id,
        )
    )
    if draft is None:
        raise draft_not_found()
    return draft


def visible_text(draft: AIReplyDraft) -> str:
    return (draft.edited_text or draft.reply_text or "").strip()


async def approve(
    session: AsyncSession,
    organization_id: uuid.UUID,
    draft_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    settings: Settings,
) -> AIReplyDraft:
    draft = await get_draft(session, organization_id, draft_id)
    if draft.status not in _APPROVE_FROM or not visible_text(draft):
        raise draft_state()
    report = await _evaluate(session, draft, settings)
    if report.blocked or report.flags:
        raise draft_not_approvable()
    draft.status = DraftStatus.APPROVED
    draft.guardrail_status = GuardrailStatus.PASSED
    draft.guardrail_results = report.as_dict()
    _reviewed(draft, reviewer_id)
    record_feedback(session, draft, FeedbackAction.APPROVED, final_text=visible_text(draft))
    await remember_learning(session, draft.organization_id, FeedbackAction.APPROVED)
    await session.commit()
    return draft


async def reject(
    session: AsyncSession,
    organization_id: uuid.UUID,
    draft_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    note: str | None,
) -> AIReplyDraft:
    draft = await get_draft(session, organization_id, draft_id)
    if draft.status not in _REJECT_FROM:
        raise draft_state()
    draft.status = DraftStatus.REJECTED
    draft.review_note = note
    _reviewed(draft, reviewer_id)
    record_feedback(session, draft, FeedbackAction.REJECTED, final_text=None, reason=note)
    await remember_learning(session, draft.organization_id, FeedbackAction.REJECTED)
    await session.commit()
    return draft


async def edit(
    session: AsyncSession,
    organization_id: uuid.UUID,
    draft_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    text: str,
    settings: Settings,
) -> AIReplyDraft:
    draft = await get_draft(session, organization_id, draft_id)
    if draft.status not in _EDIT_FROM:
        raise draft_state()
    report = await _evaluate(session, draft, settings, text=text)
    if report.blocked:
        raise ai_guardrail_blocked()
    draft.edited_text = text
    draft.guardrail_results = report.as_dict()
    if report.flags:
        draft.status = DraftStatus.REVIEW_REQUIRED
        draft.guardrail_status = GuardrailStatus.BLOCKED
    else:
        draft.status = DraftStatus.EDITED
        draft.guardrail_status = GuardrailStatus.PASSED
    _reviewed(draft, reviewer_id)
    record_feedback(session, draft, FeedbackAction.EDITED, final_text=text)
    await remember_learning(session, draft.organization_id, FeedbackAction.EDITED)
    await session.commit()
    return draft


async def escalate(
    session: AsyncSession,
    organization_id: uuid.UUID,
    draft_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    reason: str | None,
) -> AIReplyDraft:
    draft = await get_draft(session, organization_id, draft_id)
    if draft.status not in _ESCALATE_FROM:
        raise draft_state()
    draft.status = DraftStatus.REVIEW_REQUIRED
    draft.escalation_required = True
    draft.escalation_reason = reason or draft.escalation_reason or "Escalated by a teammate"
    _reviewed(draft, reviewer_id)
    await session.commit()
    return draft


async def list_queue(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    review_filter: str,
    limit: int,
) -> tuple[list[tuple[AIReplyDraft, Customer, Message]], bool]:
    stmt = (
        select(AIReplyDraft, Customer, Message)
        .join(Customer, Customer.id == AIReplyDraft.customer_id)
        .join(Message, Message.id == AIReplyDraft.message_id)
        .where(
            AIReplyDraft.organization_id == organization_id,
            Customer.organization_id == organization_id,
            Message.organization_id == organization_id,
        )
    )
    if review_filter == "review_required":
        stmt = stmt.where(AIReplyDraft.status == DraftStatus.REVIEW_REQUIRED)
    elif review_filter == "escalated":
        stmt = stmt.where(AIReplyDraft.escalation_required.is_(True))
    elif review_filter in {"low", "medium", "high"}:
        stmt = stmt.where(AIReplyDraft.risk_level == RiskLevel(review_filter))
    rows = (
        await session.execute(stmt.order_by(AIReplyDraft.created_at.desc()).limit(limit + 1))
    ).all()
    has_more = len(rows) > limit
    return list(rows[:limit]), has_more


async def _evaluate(
    session: AsyncSession, draft: AIReplyDraft, settings: Settings, text: str | None = None
):
    config = await ai_data.effective_settings(session, draft.organization_id, settings)
    message = await session.get(Message, draft.message_id)
    knowledge = await _knowledge(session, draft)
    return evaluate_reply(
        text if text is not None else visible_text(draft),
        max_chars=4000,
        forbidden_terms=config.forbidden_terms,
        knowledge_text=knowledge,
        emoji_policy=config.emoji_policy,
        personality=config.personality,
        customer_text=(message.content or "") if message else "",
    )


async def _knowledge(session: AsyncSession, draft: AIReplyDraft) -> str:
    raw_ids = [
        item.get("chunk_id")
        for item in (draft.sources or [])
        if isinstance(item, dict) and item.get("chunk_id")
    ]
    ids: list[uuid.UUID] = []
    for value in raw_ids:
        try:
            ids.append(uuid.UUID(str(value)))
        except ValueError:
            continue
    if not ids:
        return ""
    chunks = await session.scalars(
        select(KnowledgeChunk).where(
            KnowledgeChunk.id.in_(ids),
            KnowledgeChunk.organization_id == draft.organization_id,
        )
    )
    return "\n".join(chunk.content for chunk in chunks)


def _reviewed(draft: AIReplyDraft, reviewer_id: uuid.UUID) -> None:
    draft.reviewed_by = reviewer_id
    draft.reviewed_at = utcnow()
