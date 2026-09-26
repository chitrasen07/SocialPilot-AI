import uuid

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.knowledge.ingestion import _delete_chunks
from app.knowledge.storage import KnowledgeStorage
from app.models import DocumentStatus, KnowledgeDocument
from app.workers.queue import enqueue_knowledge


async def create_document(
    session: AsyncSession,
    redis: Redis,
    storage: KnowledgeStorage,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    name: str,
    original_filename: str,
    file_type: str,
    mime_type: str,
    data: bytes,
) -> KnowledgeDocument:
    document_id = uuid.uuid4()
    path = storage.save(organization_id, document_id, data)
    document = KnowledgeDocument(
        id=document_id,
        organization_id=organization_id,
        name=name[:255],
        original_filename=original_filename,
        file_type=file_type,
        mime_type=mime_type,
        file_size=len(data),
        storage_path=path,
        source_type="upload",
        status=DocumentStatus.PENDING,
        chunk_count=0,
        attempts=0,
        created_by=user_id,
    )
    session.add(document)
    try:
        await session.commit()
    except Exception:
        storage.delete(path)
        raise
    await enqueue_knowledge(redis, document.id)
    return document


async def list_documents(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
) -> tuple[list[KnowledgeDocument], bool]:
    rows = list(
        await session.scalars(
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.organization_id == organization_id,
                KnowledgeDocument.status != DocumentStatus.DELETED,
            )
            .order_by(KnowledgeDocument.created_at.desc(), KnowledgeDocument.id.desc())
            .offset(offset)
            .limit(limit + 1)
        )
    )
    return rows[:limit], len(rows) > limit


async def get_document(
    session: AsyncSession, organization_id: uuid.UUID, document_id: uuid.UUID
) -> KnowledgeDocument:
    document = await session.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.organization_id == organization_id,
            KnowledgeDocument.status != DocumentStatus.DELETED,
        )
    )
    if document is None:
        raise AppError("DOCUMENT_NOT_FOUND", "Document not found.", 404)
    return document


async def delete_document(
    session: AsyncSession,
    storage: KnowledgeStorage,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
) -> None:
    document = await get_document(session, organization_id, document_id)
    if document.storage_path:
        storage.delete(document.storage_path)
    await _delete_chunks(session, document)
    document.status = DocumentStatus.DELETED
    document.storage_path = None
    document.chunk_count = 0
    await session.commit()


async def reprocess_document(
    session: AsyncSession,
    redis: Redis,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
) -> KnowledgeDocument:
    document = await get_document(session, organization_id, document_id)
    if document.status == DocumentStatus.PROCESSING:
        raise AppError("DOCUMENT_BUSY", "This document is already being processed.", 409)
    document.status = DocumentStatus.PENDING
    document.error_message = None
    document.processed_at = None
    await session.commit()
    await enqueue_knowledge(redis, document.id)
    return document
