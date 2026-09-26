import uuid
from dataclasses import dataclass

from pydantic import BaseModel, Field


class KnowledgeSource(BaseModel):
    document_id: uuid.UUID
    document_name: str
    chunk_id: uuid.UUID
    page: int | None = None
    chunk_index: int
    relevance: float = Field(ge=0, le=1)


@dataclass(frozen=True)
class KnowledgeHit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    content: str
    page: int | None
    chunk_index: int
    distance: float

    @property
    def relevance(self) -> float:
        return round(max(0.0, min(1.0, 1.0 - self.distance)), 4)

    def source(self) -> KnowledgeSource:
        return KnowledgeSource(
            document_id=self.document_id,
            document_name=self.document_name,
            chunk_id=self.chunk_id,
            page=self.page,
            chunk_index=self.chunk_index,
            relevance=self.relevance,
        )


def format_knowledge(hits: list[KnowledgeHit]) -> str:
    if not hits:
        return "(none)"
    blocks: list[str] = []
    for hit in hits:
        label = f"Source: {hit.document_name}"
        if hit.page is not None:
            label += f", page {hit.page}"
        blocks.append(f"{label}\n{hit.content[:800]}")
    return "\n\n".join(blocks)
