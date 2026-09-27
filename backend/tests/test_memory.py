"""Customer memory service: CRUD, vector retrieval, and tenant isolation."""

import uuid

import pytest

from app.core.errors import AppError
from app.models import EMBEDDING_DIMENSIONS, Customer, CustomerMemory, MemoryType
from app.services import memory
from tests.conftest import add_instagram_account


def vector(*weights: float) -> list[float]:
    """A 768-d embedding whose first components are `weights` (rest zero)."""
    return list(weights) + [0.0] * (EMBEDDING_DIMENSIONS - len(weights))


def make_customer(db, ig_id: str = "17841400000000001", user_id: str = "user_123"):
    _, organization = db.add_member()
    account = add_instagram_account(db, organization, instagram_account_id=ig_id)

    async def create(session):
        customer = Customer(
            organization_id=organization.id,
            instagram_account_id=account.id,
            instagram_user_id=user_id,
            external_user_id=user_id,
        )
        session.add(customer)
        await session.commit()
        return customer

    return organization, db.run(create)


def create(db, organization, customer, content, embedding=None, **fields):
    return db.run(
        lambda session: memory.create_memory(
            session,
            organization.id,
            customer.id,
            memory_type=fields.pop("memory_type", MemoryType.PREFERENCE),
            content=content,
            embedding=embedding,
            **fields,
        )
    )


def search(db, organization_id, customer_id, query, limit=5):
    return db.run(
        lambda session: memory.search_customer_memory(
            session, organization_id, customer_id, query, limit
        )
    )


def test_create_list_update_delete(db):
    organization, customer = make_customer(db)
    created = create(
        db, organization, customer, "Prefers blue shoes", importance=0.9, metadata={"src": "dm"}
    )
    assert created.importance == 0.9
    assert created.embedding is None

    listed = db.run(lambda s: memory.list_customer_memories(s, organization.id, customer.id))
    assert [m.content for m in listed] == ["Prefers blue shoes"]

    updated = db.run(
        lambda s: memory.update_memory(
            s, organization.id, customer.id, created.id, content="Likes navy", embedding=vector(1)
        )
    )
    assert updated.content == "Likes navy"
    assert updated.importance == 0.9
    assert updated.embedding is not None

    db.run(lambda s: memory.delete_memory(s, organization.id, customer.id, created.id))
    assert db.count(CustomerMemory) == 0


def test_search_orders_by_cosine_similarity(db):
    organization, customer = make_customer(db)
    create(db, organization, customer, "Prefers blue shoes", vector(1, 0))
    create(db, organization, customer, "Budget under 2000", vector(0, 1))
    create(db, organization, customer, "Likes sneakers", vector(1, 1))
    create(db, organization, customer, "No embedding yet")

    results = search(db, organization.id, customer.id, vector(1, 0.1))
    assert [m.content for m, _ in results] == [
        "Prefers blue shoes",
        "Likes sneakers",
        "Budget under 2000",
    ]
    distances = [d for _, d in results]
    assert distances == sorted(distances)
    assert distances[0] < 0.01

    assert len(search(db, organization.id, customer.id, vector(1), limit=1)) == 1


def test_search_never_crosses_customers_or_organizations(db):
    org_a, customer_a = make_customer(db, "17841400000000001")
    org_b, customer_b = make_customer(db, "17841400000000002")
    create(db, org_a, customer_a, "Org A secret", vector(1))
    create(db, org_b, customer_b, "Org B secret", vector(1))

    assert [m.content for m, _ in search(db, org_a.id, customer_a.id, vector(1))] == [
        "Org A secret"
    ]
    # Org A cannot reach org B's customer by passing its ID.
    assert search(db, org_a.id, customer_b.id, vector(1)) == []


def test_foreign_customer_and_memory_are_not_found(db):
    org_a, customer_a = make_customer(db, "17841400000000001")
    org_b, customer_b = make_customer(db, "17841400000000002")
    theirs = create(db, org_b, customer_b, "Org B memory")

    with pytest.raises(AppError) as exc:
        create(db, org_a, customer_b, "Injected")
    assert exc.value.code == "CUSTOMER_NOT_FOUND"

    for call in (
        lambda s: memory.delete_memory(s, org_a.id, customer_b.id, theirs.id),
        lambda s: memory.update_memory(s, org_a.id, customer_a.id, theirs.id, content="x"),
    ):
        with pytest.raises(AppError) as exc:
            db.run(call)
        assert exc.value.code == "MEMORY_NOT_FOUND"

    with pytest.raises(AppError) as exc:
        db.run(lambda s: memory.list_customer_memories(s, org_a.id, uuid.uuid4()))
    assert exc.value.code == "CUSTOMER_NOT_FOUND"
    assert db.count(CustomerMemory) == 1


def test_wrong_embedding_dimensions_are_rejected(db):
    organization, customer = make_customer(db)
    with pytest.raises(AppError) as exc:
        create(db, organization, customer, "x", [1.0, 2.0])
    assert exc.value.code == "INVALID_EMBEDDING"
    with pytest.raises(AppError):
        search(db, organization.id, customer.id, [1.0])
