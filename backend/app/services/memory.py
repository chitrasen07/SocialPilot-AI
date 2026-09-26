"""Persistent customer memory: storage and vector retrieval only. Embeddings are supplied by
the caller (Phase 5); nothing here calls a model.

Every function takes organization_id explicitly and filters on it, so memory can never be read
or modified across tenants even if a caller passes a foreign customer or memory ID.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import EMBEDDING_DIMENSIONS, Customer, CustomerMemory, MemoryType

MAX_SEARCH_RESULTS = 50
MAX_LIST_RESULTS = 200


def _check_embedding(embedding: list[float] | None) -> None:
    if embedding is not None and len(embedding) != EMBEDDING_DIMENSIONS:
        raise AppError(
            "INVALID_EMBEDDING",
            f"Embeddings must have {EMBEDDING_DIMENSIONS} dimensions.",
            422,
        )


async def _require_customer(
    session: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> None:
    found = await session.scalar(
        select(Customer.id).where(
            Customer.id == customer_id, Customer.organization_id == organization_id
        )
    )
    if found is None:
        raise AppError("CUSTOMER_NOT_FOUND", "Customer not found.", 404)


async def _get_memory(
    session: AsyncSession,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    memory_id: uuid.UUID,
) -> CustomerMemory:
    memory = await session.scalar(
        select(CustomerMemory).where(
            CustomerMemory.id == memory_id,
            CustomerMemory.customer_id == customer_id,
            CustomerMemory.organization_id == organization_id,
        )
    )
    if memory is None:
        raise AppError("MEMORY_NOT_FOUND", "Memory not found.", 404)
    return memory


async def create_memory(
    session: AsyncSession,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    *,
    memory_type: MemoryType,
    content: str,
    importance: float = 1.0,
    embedding: list[float] | None = None,
    metadata: dict[str, Any] | None = None,
) -> CustomerMemory:
    _check_embedding(embedding)
    await _require_customer(session, organization_id, customer_id)
    memory = CustomerMemory(
        organization_id=organization_id,
        customer_id=customer_id,
        memory_type=memory_type,
        content=content,
        importance=importance,
        embedding=embedding,
        meta=metadata,
    )
    session.add(memory)
    await session.commit()
    return memory


async def update_memory(
    session: AsyncSession,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    memory_id: uuid.UUID,
    *,
    content: str | None = None,
    importance: float | None = None,
    embedding: list[float] | None = None,
    metadata: dict[str, Any] | None = None,
) -> CustomerMemory:
    """Updates only the fields that are passed (None means unchanged)."""
    _check_embedding(embedding)
    memory = await _get_memory(session, organization_id, customer_id, memory_id)
    if content is not None:
        memory.content = content
    if importance is not None:
        memory.importance = importance
    if embedding is not None:
        memory.embedding = embedding
    if metadata is not None:
        memory.meta = metadata
    await session.commit()
    return memory


async def delete_memory(
    session: AsyncSession,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    memory_id: uuid.UUID,
) -> None:
    memory = await _get_memory(session, organization_id, customer_id, memory_id)
    await session.delete(memory)
    await session.commit()


async def list_customer_memories(
    session: AsyncSession,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    limit: int = MAX_LIST_RESULTS,
) -> list[CustomerMemory]:
    await _require_customer(session, organization_id, customer_id)
    result = await session.scalars(
        select(CustomerMemory)
        .where(
            CustomerMemory.organization_id == organization_id,
            CustomerMemory.customer_id == customer_id,
        )
        .order_by(CustomerMemory.created_at.desc(), CustomerMemory.id.desc())
        .limit(min(limit, MAX_LIST_RESULTS))
    )
    return list(result)


async def search_customer_memory(
    session: AsyncSession,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    query_embedding: list[float],
    limit: int = 5,
) -> list[tuple[CustomerMemory, float]]:
    """Nearest memories by cosine distance (0 = identical), closest first.

    Exact search over one customer's memories: per-customer sets are small, and an approximate
    index would make results non-deterministic without a measurable benefit here.
    Memories without an embedding are skipped.
    """
    _check_embedding(query_embedding)
    distance = CustomerMemory.embedding.cosine_distance(query_embedding).label("distance")
    rows = await session.execute(
        select(CustomerMemory, distance)
        .where(
            CustomerMemory.organization_id == organization_id,
            CustomerMemory.customer_id == customer_id,
            CustomerMemory.embedding.is_not(None),
        )
        .order_by(distance, CustomerMemory.importance.desc(), CustomerMemory.id)
        .limit(max(1, min(limit, MAX_SEARCH_RESULTS)))
    )
    return [(memory, float(score)) for memory, score in rows]
