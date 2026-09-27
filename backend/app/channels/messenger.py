"""Facebook Messenger webhook parsing. Messages are not sent."""

from datetime import UTC, datetime

from app.channels.base import (
    ChannelCustomerProfile,
    InboundMessage,
    refuse_send,
    verify_hmac,
)
from app.models.channel import ChannelType


class MessengerChannel:
    channel = ChannelType.MESSENGER

    def verify_webhook(self, body: bytes, signature: str | None, secret: str | None) -> bool:
        return verify_hmac(body, signature, secret)

    def receive_message(self, payload: dict) -> list[InboundMessage]:
        found: list[InboundMessage] = []
        for entry in payload.get("entry") or []:
            if not isinstance(entry, dict):
                continue
            page = str(entry.get("id") or "")
            for item in entry.get("messaging") or []:
                if not isinstance(item, dict):
                    continue
                message = item.get("message") or {}
                if not isinstance(message, dict) or not message.get("mid"):
                    continue
                sender = str((item.get("sender") or {}).get("id") or "")
                recipient = str((item.get("recipient") or {}).get("id") or page)
                found.append(
                    InboundMessage(
                        external_id=str(message["mid"]),
                        sender_id=sender,
                        recipient_id=recipient,
                        text=message.get("text") if isinstance(message.get("text"), str) else None,
                        occurred_at=_time(item.get("timestamp")),
                    )
                )
        return found

    async def send_message(self, recipient: str, text: str) -> None:
        await refuse_send(recipient, text)

    def get_customer_profile(self, sender_id: str, payload: dict) -> ChannelCustomerProfile:
        del payload
        return ChannelCustomerProfile(sender_id, None, None)


def _time(value: object) -> datetime:
    if isinstance(value, int | float):
        seconds = value / 1000 if value > 10**11 else value
        return datetime.fromtimestamp(seconds, UTC)
    return datetime.now(UTC)
