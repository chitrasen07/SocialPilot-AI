"""Conversation stage from the current message and the stage already stored.

Labels come from the local classifier and a few commercial keywords. The goal text is a
fixed phrase for that stage. It is not a guess about who the customer is.
"""

import re

from app.ai.classifier import classify_locally

_NEGOTIATION = re.compile(r"\b(discount|cheaper|negotiate|offer|deal|kam)\b", re.I)
_RESOLVED = re.compile(r"\b(resolved|all good|problem solved|that worked|fixed it)\b", re.I)
_URGENT = re.compile(r"\b(asap|urgent|today|right now|jaldi)\b", re.I)
_SUPPORT = {"support_request", "refund_request", "order_status", "shipping_question"}

_GOAL = {
    "discovery": "understand what the customer needs",
    "product_interest": "learn about a product",
    "pricing": "learn the price",
    "negotiation": "discuss published terms",
    "purchase_intent": "complete a purchase",
    "support": "get help with an order",
    "complaint": "resolve a complaint",
    "resolved": "confirm the issue is resolved",
}

_ACTION = {
    "discovery": "Prepare a short draft for a person to review.",
    "product_interest": "Prepare a product draft using the knowledge base.",
    "pricing": "Prepare a pricing draft from the knowledge base.",
    "negotiation": "Prepare a draft that stays within published terms.",
    "purchase_intent": "Prepare an order draft for a person to approve.",
    "support": "Prepare a support draft for review.",
    "complaint": "Ask a person to review this complaint before any reply.",
    "resolved": "No reply is required unless the customer writes again.",
}


def understand(text: str, previous_stage: str | None = None) -> dict:
    cleaned = text or ""
    local = classify_locally(cleaned)
    intent = local.intent.value if local is not None else "unknown"
    sentiment = local.sentiment.value if local is not None else "neutral"
    purchase = local.purchase_intent.value if local is not None else "unknown"
    stage = _stage(cleaned, intent, previous_stage)
    return {
        "stage": stage,
        "intent": intent,
        "urgency": _urgency(cleaned, stage),
        "buying_probability": _buying(intent, purchase),
        "churn_probability": _churn(intent, sentiment, stage),
        "customer_goal": _GOAL[stage],
        "recommended_action": _ACTION[stage],
    }


def _stage(text: str, intent: str, previous: str | None) -> str:
    if intent == "complaint" or re.search(r"\b(complaint|scam|worst|angry)\b", text, re.I):
        return "complaint"
    if previous in {"complaint", "support"} and _RESOLVED.search(text):
        return "resolved"
    if intent in _SUPPORT:
        return "support"
    if _NEGOTIATION.search(text):
        return "negotiation"
    if intent == "purchase_question":
        return "purchase_intent"
    if intent == "pricing_question":
        return "pricing"
    if intent in {"product_question", "availability_question"}:
        return "product_interest"
    if previous and previous != "discovery":
        return previous
    return "discovery"


def _urgency(text: str, stage: str) -> str:
    if _URGENT.search(text):
        return "high"
    if stage in {"complaint", "support"}:
        return "medium"
    return "low"


def _buying(intent: str, purchase: str) -> float:
    if purchase == "high" or intent == "purchase_question":
        return 0.8
    if intent == "pricing_question":
        return 0.55
    if intent in {"availability_question", "product_question"}:
        return 0.4
    if intent == "complaint":
        return 0.1
    return 0.2


def _churn(intent: str, sentiment: str, stage: str) -> float:
    if stage == "resolved":
        return 0.15
    if stage == "complaint" or intent == "complaint":
        return 0.7
    if sentiment == "negative":
        return 0.55
    if sentiment == "positive":
        return 0.1
    return 0.2
