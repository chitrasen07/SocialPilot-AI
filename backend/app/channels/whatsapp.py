"""WhatsApp Cloud API parsing. Delivery to WhatsApp is disabled."""

from datetime import UTC, datetime

from app.channels.base import (
    ChannelCustomerProfile,
    InboundMessage,
    refuse_send,
    verify_hmac,
)
from app.models.channel import ChannelType


class WhatsAppChannel:
    channel = ChannelType.WHATSAPP

    def verify_webhook(self, body: bytes, signature: str | None, secret: str | None) -> bool:
        return verify_hmac(body, signature, secret)

    def receive_message(self, payload: dict) -> list[InboundMessage]:
        names = _names(payload)
        found: list[InboundMessage] = []
        for entry in payload.get("entry") or []:
            if not isinstance(entry, dict):
                continue
            for change in entry.get("changes") or []:
                value = change.get("value") if isinstance(change, dict) else None
                if not isinstance(value, dict):
                    continue
                phone = str((value.get("metadata") or {}).get("phone_number_id") or "")
                for item in value.get("messages") or []:
                    if not isinstance(item, dict) or not item.get("id"):
                        continue
                    sender = str(item.get("from") or "")
                    body = (
                        (item.get("text") or {}).get("body") if item.get("type") == "text" else None
                    )
                    found.append(
                        InboundMessage(
                            external_id=str(item["id"]),
                            sender_id=sender,
                            recipient_id=phone,
                            text=body if isinstance(body, str) else None,
                            occurred_at=_time(item.get("timestamp")),
                            profile_name=names.get(sender),
                        )
                    )
        return found

    async def send_message(self, recipient: str, text: str) -> None:
        await refuse_send(recipient, text)

    def get_customer_profile(self, sender_id: str, payload: dict) -> ChannelCustomerProfile:
        return ChannelCustomerProfile(sender_id, _names(payload).get(sender_id), None)


def _names(payload: dict) -> dict[str, str]:
    found: dict[str, str] = {}
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes") or []:
            value = change.get("value") if isinstance(change, dict) else None
            if not isinstance(value, dict):
                continue
            for contact in value.get("contacts") or []:
                if not isinstance(contact, dict):
                    continue
                wa_id = str(contact.get("wa_id") or "")
                name = (contact.get("profile") or {}).get("name")
                if wa_id and isinstance(name, str):
                    found[wa_id] = name
    return found


def _time(value: object) -> datetime:
    if isinstance(value, int | float | str) and str(value).isdigit():
        return datetime.fromtimestamp(int(value), UTC)
    return datetime.now(UTC)
