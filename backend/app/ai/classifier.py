"""Obvious-case classification without a model call.

Ambiguous text returns None so the orchestrator can ask the configured provider.
These labels are signals for reply style, not facts about a person.
"""

import re

from app.ai.schemas import MessageAnalysis, Signal

_HINGLISH = re.compile(
    r"\b(hai|hain|kya|nahi|bhai|yaar|bro|kitna|kitne|chahiye|mujhe|mera|ka|ki|ke)\b",
    re.I,
)
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_TELUGU = re.compile(r"[\u0C00-\u0C7F]")
_LATIN = re.compile(r"[A-Za-z]")
_EMOJI = re.compile(r"[\U0001F300-\U0001FAFF]")

_INTENT_RULES: tuple[tuple[str, str], ...] = (
    (r"\b(spam|buy followers|click here|free money)\b|https?://", "spam"),
    (r"\b(refund|money back|wapas)\b", "refund_request"),
    (r"\b(worst|scam|complaint|angry|terrible|fraud)\b", "complaint"),
    (r"\b(where is my order|order status|tracking)\b", "order_status"),
    (r"\b(shipping|delivery|deliver)\b", "shipping_question"),
    (r"\b(buy|purchase|order now|i want to buy|lena hai)\b", "purchase_question"),
    (r"\b(price|pricing|cost|kitna|how much)\b|कीमत|ధర", "pricing_question"),
    (r"\b(available|availability|in stock|stock)\b|उपलब्ध|అందుబాటు", "availability_question"),
    (r"\b(help|support|problem|issue)\b", "support_request"),
    (r"\b(nice|love|great|awesome|thanks|thank you)\b", "feedback"),
    (r"\b(hi|hello|hey|namaste|namaskar)\b", "greeting"),
    (r"\b(product|shoes|size|colour|color|model)\b", "product_question"),
)


def classify_locally(text: str) -> MessageAnalysis | None:
    cleaned = text.strip()
    if not cleaned:
        return _analysis("unknown", "unknown", "unknown", "unknown", "unknown", 0.2)
    language = _language(cleaned)
    intent = _intent(cleaned)
    if language == "unknown" and intent == "unknown":
        return None
    sentiment = _sentiment(cleaned)
    emotion = _emotion(cleaned, intent)
    purchase = _purchase(cleaned, intent)
    intent_confidence = 0.9 if intent != "unknown" else 0.45
    if intent == "unknown" and language != "unknown" and intent_confidence < 0.5:
        # Language is clear but the ask is not: still a useful local result.
        pass
    return _analysis(language, intent, sentiment, emotion, purchase, intent_confidence)


def _language(text: str) -> str:
    telugu = bool(_TELUGU.search(text))
    hindi = bool(_DEVANAGARI.search(text))
    latin = bool(_LATIN.search(text))
    if telugu and (latin or hindi):
        return "mixed"
    if hindi and latin:
        return "mixed"
    if telugu:
        return "telugu"
    if hindi:
        return "hindi"
    if latin and _HINGLISH.search(text):
        return "hinglish"
    if latin:
        return "english"
    return "unknown"


def _intent(text: str) -> str:
    for pattern, label in _INTENT_RULES:
        if re.search(pattern, text, re.I):
            return label
    return "unknown"


def _sentiment(text: str) -> str:
    positive = bool(re.search(r"\b(nice|love|great|awesome|thanks|good)\b|🔥|😊|😎", text, re.I))
    negative = bool(re.search(r"\b(worst|angry|terrible|scam|hate|bad)\b|😭|😡", text, re.I))
    if positive and negative:
        return "mixed"
    if positive:
        return "positive"
    if negative:
        return "negative"
    return "neutral"


def _emotion(text: str, intent: str) -> str:
    if re.search(r"\b(asap|urgent|today|right now|jaldi)\b", text, re.I):
        return "urgency"
    if re.search(r"\b(angry|hate|furious)\b|😡", text, re.I):
        return "anger"
    if re.search(r"\b(frustrated|ugh|worst|annoyed)\b|😭", text, re.I):
        return "frustration"
    if re.search(r"\b(confused|don't understand|samajh)\b|\?\?", text, re.I):
        return "confusion"
    if re.search(r"\b(disappointed|let down)\b", text, re.I):
        return "disappointment"
    if re.search(r"\b(nice|love|great|happy)\b|😊", text, re.I):
        return "joy"
    if intent in {
        "availability_question",
        "pricing_question",
        "purchase_question",
        "product_question",
    }:
        return "interest"
    if intent == "greeting":
        return "neutral"
    return "unknown"


def _purchase(text: str, intent: str) -> str:
    if re.search(r"\b(i want to buy|buy this today|order now|lena hai)\b", text, re.I):
        return "high"
    if intent == "pricing_question":
        return "medium"
    if intent in {"availability_question", "product_question"}:
        return "medium"
    if intent == "feedback":
        return "low"
    if intent in {"greeting", "spam"}:
        return "none"
    if intent == "unknown":
        return "unknown"
    return "low"


def _analysis(
    language: str,
    intent: str,
    sentiment: str,
    emotion: str,
    purchase: str,
    intent_confidence: float,
) -> MessageAnalysis:
    language_confidence = 0.2 if language == "unknown" else 0.9
    return MessageAnalysis(
        language=Signal(value=language, confidence=language_confidence),
        intent=Signal(value=intent, confidence=intent_confidence),
        sentiment=Signal(value=sentiment, confidence=0.85 if sentiment != "unknown" else 0.3),
        emotion=Signal(value=emotion, confidence=0.8 if emotion != "unknown" else 0.3),
        purchase_intent=Signal(value=purchase, confidence=0.8 if purchase != "unknown" else 0.3),
    )
