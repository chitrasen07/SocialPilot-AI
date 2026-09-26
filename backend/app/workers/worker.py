"""Background worker: `python -m app.workers.worker`. Run as many replicas as needed."""

import asyncio
import logging
import signal
import uuid
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.observability import configure_logging, request_id_var
from app.db.session import create_engine, create_sessionmaker
from app.integrations.http import create_http_client
from app.services.instagram import create_instagram_clients, refresh_expiring_tokens
from app.services.webhooks import process_delivery, requeue_due_deliveries
from app.workers.queue import WEBHOOK_QUEUE

logger = logging.getLogger("socialpilot.worker")

CONSUMERS = 4
POP_TIMEOUT_SECONDS = 5
REDIS_RETRY_SECONDS = 2
SWEEP_INTERVAL_SECONDS = 30
TOKEN_REFRESH_INTERVAL_SECONDS = 6 * 3600


async def consume(
    stop: asyncio.Event, redis: Redis, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    while not stop.is_set():
        try:
            item = await redis.brpop([WEBHOOK_QUEUE], timeout=POP_TIMEOUT_SECONDS)
        except RedisTimeoutError:
            # redis-py may surface an empty blocking pop as a client-side timeout.
            continue
        except RedisError:
            logger.warning("worker_redis_unavailable")
            await asyncio.sleep(REDIS_RETRY_SECONDS)
            continue
        if item is None:
            continue
        raw_id = item[1]
        token = request_id_var.set(f"delivery:{raw_id}")
        try:
            async with sessionmaker() as session:
                await process_delivery(session, uuid.UUID(raw_id))
        except Exception:
            logger.exception("worker_job_crashed")
        finally:
            request_id_var.reset(token)


async def periodic(
    stop: asyncio.Event,
    redis: Redis,
    name: str,
    interval: int,
    job: Callable[[], Awaitable[object]],
) -> None:
    """Runs `job` at most once per `interval` across all worker replicas."""
    while not stop.is_set():
        try:
            acquired = await redis.set(f"lock:periodic:{name}", "1", nx=True, ex=interval)
        except RedisError:
            logger.warning("worker_redis_unavailable")
            acquired = False
        if acquired:
            try:
                await job()
            except Exception:
                logger.exception("periodic_job_failed", extra={"fields": {"job": name}})
        try:
            await asyncio.wait_for(stop.wait(), timeout=min(interval, 60))
        except TimeoutError:
            pass


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
    http = create_http_client()
    instagram = create_instagram_clients(settings, http)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    async def sweep() -> None:
        async with sessionmaker() as session:
            count = await requeue_due_deliveries(session, redis)
        if count:
            logger.info("webhook_deliveries_requeued", extra={"fields": {"count": count}})

    async def refresh_tokens() -> None:
        if instagram is None:
            return
        async with sessionmaker() as session:
            await refresh_expiring_tokens(session, instagram)

    tasks = [consume(stop, redis, sessionmaker) for _ in range(CONSUMERS)]
    tasks.append(periodic(stop, redis, "webhook_sweep", SWEEP_INTERVAL_SECONDS, sweep))
    tasks.append(
        periodic(
            stop, redis, "instagram_token_refresh", TOKEN_REFRESH_INTERVAL_SECONDS, refresh_tokens
        )
    )

    logger.info("worker_started", extra={"fields": {"consumers": CONSUMERS}})
    try:
        await asyncio.gather(*tasks)
    finally:
        await http.aclose()
        await redis.aclose()
        await engine.dispose()
        logger.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(run())
