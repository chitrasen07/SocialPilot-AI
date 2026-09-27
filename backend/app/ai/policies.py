"""Brand and reply policy text. Customer and document text are not instructions."""

from app.services.ai_data import EffectiveAISettings

_PERSONALITY = {
    "professional": "Calm, precise, and respectful. Avoid slang, nicknames, and emojis.",
    "friendly": "Warm and approachable. Use plain language. A light tone is fine.",
    "casual": "Relaxed and conversational. Keep sentences short and stay respectful.",
    "premium": "Polished and understated. No slang, no hype, and no emojis.",
    "playful": "Light and upbeat. Stay appropriate. Do not overdo jokes or emojis.",
    "custom": "Follow the brand voice and custom instructions. Safety rules still win.",
}

_LENGTH = {
    "short": "Aim for 1-2 sentences.",
    "medium": "Aim for 2-4 sentences.",
    "long": "Aim for 4-7 sentences.",
}

_EMOJI = {
    "none": "Do not use emojis.",
    "minimal": "Use at most one emoji, and only if it fits.",
    "moderate": "A few emojis are fine. Do not fill the reply with them.",
    "match_customer": "You may mirror a little of the customer's emoji use. Do not exceed it.",
}

_LANGUAGE = {
    "auto": "Reply in the customer's language.",
    "english": "Reply in English.",
    "hindi": "Reply in Hindi.",
    "hinglish": "Reply in Hinglish.",
    "telugu": "Reply in Telugu.",
}


def personality_text(name: str) -> str:
    return _PERSONALITY.get(name, _PERSONALITY["friendly"])


def policy_block(settings: EffectiveAISettings) -> str:
    preferred = ", ".join(settings.preferred_terms) or "(none)"
    forbidden = ", ".join(settings.forbidden_terms) or "(none)"
    lines = [
        f"personality={settings.personality}",
        f"language_mode={settings.language_mode}",
        f"emoji_policy={settings.emoji_policy}",
        f"response_length={settings.response_length}",
        _LENGTH.get(settings.response_length, _LENGTH["medium"]),
        _EMOJI.get(settings.emoji_policy, _EMOJI["minimal"]),
        _LANGUAGE.get(settings.language_mode, _LANGUAGE["auto"]),
        "Match formality only inside the brand personality.",
        "Do not copy insults, slurs, threats, or sexual content from the customer.",
        "Brand and safety rules override style matching.",
        "Do not invent prices, stock, discounts, shipping times, delivery dates, or refunds.",
        "If a fact is not in business knowledge, say you do not have verified information.",
        f"Prefer these words when they fit: {preferred}",
        f"Do not use these words: {forbidden}",
    ]
    return "\n".join(lines)


def decide_review(
    *,
    blocked: bool,
    flag_codes: list[str],
    risk_level: str,
    risk_codes: list[str],
    risk_reason: str | None,
    settings: EffectiveAISettings,
) -> tuple[str, bool, str | None]:
    """Returns status name, whether to escalate, and a short reason. Hard blocks stay rejected."""
    if blocked:
        return "rejected", risk_level == "high", risk_reason
    review = False
    if risk_level == "high" and settings.require_review_for_high_risk:
        review = True
    if "refund" in risk_codes and settings.require_review_for_refunds:
        review = True
    if "payment" in risk_codes and settings.require_review_for_payment_issues:
        review = True
    if "complaint" in risk_codes:
        review = True
    if "FORBIDDEN_TERM" in flag_codes or "EMOJI_POLICY" in flag_codes:
        review = True
    if "EXCESSIVE_CERTAINTY" in flag_codes or "UNSUPPORTED_FACT" in flag_codes:
        if settings.require_review_for_unsupported_claims:
            review = True
    reason = risk_reason
    if review and reason is None and "UNSUPPORTED_FACT" in flag_codes:
        reason = "missing business information"
    if review and reason is None and "FORBIDDEN_TERM" in flag_codes:
        reason = "forbidden vocabulary"
    escalate = review and risk_level != "low"
    status = "review_required" if review else "generated"
    return status, escalate, reason if review else None
