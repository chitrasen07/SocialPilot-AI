"""multi-channel messages, settings, and analytics

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHANNEL = "('instagram', 'whatsapp', 'messenger', 'email', 'webchat')"


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
        "conversation_channels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("channel_type", sa.String(16), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_conversation_channels"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_conversation_channels_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "organization_id", "channel_type", name="uq_conversation_channels_org_type"
        ),
        sa.CheckConstraint(f"channel_type IN {_CHANNEL}", name="channel_type"),
    )
    op.create_index(
        "ix_conversation_channels_organization_id", "conversation_channels", ["organization_id"]
    )

    op.create_table(
        "channel_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("webhook_secret", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_channel_settings"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_channel_settings_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["conversation_channels.id"],
            name="fk_channel_settings_channel_id_conversation_channels",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "provider IN ('meta', 'mock', 'widget', 'email')", name="channel_provider"
        ),
        sa.CheckConstraint(
            "status IN ('connected', 'pending', 'disconnected')", name="channel_status"
        ),
    )
    op.create_index("ix_channel_settings_organization_id", "channel_settings", ["organization_id"])

    op.create_table(
        "channel_analytics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("channel_type", sa.String(16), nullable=False),
        sa.Column("total_messages", sa.Integer(), nullable=False),
        sa.Column("total_conversations", sa.Integer(), nullable=False),
        sa.Column("ai_generated", sa.Integer(), nullable=False),
        sa.Column("approved", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_channel_analytics"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_channel_analytics_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "day",
            "channel_type",
            name="uq_channel_analytics_org_day_channel",
        ),
        sa.CheckConstraint(f"channel_type IN {_CHANNEL}", name="analytics_channel"),
    )
    op.create_index(
        "ix_channel_analytics_organization_id_day",
        "channel_analytics",
        ["organization_id", "day"],
    )

    op.alter_column("customers", "instagram_account_id", nullable=True)
    op.alter_column("customers", "instagram_user_id", nullable=True)
    _channel_column("customers", "customer_channel")
    op.add_column("customers", sa.Column("external_user_id", sa.String(255), nullable=True))
    op.execute(
        "UPDATE customers SET external_user_id = instagram_user_id WHERE external_user_id IS NULL"
    )
    op.alter_column("customers", "external_user_id", nullable=False)
    op.create_index(
        "uq_customers_org_channel_external",
        "customers",
        ["organization_id", "channel_type", "external_user_id"],
        unique=True,
        postgresql_where=sa.text("instagram_account_id IS NULL"),
    )

    op.alter_column("conversations", "instagram_account_id", nullable=True)
    op.add_column("conversations", sa.Column("channel_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_conversations_channel_id_conversation_channels",
        "conversations",
        "conversation_channels",
        ["channel_id"],
        ["id"],
        ondelete="SET NULL",
    )
    _channel_column("conversations", "conversation_channel")
    op.add_column("conversations", sa.Column("priority", sa.String(16), nullable=True))
    op.execute("UPDATE conversations SET priority = 'medium' WHERE priority IS NULL")
    op.alter_column("conversations", "priority", nullable=False)
    op.create_check_constraint(
        "conversation_priority", "conversations", "priority IN ('low', 'medium', 'high')"
    )

    op.alter_column("messages", "instagram_account_id", nullable=True)
    op.add_column("messages", sa.Column("channel_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_messages_channel_id_conversation_channels",
        "messages",
        "conversation_channels",
        ["channel_id"],
        ["id"],
        ondelete="SET NULL",
    )
    _channel_column("messages", "message_channel")
    op.add_column("messages", sa.Column("sender_identifier", sa.String(255), nullable=True))
    op.add_column("messages", sa.Column("receiver_identifier", sa.String(255), nullable=True))


def _channel_column(table: str, constraint: str) -> None:
    op.add_column(table, sa.Column("channel_type", sa.String(16), nullable=True))
    op.execute(f"UPDATE {table} SET channel_type = 'instagram' WHERE channel_type IS NULL")  # noqa: S608
    op.alter_column(table, "channel_type", nullable=False)
    op.create_check_constraint(constraint, table, f"channel_type IN {_CHANNEL}")


def downgrade() -> None:
    op.drop_column("messages", "receiver_identifier")
    op.drop_column("messages", "sender_identifier")
    op.drop_constraint("message_channel", "messages", type_="check")
    op.drop_constraint(
        "fk_messages_channel_id_conversation_channels", "messages", type_="foreignkey"
    )
    op.drop_column("messages", "channel_id")
    op.drop_column("messages", "channel_type")
    op.alter_column("messages", "instagram_account_id", nullable=False)

    op.drop_constraint("conversation_priority", "conversations", type_="check")
    op.drop_column("conversations", "priority")
    op.drop_constraint("conversation_channel", "conversations", type_="check")
    op.drop_constraint(
        "fk_conversations_channel_id_conversation_channels", "conversations", type_="foreignkey"
    )
    op.drop_column("conversations", "channel_id")
    op.drop_column("conversations", "channel_type")
    op.alter_column("conversations", "instagram_account_id", nullable=False)

    op.drop_index("uq_customers_org_channel_external", table_name="customers")
    op.drop_column("customers", "external_user_id")
    op.drop_constraint("customer_channel", "customers", type_="check")
    op.drop_column("customers", "channel_type")
    op.alter_column("customers", "instagram_user_id", nullable=False)
    op.alter_column("customers", "instagram_account_id", nullable=False)

    op.drop_table("channel_analytics")
    op.drop_table("channel_settings")
    op.drop_table("conversation_channels")
