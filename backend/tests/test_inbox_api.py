"""Customer, conversation, message and memory APIs: shape, pagination, RBAC, isolation."""

import uuid

from sqlalchemy import select

from app.models import Conversation, CustomerMemory, Role
from tests.conftest import add_instagram_account, deliver, dm_payload, member_headers

IG_ID = "17841400000000001"
OTHER_IG_ID = "17841400000000002"
T1 = 1790000000000


def seed(db, verifier, role: Role = Role.AGENT, ig_id: str = IG_ID):
    """An organization with a connected account, user_123 (two messages) and user_456."""
    headers, organization = member_headers(db, verifier, role)
    add_instagram_account(db, organization, instagram_account_id=ig_id)
    deliver(db, dm_payload("user_123", "Blue shoes ka price?", f"{ig_id}_1", T1, account_id=ig_id))
    deliver(db, dm_payload("user_456", "Hello", f"{ig_id}_2", T1 + 1000, account_id=ig_id))
    deliver(db, dm_payload("user_123", "Available hai?", f"{ig_id}_3", T1 + 2000, account_id=ig_id))
    return {**headers, "X-Organization-Id": str(organization.id)}, organization


def customer_id(api, headers, user_id: str) -> str:
    items = api.get("/api/customers", headers=headers).json()["items"]
    return next(c["id"] for c in items if c["instagram_user_id"] == user_id)


# --- Customers -------------------------------------------------------------------------------


def test_list_customers(api, db, verifier):
    headers, _ = seed(db, verifier)
    body = api.get("/api/customers", headers=headers).json()

    assert body["has_more"] is False
    assert [c["instagram_user_id"] for c in body["items"]] == ["user_123", "user_456"]
    first = body["items"][0]
    assert first["conversation_count"] == 1
    assert first["last_message_at"] is not None
    assert "profile_data" not in first


def test_customer_search_and_pagination(api, db, verifier):
    headers, _ = seed(db, verifier)
    found = api.get("/api/customers", params={"search": "456"}, headers=headers).json()
    assert [c["instagram_user_id"] for c in found["items"]] == ["user_456"]
    # LIKE wildcards are matched literally.
    assert api.get("/api/customers", params={"search": "%"}, headers=headers).json()["items"] == []

    page = api.get("/api/customers", params={"limit": 1}, headers=headers).json()
    assert len(page["items"]) == 1 and page["has_more"] is True
    rest = api.get("/api/customers", params={"limit": 1, "offset": 1}, headers=headers).json()
    assert rest["has_more"] is False
    assert rest["items"][0]["id"] != page["items"][0]["id"]

    for params in ({"limit": 101}, {"limit": 0}, {"offset": -1}):
        assert api.get("/api/customers", params=params, headers=headers).status_code == 422


def test_customer_detail_includes_conversations(api, db, verifier):
    headers, _ = seed(db, verifier)
    cid = customer_id(api, headers, "user_123")
    body = api.get(f"/api/customers/{cid}", headers=headers).json()
    assert body["instagram_user_id"] == "user_123"
    assert [c["status"] for c in body["conversations"]] == ["open"]


def test_customers_are_isolated_between_organizations(api, db, verifier):
    headers_a, _ = seed(db, verifier, ig_id=IG_ID)
    headers_b, _ = seed(db, verifier, ig_id=OTHER_IG_ID)
    cid_a = customer_id(api, headers_a, "user_123")

    ids_b = {c["id"] for c in api.get("/api/customers", headers=headers_b).json()["items"]}
    assert cid_a not in ids_b and len(ids_b) == 2

    for path in (f"/api/customers/{cid_a}", f"/api/customers/{cid_a}/memories"):
        response = api.get(path, headers=headers_b)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CUSTOMER_NOT_FOUND"

    missing = api.get(f"/api/customers/{uuid.uuid4()}", headers=headers_a)
    assert missing.status_code == 404


def test_customer_endpoints_require_authentication_and_organization(api, db, verifier):
    headers, _ = seed(db, verifier)
    assert api.get("/api/customers").status_code == 401
    no_org = {"Authorization": headers["Authorization"]}
    assert api.get("/api/customers", headers=no_org).status_code == 400


# --- Memories --------------------------------------------------------------------------------


def test_memory_lifecycle(api, db, verifier):
    headers, organization = seed(db, verifier, Role.AGENT)
    cid = customer_id(api, headers, "user_123")
    created = api.post(
        f"/api/customers/{cid}/memories",
        json={"memory_type": "preference", "content": "  Prefers blue shoes  ", "importance": 0.9},
        headers=headers,
    )
    assert created.status_code == 201
    memory = created.json()
    assert memory["content"] == "Prefers blue shoes"
    assert memory["importance"] == 0.9
    assert memory["has_embedding"] is False
    assert "embedding" not in memory

    listed = api.get(f"/api/customers/{cid}/memories", headers=headers).json()["items"]
    assert [m["id"] for m in listed] == [memory["id"]]

    path = f"/api/customers/{cid}/memories/{memory['id']}"
    assert api.delete(path, headers=headers).status_code == 204
    assert api.delete(path, headers=headers).status_code == 404


def test_memory_organization_comes_from_membership_not_body(api, db, verifier):
    headers, organization = seed(db, verifier)
    _, other_org = seed(db, verifier, ig_id=OTHER_IG_ID)
    cid = customer_id(api, headers, "user_123")
    response = api.post(
        f"/api/customers/{cid}/memories",
        json={
            "memory_type": "fact",
            "content": "Lives in Pune",
            "organization_id": str(other_org.id),
        },
        headers=headers,
    )
    assert response.status_code == 201

    async def owner(session):
        return await session.scalar(select(CustomerMemory.organization_id))

    assert db.run(owner) == organization.id


def test_memory_validation(api, db, verifier):
    headers, _ = seed(db, verifier)
    cid = customer_id(api, headers, "user_123")
    for body in (
        {"memory_type": "preference", "content": "   "},
        {"memory_type": "preference", "content": "x", "importance": 1.5},
        {"memory_type": "sentiment", "content": "x"},
        {"memory_type": "fact", "content": "x" * 2001},
    ):
        response = api.post(f"/api/customers/{cid}/memories", json=body, headers=headers)
        assert response.status_code == 422, body


def test_viewer_can_read_but_not_modify_memories(api, db, verifier):
    headers, _ = seed(db, verifier, Role.VIEWER)
    cid = customer_id(api, headers, "user_123")
    assert api.get(f"/api/customers/{cid}/memories", headers=headers).status_code == 200
    response = api.post(
        f"/api/customers/{cid}/memories",
        json={"memory_type": "fact", "content": "x"},
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"
    assert (
        api.delete(f"/api/customers/{cid}/memories/{uuid.uuid4()}", headers=headers).status_code
        == 403
    )


def test_memories_of_another_organization_cannot_be_deleted(api, db, verifier):
    headers_a, _ = seed(db, verifier, ig_id=IG_ID)
    headers_b, _ = seed(db, verifier, ig_id=OTHER_IG_ID)
    cid_a = customer_id(api, headers_a, "user_123")
    memory = api.post(
        f"/api/customers/{cid_a}/memories",
        json={"memory_type": "fact", "content": "Org A only"},
        headers=headers_a,
    ).json()
    path = f"/api/customers/{cid_a}/memories/{memory['id']}"
    assert api.delete(path, headers=headers_b).status_code == 404
    assert db.count(CustomerMemory) == 1


# --- Conversations ---------------------------------------------------------------------------


def test_list_conversations_with_latest_message(api, db, verifier):
    headers, _ = seed(db, verifier)
    items = api.get("/api/conversations", headers=headers).json()["items"]

    assert [c["customer"]["instagram_user_id"] for c in items] == ["user_123", "user_456"]
    assert items[0]["last_message"]["content"] == "Available hai?"
    assert items[0]["last_message"]["sender_type"] == "customer"
    assert items[0]["status"] == "open"


def test_conversation_filters(api, db, verifier):
    headers, _ = seed(db, verifier)
    cid = customer_id(api, headers, "user_456")
    by_customer = api.get(
        "/api/conversations", params={"customer_id": cid}, headers=headers
    ).json()["items"]
    assert [c["customer"]["id"] for c in by_customer] == [cid]
    closed = api.get("/api/conversations", params={"status": "closed"}, headers=headers).json()
    assert closed["items"] == []
    assert (
        api.get("/api/conversations", params={"status": "bogus"}, headers=headers).status_code
        == 422
    )
    assert api.get("/api/conversations", params={"limit": 101}, headers=headers).status_code == 422


def test_conversation_detail_and_message_pagination(api, db, verifier):
    headers, _ = seed(db, verifier)
    conversation = api.get("/api/conversations", headers=headers).json()["items"][0]
    detail = api.get(f"/api/conversations/{conversation['id']}", headers=headers).json()
    assert detail["customer"]["instagram_user_id"] == "user_123"
    assert [m["content"] for m in detail["messages"]["items"]] == [
        "Blue shoes ka price?",
        "Available hai?",
    ]
    assert detail["messages"]["next_cursor"] is None

    path = f"/api/conversations/{conversation['id']}/messages"
    newest = api.get(path, params={"limit": 1}, headers=headers).json()
    assert [m["content"] for m in newest["items"]] == ["Available hai?"]
    older = api.get(
        path, params={"limit": 1, "before": newest["next_cursor"]}, headers=headers
    ).json()
    assert [m["content"] for m in older["items"]] == ["Blue shoes ka price?"]
    assert older["next_cursor"] is None

    bad = api.get(path, params={"before": "not-a-cursor"}, headers=headers)
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "INVALID_CURSOR"
    assert api.get(path, params={"limit": 101}, headers=headers).status_code == 422


def test_agent_updates_status(api, db, verifier):
    headers, organization = seed(db, verifier, Role.AGENT)
    conversation_id = api.get("/api/conversations", headers=headers).json()["items"][0]["id"]
    path = f"/api/conversations/{conversation_id}"

    response = api.patch(path, json={"status": "closed"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "closed"
    assert api.patch(path, json={"status": "archived"}, headers=headers).status_code == 422

    outsider, _ = member_headers(db, verifier, Role.OWNER)
    outsider["X-Organization-Id"] = str(organization.id)
    response = api.patch(path, json={"status": "open"}, headers=outsider)
    assert response.json()["error"]["code"] == "ORGANIZATION_ACCESS_DENIED"


def test_viewer_role_is_forbidden_to_patch(api, db, verifier):
    headers, _ = seed(db, verifier, Role.VIEWER)
    conversation_id = api.get("/api/conversations", headers=headers).json()["items"][0]["id"]
    response = api.patch(
        f"/api/conversations/{conversation_id}", json={"status": "closed"}, headers=headers
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"


def test_reopening_is_rejected_when_customer_has_active_thread(api, db, verifier):
    headers, _ = seed(db, verifier)
    first = api.get("/api/conversations", headers=headers).json()["items"][0]
    api.patch(f"/api/conversations/{first['id']}", json={"status": "closed"}, headers=headers)
    deliver(db, dm_payload("user_123", "Hello again", "mid_new", T1 + 9000))

    response = api.patch(
        f"/api/conversations/{first['id']}", json={"status": "open"}, headers=headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONVERSATION_ALREADY_ACTIVE"


def test_conversations_are_isolated_between_organizations(api, db, verifier):
    headers_a, _ = seed(db, verifier, ig_id=IG_ID)
    headers_b, _ = seed(db, verifier, ig_id=OTHER_IG_ID)
    conversation_a = api.get("/api/conversations", headers=headers_a).json()["items"][0]["id"]

    listed_b = api.get("/api/conversations", headers=headers_b).json()["items"]
    assert conversation_a not in {c["id"] for c in listed_b}
    for method, path, kwargs in (
        ("get", f"/api/conversations/{conversation_a}", {}),
        ("get", f"/api/conversations/{conversation_a}/messages", {}),
        ("patch", f"/api/conversations/{conversation_a}", {"json": {"status": "closed"}}),
    ):
        response = getattr(api, method)(path, headers=headers_b, **kwargs)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"

    async def status(session):
        return await session.scalar(
            select(Conversation.status).where(Conversation.id == uuid.UUID(conversation_a))
        )

    assert db.run(status) == "open"
