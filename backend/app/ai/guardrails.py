import re
from dataclasses import dataclass

_SECRET = re.compile(
    r"(BEGIN PRIVATE KEY|GEMINI_API_KEY|META_APP_SECRET|FIREBASE_PRIVATE_KEY|"
    r"sk-[A-Za-z0-9]{8,}|AIza[0-9A-Za-z\-_]{20,}|Bearer\s+[A-Za-z0-9\-\._]{10,})",
    re.I,
)
_LEAK = re.compile(
    r"(system prompt|hidden instructions|these instructions|you are socialpilot ai)",
    re.I,
)
_FALSE_ACTION = re.compile(
    r"("
    r"refund (has been|was) (processed|issued|completed)"
    r"|processed (your|the) refund"
    r"|order (has been|was) placed"
    r"|placed (your|the) order"
    r"|payment (has been|was) received"
    r"|confirmed (your|the) payment"
    r"|i have shipped"
    r")",
    re.I,
)


@dataclass(frozen=True)
class GuardrailResult:
    status: str
    reason: str | None = None


def check_reply(reply: str, *, max_chars: int) -> GuardrailResult:
    text = reply.strip()
    if not text:
        return GuardrailResult("blocked", "empty")
    if len(text) > max_chars:
        return GuardrailResult("blocked", "too_long")
    if _SECRET.search(text):
        return GuardrailResult("blocked", "secret")
    if _LEAK.search(text):
        return GuardrailResult("blocked", "prompt_leak")
    if _FALSE_ACTION.search(text):
        return GuardrailResult("blocked", "unsupported_claim")
    return GuardrailResult("passed")
