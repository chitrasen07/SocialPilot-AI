"""Inbound email parsing. Outbound mail is a draft, not an SMTP delivery."""

from datetime import UTC, datetime

from app.channels.base import (
    ChannelCustomerProfile,
    InboundMessage,
    refuse_send,
    verify_hmac,
)
from app.models.channel import ChannelType


class EmailChannel:
    channel = ChannelType.EMAIL

    def verify_webhook(self, body: bytes, signature: str | None, secret: str | None) -> bool:
        return verify_hmac(body, signature, secret)

    def receive_message(self, payload: dict) -> list[InboundMessage]:
        message_id = payload.get("message_id")
        sender = payload.get("from")
        if not isinstance(message_id, str) or not isinstance(sender, str):
            return []
        subject = payload.get("subject") if isinstance(payload.get("subject"), str) else ""
        body = payload.get("text") if isinstance(payload.get("text"), str) else ""
        text = "\n".join(part for part in (subject, body) if part).strip() or None
        recipient = payload.get("to") if isinstance(payload.get("to"), str) else ""
        return [
            InboundMessage(
                external_id=message_id,
                sender_id=sender.lower(),
                recipient_id=recipient.lower(),
                text=text,
                occurred_at=datetime.now(UTC),
                profile_name=sender,
            )
        ]

    async def send_message(self, recipient: str, text: str) -> None:
        await refuse_send(recipient, text)

    def get_customer_profile(self, sender_id: str, payload: dict) -> ChannelCustomerProfile:
        del payload
        return ChannelCustomerProfile(sender_id, sender_id, None)
