"""Official Google Gen AI SDK (`google-genai`). Imported only when this provider is built."""

import logging
from typing import Any

from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from app.ai.errors import ai_provider_failed, ai_timeout
from app.ai.schemas import ReplyModelOutput, Usage
from app.core.config import Settings

logger = logging.getLogger("socialpilot.ai")

_RETRYABLE = {408, 429, 500, 502, 503, 504}


class GeminiProvider:
    def __init__(self, settings: Settings) -> None:
        from google import genai
        from google.genai import types

        assert settings.gemini_api_key is not None
        self.name = "gemini"
        self.model = settings.gemini_model
        self._timeout = settings.ai_timeout_seconds
        self._retries = settings.ai_max_retries
        self._temperature = settings.ai_temperature
        self._max_tokens = settings.ai_max_output_tokens
        self._types = types
        self._client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())

    async def generate_structured(
        self, prompt: str, schema: type[BaseModel]
    ) -> tuple[BaseModel, Usage]:
        text, usage = await self._generate(prompt, schema)
        try:
            return schema.model_validate_json(text), usage
        except ValidationError as exc:
            logger.warning("ai_provider_error", extra={"fields": {"reason": "invalid_json"}})
            raise ai_provider_failed() from exc

    async def generate_reply(self, prompt: str) -> tuple[str, float, Usage]:
        parsed, usage = await self.generate_structured(prompt, ReplyModelOutput)
        assert isinstance(parsed, ReplyModelOutput)
        return parsed.reply, parsed.confidence, usage

    async def _generate(self, prompt: str, schema: type[BaseModel]) -> tuple[str, Usage]:
        import asyncio

        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                response = await asyncio.wait_for(
                    run_in_threadpool(self._call, prompt, schema),
                    timeout=self._timeout,
                )
                raw = response.text or ""
                return raw, _usage(response)
            except TimeoutError as exc:
                last_error = exc
            except Exception as exc:
                status = _status(exc)
                if status not in _RETRYABLE:
                    logger.warning(
                        "ai_provider_error",
                        extra={"fields": {"status": status, "error": type(exc).__name__}},
                    )
                    raise ai_provider_failed() from exc
                last_error = exc
            if attempt >= self._retries:
                break
        if isinstance(last_error, TimeoutError):
            logger.warning("ai_provider_error", extra={"fields": {"reason": "timeout"}})
            raise ai_timeout() from last_error
        logger.warning("ai_provider_error", extra={"fields": {"reason": "retry_exhausted"}})
        raise ai_provider_failed() from last_error

    def _call(self, prompt: str, schema: type[BaseModel]) -> Any:
        config = self._types.GenerateContentConfig(
            temperature=self._temperature,
            max_output_tokens=self._max_tokens,
            response_mime_type="application/json",
            response_schema=schema,
        )
        return self._client.models.generate_content(
            model=self.model, contents=prompt, config=config
        )


def _usage(response: Any) -> Usage:
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return Usage()
    return Usage(
        input_tokens=getattr(meta, "prompt_token_count", None),
        output_tokens=getattr(meta, "candidates_token_count", None),
    )


def _status(exc: Exception) -> int | None:
    for attr in ("code", "status_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None
