import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Conversation, Customer

RECENT_CONVERSATIONS = 20


@dataclass(frozen=True)
class CustomerRow:
    customer: Customer
    last_message_at: datetime | None
    conversation_count: int


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_customers(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    search: str | None,
    limit: int,
    offset: int,
) -> tuple[list[CustomerRow], bool]:
    """Most recently active first. Returns (rows, has_more)."""
    # Correlated subqueries are evaluated only for the page's rows, via the customer_id index.
    conversations = select(Conversation).where(Conversation.customer_id == Customer.id)
    last_message_at = conversations.with_only_columns(
        func.max(Conversation.last_message_at)
    ).scalar_subquery()
    conversation_count = conversations.with_only_columns(func.count()).scalar_subquery()
    query = select(Customer, last_message_at, conversation_count).where(
        Customer.organization_id == organization_id
    )
    if search:
        pattern = f"%{_escape_like(search)}%"
        query = query.where(
            or_(
                Customer.username.ilike(pattern, escape="\\"),
                Customer.display_name.ilike(pattern, escape="\\"),
                Customer.instagram_user_id.ilike(pattern, escape="\\"),
            )
        )
    rows = (
        await session.execute(
            query.order_by(Customer.updated_at.desc(), Customer.id.desc())
            .limit(limit + 1)
            .offset(offset)
        )
    ).all()
    items = [CustomerRow(customer, last, count) for customer, last, count in rows[:limit]]
    return items, len(rows) > limit


async def get_customer(
    session: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> tuple[Customer, list[Conversation]]:
    customer = await session.scalar(
        select(Customer).where(
            Customer.id == customer_id, Customer.organization_id == organization_id
        )
    )
    if customer is None:
        raise AppError("CUSTOMER_NOT_FOUND", "Customer not found.", 404)
    conversations = await session.scalars(
        select(Conversation)
        .where(
            Conversation.customer_id == customer.id,
            Conversation.organization_id == organization_id,
        )
        .order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.id.desc())
        .limit(RECENT_CONVERSATIONS)
    )
    return customer, list(conversations)
