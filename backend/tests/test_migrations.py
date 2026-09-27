"""Runs the real Alembic migrations (not create_all) against a scratch database."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests.conftest import TEST_DATABASE_URL, TEST_DB_NAME, _dev_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRATCH_DB = f"{TEST_DB_NAME}_migrations"
SCRATCH_URL = _dev_url.set(database=SCRATCH_DB).render_as_string(hide_password=False)
PHASE_4_TABLES = {"customers", "conversations", "messages", "customer_memories"}
PHASE_5_TABLES = {"message_ai_analysis", "ai_reply_drafts", "ai_settings"}
PHASE_6_TABLES = {"knowledge_documents", "knowledge_chunks"}
PHASE_8_TABLES = {
    "customer_intelligence",
    "memory_suggestions",
    "customer_segments",
    "conversation_analytics",
    "ai_feedback",
}
PHASE_9_TABLES = {"automation_rules", "tasks", "notifications"}
PHASE_10_TABLES = {"conversation_channels", "channel_settings", "channel_analytics"}
PHASE_11_TABLES = {
    "conversation_intelligence",
    "customer_journey",
    "customer_scores",
    "customer_recommendations",
    "ai_response_scores",
    "learning_metrics",
}


async def _admin(statement: str) -> None:
    engine = create_async_engine(
        TEST_DATABASE_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    async with engine.connect() as conn:
        await conn.execute(text(statement))
    await engine.dispose()


async def _tables() -> set[str]:
    engine = create_async_engine(SCRATCH_URL, poolclass=NullPool)
    async with engine.connect() as conn:
        rows = await conn.scalars(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        tables = set(rows)
    await engine.dispose()
    return tables


def alembic(*args: str) -> None:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=os.environ | {"DATABASE_URL": SCRATCH_URL},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]


@pytest.fixture
def scratch_database():
    asyncio.run(_admin(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}"'))
    asyncio.run(_admin(f'CREATE DATABASE "{SCRATCH_DB}"'))
    yield
    asyncio.run(_admin(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))


def test_upgrade_downgrade_upgrade(scratch_database):
    alembic("upgrade", "head")
    tables = asyncio.run(_tables())
    assert PHASE_4_TABLES <= tables
    assert PHASE_5_TABLES <= tables
    assert PHASE_6_TABLES <= tables
    assert PHASE_8_TABLES <= tables
    assert PHASE_9_TABLES <= tables
    assert PHASE_10_TABLES <= tables
    assert PHASE_11_TABLES <= tables

    alembic("downgrade", "-1")
    after_engagement = asyncio.run(_tables())
    assert not PHASE_11_TABLES & after_engagement
    assert PHASE_10_TABLES <= after_engagement

    alembic("downgrade", "-1")
    after_channels = asyncio.run(_tables())
    assert not PHASE_10_TABLES & after_channels
    assert PHASE_9_TABLES <= after_channels

    alembic("downgrade", "-1")
    after_automation = asyncio.run(_tables())
    assert not PHASE_9_TABLES & after_automation
    assert PHASE_8_TABLES <= after_automation
    assert PHASE_6_TABLES <= after_automation

    alembic("downgrade", "-1")
    after_intelligence = asyncio.run(_tables())
    assert not PHASE_8_TABLES & after_intelligence
    assert PHASE_6_TABLES <= after_intelligence
    assert PHASE_5_TABLES <= after_intelligence
    assert PHASE_4_TABLES <= after_intelligence

    alembic("downgrade", "-1")
    after_brand = asyncio.run(_tables())
    assert PHASE_6_TABLES <= after_brand
    assert PHASE_5_TABLES <= after_brand
    assert PHASE_4_TABLES <= after_brand

    alembic("downgrade", "-1")
    after_knowledge = asyncio.run(_tables())
    assert not PHASE_6_TABLES & after_knowledge
    assert PHASE_5_TABLES <= after_knowledge
    assert PHASE_4_TABLES <= after_knowledge

    alembic("upgrade", "head")
    alembic("downgrade", "0003")
    remaining = asyncio.run(_tables())
    assert not PHASE_4_TABLES & remaining
    assert {"instagram_events", "webhook_deliveries"} <= remaining

    alembic("upgrade", "head")
    assert PHASE_4_TABLES <= asyncio.run(_tables())
    # Models and migrations describe the same schema.
    alembic("check")
