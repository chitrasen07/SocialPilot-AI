"""customers, conversations, messages, customer memories

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIMENSIONS = 768


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _organization_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id"],
        ["organizations.id"],
        name=f"fk_{table}_organization_id_organizations",
        ondelete="CASCADE",
    )


def _instagram_account_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["instagram_account_id"],
        ["instagram_accounts.id"],
        name=f"fk_{table}_instagram_account_id_instagram_accounts",
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("instagram_account_id", sa.Uuid(), nullable=False),
        sa.Column("instagram_user_id", sa.String(64), nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("display_name", sa.String(200), nullable=True),
        sa.Column("profile_data", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_customers"),
        _organization_fk("customers"),
        _instagram_account_fk("customers"),
        sa.UniqueConstraint(
            "organization_id",
            "instagram_account_id",
            "instagram_user_id",
            name="uq_customers_org_account_user",
        ),
        sa.UniqueConstraint("id", "organization_id", name="uq_customers_id_organization_id"),
    )
    op.create_index("ix_customers_instagram_account_id", "customers", ["instagram_account_id"])
    op.create_index(
        "ix_customers_organization_id_updated_at", "customers", ["organization_id", "updated_at"]
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("instagram_account_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
        _organization_fk("conversations"),
        _instagram_account_fk("conversations"),
        sa.ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            name="fk_conversations_customer_org",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "organization_id", name="uq_conversations_id_organization_id"),
        sa.CheckConstraint("status IN ('open', 'pending', 'closed')", name="conversation_status"),
    )
    op.create_index(
        "uq_conversations_active_customer",
        "conversations",
        ["customer_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('open', 'pending')"),
    )
    op.create_index(
        "ix_conversations_customer_id_last_message_at",
        "conversations",
        ["customer_id", "last_message_at"],
    )
    op.create_index(
        "ix_conversations_organization_id_last_message_at",
        "conversations",
        ["organization_id", sa.text("last_message_at DESC NULLS LAST")],
    )
    op.create_index(
        "ix_conversations_organization_id_status", "conversations", ["organization_id", "status"]
    )
    op.create_index(
        "ix_conversations_instagram_account_id", "conversations", ["instagram_account_id"]
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("instagram_account_id", sa.Uuid(), nullable=False),
        sa.Column("external_message_id", sa.String(255), nullable=True),
        sa.Column("sender_type", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("message_type", sa.String(16), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        _organization_fk("messages"),
        _instagram_account_fk("messages"),
        sa.ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["conversations.id", "conversations.organization_id"],
            name="fk_messages_conversation_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_messages_customer_id_customers",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "external_message_id",
            name="uq_messages_organization_id_external_message_id",
        ),
        sa.CheckConstraint("sender_type IN ('customer', 'business', 'system')", name="sender_type"),
        sa.CheckConstraint(
            "message_type IN ('text', 'image', 'video', 'audio', 'unknown')",
            name="message_type",
        ),
    )
    op.create_index(
        "ix_messages_conversation_id_sent_at", "messages", ["conversation_id", "sent_at", "id"]
    )
    op.create_index("ix_messages_customer_id", "messages", ["customer_id"])
    op.create_index("ix_messages_instagram_account_id", "messages", ["instagram_account_id"])

    op.create_table(
        "customer_memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("memory_type", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("importance", sa.Float(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_customer_memories"),
        _organization_fk("customer_memories"),
        sa.ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            name="fk_customer_memories_customer_org",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "memory_type IN ('preference', 'interest', 'fact', 'interaction_summary')",
            name="memory_type",
        ),
        sa.CheckConstraint("importance >= 0 AND importance <= 1", name="importance_range"),
    )
    op.create_index(
        "ix_customer_memories_organization_id_customer_id",
        "customer_memories",
        ["organization_id", "customer_id"],
    )


def downgrade() -> None:
    op.drop_table("customer_memories")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("customers")
