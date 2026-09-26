from typing import Literal

from pydantic import BaseModel, Field

Language = Literal["english", "hindi", "hinglish", "telugu", "mixed", "unknown"]
Intent = Literal[
    "product_question",
    "pricing_question",
    "availability_question",
    "purchase_question",
    "order_status",
    "shipping_question",
    "refund_request",
    "complaint",
    "support_request",
    "greeting",
    "general_question",
    "feedback",
    "spam",
    "unknown",
]
Sentiment = Literal["positive", "neutral", "negative", "mixed", "unknown"]
Emotion = Literal[
    "joy",
    "interest",
    "frustration",
    "anger",
    "confusion",
    "urgency",
    "disappointment",
    "neutral",
    "unknown",
]
PurchaseIntent = Literal["high", "medium", "low", "none", "unknown"]


class Signal(BaseModel):
    value: str
    confidence: float = Field(ge=0, le=1)


class MessageAnalysis(BaseModel):
    language: Signal
    intent: Signal
    sentiment: Signal
    emotion: Signal
    purchase_intent: Signal


class ReplyModelOutput(BaseModel):
    reply: str
    confidence: float = Field(ge=0, le=1)


class Usage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
