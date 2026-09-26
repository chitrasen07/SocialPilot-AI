import hashlib
import hmac
import json
from datetime import timedelta

import pytest
from redis.asyncio import Redis
from sqlalchemy import select, update

from app.db.base import utcnow
from app.models import (
    ConnectionStatus,
    DeliveryStatus,
    InstagramAccount,
    InstagramEvent,
    InstagramEventType,
    Role,
    WebhookDelivery,
)
from app.services import webhooks as webhook_service
from app.services.webhooks import MAX_ATTEMPTS, process_delivery, requeue_due_deliveries
from app.workers.queue import WEBHOOK_QUEUE
from tests.conftest import (
    META_APP_SECRET,
    META_VERIFY_TOKEN,
    TEST_REDIS_URL,
    add_instagram_account,
    member_headers,
    redis_run,
)

IG_ID = "17841400000000001"


def payload(account_id: str = IG_ID, mid: str = "m_1", comment_id: str = "c_1") -> dict:
    return {
        "object": "instagram",
        "entry": [
            {
                "id": account_id,
                "time": 1790000000,
                "messaging": [
                    {
                        "sender": {"id": "customer-1"},
                        "recipient": {"id": account_id},
                        "timestamp": 1790000000123,
                        "message": {"mid": mid, "text": "Bro price kya hai?"},
                    }
                ],
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": comment_id,
                            "text": "Available in M?",
                            "from": {"id": "c2"},
                        },
                    }
                ],
            }
        ],
    }


def signed_post(api, body: bytes, secret: str = META_APP_SECRET):
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return api.post(
        "/api/webhooks/instagram",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
    )


def deliveries(db) -> list[WebhookDelivery]:
    async def query(session):
        return list(await session.scalars(select(WebhookDelivery)))

    return db.run(query)


def events(db) -> list[InstagramEvent]:
    async def query(session):
        return list(
            await session.scalars(select(InstagramEvent).order_by(InstagramEvent.event_type))
        )

    return db.run(query)


def store(db, body: dict) -> WebhookDelivery:
    raw = json.dumps(body).encode()

    async def record(session):
        return await webhook_service.record_delivery(session, "instagram", raw, body)

    return db.run(record)


def process(db, delivery_id) -> bool:
    return db.run(lambda session: process_delivery(session, delivery_id))


# --- Verification handshake -------------------------------------------------------------


def test_subscription_handshake_echoes_challenge(api):
    response = api.get(
        "/api/webhooks/instagram",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": META_VERIFY_TOKEN,
            "hub.challenge": "42",
        },
    )
    assert response.status_code == 200
    assert response.text == "42"


@pytest.mark.parametrize(
    "params",
    [
        {"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "42"},
        {"hub.mode": "unsubscribe", "hub.verify_token": META_VERIFY_TOKEN, "hub.challenge": "42"},
        {},
    ],
)
def test_subscription_handshake_rejects_bad_requests(api, params):
    response = api.get("/api/webhooks/instagram", params=params)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "WEBHOOK_VERIFICATION_FAILED"


# --- Ingestion endpoint -----------------------------------------------------------------


def test_signed_delivery_is_stored_and_enqueued_without_processing(api, db):
    body = json.dumps(payload()).encode()

    response = signed_post(api, body)

    assert response.json() == {"status": "received"}
    [delivery] = deliveries(db)
    assert delivery.status == DeliveryStatus.PENDING
    assert events(db) == []  # processing is the worker's job
    assert redis_run(lambda r: r.lrange(WEBHOOK_QUEUE, 0, -1)) == [str(delivery.id)]


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-Hub-Signature-256": "sha256=deadbeef"}, {"X-Hub-Signature-256": "md5=abc"}],
)
def test_unsigned_or_badly_signed_delivery_is_rejected(api, db, headers):
    response = api.post(
        "/api/webhooks/instagram", content=b'{"object":"instagram"}', headers=headers
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_SIGNATURE"
    assert deliveries(db) == []


def test_signature_with_wrong_secret_is_rejected(api, db):
    assert signed_post(api, b"{}", secret="attacker").status_code == 401


def test_duplicate_delivery_is_stored_and_enqueued_once(api, db):
    body = json.dumps(payload()).encode()
    signed_post(api, body)

    assert signed_post(api, body).json() == {"status": "duplicate"}
    assert len(deliveries(db)) == 1
    assert redis_run(lambda r: r.llen(WEBHOOK_QUEUE)) == 1


def test_invalid_json_is_rejected(api, db):
    assert signed_post(api, b"not json").json()["error"]["code"] == "INVALID_PAYLOAD"


def test_oversized_delivery_is_rejected(api, db):
    response = signed_post(api, b" " * 1_000_001)
    assert response.status_code == 413


def test_webhooks_disabled_without_app_secret(api, db, settings):
    api.app.state.settings = settings.model_copy(update={"meta_app_secret": None})
    assert signed_post(api, b"{}").status_code == 503


# --- Worker processing ------------------------------------------------------------------


def test_processing_extracts_events_into_the_owning_organization(api, db, verifier):
    _, organization = member_headers(db, verifier, Role.OWNER)
    account = add_instagram_account(db, organization)
    body = payload()
    body["entry"].append(payload(account_id="unknown-account")["entry"][0])
    delivery_id = store(db, body)

    assert process(db, delivery_id) is True

    stored = events(db)
    assert [(e.event_type, e.external_id) for e in stored] == [
        (InstagramEventType.COMMENT, "c_1"),
        (InstagramEventType.MESSAGE, "m_1"),
    ]
    assert {e.organization_id for e in stored} == {organization.id}
    assert {e.instagram_account_id for e in stored} == {account.id}
    [delivery] = deliveries(db)
    assert delivery.status == DeliveryStatus.PROCESSED

    async def payload_is_sql_null(session):
        return await session.scalar(
            select(WebhookDelivery.payload.is_(None)).where(WebhookDelivery.id == delivery_id)
        )

    # Raw customer content is not retained (SQL NULL, not a JSON `null` value).
    assert db.run(payload_is_sql_null) is True

    async def load(session):
        return await session.get(InstagramAccount, account.id)

    assert db.run(load).last_webhook_at is not None


def test_processing_is_idempotent(api, db, verifier):
    _, organization = member_headers(db, verifier, Role.OWNER)
    add_instagram_account(db, organization)
    first = store(db, payload())
    process(db, first)

    assert process(db, first) is False  # already processed; not claimable again
    # Same events arriving in a different delivery body do not duplicate.
    second = store(db, payload() | {"extra": 1})
    process(db, second)
    assert len(events(db)) == 2


def test_events_for_disconnected_accounts_are_dropped(api, db, verifier):
    _, organization = member_headers(db, verifier, Role.OWNER)
    add_instagram_account(db, organization, connection_status=ConnectionStatus.DISCONNECTED)
    process(db, store(db, payload()))
    assert events(db) == []


def test_failures_back_off_then_give_up(api, db, monkeypatch):
    def boom(_payload):
        raise RuntimeError("customer text that must not be stored")

    monkeypatch.setattr(webhook_service, "extract_events", boom)
    delivery_id = store(db, payload())

    process(db, delivery_id)
    [delivery] = deliveries(db)
    assert (delivery.status, delivery.attempts) == (DeliveryStatus.PENDING, 1)
    assert delivery.next_attempt_at > utcnow()
    assert delivery.last_error == "RuntimeError"

    async def make_due(session):
        await session.execute(
            update(WebhookDelivery).values(
                next_attempt_at=utcnow() - timedelta(seconds=1), attempts=MAX_ATTEMPTS - 1
            )
        )
        await session.commit()

    db.run(make_due)
    process(db, delivery_id)
    [delivery] = deliveries(db)
    assert delivery.status == DeliveryStatus.FAILED
    assert delivery.payload is not None  # kept for inspection when processing gave up


def test_sweeper_requeues_only_due_unfinished_deliveries(api, db):
    due = store(db, payload(mid="due"))
    store(db, payload(mid="future"))
    done = store(db, payload(mid="done"))

    async def arrange(session):
        past = utcnow() - timedelta(minutes=1)
        await session.execute(
            update(WebhookDelivery).where(WebhookDelivery.id == due).values(next_attempt_at=past)
        )
        await session.execute(
            update(WebhookDelivery)
            .where(WebhookDelivery.id == done)
            .values(next_attempt_at=past, status=DeliveryStatus.PROCESSED)
        )
        await session.commit()

    db.run(arrange)

    async def sweep(session):
        client = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
        try:
            return await requeue_due_deliveries(session, client)
        finally:
            await client.aclose()

    assert db.run(sweep) == 1
    assert redis_run(lambda r: r.lrange(WEBHOOK_QUEUE, 0, -1)) == [str(due)]
