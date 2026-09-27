"""brand controls and draft review

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _text(name: str) -> None:
    op.add_column("ai_settings", sa.Column(name, sa.Text(), nullable=False, server_default=""))
    op.alter_column("ai_settings", name, server_default=None)


def _bool(table: str, name: str, default: str) -> None:
    op.add_column(
        table, sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text(default))
    )
    op.alter_column(table, name, server_default=None)


def _json_list(name: str) -> None:
    op.add_column(
        "ai_settings",
        sa.Column(
            name,
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("ai_settings", name, server_default=None)


def upgrade() -> None:
    op.drop_constraint("draft_status", "ai_reply_drafts", type_="check")
    op.create_check_constraint(
        "draft_status",
        "ai_reply_drafts",
        "status IN ('generated', 'review_required', 'approved', 'rejected', 'edited', 'expired')",
    )
    op.add_column(
        "ai_reply_drafts",
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="low"),
    )
    op.alter_column("ai_reply_drafts", "risk_level", server_default=None)
    op.create_check_constraint(
        "draft_risk_level",
        "ai_reply_drafts",
        "risk_level IN ('low', 'medium', 'high')",
    )
    _bool("ai_reply_drafts", "escalation_required", "false")
    op.add_column("ai_reply_drafts", sa.Column("escalation_reason", sa.Text(), nullable=True))
    op.add_column(
        "ai_reply_drafts", sa.Column("guardrail_results", postgresql.JSONB(), nullable=True)
    )
    op.add_column("ai_reply_drafts", sa.Column("edited_text", sa.Text(), nullable=True))
    op.add_column("ai_reply_drafts", sa.Column("reviewed_by", sa.Uuid(), nullable=True))
    op.add_column(
        "ai_reply_drafts", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("ai_reply_drafts", sa.Column("review_note", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_ai_reply_drafts_reviewed_by_users",
        "ai_reply_drafts",
        "users",
        ["reviewed_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_ai_reply_drafts_organization_id_status",
        "ai_reply_drafts",
        ["organization_id", "status"],
    )

    op.add_column(
        "ai_settings",
        sa.Column("personality", sa.String(16), nullable=False, server_default="friendly"),
    )
    op.alter_column("ai_settings", "personality", server_default=None)
    op.create_check_constraint(
        "ai_personality",
        "ai_settings",
        "personality IN ('professional', 'friendly', 'casual', 'premium', 'playful', 'custom')",
    )
    _text("brand_voice")
    _text("custom_instructions")
    _json_list("preferred_terms")
    _json_list("forbidden_terms")
    op.add_column(
        "ai_settings",
        sa.Column("emoji_policy", sa.String(16), nullable=False, server_default="minimal"),
    )
    op.alter_column("ai_settings", "emoji_policy", server_default=None)
    op.create_check_constraint(
        "ai_emoji_policy",
        "ai_settings",
        "emoji_policy IN ('none', 'minimal', 'moderate', 'match_customer')",
    )
    op.add_column(
        "ai_settings",
        sa.Column("response_length", sa.String(16), nullable=False, server_default="medium"),
    )
    op.alter_column("ai_settings", "response_length", server_default=None)
    op.create_check_constraint(
        "ai_response_length",
        "ai_settings",
        "response_length IN ('short', 'medium', 'long')",
    )
    op.add_column(
        "ai_settings",
        sa.Column("language_mode", sa.String(16), nullable=False, server_default="auto"),
    )
    op.alter_column("ai_settings", "language_mode", server_default=None)
    op.create_check_constraint(
        "ai_language_mode",
        "ai_settings",
        "language_mode IN ('auto', 'english', 'hindi', 'hinglish', 'telugu')",
    )
    _bool("ai_settings", "require_review_for_refunds", "true")
    _bool("ai_settings", "require_review_for_payment_issues", "true")
    _bool("ai_settings", "require_review_for_high_risk", "true")
    _bool("ai_settings", "require_review_for_unsupported_claims", "true")


def downgrade() -> None:
    op.drop_column("ai_settings", "require_review_for_unsupported_claims")
    op.drop_column("ai_settings", "require_review_for_high_risk")
    op.drop_column("ai_settings", "require_review_for_payment_issues")
    op.drop_column("ai_settings", "require_review_for_refunds")
    op.drop_constraint("ai_language_mode", "ai_settings", type_="check")
    op.drop_column("ai_settings", "language_mode")
    op.drop_constraint("ai_response_length", "ai_settings", type_="check")
    op.drop_column("ai_settings", "response_length")
    op.drop_constraint("ai_emoji_policy", "ai_settings", type_="check")
    op.drop_column("ai_settings", "emoji_policy")
    op.drop_column("ai_settings", "forbidden_terms")
    op.drop_column("ai_settings", "preferred_terms")
    op.drop_column("ai_settings", "custom_instructions")
    op.drop_column("ai_settings", "brand_voice")
    op.drop_constraint("ai_personality", "ai_settings", type_="check")
    op.drop_column("ai_settings", "personality")

    op.drop_index("ix_ai_reply_drafts_organization_id_status", table_name="ai_reply_drafts")
    op.drop_constraint(
        "fk_ai_reply_drafts_reviewed_by_users", "ai_reply_drafts", type_="foreignkey"
    )
    op.drop_column("ai_reply_drafts", "review_note")
    op.drop_column("ai_reply_drafts", "reviewed_at")
    op.drop_column("ai_reply_drafts", "reviewed_by")
    op.drop_column("ai_reply_drafts", "edited_text")
    op.drop_column("ai_reply_drafts", "guardrail_results")
    op.drop_column("ai_reply_drafts", "escalation_reason")
    op.drop_column("ai_reply_drafts", "escalation_required")
    op.drop_constraint("draft_risk_level", "ai_reply_drafts", type_="check")
    op.drop_column("ai_reply_drafts", "risk_level")
    op.execute(
        "UPDATE ai_reply_drafts SET status = 'generated' "
        "WHERE status IN ('review_required', 'edited')"
    )
    op.drop_constraint("draft_status", "ai_reply_drafts", type_="check")
    op.create_check_constraint(
        "draft_status",
        "ai_reply_drafts",
        "status IN ('generated', 'approved', 'rejected', 'expired')",
    )
