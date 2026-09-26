"""Ingest one document. Callers enqueue the id; this function is safe to run twice."""

import logging
import uuid
from datetime import timedelta

from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import EmbeddingProvider
from app.core.config import Settings
from app.core.errors import AppError
from app.db.base import utcnow
from app.knowledge.chunking import chunk_sections
from app.knowledge.errors import PermanentIngestionError, TransientIngestionError
from app.knowledge.loaders import extract_document
from app.knowledge.storage import KnowledgeStorage
from app.models import DocumentStatus, KnowledgeChunk, KnowledgeDocument
from app.models.customer import EMBEDDING_DIMENSIONS
from app.workers.queue import enqueue_knowledge

logger = logging.getLogger("socialpilot.knowledge")

_FAILED = "Knowledge processing failed."
_NOT_CONFIGURED = "AI is not configured yet."
_TOO_LONG = "This document is too long to process."
_STUCK = "Processing did not finish."
CLAIM_TIMEOUT = timedelta(minutes=10)
PENDING_GRACE = timedelta(minutes=2)


async def process_document(
    session: AsyncSession,
    document_id: uuid.UUID,
    embeddings: EmbeddingProvider | None,
    storage: KnowledgeStorage,
    settings: Settings,
    redis: Redis | None = None,
) -> None:
    document = await _claim(session, document_id)
    if document is None:
        return
    organization_id = document.organization_id
    logger.info(
        "knowledge_ingestion_started",
        extra={
            "fields": {"organization_id": str(organization_id), "document_id": str(document.id)}
        },
    )
    try:
        if embeddings is None:
            raise PermanentIngestionError(_NOT_CONFIGURED)
        if not document.storage_path:
            raise PermanentIngestionError("This document could not be read.")
        data = storage.read(document.storage_path)
        sections = extract_document(document.file_type, data, document.original_filename)
        try:
            drafts = chunk_sections(
                sections,
                size=settings.knowledge_chunk_size,
                overlap=settings.knowledge_chunk_overlap,
                max_chunks=settings.knowledge_max_chunks,
            )
        except ValueError as exc:
            raise PermanentIngestionError(_TOO_LONG) from exc
        if not drafts:
            raise PermanentIngestionError("This file has no extractable text.")
        vectors = await _embed(embeddings, [draft.content for draft in drafts], settings)
        await _replace_chunks(session, document, drafts, vectors)
    except PermanentIngestionError as exc:
        await _fail(session, document, exc.safe_message)
    except (TransientIngestionError, AppError) as exc:
        message = exc.safe_message if isinstance(exc, TransientIngestionError) else _FAILED
        await _retry_or_fail(session, document, settings, redis, message)
    except Exception as exc:
        logger.warning(
            "knowledge_ingestion_failed",
            extra={
                "fields": {
                    "organization_id": str(organization_id),
                    "document_id": str(document_id),
                    "error": type(exc).__name__,
                }
            },
        )
        await _retry_or_fail(session, document, settings, redis, _FAILED)
        return
    else:
        logger.info(
            "knowledge_ingestion_completed",
            extra={
                "fields": {
                    "organization_id": str(organization_id),
                    "document_id": str(document.id),
                    "chunk_count": document.chunk_count,
                }
            },
        )


async def requeue_stuck_documents(session: AsyncSession, redis: Redis, settings: Settings) -> int:
    """Wake jobs the queue lost, and give up on claims that outlived the worker."""
    now = utcnow()
    rows = list(
        await session.scalars(
            select(KnowledgeDocument).where(
                KnowledgeDocument.status.in_((DocumentStatus.PENDING, DocumentStatus.PROCESSING))
            )
        )
    )
    count = 0
    for document in rows:
        if document.status == DocumentStatus.PENDING and document.updated_at > now - PENDING_GRACE:
            continue
        if (
            document.status == DocumentStatus.PROCESSING
            and document.updated_at > now - CLAIM_TIMEOUT
        ):
            continue
        if document.status == DocumentStatus.PROCESSING:
            document.attempts += 1
            if document.attempts >= settings.knowledge_max_attempts:
                document.status = DocumentStatus.FAILED
                document.error_message = _STUCK
                await _delete_chunks(session, document)
                continue
            document.status = DocumentStatus.PENDING
        document.updated_at = now
        await enqueue_knowledge(redis, document.id)
        count += 1
    await session.commit()
    return count


async def _claim(session: AsyncSession, document_id: uuid.UUID) -> KnowledgeDocument | None:
    document = await session.scalar(
        select(KnowledgeDocument)
        .where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.status == DocumentStatus.PENDING,
        )
        .with_for_update(skip_locked=True)
    )
    if document is None:
        return None
    document.status = DocumentStatus.PROCESSING
    document.error_message = None
    await session.commit()
    return document


async def _embed(
    embeddings: EmbeddingProvider, texts: list[str], settings: Settings
) -> list[list[float]]:
    batch_size = max(1, settings.knowledge_embedding_batch_size)
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        try:
            vectors.extend(await embeddings.embed_many(batch))
        except AppError as exc:
            raise TransientIngestionError(_FAILED) from exc
    if len(vectors) != len(texts) or any(len(vector) != EMBEDDING_DIMENSIONS for vector in vectors):
        raise TransientIngestionError(_FAILED)
    return vectors


async def _replace_chunks(session, document: KnowledgeDocument, drafts, vectors) -> None:
    await _delete_chunks(session, document)
    for draft, vector in zip(drafts, vectors, strict=True):
        session.add(
            KnowledgeChunk(
                organization_id=document.organization_id,
                document_id=document.id,
                chunk_index=draft.index,
                content=draft.content,
                embedding=vector,
                meta=draft.metadata,
                token_count=draft.token_count,
            )
        )
    document.status = DocumentStatus.READY
    document.chunk_count = len(drafts)
    document.processed_at = utcnow()
    document.error_message = None
    await session.commit()


async def _delete_chunks(session: AsyncSession, document: KnowledgeDocument) -> None:
    await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))


async def _fail(session: AsyncSession, document: KnowledgeDocument, message: str) -> None:
    await _delete_chunks(session, document)
    document.status = DocumentStatus.FAILED
    document.chunk_count = 0
    document.error_message = message[:500]
    document.processed_at = utcnow()
    await session.commit()
    logger.info(
        "knowledge_ingestion_failed",
        extra={
            "fields": {
                "organization_id": str(document.organization_id),
                "document_id": str(document.id),
                "status": "failed",
            }
        },
    )


async def _retry_or_fail(
    session: AsyncSession,
    document: KnowledgeDocument,
    settings: Settings,
    redis: Redis | None,
    message: str,
) -> None:
    document.attempts += 1
    if document.attempts >= settings.knowledge_max_attempts:
        await _fail(session, document, message)
        return
    await _delete_chunks(session, document)
    document.status = DocumentStatus.PENDING
    document.chunk_count = 0
    document.error_message = message[:500]
    await session.commit()
    if redis is not None:
        await enqueue_knowledge(redis, document.id)
