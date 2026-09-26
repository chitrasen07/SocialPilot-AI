"""message AI analysis, reply drafts, organization AI settings

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
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
        "message_ai_analysis",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("language_confidence", sa.Float(), nullable=False),
        sa.Column("intent", sa.String(32), nullable=False),
        sa.Column("intent_confidence", sa.Float(), nullable=False),
        sa.Column("sentiment", sa.String(16), nullable=False),
        sa.Column("sentiment_confidence", sa.Float(), nullable=False),
        sa.Column("emotion", sa.String(24), nullable=False),
        sa.Column("emotion_confidence", sa.Float(), nullable=False),
        sa.Column("purchase_intent", sa.String(16), nullable=False),
        sa.Column("purchase_intent_confidence", sa.Float(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("processing_status", sa.String(16), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_message_ai_analysis"),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name="fk_message_ai_analysis_message_id_messages",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_message_ai_analysis_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("message_id", name="uq_message_ai_analysis_message_id"),
        sa.CheckConstraint("processing_status IN ('completed', 'failed')", name="analysis_status"),
    )
    op.create_index(
        "ix_message_ai_analysis_organization_id", "message_ai_analysis", ["organization_id"]
    )

    op.create_table(
        "ai_reply_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("reply_text", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("guardrail_status", sa.String(16), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_ai_reply_drafts"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_ai_reply_drafts_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name="fk_ai_reply_drafts_message_id_messages",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_ai_reply_drafts_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_ai_reply_drafts_customer_id_customers",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('generated', 'approved', 'rejected', 'expired')", name="draft_status"
        ),
        sa.CheckConstraint("guardrail_status IN ('passed', 'blocked')", name="guardrail_status"),
    )
    op.create_index("ix_ai_reply_drafts_organization_id", "ai_reply_drafts", ["organization_id"])
    op.create_index("ix_ai_reply_drafts_message_id", "ai_reply_drafts", ["message_id"])
    op.create_index("ix_ai_reply_drafts_conversation_id", "ai_reply_drafts", ["conversation_id"])

    op.create_table(
        "ai_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("max_context_messages", sa.Integer(), nullable=False),
        sa.Column("memory_top_k", sa.Integer(), nullable=False),
        sa.Column("auto_analysis_enabled", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_ai_settings"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_ai_settings_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("organization_id", name="uq_ai_settings_organization_id"),
    )


def downgrade() -> None:
    op.drop_table("ai_settings")
    op.drop_table("ai_reply_drafts")
    op.drop_table("message_ai_analysis")
