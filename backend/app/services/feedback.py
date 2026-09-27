"""Stores how people changed AI drafts. This is review feedback, not model training."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIReplyDraft
from app.models.intelligence import AIFeedback, FeedbackAction

logger = logging.getLogger("socialpilot.intelligence")


def record_feedback(
    session: AsyncSession,
    draft: AIReplyDraft,
    action: FeedbackAction,
    *,
    final_text: str | None,
    reason: str | None = None,
) -> AIFeedback:
    row = AIFeedback(
        organization_id=draft.organization_id,
        draft_id=draft.id,
        original_text=draft.reply_text,
        final_text=final_text,
        action=action,
        reason=reason,
    )
    session.add(row)
    return row


async def submit_feedback(
    session: AsyncSession,
    organization_id: uuid.UUID,
    draft_id: uuid.UUID,
    *,
    action: FeedbackAction,
    final_text: str | None,
    reason: str | None,
) -> AIFeedback:
    from app.services.draft_review import get_draft

    draft = await get_draft(session, organization_id, draft_id)
    row = record_feedback(session, draft, action, final_text=final_text, reason=reason)
    await remember_learning(session, draft.organization_id, action)
    await session.commit()
    return row


async def remember_learning(
    session: AsyncSession, organization_id: uuid.UUID, action: FeedbackAction
) -> None:
    from app.services.intelligence_engine import note_learning

    try:
        async with session.begin_nested():
            await note_learning(session, organization_id, action)
    except Exception:
        logger.exception("learning_metric_failed")
