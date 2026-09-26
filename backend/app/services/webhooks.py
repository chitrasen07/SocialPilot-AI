import hashlib
import logging
import uuid
from datetime import timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.integrations.instagram.webhooks import extract_events
from app.models import (
    ConnectionStatus,
    DeliveryStatus,
    InstagramAccount,
    InstagramEvent,
    InstagramEventType,
    WebhookDelivery,
)
from app.services.normalization import normalize_message_event
from app.workers.queue import enqueue_delivery

logger = logging.getLogger("socialpilot.webhooks")

MAX_ATTEMPTS = 6
CLAIM_TIMEOUT = timedelta(minutes=5)
SWEEP_GRACE = timedelta(seconds=15)
_ACTIVE = (DeliveryStatus.PENDING, DeliveryStatus.PROCESSING)


def retry_delay(attempts: int) -> timedelta:
    return timedelta(seconds=min(30 * 2 ** (attempts - 1), 3600))


async def record_delivery(
    session: AsyncSession, source: str, raw_body: bytes, payload: dict[str, Any]
) -> uuid.UUID | None:
    """Stores a verified delivery. Returns None when an identical body was already received."""
    delivery_id = await session.scalar(
        insert(WebhookDelivery)
        .values(
            source=source,
            payload_sha256=hashlib.sha256(raw_body).hexdigest(),
            payload=payload,
        )
        .on_conflict_do_nothing(index_elements=[WebhookDelivery.payload_sha256])
        .returning(WebhookDelivery.id)
    )
    await session.commit()
    return delivery_id


async def process_delivery(session: AsyncSession, delivery_id: uuid.UUID) -> bool:
    """Claims and processes one delivery. Returns False if it was not claimable (already
    processed, claimed by another worker, or not yet due for retry)."""
    now = utcnow()
    delivery = await session.scalar(
        update(WebhookDelivery)
        .where(
            WebhookDelivery.id == delivery_id,
            WebhookDelivery.status.in_(_ACTIVE),
            WebhookDelivery.next_attempt_at <= now,
        )
        .values(
            status=DeliveryStatus.PROCESSING,
            attempts=WebhookDelivery.attempts + 1,
            next_attempt_at=now + CLAIM_TIMEOUT,
            updated_at=now,
        )
        .returning(WebhookDelivery)
    )
    await session.commit()
    if delivery is None:
        return False

    attempts = delivery.attempts
    try:
        await _store_events(session, delivery.payload or {})
        delivery.status = DeliveryStatus.PROCESSED
        delivery.payload = None
        delivery.processed_at = utcnow()
        delivery.last_error = None
        await session.commit()
    except Exception as exc:
        await session.rollback()
        failed = attempts >= MAX_ATTEMPTS
        await session.execute(
            update(WebhookDelivery)
            .where(WebhookDelivery.id == delivery_id)
            .values(
                status=DeliveryStatus.FAILED if failed else DeliveryStatus.PENDING,
                next_attempt_at=utcnow() + retry_delay(attempts),
                # Class name only: exception messages may contain customer message content.
                last_error=type(exc).__name__,
                updated_at=utcnow(),
            )
        )
        await session.commit()
        logger.exception(
            "webhook_delivery_failed",
            extra={"fields": {"attempts": attempts, "gave_up": failed}},
        )
    return True


async def _store_events(session: AsyncSession, payload: dict[str, Any]) -> None:
    events = extract_events(payload)
    if not events:
        return

    accounts = {
        account.instagram_account_id: account
        for account in await session.scalars(
            select(InstagramAccount).where(
                InstagramAccount.instagram_account_id.in_({e.instagram_account_id for e in events}),
                InstagramAccount.connection_status != ConnectionStatus.DISCONNECTED,
            )
        )
    }
    now = utcnow()
    rows = [
        {
            "id": uuid.uuid4(),
            "organization_id": account.organization_id,
            "instagram_account_id": account.id,
            "event_type": event.event_type,
            "external_id": event.external_id,
            "occurred_at": event.occurred_at,
            "payload": event.payload,
            "created_at": now,
            "updated_at": now,
        }
        for event in events
        if (account := accounts.get(event.instagram_account_id))
    ]
    if rows:
        await session.execute(
            insert(InstagramEvent)
            .values(rows)
            .on_conflict_do_nothing(
                index_elements=["instagram_account_id", "event_type", "external_id"]
            )
        )
        for account in accounts.values():
            account.last_webhook_at = now

    # Normalizes every matched message, not only newly inserted events, so a delivery that
    # failed midway (and rolled back) or raced another worker converges on retry.
    for event in events:
        account = accounts.get(event.instagram_account_id)
        if account and event.event_type == InstagramEventType.MESSAGE:
            await normalize_message_event(session, account, event)

    logger.info(
        "webhook_events_extracted",
        extra={"fields": {"events": len(events), "matched": len(rows)}},
    )


async def requeue_due_deliveries(session: AsyncSession, redis: Redis, limit: int = 500) -> int:
    """Re-enqueues deliveries whose queue message was lost, whose claim expired (crashed
    worker), or whose retry backoff has elapsed."""
    ids = list(
        await session.scalars(
            select(WebhookDelivery.id)
            .where(
                WebhookDelivery.status.in_(_ACTIVE),
                WebhookDelivery.next_attempt_at <= utcnow() - SWEEP_GRACE,
            )
            .order_by(WebhookDelivery.next_attempt_at)
            .limit(limit)
        )
    )
    for delivery_id in ids:
        await enqueue_delivery(redis, delivery_id)
    return len(ids)
