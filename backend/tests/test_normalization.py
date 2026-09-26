"""Webhook event -> customer -> conversation -> message normalization (worker path)."""

import asyncio
import json
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.integrations.instagram.webhooks import extract_events
from app.models import (
    Conversation,
    ConversationStatus,
    Customer,
    DeliveryStatus,
    InstagramEvent,
    Message,
    MessageType,
    SenderType,
    WebhookDelivery,
)
from app.services.normalization import normalize_message_event
from app.services.webhooks import process_delivery, record_delivery
from tests.conftest import add_instagram_account, deliver, dm_payload

IG_ID = "17841400000000001"
OTHER_IG_ID = "17841400000000002"
T1 = 1790000000000
T2 = T1 + 60_000


def all_rows(db, model, *order_by):
    async def query(session):
        return list(await session.scalars(select(model).order_by(*order_by)))

    return db.run(query)


def setup_account(db, ig_id: str = IG_ID, **org):
    _, organization = db.add_member(**org)
    return organization, add_instagram_account(db, organization, instagram_account_id=ig_id)


def test_customer_conversation_and_messages_are_created(db):
    organization, account = setup_account(db)
    deliver(db, dm_payload("user_123", "Blue shoes ka price?", "mid_1", T1))
    deliver(db, dm_payload("user_123", "Available hai?", "mid_2", T2))

    [customer] = all_rows(db, Customer)
    assert customer.organization_id == organization.id
    assert customer.instagram_account_id == account.id
    assert customer.instagram_user_id == "user_123"

    [conversation] = all_rows(db, Conversation)
    assert conversation.customer_id == customer.id
    assert conversation.organization_id == organization.id
    assert conversation.status == ConversationStatus.OPEN
    assert conversation.last_message_at == datetime.fromtimestamp(T2 / 1000, UTC)

    messages = all_rows(db, Message, Message.sent_at)
    assert [m.content for m in messages] == ["Blue shoes ka price?", "Available hai?"]
    assert {m.conversation_id for m in messages} == {conversation.id}
    assert {m.sender_type for m in messages} == {SenderType.CUSTOMER}
    assert {m.message_type for m in messages} == {MessageType.TEXT}
    assert [m.external_message_id for m in messages] == ["mid_1", "mid_2"]
    # The raw events are still recorded alongside the normalized rows.
    assert db.count(InstagramEvent) == 2


def test_redelivered_event_is_not_duplicated(db):
    setup_account(db)
    body = dm_payload("user_123", "Blue shoes ka price?", "mid_1", T1)
    deliver(db, body)
    # Meta retries can arrive as a different body (new batch) carrying the same message.
    retried = json.loads(json.dumps(body))
    retried["entry"][0]["time"] += 5
    deliver(db, retried)

    assert db.count(Customer) == 1
    assert db.count(Conversation) == 1
    assert db.count(Message) == 1


def test_second_customer_gets_separate_records(db):
    setup_account(db)
    deliver(db, dm_payload("user_123", "Blue shoes ka price?", "mid_1", T1))
    deliver(db, dm_payload("user_456", "Hi", "mid_2", T2))

    customers = all_rows(db, Customer, Customer.instagram_user_id)
    assert [c.instagram_user_id for c in customers] == ["user_123", "user_456"]
    conversations = all_rows(db, Conversation)
    assert len({c.customer_id for c in conversations}) == 2


def test_same_instagram_user_is_isolated_per_organization(db):
    org_a, _ = setup_account(db, IG_ID)
    org_b, _ = setup_account(db, OTHER_IG_ID)
    deliver(db, dm_payload("user_123", "Blue shoes ka price?", "mid_a", T1, account_id=IG_ID))
    deliver(db, dm_payload("user_123", "Red bag?", "mid_b", T1, account_id=OTHER_IG_ID))

    customers = all_rows(db, Customer)
    assert {c.organization_id for c in customers} == {org_a.id, org_b.id}
    by_org = {m.organization_id: m.content for m in all_rows(db, Message)}
    assert by_org == {org_a.id: "Blue shoes ka price?", org_b.id: "Red bag?"}
    for conversation in all_rows(db, Conversation):
        owner = next(c for c in customers if c.id == conversation.customer_id)
        assert conversation.organization_id == owner.organization_id


def test_business_echo_is_attached_to_the_customer_thread(db):
    setup_account(db)
    deliver(db, dm_payload("user_123", "Blue shoes ka price?", "mid_1", T1))
    deliver(db, dm_payload(IG_ID, "Rs 1999", "mid_2", T2, recipient="user_123", is_echo=True))

    assert db.count(Customer) == 1
    reply = next(m for m in all_rows(db, Message) if m.external_message_id == "mid_2")
    assert reply.sender_type == SenderType.BUSINESS
    assert db.count(Conversation) == 1


def test_attachments_set_message_type_and_metadata(db):
    setup_account(db)
    image = [{"type": "image", "payload": {"url": "https://cdn.example/1.jpg"}}]
    deliver(db, dm_payload("user_123", None, "mid_img", T1, attachments=image))
    deliver(db, dm_payload("user_123", None, "mid_share", T2, attachments=[{"type": "share"}]))

    by_mid = {m.external_message_id: m for m in all_rows(db, Message)}
    assert by_mid["mid_img"].message_type == MessageType.IMAGE
    assert by_mid["mid_img"].content is None
    assert by_mid["mid_img"].meta == {
        "attachments": [{"type": "image", "url": "https://cdn.example/1.jpg"}]
    }
    assert by_mid["mid_share"].message_type == MessageType.UNKNOWN


def test_message_after_close_starts_a_new_conversation(db):
    setup_account(db)
    deliver(db, dm_payload("user_123", "Blue shoes ka price?", "mid_1", T1))

    async def close(session):
        await session.execute(update(Conversation).values(status=ConversationStatus.CLOSED))
        await session.commit()

    db.run(close)
    deliver(db, dm_payload("user_123", "Available hai?", "mid_2", T2))

    conversations = all_rows(db, Conversation, Conversation.created_at)
    assert [c.status for c in conversations] == [ConversationStatus.CLOSED, ConversationStatus.OPEN]
    assert db.count(Customer) == 1


def test_out_of_order_delivery_keeps_latest_timestamp(db):
    setup_account(db)
    deliver(db, dm_payload("user_123", "Available hai?", "mid_2", T2))
    deliver(db, dm_payload("user_123", "Blue shoes ka price?", "mid_1", T1))

    [conversation] = all_rows(db, Conversation)
    assert conversation.last_message_at == datetime.fromtimestamp(T2 / 1000, UTC)


def test_unsent_message_content_is_removed(db):
    setup_account(db)
    deliver(db, dm_payload("user_123", "Blue shoes ka price?", "mid_1", T1))
    deliver(db, dm_payload("user_123", None, "mid_1", T2, is_deleted=True))

    [message] = all_rows(db, Message)
    assert message.content is None
    assert message.meta == {"deleted": True}


def test_events_for_unknown_accounts_create_nothing(db):
    setup_account(db)
    deliver(db, dm_payload("user_123", "hello", "mid_1", T1, account_id="999"))
    assert db.count(Customer) == 0
    assert db.count(Message) == 0


def _run_concurrently(db, bodies: list[dict]) -> None:
    """Records each body, then processes all deliveries at once on separate connections, as
    several worker consumers would."""

    async def go():
        engine = create_async_engine(db.url, pool_size=len(bodies))
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            ids = []
            for body in bodies:
                async with sessions() as session:
                    ids.append(
                        await record_delivery(session, "instagram", json.dumps(body).encode(), body)
                    )

            async def work(delivery_id):
                async with sessions() as session:
                    return await process_delivery(session, delivery_id)

            assert all(await asyncio.gather(*(work(i) for i in ids)))
            async with sessions() as session:
                statuses = set(await session.scalars(select(WebhookDelivery.status)))
            assert statuses == {DeliveryStatus.PROCESSED}
        finally:
            await engine.dispose()

    asyncio.run(go())


def test_concurrent_duplicate_deliveries_create_one_of_each(db):
    setup_account(db)
    bodies = []
    for batch in range(5):
        body = dm_payload("user_123", "Blue shoes ka price?", "mid_1", T1)
        body["entry"][0]["time"] += batch  # distinct deliveries, same message
        bodies.append(body)
    _run_concurrently(db, bodies)

    assert db.count(Customer) == 1
    assert db.count(Conversation) == 1
    assert db.count(Message) == 1


def test_concurrent_normalizers_rely_on_constraints_not_locks(db):
    """Calls the normalizer directly (no account-row lock from the delivery path), so all five
    transactions genuinely race on customer, conversation and message creation."""
    _, account = setup_account(db)

    async def go():
        engine = create_async_engine(db.url, pool_size=5)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        start = asyncio.Event()

        async def work(i: int):
            event = extract_events(dm_payload("user_123", "Available hai?", "mid_x", T1 + i))[0]
            async with sessions() as session:
                await start.wait()
                await normalize_message_event(session, account, event)
                await session.commit()

        try:
            tasks = [asyncio.create_task(work(i)) for i in range(5)]
            await asyncio.sleep(0.05)
            start.set()
            await asyncio.gather(*tasks)
        finally:
            await engine.dispose()

    asyncio.run(go())
    assert db.count(Customer) == 1
    assert db.count(Conversation) == 1
    assert db.count(Message) == 1


def test_concurrent_messages_from_new_customer_share_one_conversation(db):
    setup_account(db)
    bodies = [dm_payload("user_123", f"msg {i}", f"mid_{i}", T1 + i) for i in range(5)]
    _run_concurrently(db, bodies)

    assert db.count(Customer) == 1
    assert db.count(Conversation) == 1
    assert db.count(Message) == 5
