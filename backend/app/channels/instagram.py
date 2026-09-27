"""Instagram behind the channel interface. Phase 3 webhooks stay on their own route."""

from app.channels.base import (
    ChannelCustomerProfile,
    InboundMessage,
    refuse_send,
    verify_hmac,
)
from app.integrations.instagram.webhooks import extract_events
from app.models import InstagramEventType
from app.models.channel import ChannelType


class InstagramChannel:
    channel = ChannelType.INSTAGRAM

    def verify_webhook(self, body: bytes, signature: str | None, secret: str | None) -> bool:
        return verify_hmac(body, signature, secret)

    def receive_message(self, payload: dict) -> list[InboundMessage]:
        found: list[InboundMessage] = []
        for event in extract_events(payload):
            if event.event_type != InstagramEventType.MESSAGE:
                continue
            message = event.payload.get("message") or {}
            sender = str((event.payload.get("sender") or {}).get("id") or "")
            recipient = str((event.payload.get("recipient") or {}).get("id") or "")
            echo = bool(message.get("is_echo")) or sender == event.instagram_account_id
            found.append(
                InboundMessage(
                    external_id=event.external_id,
                    sender_id=recipient if echo else sender,
                    recipient_id=sender if echo else recipient,
                    text=message.get("text") if isinstance(message.get("text"), str) else None,
                    occurred_at=event.occurred_at,
                    sender_is_business=echo,
                )
            )
        return found

    async def send_message(self, recipient: str, text: str) -> None:
        await refuse_send(recipient, text)

    def get_customer_profile(self, sender_id: str, payload: dict) -> ChannelCustomerProfile:
        del payload
        return ChannelCustomerProfile(sender_id, None, None)
