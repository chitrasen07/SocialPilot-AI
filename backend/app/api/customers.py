import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import SessionDep, require_role
from app.models import OrganizationMember, Role
from app.schemas.customers import (
    CustomerConversationOut,
    CustomerDetail,
    CustomerList,
    CustomerListItem,
    CustomerOut,
    MemoryCreate,
    MemoryList,
    MemoryOut,
)
from app.services import customers as service
from app.services import memory as memory_service

router = APIRouter(prefix="/api/customers", tags=["customers"])

Viewer = Annotated[OrganizationMember, Depends(require_role(Role.VIEWER))]
Agent = Annotated[OrganizationMember, Depends(require_role(Role.AGENT))]


@router.get("")
async def list_customers(
    membership: Viewer,
    session: SessionDep,
    search: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> CustomerList:
    rows, has_more = await service.list_customers(
        session,
        membership.organization_id,
        search=search.strip() if search else None,
        limit=limit,
        offset=offset,
    )
    return CustomerList(
        items=[
            CustomerListItem(
                **CustomerOut.model_validate(row.customer).model_dump(),
                last_message_at=row.last_message_at,
                conversation_count=row.conversation_count,
            )
            for row in rows
        ],
        has_more=has_more,
    )


@router.get("/{customer_id}")
async def get_customer(
    customer_id: uuid.UUID, membership: Viewer, session: SessionDep
) -> CustomerDetail:
    customer, conversations = await service.get_customer(
        session, membership.organization_id, customer_id
    )
    return CustomerDetail(
        **CustomerOut.model_validate(customer).model_dump(),
        conversations=[CustomerConversationOut.model_validate(c) for c in conversations],
    )


@router.get("/{customer_id}/memories")
async def list_memories(
    customer_id: uuid.UUID, membership: Viewer, session: SessionDep
) -> MemoryList:
    memories = await memory_service.list_customer_memories(
        session, membership.organization_id, customer_id
    )
    return MemoryList(items=[MemoryOut.from_model(m) for m in memories])


@router.post("/{customer_id}/memories", status_code=201)
async def create_memory(
    customer_id: uuid.UUID, body: MemoryCreate, membership: Agent, session: SessionDep
) -> MemoryOut:
    memory = await memory_service.create_memory(
        session,
        membership.organization_id,
        customer_id,
        memory_type=body.memory_type,
        content=body.content,
        importance=body.importance,
        metadata=body.metadata,
    )
    return MemoryOut.from_model(memory)


@router.delete("/{customer_id}/memories/{memory_id}", status_code=204)
async def delete_memory(
    customer_id: uuid.UUID, memory_id: uuid.UUID, membership: Agent, session: SessionDep
) -> None:
    await memory_service.delete_memory(session, membership.organization_id, customer_id, memory_id)
