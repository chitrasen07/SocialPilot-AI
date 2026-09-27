"""Deterministic draft scores. This does not call a model and does not rewrite the reply."""

import re
from dataclasses import dataclass

_EMOJI = re.compile(r"[\U0001F300-\U0001FAFF]")
_WORD = re.compile(r"[A-Za-z]{4,}")
_BUYING = re.compile(r"\b(price|pricing|buy|purchase|available|order)\b", re.I)
_NEXT = re.compile(r"\b(price|available|order|help|review|team)\b", re.I)


@dataclass(frozen=True)
class OptimizedReply:
    text: str
    clarity_score: int
    helpfulness_score: int
    brand_score: int
    conversion_score: int


def optimize_reply(
    *,
    message: str,
    reply: str,
    personality: str,
    history: list[str],
    knowledge: str,
    emoji_policy: str,
) -> OptimizedReply:
    del history
    text = reply.strip()
    return OptimizedReply(
        text=text,
        clarity_score=_clarity(text),
        helpfulness_score=_helpfulness(message, text, knowledge),
        brand_score=_brand(text, personality, emoji_policy),
        conversion_score=_conversion(message, text),
    )


def _clamp(value: int) -> int:
    return max(0, min(100, value))


def _clarity(text: str) -> int:
    words = text.split()
    if not words:
        return 0
    if len(words) < 4:
        return 45
    if len(words) > 120:
        return 55
    return 90


def _helpfulness(message: str, reply: str, knowledge: str) -> int:
    asked = {word.lower() for word in _WORD.findall(message)}
    if not asked:
        return 70
    answered = {word.lower() for word in _WORD.findall(reply)}
    overlap = len(asked & answered) / len(asked)
    knowledge_words = {word.lower() for word in _WORD.findall(knowledge)}
    grounded = 10 if knowledge_words & answered else 0
    return _clamp(int(40 + overlap * 50) + grounded)


def _brand(reply: str, personality: str, emoji_policy: str) -> int:
    has_emoji = _EMOJI.search(reply) is not None
    if emoji_policy == "none" and has_emoji:
        return 35
    if personality == "professional" and has_emoji:
        return 60
    if emoji_policy == "none":
        return 90
    return 80


def _conversion(message: str, reply: str) -> int:
    buying = _BUYING.search(message) is not None
    answers = _NEXT.search(reply) is not None
    if buying and answers:
        return 85
    if buying:
        return 55
    return 60
