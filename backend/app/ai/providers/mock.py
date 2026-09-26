"""Deterministic stand-in. It never calls a network and never invents completed actions."""

import re

from pydantic import BaseModel

from app.ai.classifier import classify_locally
from app.ai.schemas import MessageAnalysis, ReplyModelOutput, Signal, Usage

_INJECTION = re.compile(
    r"ignore previous|system prompt|api key|hidden instructions|you are now an admin",
    re.I,
)


class MockAIProvider:
    name = "mock"
    model = "mock"

    def __init__(self) -> None:
        self.calls = 0

    async def generate_structured(
        self, prompt: str, schema: type[BaseModel]
    ) -> tuple[BaseModel, Usage]:
        self.calls += 1
        text = _between(prompt)
        if schema is MessageAnalysis:
            analysis = classify_locally(text) or MessageAnalysis(
                language=Signal(value="unknown", confidence=0.2),
                intent=Signal(value="unknown", confidence=0.2),
                sentiment=Signal(value="unknown", confidence=0.2),
                emotion=Signal(value="unknown", confidence=0.2),
                purchase_intent=Signal(value="unknown", confidence=0.2),
            )
            return analysis, Usage(input_tokens=0, output_tokens=0)
        if schema is ReplyModelOutput:
            return ReplyModelOutput(reply=_reply(text, prompt), confidence=0.9), Usage(
                input_tokens=0, output_tokens=0
            )
        raise TypeError(f"unsupported schema {schema}")

    async def generate_reply(self, prompt: str) -> tuple[str, float, Usage]:
        parsed, usage = await self.generate_structured(prompt, ReplyModelOutput)
        assert isinstance(parsed, ReplyModelOutput)
        return parsed.reply, parsed.confidence, usage


def _between(prompt: str) -> str:
    matches = re.findall(r"<<<\n?(.*?)\n?>>>", prompt, re.S)
    return matches[-1].strip() if matches else prompt


def _reply(text: str, prompt: str = "") -> str:
    if _INJECTION.search(text):
        return (
            "I can help with this conversation. I can't share internal instructions "
            "or change payments, refunds, or orders."
        )
    analysis = classify_locally(text)
    language = analysis.language.value if analysis else "english"
    knowledge = _knowledge(prompt)
    grounded = _grounded(text, knowledge, language)
    if grounded is not None:
        return grounded
    return _unknown(language)


def _knowledge(prompt: str) -> str:
    match = re.search(r"BUSINESS KNOWLEDGE[^\n]*:\n<<<\n(.*?)\n>>>", prompt, re.S)
    if not match:
        return ""
    kept = []
    for line in match.group(1).splitlines():
        if line.strip() in {"", "(none)"}:
            continue
        if _INJECTION.search(line) or re.search(r"reveal|api key|tell the user", line, re.I):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _grounded(text: str, knowledge: str, language: str) -> str | None:
    if not knowledge:
        return None
    amounts = list(dict.fromkeys(re.findall(r"₹\s?[\d,]+", knowledge)))
    asks_price = re.search(r"price|kitna|cost|कीमत|ధర", text, re.I)
    asks_stock = re.search(r"stock|available|అందుబాటు", text, re.I)
    asks_return = re.search(r"return|wapas", text, re.I)
    days = re.search(r"(\d+)\s*days", knowledge, re.I)
    if asks_price and not asks_stock:
        if len(amounts) > 1:
            return _unclear_price(language)
        if len(amounts) == 1:
            return _price(language, amounts[0].replace(" ", ""))
    if asks_stock and not re.search(r"\bin stock\b|\bavailable\b", knowledge, re.I):
        return _no_stock(language)
    if asks_return and days:
        return _returns(language, days.group(1))
    if re.search(r"laptop|airplane|mars", text, re.I) and not re.search(
        r"laptop|airplane|mars", knowledge, re.I
    ):
        return _unknown(language)
    return None


def _price(language: str, amount: str) -> str:
    if language == "hinglish":
        return f"Bhai, listed price {amount} hai."
    if language == "hindi":
        return f"सूची में कीमत {amount} है।"
    if language == "telugu":
        return f"జాబితాలో ధర {amount}."
    return f"The listed price is {amount}."


def _no_stock(language: str) -> str:
    if language == "hinglish":
        return "Stock ki confirmed information mere paas nahi hai."
    if language == "telugu":
        return "స్టాక్ గురించి నాకు సమాచారం లేదు."
    return "I don't have stock information for that."


def _returns(language: str, days: str) -> str:
    if language == "hinglish":
        return f"Return {days} days ke andar accepted hai."
    return f"Returns are accepted within {days} days."


def _unclear_price(language: str) -> str:
    if language == "hinglish":
        return "Documents mein alag prices hain, isliye confirm nahi kar sakta."
    return "The business documents list more than one price, so I can't confirm which applies."


def _unknown(language: str) -> str:
    if language == "hinglish":
        return (
            "Haan bhai, mere paas verified stock ya price detail nahi hai, "
            "isliye confirm nahi kar sakta."
        )
    if language == "hindi":
        return "इस जानकारी की पुष्टि मेरे पास नहीं है, इसलिए मैं अभी पक्का नहीं बता सकता।"
    if language == "telugu":
        return "ఈ విషయం నాకు నిర్ధారించడానికి సరిపడే సమాచారం లేదు."
    return "I don't have verified details for that yet, so I can't confirm it."
