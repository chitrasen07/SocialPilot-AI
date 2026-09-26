import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import ConnectionStatus


class InstagramAccountOut(BaseModel):
    """Connection metadata only; tokens are never serialized."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    instagram_account_id: str
    username: str
    account_type: str | None
    connection_status: ConnectionStatus
    scopes: list[str]
    token_expires_at: datetime | None
    connected_at: datetime | None
    last_webhook_at: datetime | None


class InstagramAccountList(BaseModel):
    items: list[InstagramAccountOut]


class ConnectResponse(BaseModel):
    authorization_url: str
