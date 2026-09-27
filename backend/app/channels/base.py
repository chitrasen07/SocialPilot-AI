"""Shared channel contract. send_message must not deliver to a customer."""

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.models.channel import ChannelType


class ChannelSendBlocked(Exception):
    """Raised instead of delivering a message. Drafts stay inside SocialPilot."""


@dataclass(frozen=True)
class InboundMessage:
    external_id: str
    sender_id: str
    recipient_id: str
    text: str | None
    occurred_at: datetime
    sender_is_business: bool = False
    profile_name: str | None = None


@dataclass(frozen=True)
class ChannelCustomerProfile:
    external_id: str
    display_name: str | None
    username: str | None = None


class ChannelProvider(Protocol):
    channel: ChannelType

    def verify_webhook(self, body: bytes, signature: str | None, secret: str | None) -> bool: ...

    def receive_message(self, payload: dict) -> list[InboundMessage]: ...

    async def send_message(self, recipient: str, text: str) -> None: ...

    def get_customer_profile(self, sender_id: str, payload: dict) -> ChannelCustomerProfile: ...


def verify_hmac(body: bytes, signature: str | None, secret: str | None) -> bool:
    if not signature or not secret or not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.removeprefix("sha256="))


async def refuse_send(recipient: str, text: str) -> None:
    del recipient, text
    raise ChannelSendBlocked("Customer messages are not sent automatically.")
