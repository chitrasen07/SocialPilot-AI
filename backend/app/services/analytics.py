"""Daily conversation and AI metrics, computed from stored messages and drafts."""

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AIReplyDraft,
    Conversation,
    DraftStatus,
    Message,
    MessageAIAnalysis,
    SenderType,
)
from app.models.channel import ChannelAnalytics
from app.models.intelligence import (
    AIFeedback,
    ConversationAnalytics,
    CustomerSegment,
    FeedbackAction,
)


async def refresh(session: AsyncSession, organization_id: uuid.UUID) -> list[ConversationAnalytics]:
    await session.execute(
        delete(ConversationAnalytics).where(
            ConversationAnalytics.organization_id == organization_id
        )
    )
    message_rows = (
        await session.execute(
            select(
                func.date(Message.sent_at).label("day"),
                func.count().label("messages"),
                func.count(func.distinct(Message.conversation_id)).label("conversations"),
            )
            .where(
                Message.organization_id == organization_id,
                Message.sender_type == SenderType.CUSTOMER,
            )
            .group_by(func.date(Message.sent_at))
        )
    ).all()
    draft_rows = (
        await session.execute(
            select(
                func.date(AIReplyDraft.created_at).label("day"),
                func.count().label("generated"),
                func.count().filter(AIReplyDraft.status == DraftStatus.APPROVED).label("approved"),
                func.count().filter(AIReplyDraft.status == DraftStatus.REJECTED).label("rejected"),
                func.count().filter(AIReplyDraft.escalation_required.is_(True)).label("escalated"),
            )
            .where(AIReplyDraft.organization_id == organization_id)
            .group_by(func.date(AIReplyDraft.created_at))
        )
    ).all()
    edit_rows = (
        await session.execute(
            select(
                func.date(AIFeedback.created_at).label("day"),
                func.count(func.distinct(AIFeedback.draft_id)),
            )
            .where(
                AIFeedback.organization_id == organization_id,
                AIFeedback.action == FeedbackAction.EDITED,
            )
            .group_by(func.date(AIFeedback.created_at))
        )
    ).all()
    by_day: dict = {}
    for row in message_rows:
        by_day.setdefault(row.day, {})["messages"] = int(row.messages)
        by_day[row.day]["conversations"] = int(row.conversations)
    for row in draft_rows:
        bucket = by_day.setdefault(row.day, {})
        bucket["generated"] = int(row.generated)
        bucket["approved"] = int(row.approved)
        bucket["rejected"] = int(row.rejected)
        bucket["escalated"] = int(row.escalated)
    for day, edited in edit_rows:
        by_day.setdefault(day, {})["edited"] = int(edited)
    stored: list[ConversationAnalytics] = []
    for day, bucket in sorted(by_day.items(), key=lambda item: item[0]):
        row = ConversationAnalytics(
            organization_id=organization_id,
            day=day,
            total_messages=bucket.get("messages", 0),
            total_conversations=bucket.get("conversations", 0),
            ai_generated=bucket.get("generated", 0),
            approved=bucket.get("approved", 0),
            edited=bucket.get("edited", 0),
            rejected=bucket.get("rejected", 0),
            escalated=bucket.get("escalated", 0),
        )
        session.add(row)
        stored.append(row)
    await _refresh_channels(session, organization_id)
    await session.commit()
    return stored


async def overview(session: AsyncSession, organization_id: uuid.UUID) -> dict:
    rows = await refresh(session, organization_id)
    generated = sum(row.ai_generated for row in rows)
    approved = sum(row.approved for row in rows)
    return {
        "days": [_day(row) for row in rows],
        "totals": {
            "total_messages": sum(row.total_messages for row in rows),
            "total_conversations": await _conversation_count(session, organization_id),
            "ai_generated": generated,
            "approved": approved,
            "edited": sum(row.edited for row in rows),
            "rejected": sum(row.rejected for row in rows),
            "escalated": sum(row.escalated for row in rows),
            "approval_rate": round(approved / generated, 2) if generated else 0,
        },
        "average_response_seconds": await _response_seconds(session, organization_id),
        "sentiment": await _sentiment(session, organization_id),
        "top_questions": await _intents(session, organization_id),
        "products": await _products(session, organization_id),
        "problems": await _problems(session, organization_id),
    }


async def channel_metrics(session: AsyncSession, organization_id: uuid.UUID) -> dict:
    await refresh(session, organization_id)
    rows = list(
        await session.scalars(
            select(ChannelAnalytics)
            .where(ChannelAnalytics.organization_id == organization_id)
            .order_by(ChannelAnalytics.channel_type, ChannelAnalytics.day)
        )
    )
    grouped: dict[str, dict] = {}
    for row in rows:
        bucket = grouped.setdefault(
            row.channel_type.value,
            {
                "channel": row.channel_type.value,
                "total_messages": 0,
                "total_conversations": 0,
                "ai_generated": 0,
                "approved": 0,
            },
        )
        bucket["total_messages"] += row.total_messages
        bucket["total_conversations"] += row.total_conversations
        bucket["ai_generated"] += row.ai_generated
        bucket["approved"] += row.approved
    waits = await _response_by_channel(session, organization_id)
    items = []
    for item in grouped.values():
        generated = item["ai_generated"]
        approved = item["approved"]
        item["approval_rate"] = round(approved / generated, 2) if generated else 0
        item["average_response_seconds"] = waits.get(item["channel"])
        items.append(item)
    return {"channels": items}


async def _refresh_channels(session: AsyncSession, organization_id: uuid.UUID) -> None:
    await session.execute(
        delete(ChannelAnalytics).where(ChannelAnalytics.organization_id == organization_id)
    )
    messages = (
        await session.execute(
            select(
                func.date(Message.sent_at).label("day"),
                Message.channel_type,
                func.count().label("messages"),
                func.count(func.distinct(Message.conversation_id)).label("conversations"),
            )
            .where(
                Message.organization_id == organization_id,
                Message.sender_type == SenderType.CUSTOMER,
            )
            .group_by(func.date(Message.sent_at), Message.channel_type)
        )
    ).all()
    drafts = (
        await session.execute(
            select(
                func.date(AIReplyDraft.created_at).label("day"),
                Message.channel_type,
                func.count().label("generated"),
                func.count().filter(AIReplyDraft.status == DraftStatus.APPROVED).label("approved"),
            )
            .join(Message, Message.id == AIReplyDraft.message_id)
            .where(AIReplyDraft.organization_id == organization_id)
            .group_by(func.date(AIReplyDraft.created_at), Message.channel_type)
        )
    ).all()
    buckets: dict[tuple, dict] = {}
    for row in messages:
        buckets[(row.day, row.channel_type)] = {
            "messages": int(row.messages),
            "conversations": int(row.conversations),
        }
    for row in drafts:
        bucket = buckets.setdefault((row.day, row.channel_type), {})
        bucket["generated"] = int(row.generated)
        bucket["approved"] = int(row.approved)
    for (day, channel), bucket in buckets.items():
        session.add(
            ChannelAnalytics(
                organization_id=organization_id,
                day=day,
                channel_type=channel,
                total_messages=bucket.get("messages", 0),
                total_conversations=bucket.get("conversations", 0),
                ai_generated=bucket.get("generated", 0),
                approved=bucket.get("approved", 0),
            )
        )


async def _response_by_channel(
    session: AsyncSession, organization_id: uuid.UUID
) -> dict[str, float]:
    rows = list(
        await session.scalars(
            select(Message)
            .where(Message.organization_id == organization_id)
            .order_by(Message.conversation_id, Message.sent_at)
            .limit(500)
        )
    )
    waits: dict[str, list[float]] = {}
    last: dict[uuid.UUID, tuple[datetime, str]] = {}
    for message in rows:
        channel = message.channel_type.value
        if message.sender_type == SenderType.CUSTOMER:
            last[message.conversation_id] = (message.sent_at, channel)
        elif message.sender_type == SenderType.BUSINESS and message.conversation_id in last:
            sent_at, origin = last.pop(message.conversation_id)
            delta = (message.sent_at - sent_at).total_seconds()
            if delta >= 0:
                waits.setdefault(origin, []).append(delta)
    return {
        channel: round(sum(values) / len(values), 1) for channel, values in waits.items() if values
    }


async def customer_metrics(session: AsyncSession, organization_id: uuid.UUID) -> dict:
    segments = (
        await session.execute(
            select(CustomerSegment.segment, func.count())
            .where(CustomerSegment.organization_id == organization_id)
            .group_by(CustomerSegment.segment)
        )
    ).all()
    return {"segments": [{"segment": name.value, "customers": count} for name, count in segments]}


async def ai_performance(session: AsyncSession, organization_id: uuid.UUID) -> dict:
    body = await overview(session, organization_id)
    return {"totals": body["totals"], "days": body["days"]}


def _day(row: ConversationAnalytics) -> dict:
    return {
        "day": row.day.isoformat(),
        "total_messages": row.total_messages,
        "total_conversations": row.total_conversations,
        "ai_generated": row.ai_generated,
        "approved": row.approved,
        "edited": row.edited,
        "rejected": row.rejected,
        "escalated": row.escalated,
    }


async def _conversation_count(session: AsyncSession, organization_id: uuid.UUID) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.organization_id == organization_id)
    )
    return int(count or 0)


async def _response_seconds(session: AsyncSession, organization_id: uuid.UUID) -> float | None:
    rows = list(
        await session.scalars(
            select(Message)
            .where(Message.organization_id == organization_id)
            .order_by(Message.conversation_id, Message.sent_at)
            .limit(500)
        )
    )
    waits: list[float] = []
    last_customer: dict[uuid.UUID, datetime] = {}
    for message in rows:
        if message.sender_type == SenderType.CUSTOMER:
            last_customer[message.conversation_id] = message.sent_at
        elif (
            message.sender_type == SenderType.BUSINESS and message.conversation_id in last_customer
        ):
            delta = (message.sent_at - last_customer.pop(message.conversation_id)).total_seconds()
            if delta >= 0:
                waits.append(delta)
    if not waits:
        return None
    return round(sum(waits) / len(waits), 1)


async def _sentiment(session: AsyncSession, organization_id: uuid.UUID) -> list[dict]:
    since = datetime.now(UTC) - timedelta(days=14)
    rows = (
        await session.execute(
            select(MessageAIAnalysis.sentiment, func.count())
            .where(
                MessageAIAnalysis.organization_id == organization_id,
                MessageAIAnalysis.created_at >= since,
            )
            .group_by(MessageAIAnalysis.sentiment)
        )
    ).all()
    return [{"sentiment": name, "count": count} for name, count in rows]


async def _intents(session: AsyncSession, organization_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            select(MessageAIAnalysis.intent, func.count())
            .where(MessageAIAnalysis.organization_id == organization_id)
            .group_by(MessageAIAnalysis.intent)
            .order_by(func.count().desc())
            .limit(8)
        )
    ).all()
    return [{"intent": name, "count": count} for name, count in rows]


async def _products(session: AsyncSession, organization_id: uuid.UUID) -> list[dict]:
    messages = list(
        await session.scalars(
            select(Message.content)
            .where(
                Message.organization_id == organization_id,
                Message.sender_type == SenderType.CUSTOMER,
            )
            .limit(300)
        )
    )
    counts: Counter[str] = Counter()
    for content in messages:
        text = (content or "").lower()
        for name in ("shoes", "sneakers", "sandals", "boots", "shirt", "dress", "bag"):
            if name in text:
                counts[name] += 1
    return [{"product": name, "count": count} for name, count in counts.most_common(8)]


async def _problems(session: AsyncSession, organization_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            select(MessageAIAnalysis.intent, func.count())
            .where(
                MessageAIAnalysis.organization_id == organization_id,
                MessageAIAnalysis.intent.in_(
                    ("refund_request", "complaint", "support_request", "shipping_question")
                ),
            )
            .group_by(MessageAIAnalysis.intent)
        )
    ).all()
    return [{"intent": name, "count": count} for name, count in rows]
