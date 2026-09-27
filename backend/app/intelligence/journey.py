"""Lifecycle stage from messages already stored. Stages move forward along the funnel."""

import re

from app.intelligence.conversation import understand

_FUNNEL = ("visitor", "lead", "interested", "qualified", "customer", "repeat_customer")
_BOUGHT = re.compile(r"\b(bought|ordered|purchased|i paid)\b", re.I)
_INTERESTED = {"product_interest", "pricing", "negotiation"}


def next_journey(current: str | None, texts: list[str]) -> tuple[str, str, float] | None:
    """Returns the new stage, reason, and confidence. None when the stage stays put."""
    usable = [text for text in texts if (text or "").strip()]
    if not usable:
        return None
    latest = usable[-1]
    reading = understand(latest)
    stage = "lead"
    reason = "the customer sent a message"
    confidence = 0.6
    if reading["stage"] in _INTERESTED:
        stage, reason, confidence = (
            "interested",
            "the customer asked about a product or price",
            0.75,
        )
    if reading["stage"] == "purchase_intent":
        stage, reason, confidence = "qualified", "the customer expressed purchase intent", 0.8
    purchases = sum(1 for text in usable if _BOUGHT.search(text))
    if purchases == 1:
        stage, reason, confidence = "customer", "a purchase was mentioned in the conversation", 0.7
    elif purchases >= 2:
        stage, reason, confidence = (
            "repeat_customer",
            "more than one purchase was mentioned",
            0.7,
        )
    if current == "inactive":
        current = "lead"
    chosen = _forward(current or "visitor", stage)
    if chosen == current:
        return None
    return chosen, reason, confidence


def _forward(current: str, desired: str) -> str:
    if current not in _FUNNEL:
        current = "visitor"
    if desired not in _FUNNEL:
        return current
    if _FUNNEL.index(desired) >= _FUNNEL.index(current):
        return desired
    return current
