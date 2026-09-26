import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.citations import KnowledgeHit
from app.models import EMBEDDING_DIMENSIONS, DocumentStatus, KnowledgeChunk, KnowledgeDocument

MAX_TOP_K = 20


async def search_knowledge(
    session: AsyncSession,
    organization_id: uuid.UUID,
    query_embedding: list[float],
    *,
    top_k: int,
    max_distance: float,
) -> list[KnowledgeHit]:
    """Nearest ready chunks for one organization, by cosine distance (0 = identical).

    Exact search, same metric as customer memory. Chunks from other organizations, and
    documents that are not ready, are excluded before the limit is applied.
    """
    if len(query_embedding) != EMBEDDING_DIMENSIONS:
        return []
    limit = max(1, min(top_k, MAX_TOP_K))
    distance = KnowledgeChunk.embedding.cosine_distance(query_embedding)
    rows = await session.execute(
        select(KnowledgeChunk, KnowledgeDocument, distance.label("distance"))
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(
            KnowledgeChunk.organization_id == organization_id,
            KnowledgeDocument.organization_id == organization_id,
            KnowledgeDocument.status == DocumentStatus.READY,
            KnowledgeChunk.embedding.is_not(None),
            distance <= max_distance,
        )
        .order_by(distance, KnowledgeChunk.id)
        .limit(limit)
    )
    hits: list[KnowledgeHit] = []
    for chunk, document, score in rows:
        page = chunk.meta.get("page") if isinstance(chunk.meta, dict) else None
        hits.append(
            KnowledgeHit(
                chunk_id=chunk.id,
                document_id=document.id,
                document_name=document.name,
                content=chunk.content,
                page=page if isinstance(page, int) else None,
                chunk_index=chunk.chunk_index,
                distance=float(score),
            )
        )
    return hits
