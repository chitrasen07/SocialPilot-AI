"""Automation rules, tasks, and notifications. Drafts are not sent."""

import uuid

import pytest

from app.models import AIReplyDraft, Role, Task
from app.services.automation import match_conditions
from tests.conftest import add_instagram_account, deliver, dm_payload, member_headers

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def headers_for(db, verifier, role: Role):
    auth, organization = member_headers(db, verifier, role)
    return {**auth, "X-Organization-Id": str(organization.id)}, organization


def test_condition_evaluation():
    facts = {"intent": "pricing_question", "sentiment": "neutral", "text": "Blue shoes price?"}
    assert match_conditions({}, facts) is True
    assert match_conditions({"intent": "pricing_question"}, facts) is True
    assert match_conditions({"intent": "refund_request"}, facts) is False
    assert match_conditions({"sentiment": "negative"}, facts) is False
    assert match_conditions({"contains": "shoes"}, facts) is True
    assert (
        match_conditions({"segment": "high_intent_buyer"}, {"segments": ["new_customer"]}) is False
    )
    assert match_conditions({"segment": "high_intent_buyer"}, {"segments": ["high_intent_buyer"]})


def test_admin_creates_rule_and_others_cannot(api, db, verifier):
    admin, _ = headers_for(db, verifier, Role.ADMIN)
    agent, _ = headers_for(db, verifier, Role.AGENT)
    viewer, _ = headers_for(db, verifier, Role.VIEWER)
    body = {
        "name": "When customer asks product price",
        "description": "Prepare a draft",
        "trigger_type": "intent_detected",
        "action_type": "generate_draft",
        "conditions": {"intent": "pricing_question"},
        "enabled": True,
    }
    created = api.post("/api/automation/rules", json=body, headers=admin)
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]
    assert created.json()["enabled"] is True
    assert api.post("/api/automation/rules", json=body, headers=agent).status_code == 403
    assert api.post("/api/automation/rules", json=body, headers=viewer).status_code == 403
    listed = api.get("/api/automation/rules", headers=viewer)
    assert listed.status_code == 200
    assert listed.json()["items"] == []
    assert api.get("/api/automation/rules", headers=admin).json()["items"][0]["id"] == rule_id
    patched = api.patch(f"/api/automation/rules/{rule_id}", json={"enabled": False}, headers=admin)
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False
    assert api.delete(f"/api/automation/rules/{rule_id}", headers=agent).status_code == 403
    assert api.delete(f"/api/automation/rules/{rule_id}", headers=admin).status_code == 204


def test_enabled_rule_prepares_a_draft_and_disabled_rule_does_not(api, db, verifier):
    headers, organization = headers_for(db, verifier, Role.ADMIN)
    add_instagram_account(db, organization)
    disabled = api.post(
        "/api/automation/rules",
        json={
            "name": "Off",
            "trigger_type": "intent_detected",
            "action_type": "generate_draft",
            "conditions": {"intent": "pricing_question"},
            "enabled": False,
        },
        headers=headers,
    )
    assert disabled.status_code == 201, disabled.text
    deliver(db, dm_payload("user_123", "Price kya hai?", "auto_off", 1790000100000))
    assert db.count(AIReplyDraft) == 0

    enabled = api.post(
        "/api/automation/rules",
        json={
            "name": "When customer asks product price",
            "description": "Prepare a draft",
            "trigger_type": "intent_detected",
            "action_type": "generate_draft",
            "conditions": {"intent": "pricing_question"},
            "enabled": True,
        },
        headers=headers,
    )
    assert enabled.status_code == 201, enabled.text
    deliver(db, dm_payload("user_123", "Blue shoes price?", "auto_on", 1790000101000))

    assert db.count(AIReplyDraft) == 1
    queue = api.get("/api/ai/review-queue", headers=headers)
    assert queue.status_code == 200, queue.text
    assert queue.json()["items"][0]["sent"] is False
    assert queue.json()["items"][0]["reply_text"]
    notes = api.get("/api/notifications", headers=headers)
    assert notes.status_code == 200, notes.text
    assert notes.json()["unread_count"] >= 1
    note_id = notes.json()["items"][0]["id"]
    read = api.post(f"/api/notifications/{note_id}/read", headers=headers)
    assert read.status_code == 200
    assert read.json()["read"] is True
    assert api.get("/api/notifications", headers=headers).json()["unread_count"] == 0


def test_negative_sentiment_opens_a_task(api, db, verifier):
    headers, organization = headers_for(db, verifier, Role.ADMIN)
    add_instagram_account(db, organization)
    created = api.post(
        "/api/automation/rules",
        json={
            "name": "Review refund complaint",
            "description": "A person should read this",
            "trigger_type": "sentiment_changed",
            "action_type": "create_task",
            "conditions": {"sentiment": "negative"},
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    deliver(db, dm_payload("user_123", "This is the worst product", "auto_neg", 1790000102000))
    tasks = api.get("/api/tasks?priority=high", headers=headers)
    assert tasks.status_code == 200, tasks.text
    assert tasks.json()["items"][0]["title"] == "Review refund complaint"
    assert tasks.json()["items"][0]["status"] == "open"
    assert tasks.json()["items"][0]["priority"] == "high"


def test_task_assignment_completion_and_roles(api, db, verifier):
    admin, _ = headers_for(db, verifier, Role.ADMIN)
    viewer, _ = headers_for(db, verifier, Role.VIEWER)
    me = api.get("/api/me", headers=admin).json()["user"]["id"]
    created = api.post(
        "/api/tasks",
        json={"title": "Follow up with Rahul", "priority": "high", "assigned_to": me},
        headers=admin,
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    assert created.json()["assigned_to"] == me
    mine = api.get("/api/tasks?assigned=me", headers=admin)
    assert mine.json()["items"][0]["id"] == task_id
    done = api.patch(f"/api/tasks/{task_id}", json={"status": "completed"}, headers=admin)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed"
    assert done.json()["completed_at"]
    assert api.post("/api/tasks", json={"title": "Nope"}, headers=viewer).status_code == 403
    assert (
        api.patch(f"/api/tasks/{task_id}", json={"status": "open"}, headers=viewer).status_code
        == 403
    )
    assert api.get("/api/tasks", headers=viewer).json()["items"] == []


def test_rules_tasks_and_notifications_are_isolated(api, db, verifier):
    headers_a, organization_a = headers_for(db, verifier, Role.ADMIN)
    headers_b, _ = headers_for(db, verifier, Role.ADMIN)
    add_instagram_account(db, organization_a, instagram_account_id="17841400000000011")
    created = api.post(
        "/api/automation/rules",
        json={
            "name": "Notify on price",
            "trigger_type": "message_received",
            "action_type": "notify_agent",
            "conditions": {"contains": "price"},
        },
        headers=headers_a,
    )
    rule_id = created.json()["id"]
    assert (
        api.patch(
            f"/api/automation/rules/{rule_id}", json={"enabled": False}, headers=headers_b
        ).status_code
        == 404
    )
    assert api.delete(f"/api/automation/rules/{rule_id}", headers=headers_b).status_code == 404
    deliver(
        db,
        dm_payload(
            "user_123",
            "What is the price?",
            "auto_iso",
            1790000103000,
            account_id="17841400000000011",
        ),
    )
    assert api.get("/api/notifications", headers=headers_a).json()["unread_count"] >= 1
    assert api.get("/api/notifications", headers=headers_b).json()["unread_count"] == 0
    note_id = api.get("/api/notifications", headers=headers_a).json()["items"][0]["id"]
    missing = api.post(f"/api/notifications/{note_id}/read", headers=headers_b)
    assert missing.status_code == 404
    task = api.post("/api/tasks", json={"title": "Contact high intent customer"}, headers=headers_a)
    task_id = task.json()["id"]
    assert api.get("/api/tasks", headers=headers_b).json()["items"] == []
    assert (
        api.patch(
            f"/api/tasks/{task_id}", json={"status": "cancelled"}, headers=headers_b
        ).status_code
        == 404
    )
    assert api.get("/api/automation/rules", headers=headers_b).json()["items"] == []


def test_segment_rule_creates_a_follow_up(api, db, verifier):
    headers, organization = headers_for(db, verifier, Role.OWNER)
    add_instagram_account(db, organization)
    created = api.post(
        "/api/automation/rules",
        json={
            "name": "Contact high intent customer",
            "description": "Sales follow-up",
            "trigger_type": "segment_changed",
            "action_type": "create_task",
            "conditions": {"segment": "high_intent_buyer"},
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    deliver(db, dm_payload("user_123", "I want to buy this today", "auto_buy", 1790000104000))
    tasks = api.get("/api/tasks", headers=headers)
    assert tasks.status_code == 200, tasks.text
    titles = [item["title"] for item in tasks.json()["items"]]
    assert "Contact high intent customer" in titles
    assert db.count(Task) >= 1
    assert uuid.UUID(tasks.json()["items"][0]["id"])
