import hmac
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse

from app.api.deps import SessionDep
from app.core.errors import AppError
from app.integrations.instagram.webhooks import SIGNATURE_HEADER, signature_is_valid
from app.services.webhooks import record_delivery
from app.workers.queue import enqueue_delivery

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
logger = logging.getLogger("socialpilot.webhooks")

MAX_BODY_BYTES = 1_000_000


@router.get("/instagram", response_class=PlainTextResponse)
async def verify_subscription(
    request: Request,
    mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> str:
    """Meta's one-time endpoint verification handshake."""
    expected = request.app.state.settings.meta_webhook_verify_token
    if (
        expected is None
        or mode != "subscribe"
        or not verify_token
        or not challenge
        or not hmac.compare_digest(verify_token, expected.get_secret_value())
    ):
        raise AppError("WEBHOOK_VERIFICATION_FAILED", "Webhook verification failed.", 403)
    return challenge


@router.post("/instagram")
async def receive(request: Request, session: SessionDep) -> dict[str, str]:
    """Verifies, stores and enqueues; all processing happens in the worker."""
    app_secret = request.app.state.settings.meta_app_secret
    if app_secret is None:
        raise AppError("INSTAGRAM_NOT_CONFIGURED", "Webhooks are not configured.", 503)

    buffer = bytearray()
    async for chunk in request.stream():
        buffer += chunk
        if len(buffer) > MAX_BODY_BYTES:
            raise AppError("PAYLOAD_TOO_LARGE", "Webhook payload is too large.", 413)
    body = bytes(buffer)

    if not signature_is_valid(
        app_secret.get_secret_value(), body, request.headers.get(SIGNATURE_HEADER)
    ):
        logger.warning("webhook_signature_invalid")
        raise AppError("INVALID_SIGNATURE", "Webhook signature is invalid.", 401)

    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise AppError("INVALID_PAYLOAD", "Webhook payload is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise AppError("INVALID_PAYLOAD", "Webhook payload must be a JSON object.")

    delivery_id = await record_delivery(session, "instagram", body, payload)
    if delivery_id is None:
        logger.info("webhook_duplicate_ignored")
        return {"status": "duplicate"}

    try:
        await enqueue_delivery(request.app.state.redis, delivery_id)
    except Exception:
        # Stored durably already; the worker's sweeper will pick it up.
        logger.warning("webhook_enqueue_failed", extra={"fields": {"delivery": str(delivery_id)}})
    logger.info("webhook_received", extra={"fields": {"delivery": str(delivery_id)}})
    return {"status": "received"}
