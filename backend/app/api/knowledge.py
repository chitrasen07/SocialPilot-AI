import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from pydantic import BaseModel, Field

from app.ai.errors import ai_rate_limited
from app.api.deps import SessionDep, require_role
from app.core.config import Settings
from app.core.errors import AppError
from app.knowledge import documents as documents_service
from app.knowledge.retrieval import search_knowledge
from app.knowledge.security import validate_upload
from app.knowledge.storage import LocalKnowledgeStorage
from app.models import KnowledgeDocument, OrganizationMember, Role
from app.services import ai_data

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

Viewer = Annotated[OrganizationMember, Depends(require_role(Role.VIEWER))]
Admin = Annotated[OrganizationMember, Depends(require_role(Role.ADMIN))]


class DocumentOut(BaseModel):
    id: uuid.UUID
    name: str
    original_filename: str
    file_type: str
    file_size: int
    status: str
    chunk_count: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None

    @classmethod
    def from_model(cls, row: KnowledgeDocument) -> "DocumentOut":
        return cls(
            id=row.id,
            name=row.name,
            original_filename=row.original_filename,
            file_type=row.file_type,
            file_size=row.file_size,
            status=row.status.value,
            chunk_count=row.chunk_count,
            error_message=row.error_message,
            created_at=row.created_at,
            updated_at=row.updated_at,
            processed_at=row.processed_at,
        )


class DocumentList(BaseModel):
    items: list[DocumentOut]
    has_more: bool


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int | None = Field(default=None, ge=1, le=20)


class SearchHitOut(BaseModel):
    document_id: uuid.UUID
    document_name: str
    chunk_id: uuid.UUID
    page: int | None
    chunk_index: int
    content: str
    relevance: float
    distance: float


def _storage(request: Request) -> LocalKnowledgeStorage:
    settings: Settings = request.app.state.settings
    return LocalKnowledgeStorage(settings.knowledge_storage_path)


async def _limit(request: Request, membership: OrganizationMember) -> None:
    settings: Settings = request.app.state.settings
    limit = settings.ai_requests_per_minute
    if limit <= 0:
        return
    redis = request.app.state.redis
    for key in (f"ai:rl:user:{membership.user_id}", f"ai:rl:org:{membership.organization_id}"):
        try:
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 60)
        except Exception as exc:
            raise AppError("AI_UNAVAILABLE", "AI is temporarily unavailable.", 503) from exc
        if count > limit:
            raise ai_rate_limited()


@router.post("/documents", status_code=201)
async def upload_document(
    request: Request,
    membership: Admin,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    name: Annotated[str | None, Form()] = None,
) -> DocumentOut:
    settings: Settings = request.app.state.settings
    max_bytes = settings.knowledge_max_file_size_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    file_type, mime, filename = validate_upload(
        file.filename or "", file.content_type, data, max_bytes
    )
    display = (name or filename).strip() or filename
    document = await documents_service.create_document(
        session,
        request.app.state.redis,
        _storage(request),
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        name=display,
        original_filename=filename,
        file_type=file_type,
        mime_type=mime,
        data=data,
    )
    return DocumentOut.from_model(document)


@router.get("/documents")
async def list_documents(
    membership: Viewer,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> DocumentList:
    rows, has_more = await documents_service.list_documents(
        session, membership.organization_id, limit=limit, offset=offset
    )
    return DocumentList(items=[DocumentOut.from_model(row) for row in rows], has_more=has_more)


@router.get("/documents/{document_id}")
async def get_document(
    document_id: uuid.UUID, membership: Viewer, session: SessionDep
) -> DocumentOut:
    document = await documents_service.get_document(
        session, membership.organization_id, document_id
    )
    return DocumentOut.from_model(document)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID, request: Request, membership: Admin, session: SessionDep
) -> None:
    await documents_service.delete_document(
        session, _storage(request), membership.organization_id, document_id
    )


@router.post("/documents/{document_id}/reprocess")
async def reprocess_document(
    document_id: uuid.UUID, request: Request, membership: Admin, session: SessionDep
) -> DocumentOut:
    document = await documents_service.reprocess_document(
        session, request.app.state.redis, membership.organization_id, document_id
    )
    return DocumentOut.from_model(document)


@router.post("/search")
async def search(
    body: SearchRequest, request: Request, membership: Viewer, session: SessionDep
) -> dict[str, list[SearchHitOut]]:
    await _limit(request, membership)
    embeddings = request.app.state.ai_orchestrator._require_embeddings()
    settings: Settings = request.app.state.settings
    config = await ai_data.effective_settings(session, membership.organization_id, settings)
    vector = await embeddings.embed(body.query[:500])
    hits = await search_knowledge(
        session,
        membership.organization_id,
        vector,
        top_k=body.top_k or config.knowledge_top_k,
        max_distance=config.knowledge_max_distance,
    )
    return {
        "items": [
            SearchHitOut(
                document_id=hit.document_id,
                document_name=hit.document_name,
                chunk_id=hit.chunk_id,
                page=hit.page,
                chunk_index=hit.chunk_index,
                content=hit.content[:500],
                relevance=hit.relevance,
                distance=hit.distance,
            )
            for hit in hits
        ]
    }
