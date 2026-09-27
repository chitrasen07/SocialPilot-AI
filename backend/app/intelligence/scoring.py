"""Lead score from commercial message signals. The result stays between 0 and 100."""

from app.ai.classifier import classify_locally

_POINTS = (
    ("purchase_intent", 30),
    ("asked_price", 20),
    ("asked_availability", 20),
    ("repeated", 10),
    ("positive", 10),
    ("returning", 10),
    ("complaint", -20),
    ("inactive", -10),
)


def score_messages(
    texts: list[str], *, inactive: bool = False, returning: bool = False
) -> tuple[int, str]:
    flags: set[str] = set()
    usable = [text for text in texts if (text or "").strip()]
    for text in usable:
        local = classify_locally(text)
        if local is None:
            continue
        intent = local.intent.value
        if intent == "purchase_question" or local.purchase_intent.value == "high":
            flags.add("purchase_intent")
        if intent == "pricing_question":
            flags.add("asked_price")
        if intent == "availability_question":
            flags.add("asked_availability")
        if local.sentiment.value == "positive":
            flags.add("positive")
        if intent == "complaint":
            flags.add("complaint")
    if len(usable) >= 2:
        flags.add("repeated")
    if returning or len(usable) >= 3:
        flags.add("returning")
    if inactive:
        flags.add("inactive")
    return _total(flags)


def _total(flags: set[str]) -> tuple[int, str]:
    total = 0
    reasons: list[str] = []
    for name, points in _POINTS:
        if name not in flags:
            continue
        total += points
        reasons.append(f"{name} {points:+d}")
    bounded = max(0, min(100, total))
    return bounded, ", ".join(reasons) if reasons else "no commercial signals"
