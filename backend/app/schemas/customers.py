import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models import ConversationStatus, CustomerMemory, MemoryType


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    instagram_account_id: uuid.UUID | None = None
    instagram_user_id: str | None = None
    channel_type: str = "instagram"
    username: str | None
    display_name: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CustomerListItem(CustomerOut):
    last_message_at: datetime | None
    conversation_count: int


class CustomerList(BaseModel):
    items: list[CustomerListItem]
    has_more: bool


class CustomerConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ConversationStatus
    last_message_at: datetime | None
    created_at: datetime


class CustomerDetail(CustomerOut):
    conversations: list[CustomerConversationOut]


class MemoryOut(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    memory_type: MemoryType
    content: str
    importance: float
    metadata: dict[str, Any] | None
    # The vector itself is internal; clients only need to know whether one exists.
    has_embedding: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, memory: CustomerMemory) -> "MemoryOut":
        return cls(
            id=memory.id,
            customer_id=memory.customer_id,
            memory_type=memory.memory_type,
            content=memory.content,
            importance=memory.importance,
            metadata=memory.meta,
            has_embedding=memory.embedding is not None,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
        )


class MemoryList(BaseModel):
    items: list[MemoryOut]


class MemoryCreate(BaseModel):
    memory_type: MemoryType
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    importance: float = Field(default=1.0, ge=0, le=1)
    metadata: dict[str, Any] | None = None
