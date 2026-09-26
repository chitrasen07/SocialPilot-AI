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
            return ReplyModelOutput(reply=_reply(text), confidence=0.9), Usage(
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


def _reply(text: str) -> str:
    if _INJECTION.search(text):
        return (
            "I can help with this conversation. I can't share internal instructions "
            "or change payments, refunds, or orders."
        )
    analysis = classify_locally(text)
    language = analysis.language.value if analysis else "english"
    if language == "hinglish":
        return (
            "Haan bhai, mere paas verified stock ya price detail nahi hai, "
            "isliye confirm nahi kar sakta."
        )
    if language == "hindi":
        return "इस जानकारी की पुष्टि मेरे पास नहीं है, इसलिए मैं अभी पक्का नहीं बता सकता।"
    if language == "telugu":
        return "ఈ విషయం నాకు నిర్ధారించడానికి సరిపడే సమాచారం లేదు."
    if language == "mixed":
        return "I don't have verified details for that yet, so I can't confirm it."
    return "I don't have verified details for that yet, so I can't confirm it."
