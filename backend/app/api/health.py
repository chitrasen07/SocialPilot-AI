import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import error_response

router = APIRouter(prefix="/api/health", tags=["health"])
logger = logging.getLogger("socialpilot.health")

CHECK_TIMEOUT_SECONDS = 3


async def check_database(engine: AsyncEngine) -> str:
    async with engine.connect() as conn:
        has_vector = await conn.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        )
    return "ok" if has_vector else "pgvector_missing"


async def check_redis(redis: Redis) -> str:
    await redis.ping()
    return "ok"


async def run_check(name: str, check: Coroutine[Any, Any, str]) -> str:
    try:
        return await asyncio.wait_for(check, timeout=CHECK_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.warning("health_check_failed", extra={"fields": {"check": name, "error": repr(exc)}})
        return "unavailable"


@router.get("")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", response_model=None)
async def readiness(request: Request) -> dict | JSONResponse:
    database, redis = await asyncio.gather(
        run_check("database", check_database(request.app.state.engine)),
        run_check("redis", check_redis(request.app.state.redis)),
    )
    checks = {"database": database, "redis": redis}
    if any(status != "ok" for status in checks.values()):
        return error_response(503, "SERVICE_UNAVAILABLE", "Dependencies are not ready.", checks)
    return {"status": "ok", "checks": checks}
