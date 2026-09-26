import uuid

from redis.asyncio import Redis

# Wake-up signals only. Processing state lives in the database, so a lost entry is
# picked up by the sweeper instead of being dropped.
WEBHOOK_QUEUE = "queue:webhook_deliveries"
KNOWLEDGE_QUEUE = "queue:knowledge_documents"


async def enqueue_delivery(redis: Redis, delivery_id: uuid.UUID) -> None:
    await redis.lpush(WEBHOOK_QUEUE, str(delivery_id))


async def enqueue_knowledge(redis: Redis, document_id: uuid.UUID) -> None:
    await redis.lpush(KNOWLEDGE_QUEUE, str(document_id))
