import enum
import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, string_enum

# Must match the embedding model configured in Phase 5; changing it requires a migration.
EMBEDDING_DIMENSIONS = 768


class Customer(UUIDPrimaryKey, Timestamps, Base):
    """A person who messaged a connected Instagram account.

    Identity is (organization, Instagram account, Instagram-scoped user ID); usernames change.
    """

    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "instagram_account_id",
            "instagram_user_id",
            name="uq_customers_org_account_user",
        ),
        # Target for composite foreign keys that pin child rows to the same organization.
        UniqueConstraint("id", "organization_id"),
        Index("ix_customers_organization_id_updated_at", "organization_id", "updated_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    instagram_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instagram_accounts.id", ondelete="CASCADE"), index=True
    )
    instagram_user_id: Mapped[str] = mapped_column(String(64))
    username: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str | None] = mapped_column(String(200))
    profile_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    is_active: Mapped[bool] = mapped_column(default=True)


class MemoryType(enum.StrEnum):
    PREFERENCE = "preference"
    INTEREST = "interest"
    FACT = "fact"
    INTERACTION_SUMMARY = "interaction_summary"


class CustomerMemory(UUIDPrimaryKey, Timestamps, Base):
    """Persistent application memory about a customer (not model training)."""

    __tablename__ = "customer_memories"
    __table_args__ = (
        ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            ondelete="CASCADE",
            name="fk_customer_memories_customer_org",
        ),
        CheckConstraint("importance >= 0 AND importance <= 1", name="importance_range"),
        Index("ix_customer_memories_organization_id_customer_id", "organization_id", "customer_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    customer_id: Mapped[uuid.UUID]
    memory_type: Mapped[MemoryType] = mapped_column(string_enum(MemoryType, "memory_type", 32))
    content: Mapped[str] = mapped_column(Text)
    # NULL until an embedding is generated (Phase 5); such rows are skipped by vector search.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    # `metadata` is reserved on declarative classes, hence the attribute name.
    meta: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB(none_as_null=True))
    importance: Mapped[float] = mapped_column(default=1.0)
