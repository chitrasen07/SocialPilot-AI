import uuid

from redis.asyncio import Redis

# Wake-up signals only: processing state lives in webhook_deliveries, so a lost entry is
# picked up by the sweeper instead of being dropped.
WEBHOOK_QUEUE = "queue:webhook_deliveries"


async def enqueue_delivery(redis: Redis, delivery_id: uuid.UUID) -> None:
    await redis.lpush(WEBHOOK_QUEUE, str(delivery_id))
