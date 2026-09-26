import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.models import InstagramEventType

SIGNATURE_HEADER = "x-hub-signature-256"


def signature_is_valid(app_secret: str, body: bytes, header: str | None) -> bool:
    """Meta signs the raw body with HMAC-SHA256 using the app secret: `sha256=<hex>`."""
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


@dataclass(frozen=True)
class NormalizedEvent:
    instagram_account_id: str
    event_type: InstagramEventType
    external_id: str
    occurred_at: datetime
    payload: dict[str, Any]


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, int | float):
        return datetime.now(UTC)
    # Messaging timestamps are milliseconds; entry times may be seconds.
    seconds = value / 1000 if value > 10**11 else value
    return datetime.fromtimestamp(seconds, UTC)


def extract_events(payload: dict[str, Any]) -> list[NormalizedEvent]:
    """Extracts direct messages and comments; other event kinds are ignored for now."""
    if payload.get("object") != "instagram":
        return []

    events: list[NormalizedEvent] = []
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict) or "id" not in entry:
            continue
        account_id = str(entry["id"])

        for item in entry.get("messaging") or []:
            message = item.get("message") if isinstance(item, dict) else None
            if isinstance(message, dict) and message.get("mid"):
                events.append(
                    NormalizedEvent(
                        account_id,
                        InstagramEventType.MESSAGE,
                        str(message["mid"]),
                        _timestamp(item.get("timestamp")),
                        item,
                    )
                )

        for change in entry.get("changes") or []:
            if not isinstance(change, dict) or change.get("field") != "comments":
                continue
            value = change.get("value")
            if isinstance(value, dict) and value.get("id"):
                events.append(
                    NormalizedEvent(
                        account_id,
                        InstagramEventType.COMMENT,
                        str(value["id"]),
                        _timestamp(entry.get("time")),
                        value,
                    )
                )
    return events
