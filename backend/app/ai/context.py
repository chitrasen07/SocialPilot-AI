from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import EmbeddingProvider
from app.ai.schemas import MessageAnalysis
from app.models import Message, SenderType
from app.services.memory import search_customer_memory

_SNIP = 400


@dataclass(frozen=True)
class BuiltContext:
    history: list[str]
    memories: list[str]


async def build_context(
    session: AsyncSession,
    message: Message,
    analysis: MessageAnalysis,
    embeddings: EmbeddingProvider,
    *,
    max_messages: int,
    memory_top_k: int,
) -> BuiltContext:
    history = await _history(session, message, max_messages)
    memories: list[str] = []
    if message.content and memory_top_k > 0:
        vector = await embeddings.embed(message.content[:2000])
        found = await search_customer_memory(
            session,
            message.organization_id,
            message.customer_id,
            vector,
            limit=memory_top_k,
        )
        memories = [item.content[:_SNIP] for item, _score in found]
    _ = analysis
    return BuiltContext(history=history, memories=memories)


async def _history(session: AsyncSession, message: Message, limit: int) -> list[str]:
    rows = list(
        await session.scalars(
            select(Message)
            .where(
                Message.organization_id == message.organization_id,
                Message.conversation_id == message.conversation_id,
                Message.id != message.id,
            )
            .order_by(Message.sent_at.desc(), Message.id.desc())
            .limit(max(1, min(limit, 50)))
        )
    )
    rows.reverse()
    lines = []
    for row in rows:
        who = "business" if row.sender_type == SenderType.BUSINESS else row.sender_type.value
        body = (row.content or "")[:_SNIP]
        if body:
            lines.append(f"{who}: {body}")
    return lines
