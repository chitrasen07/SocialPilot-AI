"""Organization automation rules, human tasks, and in-app notifications.

Actions prepare drafts or work for people. They do not send Instagram messages.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, string_enum


class TriggerType(enum.StrEnum):
    MESSAGE = "message_received"
    SENTIMENT = "sentiment_changed"
    INTENT = "intent_detected"
    CUSTOMER = "customer_created"
    SEGMENT = "segment_changed"


class ActionType(enum.StrEnum):
    DRAFT = "generate_draft"
    TASK = "create_task"
    NOTIFY = "notify_agent"


class TaskStatus(enum.StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskPriority(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class NotificationType(enum.StrEnum):
    TASK = "task"
    DRAFT = "draft"
    REVIEW = "review"
    INTENT = "intent"


class AutomationRule(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "automation_rules"
    __table_args__ = (Index("ix_automation_rules_organization_id", "organization_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    trigger_type: Mapped[TriggerType] = mapped_column(
        string_enum(TriggerType, "automation_trigger", 24)
    )
    conditions: Mapped[dict] = mapped_column(JSONB, default=dict)
    action_type: Mapped[ActionType] = mapped_column(
        string_enum(ActionType, "automation_action", 24)
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class Task(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            ondelete="CASCADE",
            name="fk_tasks_customer_org",
        ),
        Index("ix_tasks_organization_id_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    customer_id: Mapped[uuid.UUID | None]
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[TaskStatus] = mapped_column(
        string_enum(TaskStatus, "task_status"), default=TaskStatus.OPEN
    )
    priority: Mapped[TaskPriority] = mapped_column(
        string_enum(TaskPriority, "task_priority"), default=TaskPriority.MEDIUM
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_organization_id_user_id", "organization_id", "user_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[NotificationType] = mapped_column(
        string_enum(NotificationType, "notification_type")
    )
    title: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text, default="")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
