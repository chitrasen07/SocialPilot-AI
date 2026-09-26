import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models import ConversationStatus, Message, MessageType, SenderType
from app.schemas.customers import CustomerOut
from app.services.conversations import ConversationRow


class MessagePreviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    content: str | None
    sender_type: SenderType
    message_type: MessageType
    sent_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    instagram_account_id: uuid.UUID
    status: ConversationStatus
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime
    customer: CustomerOut


class ConversationListItem(ConversationOut):
    last_message: MessagePreviewOut | None

    @classmethod
    def from_row(cls, row: ConversationRow) -> "ConversationListItem":
        base = ConversationOut.model_validate(row.conversation)
        preview = MessagePreviewOut.model_validate(row.last_message) if row.last_message else None
        return cls(**base.model_dump(), last_message=preview)


class ConversationList(BaseModel):
    items: list[ConversationListItem]
    has_more: bool


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_type: SenderType
    message_type: MessageType
    content: str | None
    metadata: dict[str, Any] | None
    sent_at: datetime

    @classmethod
    def from_model(cls, message: Message) -> "MessageOut":
        return cls(
            id=message.id,
            conversation_id=message.conversation_id,
            sender_type=message.sender_type,
            message_type=message.message_type,
            content=message.content,
            metadata=message.meta,
            sent_at=message.sent_at,
        )


class MessagePage(BaseModel):
    """Oldest-first; pass next_cursor as `before` to load older messages."""

    items: list[MessageOut]
    next_cursor: str | None


class ConversationDetail(ConversationOut):
    messages: MessagePage


class ConversationUpdate(BaseModel):
    status: ConversationStatus
