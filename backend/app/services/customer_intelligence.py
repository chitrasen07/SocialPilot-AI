"""Deterministic customer profile, memory suggestions, and segments.

Nothing here calls an AI provider. Sensitive personal details are not stored.
Suggestions stay pending until a person approves them.
"""

import re
import uuid
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import MessageAnalysis
from app.core.errors import AppError
from app.db.base import utcnow
from app.models import CustomerMemory, MemoryType, Message, MessageAIAnalysis, SenderType
from app.models.intelligence import (
    CustomerIntelligence,
    CustomerSegment,
    MemorySuggestion,
    SegmentName,
    SuggestionCategory,
    SuggestionStatus,
)
from app.services.memory import create_memory

_SENSITIVE = re.compile(
    r"\b(birthday|born|age|years old|religion|pregnant|diagnosis|illness|address|"
    r"phone|email|aadhaar|passport|bank account)\b",
    re.I,
)
_PREFER = re.compile(
    r"\b(?:i always prefer|i prefer|always prefer|i like|i love)\s+([a-z0-9][^.]{1,60})",
    re.I,
)
_LANGUAGE = re.compile(
    r"\b(?:reply|talk|speak|write|message)\s+in\s+(english|hindi|hinglish|telugu)\b",
    re.I,
)
_SHOPPING = re.compile(
    r"\b(?:i usually buy|i always buy|my size is|i wear size)\s+([a-z0-9][^.]{1,40})",
    re.I,
)
_PRODUCTISH = re.compile(
    r"\b(shoes|sneakers|sandals|boots|shirt|dress|bag|footwear|blue|black|red|white|size|color|colour)\b",
    re.I,
)
_PRODUCTS = (
    "shoes",
    "sneakers",
    "sandals",
    "boots",
    "shirt",
    "dress",
    "bag",
    "footwear",
)
_ISSUE_INTENTS = {
    "shipping_question": "Asked about delivery",
    "refund_request": "Asked about a refund",
    "complaint": "Raised a support complaint",
    "support_request": "Asked for support",
}


@dataclass(frozen=True)
class CustomerInsights:
    profile: CustomerIntelligence | None
    segments: list[CustomerSegment]
    pending_suggestions: int


def generate_customer_summary(
    *,
    preferences: list[str],
    interests: list[str],
    products: list[str],
    buying_intent: str,
    communication_style: str,
    language_preference: str,
    previous_issues: list[str],
    sentiment_trend: str,
) -> str:
    lines = [
        f"Language: {language_preference}",
        f"Style: {communication_style}",
        f"Buying intent: {buying_intent}",
        f"Sentiment: {sentiment_trend}",
    ]
    if preferences:
        lines.append("Preferences: " + "; ".join(preferences[:5]))
    if interests:
        lines.append("Interests: " + ", ".join(interests[:5]))
    if products:
        lines.append("Products: " + ", ".join(products[:5]))
    if previous_issues:
        lines.append("Previous questions: " + "; ".join(previous_issues[:5]))
    return "\n".join(lines)


async def update_customer_profile(
    session: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> CustomerIntelligence:
    await _require_customer(session, organization_id, customer_id)
    messages = list(
        await session.scalars(
            select(Message)
            .where(
                Message.organization_id == organization_id,
                Message.customer_id == customer_id,
                Message.sender_type == SenderType.CUSTOMER,
            )
            .order_by(Message.sent_at.desc())
            .limit(50)
        )
    )
    analyses = list(
        await session.scalars(
            select(MessageAIAnalysis)
            .where(
                MessageAIAnalysis.organization_id == organization_id,
                MessageAIAnalysis.message_id.in_([item.id for item in messages] or [uuid.uuid4()]),
            )
            .limit(50)
        )
    )
    memories = list(
        await session.scalars(
            select(CustomerMemory).where(
                CustomerMemory.organization_id == organization_id,
                CustomerMemory.customer_id == customer_id,
            )
        )
    )
    built = _build(messages, analyses, memories)
    row = await session.scalar(
        select(CustomerIntelligence).where(
            CustomerIntelligence.organization_id == organization_id,
            CustomerIntelligence.customer_id == customer_id,
        )
    )
    if row is None:
        row = CustomerIntelligence(organization_id=organization_id, customer_id=customer_id)
        session.add(row)
    row.summary = built["summary"]
    row.preferences = built["preferences"]
    row.interests = built["interests"]
    row.frequent_products = built["products"]
    row.buying_intent = built["buying_intent"]
    row.communication_style = built["style"]
    row.language_preference = built["language"]
    row.previous_issues = built["issues"]
    row.sentiment_trend = built["sentiment"]
    previous = {
        item.value if hasattr(item, "value") else str(item)
        for item in await session.scalars(
            select(CustomerSegment.segment).where(
                CustomerSegment.organization_id == organization_id,
                CustomerSegment.customer_id == customer_id,
            )
        )
    }
    current = await _replace_segments(session, organization_id, customer_id, messages, analyses)
    await session.commit()
    added = sorted(current - previous)
    if added:
        from app.services.automation import on_segments_changed

        await on_segments_changed(session, organization_id, customer_id, added)
    return row


async def get_customer_insights(
    session: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> CustomerInsights:
    await _require_customer(session, organization_id, customer_id)
    profile = await session.scalar(
        select(CustomerIntelligence).where(
            CustomerIntelligence.organization_id == organization_id,
            CustomerIntelligence.customer_id == customer_id,
        )
    )
    segments = list(
        await session.scalars(
            select(CustomerSegment)
            .where(
                CustomerSegment.organization_id == organization_id,
                CustomerSegment.customer_id == customer_id,
            )
            .order_by(CustomerSegment.segment)
        )
    )
    pending = list(
        await session.scalars(
            select(MemorySuggestion.id).where(
                MemorySuggestion.organization_id == organization_id,
                MemorySuggestion.customer_id == customer_id,
                MemorySuggestion.status == SuggestionStatus.PENDING,
            )
        )
    )
    return CustomerInsights(profile, segments, len(pending))


async def suggest_from_message(
    session: AsyncSession,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    message: Message,
    analysis: MessageAnalysis | None,
) -> MemorySuggestion | None:
    text = message.content or ""
    if _SENSITIVE.search(text):
        return None
    content, category = _suggestion(text, analysis)
    if content is None or category is None:
        return None
    existing = await session.scalar(
        select(MemorySuggestion.id).where(
            MemorySuggestion.organization_id == organization_id,
            MemorySuggestion.customer_id == customer_id,
            MemorySuggestion.content == content,
            MemorySuggestion.status != SuggestionStatus.REJECTED,
        )
    )
    if existing is not None:
        return None
    remembered = await session.scalar(
        select(CustomerMemory.id).where(
            CustomerMemory.organization_id == organization_id,
            CustomerMemory.customer_id == customer_id,
            CustomerMemory.content == content,
        )
    )
    if remembered is not None:
        return None
    row = MemorySuggestion(
        organization_id=organization_id,
        customer_id=customer_id,
        source_message_id=message.id,
        content=content,
        category=category,
        status=SuggestionStatus.PENDING,
    )
    session.add(row)
    await session.commit()
    return row


async def list_suggestions(
    session: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> list[MemorySuggestion]:
    await _require_customer(session, organization_id, customer_id)
    return list(
        await session.scalars(
            select(MemorySuggestion)
            .where(
                MemorySuggestion.organization_id == organization_id,
                MemorySuggestion.customer_id == customer_id,
            )
            .order_by(MemorySuggestion.created_at.desc())
        )
    )


async def review_suggestion(
    session: AsyncSession,
    organization_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    *,
    approve: bool,
) -> MemorySuggestion:
    row = await session.scalar(
        select(MemorySuggestion).where(
            MemorySuggestion.id == suggestion_id,
            MemorySuggestion.organization_id == organization_id,
        )
    )
    if row is None:
        raise AppError("SUGGESTION_NOT_FOUND", "Suggestion not found.", 404)
    if row.status != SuggestionStatus.PENDING:
        raise AppError("SUGGESTION_STATE", "This suggestion was already reviewed.", 409)
    row.reviewed_by = reviewer_id
    row.reviewed_at = utcnow()
    if approve:
        memory_type = {
            SuggestionCategory.PREFERENCE: MemoryType.PREFERENCE,
            SuggestionCategory.COMMUNICATION: MemoryType.PREFERENCE,
            SuggestionCategory.SHOPPING: MemoryType.INTEREST,
        }[row.category]
        row.status = SuggestionStatus.APPROVED
        await create_memory(
            session,
            organization_id,
            row.customer_id,
            memory_type=memory_type,
            content=row.content,
            metadata={"source": "suggestion", "suggestion_id": str(row.id)},
        )
    else:
        row.status = SuggestionStatus.REJECTED
        await session.commit()
    return row


async def refresh_for_prompt(
    session: AsyncSession,
    organization_id: uuid.UUID,
    message: Message,
    analysis: MessageAnalysis | None,
) -> str:
    """Updates the profile used as untrusted reply context. Does not send anything."""
    await suggest_from_message(session, organization_id, message.customer_id, message, analysis)
    profile = await update_customer_profile(session, organization_id, message.customer_id)
    return profile.summary


def _suggestion(
    text: str, _analysis: MessageAnalysis | None
) -> tuple[str | None, SuggestionCategory | None]:
    if _SENSITIVE.search(text):
        return None, None
    match = _PREFER.search(text)
    if match:
        phrase = " ".join(match.group(1).split()).rstrip(".")
        if phrase and not _SENSITIVE.search(phrase) and _PRODUCTISH.search(phrase):
            return f"Customer prefers {phrase}.", SuggestionCategory.PREFERENCE
    language = _LANGUAGE.search(text)
    if language:
        return (
            f"Customer prefers replies in {language.group(1).lower()}.",
            SuggestionCategory.COMMUNICATION,
        )
    shopping = _SHOPPING.search(text)
    if shopping:
        phrase = " ".join(shopping.group(1).split()).rstrip(".")
        if phrase and not _SENSITIVE.search(phrase):
            return f"Customer usually shops for {phrase}.", SuggestionCategory.SHOPPING
    return None, None


def _build(
    messages: list[Message], analyses: list[MessageAIAnalysis], memories: list[CustomerMemory]
) -> dict:
    preferences = [item.content for item in memories if item.memory_type == MemoryType.PREFERENCE][
        :8
    ]
    interests = [item.content for item in memories if item.memory_type == MemoryType.INTEREST][:8]
    products = _products(messages)
    languages = [item.language for item in analyses if item.language != "unknown"]
    language = Counter(languages).most_common(1)[0][0] if languages else "unknown"
    intents = [item.purchase_intent for item in analyses]
    buying = (
        "high"
        if "high" in intents
        else "medium"
        if "medium" in intents
        else "low"
        if intents
        else "unknown"
    )
    sentiments = [item.sentiment for item in analyses if item.sentiment != "unknown"]
    sentiment = Counter(sentiments).most_common(1)[0][0] if sentiments else "unknown"
    issues = []
    for item in analyses:
        label = _ISSUE_INTENTS.get(item.intent)
        if label and label not in issues:
            issues.append(label)
    style = "casual" if language == "hinglish" else "direct" if language == "english" else language
    summary = generate_customer_summary(
        preferences=preferences,
        interests=interests,
        products=products,
        buying_intent=buying,
        communication_style=style,
        language_preference=language,
        previous_issues=issues,
        sentiment_trend=sentiment,
    )
    return {
        "summary": summary,
        "preferences": preferences,
        "interests": interests,
        "products": products,
        "buying_intent": buying,
        "style": style,
        "language": language,
        "issues": issues,
        "sentiment": sentiment,
    }


def _products(messages: list[Message]) -> list[str]:
    counts: Counter[str] = Counter()
    for message in messages:
        text = (message.content or "").lower()
        for name in _PRODUCTS:
            if name in text:
                counts[name] += 1
    return [name for name, _count in counts.most_common(5)]


async def _replace_segments(
    session: AsyncSession,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    messages: list[Message],
    analyses: list[MessageAIAnalysis],
) -> set[str]:
    await session.execute(
        delete(CustomerSegment).where(
            CustomerSegment.organization_id == organization_id,
            CustomerSegment.customer_id == customer_id,
        )
    )
    conversations = {item.conversation_id for item in messages}
    chosen: list[tuple[SegmentName, float]] = []
    if len(conversations) <= 1:
        chosen.append((SegmentName.NEW, 0.8))
    else:
        chosen.append((SegmentName.RETURNING, 0.85))
    intents = Counter(item.intent for item in analyses)
    if any(item.purchase_intent == "high" for item in analyses):
        chosen.append((SegmentName.HIGH_INTENT, 0.8))
    if intents["pricing_question"]:
        chosen.append(
            (SegmentName.PRICE_SENSITIVE, min(0.9, 0.55 + 0.1 * intents["pricing_question"]))
        )
    if intents["product_question"]:
        chosen.append(
            (SegmentName.PRODUCT_EXPLORER, min(0.9, 0.55 + 0.1 * intents["product_question"]))
        )
    support = intents["refund_request"] + intents["complaint"] + intents["support_request"]
    if support:
        chosen.append((SegmentName.SUPPORT, min(0.9, 0.6 + 0.1 * support)))
    names: set[str] = set()
    for name, confidence in chosen:
        names.add(name.value)
        session.add(
            CustomerSegment(
                organization_id=organization_id,
                customer_id=customer_id,
                segment=name,
                confidence=round(confidence, 2),
            )
        )
    return names


async def _require_customer(
    session: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> None:
    from app.models import Customer

    found = await session.scalar(
        select(Customer.id).where(
            Customer.id == customer_id, Customer.organization_id == organization_id
        )
    )
    if found is None:
        raise AppError("CUSTOMER_NOT_FOUND", "Customer not found.", 404)
