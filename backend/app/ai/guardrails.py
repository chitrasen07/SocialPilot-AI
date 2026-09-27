"""Deterministic checks on a draft. These do not call an AI provider."""

import re
from dataclasses import dataclass, field

_SECRET = re.compile(
    r"(BEGIN PRIVATE KEY|GEMINI_API_KEY|META_APP_SECRET|FIREBASE_PRIVATE_KEY|"
    r"sk-[A-Za-z0-9]{8,}|AIza[0-9A-Za-z\-_]{20,}|Bearer\s+[A-Za-z0-9\-\._]{10,})",
    re.I,
)
_LEAK = re.compile(
    r"(system prompt|hidden instructions|these instructions|you are socialpilot ai)",
    re.I,
)
_PROMISE = re.compile(
    r"("
    r"refund (has been|was|is) (processed|issued|completed|guaranteed)"
    r"|processed (your|the) refund"
    r"|payment has been refunded"
    r"|(has|have) been refunded"
    r"|order (has been|was) placed"
    r"|placed (your|the) order"
    r"|payment (has been|was) received"
    r"|confirmed (your|the) payment"
    r"|i have shipped"
    r"|will definitely arrive"
    r"|definitely arrive"
    r"|100% guaranteed"
    r"|your refund is guaranteed"
    r")",
    re.I,
)
_CERTAINTY = re.compile(r"\b(100% certain|definitely|guaranteed|always works)\b", re.I)
_ABUSE = re.compile(r"\b(fuck|shit|bitch|asshole|kill yourself)\b", re.I)
_PRICE = re.compile(r"₹\s?[\d,]+|\$\s?[\d,]+")
_STOCK = re.compile(r"\b(in stock|available now|currently available)\b", re.I)
_STOCK_DENIAL = re.compile(r"\b(don't|do not|not|nahi|no)\b", re.I)
_DELIVERY = re.compile(
    r"\b(arrive|arriving|delivered|delivery) (tomorrow|today|on \w+day)\b",
    re.I,
)
_DISCOUNT = re.compile(r"\b(\d+\s?% off|free forever|free shipping)\b", re.I)
_EMOJI = re.compile(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]")

_EMOJI_LIMIT = {"none": 0, "minimal": 1, "moderate": 3, "match_customer": 3}


@dataclass(frozen=True)
class GuardrailFlag:
    code: str
    severity: str


@dataclass
class GuardrailReport:
    blocked: bool = False
    flags: list[GuardrailFlag] = field(default_factory=list)
    reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "blocked": self.blocked,
            "flags": [{"code": item.code, "severity": item.severity} for item in self.flags],
        }


@dataclass(frozen=True)
class GuardrailResult:
    status: str
    reason: str | None = None


def check_reply(reply: str, *, max_chars: int) -> GuardrailResult:
    """Phase 5 shape: blocked or passed. Soft brand flags are not a hard block."""
    report = evaluate_reply(reply, max_chars=max_chars)
    if report.blocked:
        return GuardrailResult("blocked", report.reason)
    return GuardrailResult("passed")


def evaluate_reply(
    reply: str,
    *,
    max_chars: int,
    forbidden_terms: list[str] | None = None,
    knowledge_text: str = "",
    emoji_policy: str = "minimal",
    personality: str = "friendly",
    customer_text: str = "",
) -> GuardrailReport:
    text = reply.strip()
    report = GuardrailReport()
    if not text:
        return GuardrailReport(blocked=True, reason="empty", flags=[GuardrailFlag("EMPTY", "high")])
    if len(text) > max_chars:
        return GuardrailReport(
            blocked=True, reason="too_long", flags=[GuardrailFlag("TOO_LONG", "high")]
        )
    if _SECRET.search(text):
        return _hard(report, "secret", "SECRET_DISCLOSURE")
    if _LEAK.search(text):
        return _hard(report, "prompt_leak", "SYSTEM_PROMPT_DISCLOSURE")
    if _PROMISE.search(text):
        return _hard(report, "unsupported_claim", "UNSUPPORTED_PROMISE")
    if _ABUSE.search(text):
        return _hard(report, "unsafe_content", "UNSAFE_CONTENT")

    for term in forbidden_terms or []:
        if term and _term_in(text, term):
            report.flags.append(GuardrailFlag("FORBIDDEN_TERM", "high"))
            break
    if _CERTAINTY.search(text) and not any(item.code == "FORBIDDEN_TERM" for item in report.flags):
        report.flags.append(GuardrailFlag("EXCESSIVE_CERTAINTY", "medium"))
    if knowledge_text is not None:
        _facts(text, knowledge_text, report)
    _emoji(text, emoji_policy, personality, customer_text, report)
    return report


def _hard(report: GuardrailReport, reason: str, code: str) -> GuardrailReport:
    report.blocked = True
    report.reason = reason
    report.flags.append(GuardrailFlag(code, "high"))
    return report


def _term_in(text: str, term: str) -> bool:
    pattern = rf"(?i)(?<!\w){re.escape(term.strip())}(?!\w)"
    return re.search(pattern, text) is not None


def _facts(text: str, knowledge: str, report: GuardrailReport) -> None:
    known = knowledge.lower()
    for amount in _PRICE.findall(text):
        digits = re.sub(r"\D", "", amount)
        if digits and digits not in re.sub(r"\D", "", knowledge):
            report.flags.append(GuardrailFlag("UNSUPPORTED_FACT", "high"))
            return
    if _STOCK.search(text) and not _STOCK_DENIAL.search(text) and "in stock" not in known:
        if "available" not in known:
            report.flags.append(GuardrailFlag("UNSUPPORTED_FACT", "high"))
            return
    if _DELIVERY.search(text) and not _DELIVERY.search(knowledge):
        report.flags.append(GuardrailFlag("UNSUPPORTED_FACT", "high"))
        return
    if _DISCOUNT.search(text) and not _DISCOUNT.search(knowledge):
        report.flags.append(GuardrailFlag("UNSUPPORTED_FACT", "high"))


def _emoji(
    text: str,
    policy: str,
    personality: str,
    customer_text: str,
    report: GuardrailReport,
) -> None:
    count = len(_EMOJI.findall(text))
    if personality in {"professional", "premium"}:
        limit = 0
    elif policy == "match_customer":
        customer_count = len(_EMOJI.findall(customer_text))
        limit = min(max(customer_count, 1), 3)
    else:
        limit = _EMOJI_LIMIT.get(policy, 1)
    if count > limit:
        report.flags.append(GuardrailFlag("EMOJI_POLICY", "medium"))
