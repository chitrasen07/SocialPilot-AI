import logging
import time
import uuid

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.classifier import classify_locally
from app.ai.context import build_context
from app.ai.embeddings import EmbeddingProvider
from app.ai.errors import ai_disabled, ai_guardrail_blocked, ai_not_configured, ai_provider_failed
from app.ai.guardrails import evaluate_reply
from app.ai.policies import decide_review
from app.ai.prompts import analysis_prompt, reply_prompt
from app.ai.providers.base import AIProvider
from app.ai.risk import assess_risk
from app.ai.schemas import MessageAnalysis, Usage
from app.core.config import Settings
from app.knowledge.citations import format_knowledge
from app.models import AIReplyDraft, DraftStatus, GuardrailStatus, MessageAIAnalysis
from app.services import ai_data
from app.services.customer_intelligence import refresh_for_prompt

logger = logging.getLogger("socialpilot.ai")

_RULES = "rules"


class AIOrchestrator:
    def __init__(
        self,
        provider: AIProvider | None,
        embeddings: EmbeddingProvider | None,
        settings: Settings,
    ) -> None:
        self._provider = provider
        self._embeddings = embeddings
        self._settings = settings

    async def analyze(
        self, session: AsyncSession, organization_id: uuid.UUID, message_id: uuid.UUID
    ) -> MessageAIAnalysis:
        await self._require_enabled(session, organization_id)
        message = await ai_data.get_message(session, organization_id, message_id)
        existing = await ai_data.get_analysis(session, organization_id, message.id)
        if existing is not None:
            await refresh_for_prompt(session, organization_id, message, _from_row(existing))
            return existing

        logger.info(
            "ai_analysis_started",
            extra={
                "fields": {"organization_id": str(organization_id), "message_id": str(message.id)}
            },
        )
        started = time.perf_counter()
        text = message.content or ""
        local = classify_locally(text)
        if local is not None:
            analysis, usage, provider, model = (
                local,
                Usage(input_tokens=0, output_tokens=0),
                _RULES,
                "local-rules",
            )
        else:
            provider_impl = self._require_provider()
            try:
                parsed, usage = await provider_impl.generate_structured(
                    analysis_prompt(text), MessageAnalysis
                )
            except ValidationError as exc:
                raise ai_provider_failed() from exc
            if not isinstance(parsed, MessageAnalysis):
                raise ai_provider_failed()
            analysis, provider, model = parsed, provider_impl.name, provider_impl.model
        latency_ms = int((time.perf_counter() - started) * 1000)
        stored = await ai_data.save_analysis(
            session,
            organization_id=organization_id,
            message_id=message.id,
            analysis=analysis,
            provider=provider,
            model=model,
            usage=usage,
            latency_ms=latency_ms,
        )
        logger.info(
            "ai_analysis_completed",
            extra={
                "fields": {
                    "organization_id": str(organization_id),
                    "message_id": str(message.id),
                    "provider": provider,
                    "model": model,
                    "latency_ms": latency_ms,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                }
            },
        )
        await refresh_for_prompt(session, organization_id, message, analysis)
        return stored

    async def generate_reply(
        self, session: AsyncSession, organization_id: uuid.UUID, message_id: uuid.UUID
    ) -> AIReplyDraft:
        config = await self._require_enabled(session, organization_id)
        analysis_row = await self.analyze(session, organization_id, message_id)
        message = await ai_data.get_message(session, organization_id, message_id)
        analysis = _from_row(analysis_row)
        intelligence = await refresh_for_prompt(session, organization_id, message, analysis)
        embeddings = self._require_embeddings()
        use_knowledge = config.knowledge_enabled and config.knowledge_top_k > 0
        context = await build_context(
            session,
            message,
            analysis,
            embeddings,
            max_messages=config.max_context_messages,
            memory_top_k=config.memory_top_k,
            knowledge_top_k=config.knowledge_top_k if use_knowledge else 0,
            knowledge_max_distance=config.knowledge_max_distance,
        )
        sources = [hit.source().model_dump(mode="json") for hit in context.knowledge]
        knowledge_text = format_knowledge(context.knowledge)
        provider = self._require_provider()
        max_chars = max(200, min(config.max_output_tokens * 4, 4000))
        started = time.perf_counter()
        reply, _confidence, usage = await provider.generate_reply(
            reply_prompt(
                message=message.content or "",
                analysis=analysis,
                history=context.history,
                memories=context.memories,
                knowledge=knowledge_text,
                max_chars=max_chars,
                settings=config,
                intelligence=intelligence,
            )
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        report = evaluate_reply(
            reply,
            max_chars=max_chars,
            forbidden_terms=config.forbidden_terms,
            knowledge_text=knowledge_text,
            emoji_policy=config.emoji_policy,
            personality=config.personality,
            customer_text=message.content or "",
        )
        risk = assess_risk(
            message.content or "",
            emotion=analysis.emotion.value,
            sentiment=analysis.sentiment.value,
        )
        status_name, escalate, reason = decide_review(
            blocked=report.blocked,
            flag_codes=[item.code for item in report.flags],
            risk_level=risk.level,
            risk_codes=risk.codes,
            risk_reason=risk.reason,
            settings=config,
        )
        results = report.as_dict() | {"reason_codes": risk.codes}
        if report.blocked:
            await ai_data.save_draft(
                session,
                message=message,
                reply_text=None,
                provider=provider.name,
                model=provider.model,
                status=DraftStatus.REJECTED,
                guardrail_status=GuardrailStatus.BLOCKED,
                usage=usage,
                latency_ms=latency_ms,
                sources=sources,
                risk_level=risk.level,
                escalation_required=escalate,
                escalation_reason=reason,
                guardrail_results=results,
            )
            logger.info(
                "ai_guardrail_blocked",
                extra={
                    "fields": {
                        "organization_id": str(organization_id),
                        "message_id": str(message.id),
                        "reason": report.reason,
                    }
                },
            )
            raise ai_guardrail_blocked()

        from app.intelligence.optimizer import optimize_reply
        from app.services.intelligence_engine import store_response_score

        optimized = optimize_reply(
            message=message.content or "",
            reply=reply,
            personality=config.personality,
            history=context.history,
            knowledge=knowledge_text,
            emoji_policy=config.emoji_policy,
        )
        draft = await ai_data.save_draft(
            session,
            message=message,
            reply_text=optimized.text,
            provider=provider.name,
            model=provider.model,
            status=DraftStatus(status_name),
            guardrail_status=GuardrailStatus.PASSED,
            usage=usage,
            latency_ms=latency_ms,
            sources=sources,
            risk_level=risk.level,
            escalation_required=escalate,
            escalation_reason=reason,
            guardrail_results=results,
        )
        await store_response_score(session, draft, optimized)
        logger.info(
            "ai_reply_generated",
            extra={
                "fields": {
                    "organization_id": str(organization_id),
                    "message_id": str(message.id),
                    "provider": provider.name,
                    "model": provider.model,
                    "latency_ms": latency_ms,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                }
            },
        )
        return draft

    async def _require_enabled(self, session: AsyncSession, organization_id: uuid.UUID):
        if self._provider is None or self._embeddings is None:
            raise ai_not_configured()
        config = await ai_data.effective_settings(session, organization_id, self._settings)
        if not config.enabled:
            raise ai_disabled()
        return config

    def _require_provider(self) -> AIProvider:
        if self._provider is None:
            raise ai_not_configured()
        return self._provider

    def _require_embeddings(self) -> EmbeddingProvider:
        if self._embeddings is None:
            raise ai_not_configured()
        return self._embeddings


def _from_row(row: MessageAIAnalysis) -> MessageAnalysis:
    from app.ai.schemas import Signal

    return MessageAnalysis(
        language=Signal(value=row.language, confidence=row.language_confidence),
        intent=Signal(value=row.intent, confidence=row.intent_confidence),
        sentiment=Signal(value=row.sentiment, confidence=row.sentiment_confidence),
        emotion=Signal(value=row.emotion, confidence=row.emotion_confidence),
        purchase_intent=Signal(
            value=row.purchase_intent, confidence=row.purchase_intent_confidence
        ),
    )
