"""Website chat. The visitor sees their own messages. Drafts stay in the inbox."""

from datetime import UTC, datetime

from app.channels.base import (
    ChannelCustomerProfile,
    InboundMessage,
    refuse_send,
    verify_hmac,
)
from app.models.channel import ChannelType


class WebChatChannel:
    channel = ChannelType.WEBCHAT

    def verify_webhook(self, body: bytes, signature: str | None, secret: str | None) -> bool:
        return verify_hmac(body, signature, secret)

    def receive_message(self, payload: dict) -> list[InboundMessage]:
        visitor = payload.get("visitor_id")
        message_id = payload.get("message_id")
        if not isinstance(visitor, str) or not isinstance(message_id, str):
            return []
        text = payload.get("text") if isinstance(payload.get("text"), str) else None
        return [
            InboundMessage(
                external_id=message_id,
                sender_id=visitor,
                recipient_id="website",
                text=text,
                occurred_at=datetime.now(UTC),
            )
        ]

    async def send_message(self, recipient: str, text: str) -> None:
        await refuse_send(recipient, text)

    def get_customer_profile(self, sender_id: str, payload: dict) -> ChannelCustomerProfile:
        del payload
        return ChannelCustomerProfile(sender_id, "Website visitor", None)
