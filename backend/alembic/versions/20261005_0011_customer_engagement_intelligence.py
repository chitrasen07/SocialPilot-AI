"""customer engagement intelligence

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STAGE = (
    "('discovery', 'product_interest', 'pricing', 'negotiation', "
    "'purchase_intent', 'support', 'complaint', 'resolved')"
)
_URGENCY = "('low', 'medium', 'high')"
_JOURNEY = (
    "('visitor', 'lead', 'interested', 'qualified', 'customer', 'repeat_customer', 'inactive')"
)


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
        "conversation_intelligence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("intent", sa.String(32), nullable=False),
        sa.Column("urgency", sa.String(16), nullable=False),
        sa.Column("buying_probability", sa.Float(), nullable=False),
        sa.Column("churn_probability", sa.Float(), nullable=False),
        sa.Column("customer_goal", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_conversation_intelligence"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_conversation_intelligence_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["conversations.id", "conversations.organization_id"],
            name="fk_conversation_intelligence_conversation_org",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "conversation_id",
            name="uq_conversation_intelligence_org_conversation",
        ),
        sa.CheckConstraint(f"stage IN {_STAGE}", name="engagement_stage"),
        sa.CheckConstraint(f"urgency IN {_URGENCY}", name="engagement_urgency"),
    )
    op.create_index(
        "ix_conversation_intelligence_organization_id",
        "conversation_intelligence",
        ["organization_id"],
    )

    op.create_table(
        "customer_journey",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("current_stage", sa.String(32), nullable=False),
        sa.Column("previous_stage", sa.String(32), nullable=True),
        sa.Column("changed_reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_customer_journey"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_customer_journey_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            name="fk_customer_journey_customer_org",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(f"current_stage IN {_JOURNEY}", name="journey_stage"),
        sa.CheckConstraint(f"previous_stage IN {_JOURNEY}", name="journey_previous_stage"),
    )
    op.create_index(
        "ix_customer_journey_organization_id_customer_id",
        "customer_journey",
        ["organization_id", "customer_id"],
    )

    op.create_table(
        "customer_scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("lead_score", sa.Integer(), nullable=False),
        sa.Column("score_reason", sa.Text(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_customer_scores"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_customer_scores_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            name="fk_customer_scores_customer_org",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "organization_id", "customer_id", name="uq_customer_scores_org_customer"
        ),
    )
    op.create_index("ix_customer_scores_organization_id", "customer_scores", ["organization_id"])

    op.create_table(
        "customer_recommendations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("product_name", sa.String(120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_customer_recommendations"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_customer_recommendations_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            name="fk_customer_recommendations_customer_org",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_customer_recommendations_organization_id_customer_id",
        "customer_recommendations",
        ["organization_id", "customer_id"],
    )

    op.create_table(
        "ai_response_scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=False),
        sa.Column("clarity_score", sa.Integer(), nullable=False),
        sa.Column("helpfulness_score", sa.Integer(), nullable=False),
        sa.Column("brand_score", sa.Integer(), nullable=False),
        sa.Column("conversion_score", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_ai_response_scores"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_ai_response_scores_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["draft_id"],
            ["ai_reply_drafts.id"],
            name="fk_ai_response_scores_draft_id_ai_reply_drafts",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("draft_id", name="uq_ai_response_scores_draft_id"),
    )
    op.create_index(
        "ix_ai_response_scores_organization_id", "ai_response_scores", ["organization_id"]
    )

    op.create_table(
        "learning_metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("personality", sa.String(32), nullable=False),
        sa.Column("response_length", sa.String(16), nullable=False),
        sa.Column("language_mode", sa.String(16), nullable=False),
        sa.Column("emoji_policy", sa.String(32), nullable=False),
        sa.Column("accepted", sa.Integer(), nullable=False),
        sa.Column("edited", sa.Integer(), nullable=False),
        sa.Column("rejected", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_learning_metrics"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_learning_metrics_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "personality",
            "response_length",
            "language_mode",
            "emoji_policy",
            name="uq_learning_metrics_style",
        ),
    )
    op.create_index("ix_learning_metrics_organization_id", "learning_metrics", ["organization_id"])


def downgrade() -> None:
    op.drop_table("learning_metrics")
    op.drop_table("ai_response_scores")
    op.drop_table("customer_recommendations")
    op.drop_table("customer_scores")
    op.drop_table("customer_journey")
    op.drop_table("conversation_intelligence")
