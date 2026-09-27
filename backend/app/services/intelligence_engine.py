"""Stores engagement rows from messages, memories, and knowledge already in the database.

Nothing here sends a message or calls a second model.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.conversation import understand
from app.intelligence.journey import next_journey
from app.intelligence.optimizer import OptimizedReply
from app.intelligence.recommendations import recommend
from app.intelligence.scoring import score_messages
from app.models import (
    AIFeedback,
    AIReplyDraft,
    Conversation,
    Customer,
    CustomerMemory,
    DocumentStatus,
    FeedbackAction,
    KnowledgeChunk,
    KnowledgeDocument,
    Message,
    OrganizationAISettings,
    SenderType,
)
from app.models.engagement import (
    AIResponseScore,
    ConversationIntelligence,
    ConversationStage,
    CustomerJourney,
    CustomerRecommendation,
    CustomerScore,
    JourneyStage,
    LearningMetric,
    Urgency,
)

logger = logging.getLogger("socialpilot.intelligence")

_PRODUCT_STAGES = {"product_interest", "pricing", "negotiation", "purchase_intent"}
_QUALIFIED = {JourneyStage.QUALIFIED, JourneyStage.CUSTOMER, JourneyStage.REPEAT_CUSTOMER}
_INACTIVE_AFTER = timedelta(days=14)
_FUNNEL = (
    "visitor",
    "lead",
    "interested",
    "qualified",
    "customer",
    "repeat_customer",
    "inactive",
)


async def observe_customer_message(
    session: AsyncSession,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    text: str | None,
) -> None:
    """Updates intelligence for one stored customer message. Failures do not block ingest."""
    del message_id
    try:
        async with session.begin_nested():
            await _observe(session, organization_id, customer_id, conversation_id, text)
    except Exception:
        logger.exception("engagement_observe_failed")
        return
    try:
        await session.commit()
    except Exception:
        logger.exception("engagement_observe_failed")


async def store_response_score(
    session: AsyncSession, draft: AIReplyDraft, optimized: OptimizedReply
) -> None:
    try:
        async with session.begin_nested():
            session.add(
                AIResponseScore(
                    organization_id=draft.organization_id,
                    draft_id=draft.id,
                    clarity_score=optimized.clarity_score,
                    helpfulness_score=optimized.helpfulness_score,
                    brand_score=optimized.brand_score,
                    conversion_score=optimized.conversion_score,
                )
            )
        await session.commit()
    except Exception:
        logger.exception("response_score_failed")


async def note_learning(
    session: AsyncSession, organization_id: uuid.UUID, action: FeedbackAction
) -> None:
    settings = await session.scalar(
        select(OrganizationAISettings).where(
            OrganizationAISettings.organization_id == organization_id
        )
    )
    personality = settings.personality.value if settings is not None else "friendly"
    length = settings.response_length.value if settings is not None else "medium"
    language = settings.language_mode.value if settings is not None else "auto"
    emoji = settings.emoji_policy.value if settings is not None else "minimal"
    row = await session.scalar(
        select(LearningMetric).where(
            LearningMetric.organization_id == organization_id,
            LearningMetric.personality == personality,
            LearningMetric.response_length == length,
            LearningMetric.language_mode == language,
            LearningMetric.emoji_policy == emoji,
        )
    )
    if row is None:
        row = LearningMetric(
            organization_id=organization_id,
            personality=personality,
            response_length=length,
            language_mode=language,
            emoji_policy=emoji,
            accepted=0,
            edited=0,
            rejected=0,
        )
        session.add(row)
    if action == FeedbackAction.APPROVED:
        row.accepted += 1
    elif action == FeedbackAction.EDITED:
        row.edited += 1
    else:
        row.rejected += 1


async def customer_insights(
    session: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> dict:
    customer = await session.get(Customer, customer_id)
    if customer is None or customer.organization_id != organization_id:
        from app.core.errors import AppError

        raise AppError("CUSTOMER_NOT_FOUND", "Customer not found.", 404)
    await _mark_inactive(session, organization_id, customer_id)
    journey = await _latest_journey(session, organization_id, customer_id)
    score = await session.scalar(
        select(CustomerScore).where(
            CustomerScore.organization_id == organization_id,
            CustomerScore.customer_id == customer_id,
        )
    )
    intelligence = await session.scalar(
        select(ConversationIntelligence)
        .join(Conversation, Conversation.id == ConversationIntelligence.conversation_id)
        .where(
            ConversationIntelligence.organization_id == organization_id,
            Conversation.organization_id == organization_id,
            Conversation.customer_id == customer_id,
        )
        .order_by(ConversationIntelligence.updated_at.desc())
        .limit(1)
    )
    recommendations = list(
        await session.scalars(
            select(CustomerRecommendation)
            .where(
                CustomerRecommendation.organization_id == organization_id,
                CustomerRecommendation.customer_id == customer_id,
            )
            .order_by(CustomerRecommendation.confidence.desc())
            .limit(5)
        )
    )
    action = intelligence.recommended_action if intelligence is not None else ""
    return {
        "lifecycle_stage": journey.current_stage.value if journey is not None else "visitor",
        "lead_score": score.lead_score if score is not None else 0,
        "score_reason": score.score_reason if score is not None else "",
        "buying_probability": intelligence.buying_probability if intelligence is not None else 0,
        "churn_risk": intelligence.churn_probability if intelligence is not None else 0,
        "recommended_actions": [action] if action else [],
        "recommendations": [
            {
                "product_name": item.product_name,
                "reason": item.reason,
                "confidence": item.confidence,
            }
            for item in recommendations
        ],
    }


async def dashboard(session: AsyncSession, organization_id: uuid.UUID) -> dict:
    await _mark_inactive(session, organization_id, None)
    journeys = await _latest_journeys(session, organization_id)
    counts = {stage: 0 for stage in _FUNNEL}
    qualified = 0
    for row in journeys:
        name = row.current_stage.value
        counts[name] = counts.get(name, 0) + 1
        if row.current_stage in _QUALIFIED:
            qualified += 1
    average = await session.scalar(
        select(func.avg(CustomerScore.lead_score)).where(
            CustomerScore.organization_id == organization_id
        )
    )
    intents = (
        await session.execute(
            select(ConversationIntelligence.intent, func.count())
            .where(ConversationIntelligence.organization_id == organization_id)
            .group_by(ConversationIntelligence.intent)
            .order_by(func.count().desc())
            .limit(8)
        )
    ).all()
    products = (
        await session.execute(
            select(CustomerRecommendation.product_name, func.count())
            .where(CustomerRecommendation.organization_id == organization_id)
            .group_by(CustomerRecommendation.product_name)
            .order_by(func.count().desc())
            .limit(8)
        )
    ).all()
    risky = list(
        await session.scalars(
            select(ConversationIntelligence)
            .where(
                ConversationIntelligence.organization_id == organization_id,
                ConversationIntelligence.churn_probability >= 0.55,
            )
            .order_by(ConversationIntelligence.churn_probability.desc())
            .limit(8)
        )
    )
    learning = await _learning(session, organization_id)
    conversations = await session.scalar(
        select(func.count())
        .select_from(ConversationIntelligence)
        .where(ConversationIntelligence.organization_id == organization_id)
    )
    return {
        "total_conversations": int(conversations or 0),
        "qualified_leads": qualified,
        "funnel": [{"stage": stage, "customers": counts[stage]} for stage in _FUNNEL],
        "average_lead_score": round(float(average), 1) if average is not None else None,
        "top_intents": [{"intent": name, "count": count} for name, count in intents],
        "top_products": [{"product": name, "count": count} for name, count in products],
        "churn_risk_customers": await _churn_customers(session, organization_id, risky),
        "ai_improvement_score": learning["ai_improvement_score"],
        "learning": learning,
    }


async def _observe(
    session: AsyncSession,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    conversation_id: uuid.UUID,
    text: str | None,
) -> None:
    texts = await _customer_texts(session, organization_id, customer_id)
    if text and (not texts or texts[-1] != text):
        texts.append(text)
    current = await session.scalar(
        select(ConversationIntelligence).where(
            ConversationIntelligence.organization_id == organization_id,
            ConversationIntelligence.conversation_id == conversation_id,
        )
    )
    previous = current.stage.value if current is not None else None
    reading = understand(text or (texts[-1] if texts else ""), previous)
    if current is None:
        current = ConversationIntelligence(
            organization_id=organization_id,
            conversation_id=conversation_id,
            stage=ConversationStage(reading["stage"]),
            intent=reading["intent"],
            urgency=Urgency(reading["urgency"]),
            buying_probability=reading["buying_probability"],
            churn_probability=reading["churn_probability"],
            customer_goal=reading["customer_goal"],
            recommended_action=reading["recommended_action"],
        )
        session.add(current)
    else:
        current.stage = ConversationStage(reading["stage"])
        current.intent = reading["intent"]
        current.urgency = Urgency(reading["urgency"])
        current.buying_probability = reading["buying_probability"]
        current.churn_probability = reading["churn_probability"]
        current.customer_goal = reading["customer_goal"]
        current.recommended_action = reading["recommended_action"]
    await _journey(session, organization_id, customer_id, texts)
    await _score(session, organization_id, customer_id, texts, inactive=False)
    if reading["stage"] in _PRODUCT_STAGES:
        await _recommend(session, organization_id, customer_id, texts)


async def _customer_texts(
    session: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> list[str]:
    rows = list(
        await session.scalars(
            select(Message.content)
            .where(
                Message.organization_id == organization_id,
                Message.customer_id == customer_id,
                Message.sender_type == SenderType.CUSTOMER,
            )
            .order_by(Message.sent_at.desc())
            .limit(30)
        )
    )
    rows.reverse()
    return [row or "" for row in rows]


async def _journey(
    session: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID, texts: list[str]
) -> None:
    latest = await _latest_journey(session, organization_id, customer_id)
    current = latest.current_stage.value if latest is not None else None
    change = next_journey(current, texts)
    if change is None:
        return
    stage, reason, confidence = change
    session.add(
        CustomerJourney(
            organization_id=organization_id,
            customer_id=customer_id,
            current_stage=JourneyStage(stage),
            previous_stage=JourneyStage(current) if current else None,
            changed_reason=reason,
            confidence=confidence,
        )
    )


async def _score(
    session: AsyncSession,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    texts: list[str],
    *,
    inactive: bool,
) -> None:
    memories = list(
        await session.scalars(
            select(CustomerMemory.content).where(
                CustomerMemory.organization_id == organization_id,
                CustomerMemory.customer_id == customer_id,
            )
        )
    )
    returning = any("bought" in item.lower() or "ordered" in item.lower() for item in memories)
    value, reason = score_messages(texts, inactive=inactive, returning=returning)
    row = await session.scalar(
        select(CustomerScore).where(
            CustomerScore.organization_id == organization_id,
            CustomerScore.customer_id == customer_id,
        )
    )
    if row is None:
        session.add(
            CustomerScore(
                organization_id=organization_id,
                customer_id=customer_id,
                lead_score=value,
                score_reason=reason,
            )
        )
        return
    row.lead_score = value
    row.score_reason = reason


async def _recommend(
    session: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID, texts: list[str]
) -> None:
    documents = list(
        await session.scalars(
            select(KnowledgeChunk.content)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(
                KnowledgeChunk.organization_id == organization_id,
                KnowledgeDocument.organization_id == organization_id,
                KnowledgeDocument.status == DocumentStatus.READY,
            )
            .limit(40)
        )
    )
    memories = list(
        await session.scalars(
            select(CustomerMemory.content).where(
                CustomerMemory.organization_id == organization_id,
                CustomerMemory.customer_id == customer_id,
            )
        )
    )
    chosen = recommend("\n".join(texts), memories, documents)
    await session.execute(
        delete(CustomerRecommendation).where(
            CustomerRecommendation.organization_id == organization_id,
            CustomerRecommendation.customer_id == customer_id,
        )
    )
    for item in chosen:
        session.add(
            CustomerRecommendation(
                organization_id=organization_id,
                customer_id=customer_id,
                product_name=item["product_name"],
                reason=item["reason"],
                confidence=item["confidence"],
            )
        )


async def _latest_journey(
    session: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> CustomerJourney | None:
    return await session.scalar(
        select(CustomerJourney)
        .where(
            CustomerJourney.organization_id == organization_id,
            CustomerJourney.customer_id == customer_id,
        )
        .order_by(CustomerJourney.created_at.desc())
        .limit(1)
    )


async def _latest_journeys(
    session: AsyncSession, organization_id: uuid.UUID
) -> list[CustomerJourney]:
    return list(
        await session.scalars(
            select(CustomerJourney)
            .where(CustomerJourney.organization_id == organization_id)
            .distinct(CustomerJourney.customer_id)
            .order_by(CustomerJourney.customer_id, CustomerJourney.created_at.desc())
        )
    )


async def _mark_inactive(
    session: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID | None
) -> None:
    cutoff = datetime.now(UTC) - _INACTIVE_AFTER
    query = select(Message.customer_id, func.max(Message.sent_at)).where(
        Message.organization_id == organization_id,
        Message.sender_type == SenderType.CUSTOMER,
    )
    if customer_id is not None:
        query = query.where(Message.customer_id == customer_id)
    rows = (await session.execute(query.group_by(Message.customer_id).limit(200))).all()
    changed = False
    for person_id, last_sent in rows:
        if last_sent is None or last_sent >= cutoff:
            continue
        latest = await _latest_journey(session, organization_id, person_id)
        if latest is None or latest.current_stage == JourneyStage.INACTIVE:
            continue
        session.add(
            CustomerJourney(
                organization_id=organization_id,
                customer_id=person_id,
                current_stage=JourneyStage.INACTIVE,
                previous_stage=latest.current_stage,
                changed_reason="no recent customer messages",
                confidence=0.6,
            )
        )
        texts = await _customer_texts(session, organization_id, person_id)
        await _score(session, organization_id, person_id, texts, inactive=True)
        changed = True
    if changed:
        await session.commit()


async def _churn_customers(
    session: AsyncSession, organization_id: uuid.UUID, rows: list[ConversationIntelligence]
) -> list[dict]:
    items: list[dict] = []
    seen: set[uuid.UUID] = set()
    for row in rows:
        customer_id = await session.scalar(
            select(Message.customer_id).where(
                Message.organization_id == organization_id,
                Message.conversation_id == row.conversation_id,
            )
        )
        if customer_id is None or customer_id in seen:
            continue
        seen.add(customer_id)
        customer = await session.get(Customer, customer_id)
        if customer is None or customer.organization_id != organization_id:
            continue
        items.append(
            {
                "customer_id": str(customer.id),
                "display_name": customer.display_name or customer.username,
                "churn_probability": row.churn_probability,
            }
        )
    return items


async def _learning(session: AsyncSession, organization_id: uuid.UUID) -> dict:
    counts = dict(
        (
            await session.execute(
                select(AIFeedback.action, func.count())
                .where(AIFeedback.organization_id == organization_id)
                .group_by(AIFeedback.action)
            )
        ).all()
    )
    accepted = int(counts.get(FeedbackAction.APPROVED, 0))
    edited = int(counts.get(FeedbackAction.EDITED, 0))
    rejected = int(counts.get(FeedbackAction.REJECTED, 0))
    total = accepted + edited + rejected
    rows = list(
        await session.scalars(
            select(LearningMetric).where(LearningMetric.organization_id == organization_id)
        )
    )
    best = _best_style(rows)
    return {
        "accepted": accepted,
        "edited": edited,
        "rejected": rejected,
        "best_personality": best.get("personality"),
        "best_response_length": best.get("response_length"),
        "best_language_style": best.get("language_mode"),
        "best_emoji_usage": best.get("emoji_policy"),
        "ai_improvement_score": round(accepted / total, 2) if total else 0,
    }


def _best_style(rows: list[LearningMetric]) -> dict:
    ranked = []
    for row in rows:
        total = row.accepted + row.edited + row.rejected
        if total <= 0:
            continue
        ranked.append((row.accepted / total, row.accepted, row))
    if not ranked:
        return {}
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    winner = ranked[0][2]
    return {
        "personality": winner.personality,
        "response_length": winner.response_length,
        "language_mode": winner.language_mode,
        "emoji_policy": winner.emoji_policy,
    }
