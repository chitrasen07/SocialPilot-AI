"""Matches organization rules to customer events and runs the chosen action.

Generating a draft uses the existing AI orchestrator. No action sends a message.
"""

import logging
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import build_ai
from app.ai.orchestrator import AIOrchestrator
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import OrganizationMember, Role
from app.models.automation import (
    ActionType,
    AutomationRule,
    Notification,
    NotificationType,
    Task,
    TaskPriority,
    TaskStatus,
    TriggerType,
)
from app.services import ai_data

logger = logging.getLogger("socialpilot.automation")

_RUNNING: ContextVar[bool] = ContextVar("automation_running", default=False)
_MESSAGE_TRIGGERS = (
    TriggerType.MESSAGE,
    TriggerType.INTENT,
    TriggerType.SENTIMENT,
    TriggerType.SEGMENT,
)
_ANALYSIS_KEYS = {"intent", "sentiment", "purchase_intent"}


@dataclass
class AutomationEvent:
    organization_id: uuid.UUID
    trigger: TriggerType
    customer_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    text: str | None = None
    intent: str | None = None
    sentiment: str | None = None
    purchase_intent: str | None = None
    segment: str | None = None
    segments: list[str] = field(default_factory=list)


@dataclass
class ActionResult:
    rule_id: uuid.UUID
    action: str
    task_id: uuid.UUID | None = None
    draft_id: uuid.UUID | None = None


def match_conditions(conditions: dict | None, facts: dict) -> bool:
    """Every stored condition must match. An empty object matches the trigger itself."""
    if not conditions:
        return True
    for key, expected in conditions.items():
        if expected is None or expected == "":
            continue
        if key == "contains":
            if str(expected).lower() not in (facts.get("text") or "").lower():
                return False
            continue
        if key == "segment" and facts.get("segments"):
            if str(expected) not in {str(item) for item in facts["segments"]}:
                return False
            continue
        if str(facts.get(key) or "") != str(expected):
            return False
    return True


async def evaluate_event(session: AsyncSession, event: AutomationEvent) -> list[ActionResult]:
    if _RUNNING.get():
        return []
    rules = await _enabled(session, event.organization_id, (event.trigger,))
    if not rules:
        return []
    event = await _enrich(session, event, rules)
    results: list[ActionResult] = []
    for rule in rules:
        if match_conditions(rule.conditions, _facts(event)):
            results.append(await execute_action(session, rule, event))
    return results


async def execute_action(
    session: AsyncSession, rule: AutomationRule, event: AutomationEvent
) -> ActionResult:
    if rule.action_type == ActionType.DRAFT:
        draft_id = await _generate_draft(session, event)
        if draft_id is not None:
            await _notify(
                session,
                event,
                NotificationType.DRAFT,
                f"Draft ready: {rule.name}",
                "An AI draft is waiting for review. It has not been sent.",
            )
        return ActionResult(rule.id, rule.action_type.value, draft_id=draft_id)
    if rule.action_type == ActionType.TASK:
        task = await _create_task(session, rule, event)
        await _notify(
            session,
            event,
            NotificationType.TASK,
            rule.name,
            task.description or "A follow-up task is open.",
        )
        return ActionResult(rule.id, rule.action_type.value, task_id=task.id)
    await _notify(
        session,
        event,
        NotificationType.REVIEW,
        rule.name,
        rule.description or "A teammate should look at this conversation.",
    )
    return ActionResult(rule.id, rule.action_type.value)


async def on_customer_created(
    session: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> None:
    try:
        await evaluate_event(
            session,
            AutomationEvent(
                organization_id=organization_id,
                trigger=TriggerType.CUSTOMER,
                customer_id=customer_id,
            ),
        )
    except Exception:
        logger.exception("automation_customer_failed")


async def on_customer_message(
    session: AsyncSession,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    text: str | None,
) -> None:
    try:
        rules = await _enabled(session, organization_id, _MESSAGE_TRIGGERS)
        if not rules:
            return
        event = AutomationEvent(
            organization_id=organization_id,
            trigger=TriggerType.MESSAGE,
            customer_id=customer_id,
            conversation_id=conversation_id,
            message_id=message_id,
            text=text,
        )
        if _needs_analysis(rules):
            event = await _enrich(session, event, rules)
        for rule in rules:
            if rule.trigger_type == TriggerType.SEGMENT:
                continue
            scoped = _for_trigger(event, rule.trigger_type)
            if match_conditions(rule.conditions, _facts(scoped)):
                await execute_action(session, rule, scoped)
    except Exception:
        logger.exception("automation_message_failed")


async def on_segments_changed(
    session: AsyncSession,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    segments: list[str],
) -> None:
    if not segments or _RUNNING.get():
        return
    try:
        await evaluate_event(
            session,
            AutomationEvent(
                organization_id=organization_id,
                trigger=TriggerType.SEGMENT,
                customer_id=customer_id,
                segment=segments[0],
                segments=segments,
            ),
        )
    except Exception:
        logger.exception("automation_segment_failed")


def _facts(event: AutomationEvent) -> dict:
    return {
        "intent": event.intent,
        "sentiment": event.sentiment,
        "purchase_intent": event.purchase_intent,
        "segment": event.segment,
        "segments": event.segments,
        "text": event.text or "",
    }


def _for_trigger(event: AutomationEvent, trigger: TriggerType) -> AutomationEvent:
    return AutomationEvent(
        organization_id=event.organization_id,
        trigger=trigger,
        customer_id=event.customer_id,
        conversation_id=event.conversation_id,
        message_id=event.message_id,
        text=event.text,
        intent=event.intent,
        sentiment=event.sentiment,
        purchase_intent=event.purchase_intent,
        segment=event.segment,
        segments=event.segments,
    )


def _needs_analysis(rules: list[AutomationRule]) -> bool:
    for rule in rules:
        if rule.trigger_type in {TriggerType.INTENT, TriggerType.SENTIMENT, TriggerType.SEGMENT}:
            return True
        if _ANALYSIS_KEYS & set(rule.conditions or {}):
            return True
    return False


async def _enabled(
    session: AsyncSession, organization_id: uuid.UUID, triggers: tuple[TriggerType, ...]
) -> list[AutomationRule]:
    return list(
        await session.scalars(
            select(AutomationRule).where(
                AutomationRule.organization_id == organization_id,
                AutomationRule.enabled.is_(True),
                AutomationRule.trigger_type.in_(triggers),
            )
        )
    )


async def _enrich(
    session: AsyncSession, event: AutomationEvent, rules: list[AutomationRule]
) -> AutomationEvent:
    if event.message_id is None or event.intent is not None or not _needs_analysis(rules):
        return event
    orchestrator = _orchestrator()
    if orchestrator is None:
        logger.info("automation_ai_unavailable")
        return event
    row = await orchestrator.analyze(session, event.organization_id, event.message_id)
    return AutomationEvent(
        organization_id=event.organization_id,
        trigger=event.trigger,
        customer_id=event.customer_id,
        conversation_id=event.conversation_id,
        message_id=event.message_id,
        text=event.text,
        intent=row.intent,
        sentiment=row.sentiment,
        purchase_intent=row.purchase_intent,
        segment=event.segment,
        segments=event.segments,
    )


async def _generate_draft(session: AsyncSession, event: AutomationEvent) -> uuid.UUID | None:
    if event.message_id is None:
        return None
    existing = await ai_data.latest_draft(session, event.organization_id, event.message_id)
    if existing is not None:
        return existing.id
    orchestrator = _orchestrator()
    if orchestrator is None:
        logger.info("automation_ai_unavailable")
        return None
    token = _RUNNING.set(True)
    try:
        draft = await orchestrator.generate_reply(session, event.organization_id, event.message_id)
    except AppError:
        logger.info("automation_draft_skipped")
        return None
    finally:
        _RUNNING.reset(token)
    return draft.id


async def _create_task(session: AsyncSession, rule: AutomationRule, event: AutomationEvent) -> Task:
    title = rule.name.strip() or "Follow up"
    existing = await session.scalar(
        select(Task).where(
            Task.organization_id == event.organization_id,
            Task.customer_id == event.customer_id,
            Task.title == title,
            Task.status.in_((TaskStatus.OPEN, TaskStatus.IN_PROGRESS)),
        )
    )
    if existing is not None:
        return existing
    priority = TaskPriority.MEDIUM
    if event.sentiment == "negative" or event.segment == "high_intent_buyer":
        priority = TaskPriority.HIGH
    task = Task(
        organization_id=event.organization_id,
        customer_id=event.customer_id,
        conversation_id=event.conversation_id,
        title=title,
        description=rule.description or "",
        status=TaskStatus.OPEN,
        priority=priority,
    )
    session.add(task)
    await session.commit()
    return task


async def _notify(
    session: AsyncSession,
    event: AutomationEvent,
    kind: NotificationType,
    title: str,
    message: str,
) -> None:
    members = list(
        await session.scalars(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == event.organization_id,
                OrganizationMember.role.in_((Role.AGENT, Role.ADMIN, Role.OWNER)),
            )
        )
    )
    for member in members:
        already = await session.scalar(
            select(Notification.id).where(
                Notification.organization_id == event.organization_id,
                Notification.user_id == member.user_id,
                Notification.title == title,
                Notification.read.is_(False),
            )
        )
        if already is not None:
            continue
        session.add(
            Notification(
                organization_id=event.organization_id,
                user_id=member.user_id,
                type=kind,
                title=title,
                message=message,
                read=False,
            )
        )
    await session.commit()


async def list_rules(session: AsyncSession, organization_id: uuid.UUID) -> list[AutomationRule]:
    return list(
        await session.scalars(
            select(AutomationRule)
            .where(AutomationRule.organization_id == organization_id)
            .order_by(AutomationRule.created_at.desc())
        )
    )


async def get_rule(
    session: AsyncSession, organization_id: uuid.UUID, rule_id: uuid.UUID
) -> AutomationRule:
    rule = await session.scalar(
        select(AutomationRule).where(
            AutomationRule.id == rule_id,
            AutomationRule.organization_id == organization_id,
        )
    )
    if rule is None:
        raise AppError("RULE_NOT_FOUND", "Automation rule not found.", 404)
    return rule


async def save_rule(session: AsyncSession, rule: AutomationRule) -> AutomationRule:
    session.add(rule)
    await session.commit()
    return rule


async def delete_rule(
    session: AsyncSession, organization_id: uuid.UUID, rule_id: uuid.UUID
) -> None:
    rule = await get_rule(session, organization_id, rule_id)
    await session.delete(rule)
    await session.commit()


async def list_tasks(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    status: TaskStatus | None,
    priority: TaskPriority | None,
    assigned_to: uuid.UUID | None,
    limit: int,
) -> list[Task]:
    stmt = select(Task).where(Task.organization_id == organization_id)
    if status is not None:
        stmt = stmt.where(Task.status == status)
    if priority is not None:
        stmt = stmt.where(Task.priority == priority)
    if assigned_to is not None:
        stmt = stmt.where(Task.assigned_to == assigned_to)
    return list(await session.scalars(stmt.order_by(Task.created_at.desc()).limit(limit)))


async def get_task(session: AsyncSession, organization_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    task = await session.scalar(
        select(Task).where(Task.id == task_id, Task.organization_id == organization_id)
    )
    if task is None:
        raise AppError("TASK_NOT_FOUND", "Task not found.", 404)
    return task


async def save_task(session: AsyncSession, task: Task) -> Task:
    session.add(task)
    await session.commit()
    return task


async def list_notifications(
    session: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[list[Notification], int]:
    rows = list(
        await session.scalars(
            select(Notification)
            .where(
                Notification.organization_id == organization_id,
                Notification.user_id == user_id,
            )
            .order_by(Notification.created_at.desc())
            .limit(30)
        )
    )
    unread_ids = list(
        await session.scalars(
            select(Notification.id).where(
                Notification.organization_id == organization_id,
                Notification.user_id == user_id,
                Notification.read.is_(False),
            )
        )
    )
    return rows, len(unread_ids)


async def mark_read(
    session: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    notification_id: uuid.UUID,
) -> Notification:
    row = await session.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.organization_id == organization_id,
            Notification.user_id == user_id,
        )
    )
    if row is None:
        raise AppError("NOTIFICATION_NOT_FOUND", "Notification not found.", 404)
    row.read = True
    await session.commit()
    return row


def _orchestrator() -> AIOrchestrator | None:
    settings = get_settings()
    built = build_ai(settings)
    if built is None:
        return None
    provider, embeddings = built
    return AIOrchestrator(provider, embeddings, settings)
