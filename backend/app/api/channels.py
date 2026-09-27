"""Channel connections and inbound webhooks. Nothing here sends a customer message."""

import json
import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import SessionDep, require_role
from app.channels import PROVIDERS
from app.core.crypto import TokenCipher
from app.core.errors import AppError
from app.models import Message, OrganizationMember, Role
from app.models.channel import (
    ChannelProviderName,
    ChannelSettings,
    ChannelStatus,
    ChannelType,
    ConversationChannel,
)
from app.services.channel_normalization import ingest

router = APIRouter(prefix="/api/channels", tags=["channels"])

Viewer = Annotated[OrganizationMember, Depends(require_role(Role.VIEWER))]
Admin = Annotated[OrganizationMember, Depends(require_role(Role.ADMIN))]

_PROVIDERS = {
    ChannelType.INSTAGRAM: ChannelProviderName.META,
    ChannelType.WHATSAPP: ChannelProviderName.MOCK,
    ChannelType.MESSENGER: ChannelProviderName.MOCK,
    ChannelType.EMAIL: ChannelProviderName.EMAIL,
    ChannelType.WEBCHAT: ChannelProviderName.WIDGET,
}


class ConnectIn(BaseModel):
    channel_type: ChannelType
    display_name: str = Field(default="", max_length=120)


class ChannelPatch(BaseModel):
    status: ChannelStatus | None = None
    display_name: str | None = Field(default=None, max_length=120)


class ChannelOut(BaseModel):
    id: uuid.UUID
    channel_type: str
    status: str
    provider: str
    display_name: str


class ConnectOut(ChannelOut):
    setup_token: str


class WidgetMessage(BaseModel):
    visitor_id: str = Field(min_length=1, max_length=80)
    message_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=4000)


def _cipher(request: Request) -> TokenCipher:
    settings = request.app.state.settings
    return TokenCipher(settings.token_encryption_keys)


def _out(channel: ConversationChannel, settings: ChannelSettings) -> ChannelOut:
    return ChannelOut(
        id=channel.id,
        channel_type=channel.channel_type.value,
        status=settings.status.value,
        provider=settings.provider.value,
        display_name=settings.display_name,
    )


async def _pair(
    session, organization_id: uuid.UUID, channel_id: uuid.UUID
) -> tuple[ConversationChannel, ChannelSettings]:
    channel = await session.scalar(
        select(ConversationChannel).where(
            ConversationChannel.id == channel_id,
            ConversationChannel.organization_id == organization_id,
        )
    )
    settings = await session.scalar(
        select(ChannelSettings).where(
            ChannelSettings.channel_id == channel_id,
            ChannelSettings.organization_id == organization_id,
        )
    )
    if channel is None or settings is None:
        raise AppError("CHANNEL_NOT_FOUND", "Channel not found.", 404)
    return channel, settings


@router.get("")
async def list_channels(membership: Viewer, session: SessionDep) -> dict:
    return await _list(session, membership.organization_id)


@router.get("/settings")
async def channel_settings(membership: Viewer, session: SessionDep) -> dict:
    return await _list(session, membership.organization_id)


@router.post("/connect", status_code=201)
async def connect_channel(
    body: ConnectIn, request: Request, membership: Admin, session: SessionDep
) -> ConnectOut:
    if body.channel_type == ChannelType.INSTAGRAM:
        raise AppError(
            "USE_INSTAGRAM_CONNECT",
            "Connect Instagram from the Instagram integration.",
            409,
        )
    existing = await session.scalar(
        select(ConversationChannel).where(
            ConversationChannel.organization_id == membership.organization_id,
            ConversationChannel.channel_type == body.channel_type,
        )
    )
    if existing is not None:
        raise AppError("CHANNEL_EXISTS", "That channel is already connected.", 409)
    token = secrets.token_urlsafe(24)
    channel = ConversationChannel(
        organization_id=membership.organization_id, channel_type=body.channel_type
    )
    session.add(channel)
    await session.flush()
    settings = ChannelSettings(
        organization_id=membership.organization_id,
        channel_id=channel.id,
        provider=_PROVIDERS[body.channel_type],
        status=ChannelStatus.CONNECTED,
        display_name=body.display_name.strip(),
        webhook_secret=_cipher(request).encrypt(token),
    )
    session.add(settings)
    await session.commit()
    listed = _out(channel, settings)
    return ConnectOut(**listed.model_dump(), setup_token=token)


@router.patch("/{channel_id}")
async def update_channel(
    channel_id: uuid.UUID, body: ChannelPatch, membership: Admin, session: SessionDep
) -> ChannelOut:
    channel, settings = await _pair(session, membership.organization_id, channel_id)
    if body.status is not None:
        settings.status = body.status
    if body.display_name is not None:
        settings.display_name = body.display_name.strip()
    await session.commit()
    return _out(channel, settings)


@router.post("/webhook/{channel_id}")
async def receive_webhook(channel_id: uuid.UUID, request: Request, session: SessionDep) -> dict:
    body = await request.body()
    channel = await session.get(ConversationChannel, channel_id)
    if channel is None:
        raise AppError("CHANNEL_NOT_FOUND", "Channel not found.", 404)
    settings = await session.scalar(
        select(ChannelSettings).where(ChannelSettings.channel_id == channel.id)
    )
    if (
        settings is None
        or settings.status != ChannelStatus.CONNECTED
        or not settings.webhook_secret
    ):
        raise AppError("CHANNEL_NOT_READY", "This channel is not accepting messages.", 409)
    try:
        secret = _cipher(request).decrypt(settings.webhook_secret)
    except ValueError as exc:
        raise AppError("CHANNEL_NOT_READY", "This channel is not accepting messages.", 409) from exc
    provider = PROVIDERS[channel.channel_type]
    signature = request.headers.get("x-channel-signature")
    if not provider.verify_webhook(body, signature, secret):
        raise AppError("WEBHOOK_SIGNATURE_INVALID", "The webhook signature is invalid.", 401)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AppError("INVALID_WEBHOOK", "The webhook body could not be read.", 400) from exc
    if not isinstance(payload, dict):
        raise AppError("INVALID_WEBHOOK", "The webhook body could not be read.", 400)
    stored = 0
    for inbound in provider.receive_message(payload):
        message = await ingest(
            session,
            channel.organization_id,
            provider,
            inbound,
            prepare_draft=channel.channel_type in {ChannelType.EMAIL, ChannelType.WEBCHAT},
        )
        if message is not None:
            stored += 1
    return {"received": stored}


@router.post("/webchat/{channel_id}/messages", status_code=201)
async def webchat_message(
    channel_id: uuid.UUID, body: WidgetMessage, request: Request, session: SessionDep
) -> dict:
    channel, settings = await _public_channel(session, channel_id, request)
    provider = PROVIDERS[ChannelType.WEBCHAT]
    message = await ingest(
        session,
        channel.organization_id,
        provider,
        provider.receive_message(body.model_dump())[0],
        prepare_draft=True,
    )
    if message is None:
        raise AppError("MESSAGE_DUPLICATE", "That message was already received.", 409)
    return {"id": str(message.id), "handoff": False}


@router.get("/webchat/{channel_id}/messages")
async def webchat_history(
    channel_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    visitor_id: str,
) -> dict:
    channel, _settings = await _public_channel(session, channel_id, request)
    from app.models import Customer

    customer_id = await session.scalar(
        select(Customer.id).where(
            Customer.organization_id == channel.organization_id,
            Customer.channel_type == ChannelType.WEBCHAT,
            Customer.external_user_id == visitor_id,
        )
    )
    if customer_id is None:
        return {"items": [], "handoff": False}
    from app.models import Conversation

    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.organization_id == channel.organization_id,
            Conversation.customer_id == customer_id,
        )
    )
    if conversation is None:
        return {"items": [], "handoff": False}
    rows = list(
        await session.scalars(
            select(Message)
            .where(
                Message.organization_id == channel.organization_id,
                Message.conversation_id == conversation.id,
            )
            .order_by(Message.sent_at)
            .limit(50)
        )
    )
    return {
        "items": [
            {"id": str(row.id), "sender": row.sender_type.value, "text": row.content}
            for row in rows
        ],
        "handoff": conversation.status.value == "pending",
    }


async def _public_channel(session, channel_id: uuid.UUID, request: Request):
    channel = await session.get(ConversationChannel, channel_id)
    settings = await session.scalar(
        select(ChannelSettings).where(ChannelSettings.channel_id == channel_id)
    )
    if (
        channel is None
        or settings is None
        or channel.channel_type != ChannelType.WEBCHAT
        or settings.status != ChannelStatus.CONNECTED
        or not settings.webhook_secret
    ):
        raise AppError("CHANNEL_NOT_FOUND", "Channel not found.", 404)
    try:
        secret = _cipher(request).decrypt(settings.webhook_secret)
    except ValueError as exc:
        raise AppError("CHANNEL_NOT_FOUND", "Channel not found.", 404) from exc
    header = request.headers.get("x-widget-token") or ""
    if len(header) != len(secret) or not secrets.compare_digest(header, secret):
        raise AppError("WIDGET_TOKEN_INVALID", "The widget token is invalid.", 401)
    return channel, settings


async def _list(session, organization_id: uuid.UUID) -> dict:
    rows = (
        await session.execute(
            select(ConversationChannel, ChannelSettings)
            .join(ChannelSettings, ChannelSettings.channel_id == ConversationChannel.id)
            .where(ConversationChannel.organization_id == organization_id)
            .order_by(ConversationChannel.channel_type)
        )
    ).all()
    return {
        "items": [_out(channel, settings).model_dump(mode="json") for channel, settings in rows]
    }
