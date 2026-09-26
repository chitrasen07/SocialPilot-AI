import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

os.environ["ENVIRONMENT"] = "test"
os.environ["AI_PROVIDER"] = "mock"
os.environ.setdefault(
    "DATABASE_URL", "postgresql://socialpilot:socialpilot@localhost:5432/socialpilot"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

# Tests always run against "<dev database>_test" so they can never truncate development data.
_dev_url = make_url(os.environ["DATABASE_URL"]).set(drivername="postgresql+asyncpg")
TEST_DB_NAME = f"{_dev_url.database}_test"
TEST_DATABASE_URL = _dev_url.set(database=TEST_DB_NAME).render_as_string(hide_password=False)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# Likewise, Redis logical database 15 is reserved for tests and flushed between them.
TEST_REDIS_URL = os.environ["REDIS_URL"].rsplit("/", 1)[0] + "/15"
os.environ["REDIS_URL"] = TEST_REDIS_URL

from cryptography.fernet import Fernet  # noqa: E402
from pydantic import SecretStr  # noqa: E402
from redis.asyncio import Redis  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.crypto import TokenCipher  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.core.firebase import VerifiedIdentity  # noqa: E402
from app.db.base import Base, utcnow  # noqa: E402
from app.integrations.instagram.provider import (  # noqa: E402
    InstagramProfile,
    InstagramProviderError,
    TokenGrant,
)
from app.main import create_app  # noqa: E402
from app.models import Organization, OrganizationMember, Role, User  # noqa: E402
from app.services.instagram import InstagramClients  # noqa: E402

META_APP_SECRET = "test-app-secret"
META_VERIFY_TOKEN = "test-verify-token"


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "meta_app_id": "123",
        "meta_app_secret": META_APP_SECRET,
        "meta_redirect_uri": "https://app.example.com/api/instagram/callback",
        "meta_webhook_verify_token": META_VERIFY_TOKEN,
        "token_encryption_keys": Fernet.generate_key().decode(),
        "frontend_url": "http://localhost:5173",
        "ai_provider": "mock",
    } | overrides
    return Settings(**values)


class FakeInstagramProvider:
    """Stands in for the Meta provider; records calls and can be told to fail."""

    def __init__(self) -> None:
        self.profile = InstagramProfile("17841400000000001", "acme.store", "BUSINESS")
        self.fail_on: str | None = None
        self.subscribed: list[str] = []
        self.refreshed: list[str] = []

    def _maybe_fail(self, operation: str, needs_reauth: bool = False) -> None:
        if self.fail_on == operation:
            raise InstagramProviderError(f"{operation}: failed", needs_reauth=needs_reauth)

    def authorization_url(self, state: str) -> str:
        return f"https://instagram.test/oauth/authorize?state={state}"

    async def exchange_code(self, code: str) -> TokenGrant:
        self._maybe_fail("exchange_code")
        return TokenGrant(
            f"ig-token-{code}", utcnow() + timedelta(days=60), ["instagram_business_basic"]
        )

    async def refresh_token(self, access_token: str) -> TokenGrant:
        self._maybe_fail("refresh_token", needs_reauth=True)
        self.refreshed.append(access_token)
        return TokenGrant(f"{access_token}-refreshed", utcnow() + timedelta(days=60), [])

    async def get_profile(self, access_token: str) -> InstagramProfile:
        self._maybe_fail("get_profile")
        return self.profile

    async def subscribe_webhooks(self, access_token: str) -> None:
        self._maybe_fail("subscribe_webhooks")
        self.subscribed.append(access_token)


class FakeTokenVerifier:
    """Stands in for Firebase Admin: tokens are opaque keys registered by the test."""

    def __init__(self) -> None:
        self.identities: dict[str, VerifiedIdentity] = {}

    def register(self, identity: VerifiedIdentity) -> dict[str, str]:
        token = f"token-{identity.uid}"
        self.identities[token] = identity
        return {"Authorization": f"Bearer {token}"}

    async def verify(self, token: str) -> VerifiedIdentity:
        try:
            return self.identities[token]
        except KeyError:
            raise AppError("INVALID_TOKEN", "The authentication token is invalid.", 401) from None


def make_identity(uid: str | None = None, **overrides: Any) -> VerifiedIdentity:
    uid = uid or uuid.uuid4().hex
    values = {
        "uid": uid,
        "email": f"{uid}@example.com",
        "email_verified": True,
        "name": "Asha Rao",
        "picture": None,
    } | overrides
    return VerifiedIdentity(**values)


@dataclass
class Database:
    url: str

    def run(self, fn: Callable[[AsyncSession], Awaitable[Any]]) -> Any:
        async def go() -> Any:
            engine = create_async_engine(self.url, poolclass=NullPool)
            try:
                async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                    return await fn(session)
            finally:
                await engine.dispose()

        return asyncio.run(go())

    def count(self, model: type) -> int:
        async def query(session: AsyncSession) -> int:
            return await session.scalar(text(f"SELECT count(*) FROM {model.__tablename__}"))  # noqa: S608

        return self.run(query)

    def add_member(self, user: User | None = None, role: Role = Role.OWNER, **org: Any):
        """Creates an organization (and a user if none is given) joined with `role`."""

        async def create(session: AsyncSession) -> tuple[User, Organization]:
            member = user or User(firebase_uid=uuid.uuid4().hex, email="m@example.com")
            organization = Organization(
                name=org.get("name", "Acme"), slug=org.get("slug", uuid.uuid4().hex[:12])
            )
            session.add_all([member, organization])
            await session.flush()
            session.add(
                OrganizationMember(organization_id=organization.id, user_id=member.id, role=role)
            )
            await session.commit()
            return member, organization

        return self.run(create)


@pytest.fixture(scope="session")
def _database_schema() -> str:
    async def setup() -> None:
        admin = create_async_engine(_dev_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
        async with admin.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB_NAME}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
        await admin.dispose()

        engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(setup())
    return TEST_DATABASE_URL


@pytest.fixture
def db(_database_schema: str) -> Database:
    database = Database(_database_schema)
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)

    async def truncate(session: AsyncSession) -> None:
        await session.execute(text(f"TRUNCATE {tables} CASCADE"))
        await session.commit()

    database.run(truncate)
    return database


def member_headers(db: Database, verifier: FakeTokenVerifier, role: Role, **org: Any):
    """Creates a user with `role` in a new organization; returns (auth headers, organization)."""
    identity = make_identity()
    _, organization = db.add_member(
        user=User(firebase_uid=identity.uid, email=identity.email, email_verified=True),
        role=role,
        **org,
    )
    return verifier.register(identity), organization


def add_instagram_account(db: Database, organization: Organization, **fields: Any):
    from app.models import ConnectionStatus, InstagramAccount

    values: dict[str, Any] = {
        "organization_id": organization.id,
        "instagram_account_id": "17841400000000001",
        "username": "acme.store",
        "connection_status": ConnectionStatus.CONNECTED,
        "connected_at": utcnow(),
    } | fields

    async def create(session: AsyncSession) -> InstagramAccount:
        account = InstagramAccount(**values)
        session.add(account)
        await session.commit()
        return account

    return db.run(create)


def dm_payload(
    sender: str,
    text: str | None,
    mid: str,
    timestamp_ms: int,
    *,
    account_id: str = "17841400000000001",
    recipient: str | None = None,
    **message_fields: Any,
) -> dict[str, Any]:
    """A single Instagram direct-message webhook body as delivered by Meta."""
    message: dict[str, Any] = {"mid": mid} | message_fields
    if text is not None:
        message["text"] = text
    return {
        "object": "instagram",
        "entry": [
            {
                "id": account_id,
                "time": timestamp_ms // 1000,
                "messaging": [
                    {
                        "sender": {"id": sender},
                        "recipient": {"id": recipient or account_id},
                        "timestamp": timestamp_ms,
                        "message": message,
                    }
                ],
            }
        ],
    }


def deliver(db: Database, body: dict[str, Any]) -> None:
    """Runs a webhook body through the real pipeline: record the delivery, then process it
    exactly as the worker does."""
    import json

    from app.models import DeliveryStatus, WebhookDelivery
    from app.services.webhooks import process_delivery, record_delivery

    raw = json.dumps(body).encode()

    async def run(session: AsyncSession) -> None:
        delivery_id = await record_delivery(session, "instagram", raw, body)
        assert delivery_id is not None
        assert await process_delivery(session, delivery_id)
        # process_delivery swallows errors into a retry; surface them here instead.
        delivery = await session.get(WebhookDelivery, delivery_id, populate_existing=True)
        assert delivery.status == DeliveryStatus.PROCESSED, delivery.last_error

    db.run(run)


def redis_run(fn: Callable[[Redis], Awaitable[Any]]) -> Any:
    """Runs `fn` against the test Redis database with a short-lived client."""

    async def go() -> Any:
        client = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
        try:
            return await fn(client)
        finally:
            await client.aclose()

    return asyncio.run(go())


@pytest.fixture
def redis_db() -> None:
    redis_run(lambda client: client.flushdb())


@pytest.fixture
def verifier() -> FakeTokenVerifier:
    return FakeTokenVerifier()


@pytest.fixture
def instagram_provider() -> FakeInstagramProvider:
    return FakeInstagramProvider()


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def instagram(settings: Settings, instagram_provider: FakeInstagramProvider) -> InstagramClients:
    assert isinstance(settings.token_encryption_keys, SecretStr)
    return InstagramClients(instagram_provider, TokenCipher(settings.token_encryption_keys))


@pytest.fixture
def api(db, redis_db, verifier, settings, instagram):
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.token_verifier = verifier
        app.state.instagram = instagram
        yield client
