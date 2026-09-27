"""Automation rules. Admin changes them. They never send Instagram messages."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, require_role
from app.core.errors import AppError
from app.models import OrganizationMember, Role
from app.models.automation import ActionType, AutomationRule, TriggerType
from app.services import automation as service

router = APIRouter(prefix="/api/automation/rules", tags=["automation"])

Viewer = Annotated[OrganizationMember, Depends(require_role(Role.VIEWER))]
Admin = Annotated[OrganizationMember, Depends(require_role(Role.ADMIN))]

_TRIGGERS = {item.value for item in TriggerType}
_ACTIONS = {item.value for item in ActionType}
_CONDITION_KEYS = {"intent", "sentiment", "segment", "purchase_intent", "contains"}


class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    enabled: bool = True
    trigger_type: Literal[
        "message_received",
        "sentiment_changed",
        "intent_detected",
        "customer_created",
        "segment_changed",
    ]
    conditions: dict = Field(default_factory=dict)
    action_type: Literal["generate_draft", "create_task", "notify_agent"]


class RulePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None
    trigger_type: (
        Literal[
            "message_received",
            "sentiment_changed",
            "intent_detected",
            "customer_created",
            "segment_changed",
        ]
        | None
    ) = None
    conditions: dict | None = None
    action_type: Literal["generate_draft", "create_task", "notify_agent"] | None = None


class RuleOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    enabled: bool
    trigger_type: str
    conditions: dict
    action_type: str
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class RuleList(BaseModel):
    items: list[RuleOut]


def _conditions(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise AppError("INVALID_RULE", "Conditions must be an object.", 422)
    cleaned: dict[str, str] = {}
    for key, value in raw.items():
        if key not in _CONDITION_KEYS:
            raise AppError("INVALID_RULE", "That condition is not supported.", 422)
        if not isinstance(value, str):
            raise AppError("INVALID_RULE", "Condition values must be text.", 422)
        text = " ".join(value.replace("\x00", "").split())
        limit = 200 if key == "contains" else 64
        if not text or len(text) > limit:
            raise AppError("INVALID_RULE", "Check the condition text length.", 422)
        cleaned[key] = text
    return cleaned


def _out(rule: AutomationRule) -> RuleOut:
    return RuleOut(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        enabled=rule.enabled,
        trigger_type=rule.trigger_type.value,
        conditions=dict(rule.conditions or {}),
        action_type=rule.action_type.value,
        created_by=rule.created_by,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.get("")
async def list_rules(membership: Viewer, session: SessionDep) -> RuleList:
    rows = await service.list_rules(session, membership.organization_id)
    return RuleList(items=[_out(row) for row in rows])


@router.post("", status_code=201)
async def create_rule(body: RuleIn, membership: Admin, session: SessionDep) -> RuleOut:
    rule = AutomationRule(
        organization_id=membership.organization_id,
        name=body.name.strip(),
        description=body.description.strip(),
        enabled=body.enabled,
        trigger_type=TriggerType(body.trigger_type),
        conditions=_conditions(body.conditions),
        action_type=ActionType(body.action_type),
        created_by=membership.user_id,
    )
    if body.trigger_type not in _TRIGGERS or body.action_type not in _ACTIONS:
        raise AppError("INVALID_RULE", "Choose a supported trigger and action.", 422)
    saved = await service.save_rule(session, rule)
    return _out(saved)


@router.patch("/{rule_id}")
async def update_rule(
    rule_id: uuid.UUID, body: RulePatch, membership: Admin, session: SessionDep
) -> RuleOut:
    rule = await service.get_rule(session, membership.organization_id, rule_id)
    if body.name is not None:
        rule.name = body.name.strip()
    if body.description is not None:
        rule.description = body.description.strip()
    if body.enabled is not None:
        rule.enabled = body.enabled
    if body.trigger_type is not None:
        rule.trigger_type = TriggerType(body.trigger_type)
    if body.action_type is not None:
        rule.action_type = ActionType(body.action_type)
    if body.conditions is not None:
        rule.conditions = _conditions(body.conditions)
    saved = await service.save_rule(session, rule)
    return _out(saved)


@router.delete("/{rule_id}", status_code=204)
async def remove_rule(rule_id: uuid.UUID, membership: Admin, session: SessionDep) -> None:
    await service.delete_rule(session, membership.organization_id, rule_id)
