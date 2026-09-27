"""Engagement intelligence. Scores and stages stay inside the app. Nothing is sent."""

import uuid

import pytest

from app.intelligence.conversation import understand
from app.intelligence.journey import next_journey
from app.intelligence.optimizer import optimize_reply
from app.intelligence.recommendations import recommend
from app.intelligence.scoring import score_messages
from app.models import AIResponseScore, DocumentStatus, KnowledgeChunk, KnowledgeDocument, Role
from tests.conftest import deliver, dm_payload, member_headers
from tests.test_ai import message_id
from tests.test_inbox_api import customer_id, seed

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

_SENSITIVE = ("birthday", "religion", "gender", "income", "diagnosis")


def test_price_question_is_pricing_stage():
    reading = understand("price kya hai?")
    assert reading["stage"] == "pricing"
    assert reading["buying_probability"] == 0.55
    assert reading["customer_goal"] == "learn the price"


def test_purchase_language_is_purchase_intent():
    reading = understand("I want to buy this")
    assert reading["stage"] == "purchase_intent"
    assert reading["buying_probability"] == 0.8


def test_complaint_stage_and_goal_are_not_personal():
    reading = understand("this is the worst scam")
    assert reading["stage"] == "complaint"
    assert reading["churn_probability"] == 0.7
    blob = f"{reading['customer_goal']} {reading['recommended_action']}"
    assert all(word not in blob for word in _SENSITIVE)
    assert "send" not in reading["recommended_action"].lower()


def test_discount_is_negotiation():
    assert understand("can I get a discount?")["stage"] == "negotiation"


def test_support_question_is_support():
    assert understand("where is my order?")["stage"] == "support"


def test_thanks_after_support_is_resolved():
    assert understand("that worked", "support")["stage"] == "resolved"


def test_greeting_does_not_erase_pricing_stage():
    assert understand("hello", "pricing")["stage"] == "pricing"


def test_urgent_language_sets_high_urgency():
    assert understand("I need this today")["urgency"] == "high"


def test_lead_score_adds_price_availability_and_purchase():
    score, reason = score_messages(["I want to buy this", "what is the price?", "is it available?"])
    assert score == 90
    assert "purchase_intent +30" in reason
    assert "asked_price +20" in reason
    assert "asked_availability +20" in reason


def test_complaint_reduces_lead_score():
    score, reason = score_messages(["I want to buy this", "this is the worst scam"])
    assert score == 20
    assert "complaint -20" in reason


def test_lead_score_stays_within_bounds():
    low, _reason = score_messages(["worst scam"] * 5)
    high, _high_reason = score_messages(
        ["I want to buy this", "what is the price?", "is it available?", "thanks, this is great"]
    )
    assert low == 0
    assert high == 100


def test_first_message_moves_journey_to_lead():
    stage, reason, confidence = next_journey(None, ["hello"])
    assert stage == "lead"
    assert reason
    assert confidence > 0


def test_pricing_moves_journey_to_interested():
    stage, _reason, _confidence = next_journey(None, ["what is the price?"])
    assert stage == "interested"


def test_purchase_intent_moves_journey_to_qualified():
    stage, _reason, _confidence = next_journey(None, ["I want to buy this"])
    assert stage == "qualified"


def test_journey_does_not_move_backward():
    assert next_journey("qualified", ["hello"]) is None


def test_purchase_mention_moves_journey_to_customer():
    stage, _reason, _confidence = next_journey(None, ["I ordered the shoes"])
    assert stage == "customer"


def test_recommendations_come_only_from_knowledge():
    found = recommend("do you have canvas shoes?", [], ["Product: Canvas shoes"])
    assert found[0]["product_name"] == "Canvas shoes"
    assert found[0]["confidence"] == 0.85


def test_unknown_product_is_not_recommended():
    assert recommend("do you have a diamond tiara?", [], ["Product: Canvas shoes"]) == []


def test_approved_memory_can_match_a_catalog_product():
    found = recommend("hello", ["Interested in canvas shoes"], ["Product: Canvas shoes"])
    assert found[0]["product_name"] == "Canvas shoes"
    assert "approved memory" in found[0]["reason"]


def test_optimizer_is_deterministic_and_keeps_the_reply():
    kwargs = {
        "message": "What is the price?",
        "reply": "  The price is 1999.  ",
        "personality": "friendly",
        "history": ["customer: hello"],
        "knowledge": "The price is 1999.",
        "emoji_policy": "minimal",
    }
    first = optimize_reply(**kwargs)
    assert first.text == "The price is 1999."
    assert first == optimize_reply(**kwargs)
    assert 0 <= first.clarity_score <= 100
    assert first.conversion_score == 85


def test_optimizer_lowers_brand_score_when_emoji_is_forbidden():
    plain = optimize_reply(
        message="hello",
        reply="Hello, how can we help?",
        personality="professional",
        history=[],
        knowledge="",
        emoji_policy="none",
    )
    emoji = optimize_reply(
        message="hello",
        reply="Hello 😊",
        personality="professional",
        history=[],
        knowledge="",
        emoji_policy="none",
    )
    assert plain.brand_score == 90
    assert emoji.brand_score == 35


def test_ingested_message_stores_stage_score_and_journey(api, db, verifier):
    headers, _organization = seed(db, verifier)
    customer = customer_id(api, headers, "user_123")
    body = api.get(f"/api/intelligence/customers/{customer}", headers=headers)
    assert body.status_code == 200, body.text
    insights = body.json()
    assert insights["lifecycle_stage"] == "interested"
    assert insights["lead_score"] == 50
    assert insights["buying_probability"] == 0.4
    assert insights["recommended_actions"]
    assert "send" not in insights["recommended_actions"][0].lower()
    dashboard = api.get("/api/intelligence/dashboard", headers=headers)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["total_conversations"] >= 1
    assert dashboard.json()["average_lead_score"] is not None


def test_recommendation_is_stored_for_a_catalog_product(api, db, verifier):
    headers, organization = seed(db, verifier)

    async def catalog(session):
        document = KnowledgeDocument(
            organization_id=organization.id,
            name="Catalog",
            original_filename="catalog.txt",
            file_type="txt",
            mime_type="text/plain",
            file_size=32,
            status=DocumentStatus.READY,
        )
        session.add(document)
        await session.flush()
        session.add(
            KnowledgeChunk(
                organization_id=organization.id,
                document_id=document.id,
                chunk_index=0,
                content="Product: Canvas shoes",
            )
        )
        await session.commit()

    db.run(catalog)
    deliver(
        db,
        dm_payload(
            "user_123",
            "Do you have canvas shoes?",
            "mid_canvas",
            1790000090000,
        ),
    )
    customer = customer_id(api, headers, "user_123")
    body = api.get(f"/api/intelligence/customers/{customer}", headers=headers)
    assert body.status_code == 200, body.text
    names = [item["product_name"] for item in body.json()["recommendations"]]
    assert names == ["Canvas shoes"]
    assert "diamond" not in " ".join(names).lower()


def test_feedback_updates_learning_metrics(api, db, verifier):
    headers, _organization = seed(db, verifier)
    mid = message_id(api, headers, "Blue shoes ka price?")
    created = api.post("/api/ai/generate-reply", json={"message_id": mid}, headers=headers)
    assert created.status_code == 200, created.text
    assert created.json()["sent"] is False
    assert db.count(AIResponseScore) >= 1
    feedback = api.post(
        f"/api/ai/drafts/{created.json()['id']}/feedback",
        json={"action": "approved", "final_text": created.json()["reply_text"]},
        headers=headers,
    )
    assert feedback.status_code == 201, feedback.text
    dashboard = api.get("/api/intelligence/dashboard", headers=headers).json()
    assert dashboard["learning"]["accepted"] == 1
    assert dashboard["learning"]["best_personality"] == "friendly"
    assert dashboard["ai_improvement_score"] == 1


def test_dashboard_hides_other_organizations(api, db, verifier):
    headers, _organization = seed(db, verifier)
    customer = customer_id(api, headers, "user_123")
    other, _other_org = seed(db, verifier, ig_id="17841400000000077")
    missing = api.get(f"/api/intelligence/customers/{customer}", headers=other)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CUSTOMER_NOT_FOUND"
    foreign = api.get(f"/api/intelligence/customers/{uuid.uuid4()}", headers=headers)
    assert foreign.status_code == 404
    dashboard = api.get("/api/intelligence/dashboard", headers=other).json()
    assert customer not in [item["customer_id"] for item in dashboard["churn_risk_customers"]]


def test_viewer_can_read_intelligence_and_anonymous_cannot(api, db, verifier):
    headers, _organization = seed(db, verifier, Role.VIEWER)
    assert api.get("/api/intelligence/dashboard", headers=headers).status_code == 200
    anonymous = api.get("/api/intelligence/dashboard")
    assert anonymous.status_code == 401
    auth, organization = member_headers(db, verifier, Role.AGENT)
    agent_headers = {**auth, "X-Organization-Id": str(organization.id)}
    assert api.get("/api/intelligence/dashboard", headers=agent_headers).status_code == 200
