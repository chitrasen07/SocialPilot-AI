"""customer intelligence, analytics, and feedback

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "customer_intelligence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("preferences", postgresql.JSONB(), nullable=False),
        sa.Column("interests", postgresql.JSONB(), nullable=False),
        sa.Column("frequent_products", postgresql.JSONB(), nullable=False),
        sa.Column("buying_intent", sa.String(16), nullable=False),
        sa.Column("communication_style", sa.String(32), nullable=False),
        sa.Column("language_preference", sa.String(16), nullable=False),
        sa.Column("previous_issues", postgresql.JSONB(), nullable=False),
        sa.Column("sentiment_trend", sa.String(16), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_customer_intelligence"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_customer_intelligence_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            name="fk_customer_intelligence_customer_org",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "organization_id", "customer_id", name="uq_customer_intelligence_org_customer"
        ),
    )
    op.create_index(
        "ix_customer_intelligence_organization_id", "customer_intelligence", ["organization_id"]
    )

    op.create_table(
        "memory_suggestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("source_message_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        *_timestamps(),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_memory_suggestions"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_memory_suggestions_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            name="fk_memory_suggestions_customer_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_message_id"],
            ["messages.id"],
            name="fk_memory_suggestions_source_message_id_messages",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name="fk_memory_suggestions_reviewed_by_users",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "category IN ('preference', 'communication', 'shopping')",
            name="suggestion_category",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')", name="suggestion_status"
        ),
    )
    op.create_index(
        "ix_memory_suggestions_organization_id_customer_id",
        "memory_suggestions",
        ["organization_id", "customer_id"],
    )

    op.create_table(
        "customer_segments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("segment", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_customer_segments"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_customer_segments_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            name="fk_customer_segments_customer_org",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "customer_id",
            "segment",
            name="uq_customer_segments_org_customer_segment",
        ),
        sa.CheckConstraint(
            "segment IN ('new_customer', 'returning_customer', 'high_intent_buyer', "
            "'price_sensitive', 'product_explorer', 'support_customer')",
            name="segment_name",
        ),
    )
    op.create_index(
        "ix_customer_segments_organization_id", "customer_segments", ["organization_id"]
    )

    op.create_table(
        "conversation_analytics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("total_messages", sa.Integer(), nullable=False),
        sa.Column("total_conversations", sa.Integer(), nullable=False),
        sa.Column("ai_generated", sa.Integer(), nullable=False),
        sa.Column("approved", sa.Integer(), nullable=False),
        sa.Column("edited", sa.Integer(), nullable=False),
        sa.Column("rejected", sa.Integer(), nullable=False),
        sa.Column("escalated", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_conversation_analytics"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_conversation_analytics_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("organization_id", "day", name="uq_conversation_analytics_org_day"),
    )
    op.create_index(
        "ix_conversation_analytics_organization_id_day",
        "conversation_analytics",
        ["organization_id", "day"],
    )

    op.create_table(
        "ai_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=True),
        sa.Column("final_text", sa.Text(), nullable=True),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_ai_feedback"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_ai_feedback_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["draft_id"],
            ["ai_reply_drafts.id"],
            name="fk_ai_feedback_draft_id_ai_reply_drafts",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("action IN ('approved', 'edited', 'rejected')", name="feedback_action"),
    )
    op.create_index("ix_ai_feedback_organization_id", "ai_feedback", ["organization_id"])
    op.create_index("ix_ai_feedback_draft_id", "ai_feedback", ["draft_id"])


def downgrade() -> None:
    op.drop_table("ai_feedback")
    op.drop_table("conversation_analytics")
    op.drop_table("customer_segments")
    op.drop_table("memory_suggestions")
    op.drop_table("customer_intelligence")
