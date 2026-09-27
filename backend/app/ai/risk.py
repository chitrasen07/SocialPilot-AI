"""Deterministic risk labels. High means the draft needs review, not that the customer is right."""

import re
from dataclasses import dataclass, field

_SAFETY = re.compile(
    r"\b(injur\w*|hurt me|hospital|allergic|unsafe product|caused me harm)\b",
    re.I,
)
_LEGAL = re.compile(r"\b(fraud|lawyer|lawsuit|sue you|police|illegal)\b", re.I)
_PAYMENT_HIGH = re.compile(
    r"charged twice|double charged|unauthorized charge|need my money back",
    re.I,
)
_REFUND = re.compile(r"\b(refund|money back|wapas)\b", re.I)
_PAYMENT = re.compile(r"\b(charged|payment|transaction|billed)\b", re.I)
_ANGER = re.compile(r"\b(furious|worst|scam|terrible service)\b", re.I)

_REASONS = (
    ("safety", "safety concern"),
    ("legal", "legal complaint"),
    ("payment", "payment issue"),
    ("refund", "refund dispute"),
    ("complaint", "angry customer"),
)


@dataclass
class RiskAssessment:
    level: str = "low"
    escalation_required: bool = False
    codes: list[str] = field(default_factory=list)
    reason: str | None = None


def assess_risk(
    message: str, *, emotion: str = "neutral", sentiment: str = "neutral"
) -> RiskAssessment:
    """Labels come from the message text and the stored analysis, not from personal traits."""
    text = message or ""
    codes: list[str] = []
    if _SAFETY.search(text):
        codes.append("safety")
    if _LEGAL.search(text):
        codes.append("legal")
    if _PAYMENT_HIGH.search(text) or (_PAYMENT.search(text) and _REFUND.search(text)):
        codes.append("payment")
    elif _PAYMENT.search(text):
        codes.append("payment")
    if _REFUND.search(text):
        codes.append("refund")
    if emotion == "anger" or sentiment == "negative" and _ANGER.search(text):
        codes.append("complaint")

    if any(code in codes for code in ("safety", "legal", "payment")) and (
        "payment" in codes and _PAYMENT_HIGH.search(text) or "safety" in codes or "legal" in codes
    ):
        level = "high"
    elif "payment" in codes or "refund" in codes or "complaint" in codes:
        level = "medium"
    else:
        level = "low"

    reason = next((label for code, label in _REASONS if code in codes), None)
    return RiskAssessment(
        level=level, escalation_required=level != "low", codes=codes, reason=reason
    )
