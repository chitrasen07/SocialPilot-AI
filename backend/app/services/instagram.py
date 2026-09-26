import hashlib
import hmac
import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

import httpx
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.core.config import Settings
from app.core.crypto import TokenCipher
from app.core.errors import AppError
from app.db.base import utcnow
from app.integrations.instagram.meta import MetaInstagramProvider
from app.integrations.instagram.provider import InstagramProvider, InstagramProviderError
from app.models import ConnectionStatus, InstagramAccount, OrganizationMember, Role

logger = logging.getLogger("socialpilot.instagram")

OAUTH_STATE_TTL_SECONDS = 600
_STATE_KEY = "oauth:instagram:{}"
MANAGE_ROLE = Role.ADMIN
REFRESH_WINDOW = timedelta(days=7)


@dataclass(frozen=True)
class InstagramClients:
    provider: InstagramProvider
    cipher: TokenCipher


def create_instagram_clients(
    settings: Settings, http: httpx.AsyncClient
) -> InstagramClients | None:
    """Returns None when the Meta app or token encryption is not configured."""
    if not settings.instagram_oauth_configured:
        return None
    assert settings.token_encryption_keys is not None
    return InstagramClients(
        provider=MetaInstagramProvider(settings, http),
        cipher=TokenCipher(settings.token_encryption_keys),
    )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class PendingConnection:
    authorization_url: str
    # Set as an HttpOnly cookie; the callback must present it, binding the flow to the browser
    # that started it (prevents an attacker's state being completed by a victim).
    browser_nonce: str


async def start_connection(
    redis: Redis, provider: InstagramProvider, membership: OrganizationMember
) -> PendingConnection:
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    record = {
        "user_id": str(membership.user_id),
        "organization_id": str(membership.organization_id),
        "nonce_sha256": _digest(nonce),
    }
    await redis.set(_STATE_KEY.format(state), json.dumps(record), ex=OAUTH_STATE_TTL_SECONDS)
    return PendingConnection(provider.authorization_url(state), nonce)


@dataclass(frozen=True)
class OAuthContext:
    user_id: uuid.UUID
    organization_id: uuid.UUID


async def consume_state(redis: Redis, state: str | None, nonce: str | None) -> OAuthContext:
    """Single use: GETDEL removes the state atomically, so replays fail."""
    raw = await redis.getdel(_STATE_KEY.format(state)) if state else None
    if raw is None:
        raise AppError("OAUTH_STATE_INVALID", "This connection link is invalid or has expired.")
    record = json.loads(raw)
    if not nonce or not hmac.compare_digest(_digest(nonce), record["nonce_sha256"]):
        raise AppError("OAUTH_STATE_MISMATCH", "Start the connection again from the same browser.")
    return OAuthContext(uuid.UUID(record["user_id"]), uuid.UUID(record["organization_id"]))


async def complete_connection(
    session: AsyncSession, clients: InstagramClients, context: OAuthContext, code: str
) -> InstagramAccount:
    # Re-check authorization: the role may have changed since the flow started.
    membership = await session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == context.organization_id,
            OrganizationMember.user_id == context.user_id,
        )
    )
    if membership is None or not membership.role.at_least(MANAGE_ROLE):
        raise AppError(
            "ORGANIZATION_ACCESS_DENIED", "You can no longer manage this organization.", 403
        )

    try:
        grant = await clients.provider.exchange_code(code)
        profile = await clients.provider.get_profile(grant.access_token)
    except InstagramProviderError as exc:
        raise AppError(
            "INSTAGRAM_CONNECTION_FAILED", "Instagram did not complete the connection.", 502
        ) from exc

    await _ensure_not_connected_elsewhere(session, profile.account_id, context.organization_id)

    try:
        await clients.provider.subscribe_webhooks(grant.access_token)
    except InstagramProviderError as exc:
        raise AppError(
            "INSTAGRAM_WEBHOOK_SUBSCRIPTION_FAILED",
            "Instagram connected, but event delivery could not be enabled. Try again.",
            502,
        ) from exc

    account = await session.scalar(
        select(InstagramAccount).where(
            InstagramAccount.organization_id == context.organization_id,
            InstagramAccount.instagram_account_id == profile.account_id,
        )
    )
    if account is None:
        account = InstagramAccount(
            organization_id=context.organization_id, instagram_account_id=profile.account_id
        )
        session.add(account)

    now = utcnow()
    account.username = profile.username
    account.account_type = profile.account_type
    account.connection_status = ConnectionStatus.CONNECTED
    account.access_token_ciphertext = clients.cipher.encrypt(grant.access_token)
    account.token_expires_at = grant.expires_at
    account.scopes = grant.scopes
    account.connected_at = now
    account.disconnected_at = None
    try:
        await session.commit()
    except IntegrityError as exc:
        # Lost a race against another organization connecting the same account.
        await session.rollback()
        raise _account_in_use() from exc

    logger.info(
        "instagram_account_connected",
        extra={
            "fields": {"organization_id": str(context.organization_id), "account": str(account.id)}
        },
    )
    return account


def _account_in_use() -> AppError:
    return AppError(
        "INSTAGRAM_ACCOUNT_IN_USE",
        "This Instagram account is already connected to another organization.",
        409,
    )


async def _ensure_not_connected_elsewhere(
    session: AsyncSession, instagram_account_id: str, organization_id: uuid.UUID
) -> None:
    other = await session.scalar(
        select(InstagramAccount.id).where(
            InstagramAccount.instagram_account_id == instagram_account_id,
            InstagramAccount.organization_id != organization_id,
            InstagramAccount.connection_status != ConnectionStatus.DISCONNECTED,
        )
    )
    if other is not None:
        raise _account_in_use()


async def list_accounts(
    session: AsyncSession, organization_id: uuid.UUID
) -> list[InstagramAccount]:
    result = await session.scalars(
        select(InstagramAccount)
        .where(
            InstagramAccount.organization_id == organization_id,
            InstagramAccount.connection_status != ConnectionStatus.DISCONNECTED,
        )
        .order_by(InstagramAccount.connected_at)
    )
    return list(result)


async def disconnect_account(
    session: AsyncSession, organization_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    """Stops processing for the account and destroys its stored token. Historical events stay
    with the organization. Revoking the app itself happens in the user's Instagram settings."""
    account = await session.scalar(
        select(InstagramAccount).where(
            InstagramAccount.id == account_id,
            InstagramAccount.organization_id == organization_id,
            InstagramAccount.connection_status != ConnectionStatus.DISCONNECTED,
        )
    )
    if account is None:
        raise AppError("INSTAGRAM_ACCOUNT_NOT_FOUND", "Instagram account not found.", 404)
    account.connection_status = ConnectionStatus.DISCONNECTED
    account.access_token_ciphertext = None
    account.token_expires_at = None
    account.disconnected_at = utcnow()
    await session.commit()


async def refresh_expiring_tokens(session: AsyncSession, clients: InstagramClients) -> None:
    """Refreshes long-lived tokens before they expire; flags accounts that need re-auth."""
    now = utcnow()
    accounts = await session.scalars(
        select(InstagramAccount)
        .options(undefer(InstagramAccount.access_token_ciphertext))
        .where(
            InstagramAccount.connection_status == ConnectionStatus.CONNECTED,
            InstagramAccount.token_expires_at < now + REFRESH_WINDOW,
        )
        .limit(200)
    )
    for account in accounts:
        if account.token_expires_at is None or account.access_token_ciphertext is None:
            continue
        if account.token_expires_at <= now:
            account.connection_status = ConnectionStatus.NEEDS_REAUTH
            continue
        try:
            token = clients.cipher.decrypt(account.access_token_ciphertext)
        except ValueError:
            # Encrypted with a key that is no longer configured; only re-auth can recover.
            account.connection_status = ConnectionStatus.NEEDS_REAUTH
            logger.error(
                "instagram_token_undecryptable", extra={"fields": {"account": str(account.id)}}
            )
            continue
        try:
            grant = await clients.provider.refresh_token(token)
        except InstagramProviderError as exc:
            if exc.needs_reauth:
                account.connection_status = ConnectionStatus.NEEDS_REAUTH
            logger.warning(
                "instagram_token_refresh_failed",
                extra={"fields": {"account": str(account.id), "needs_reauth": exc.needs_reauth}},
            )
            continue
        account.access_token_ciphertext = clients.cipher.encrypt(grant.access_token)
        account.token_expires_at = grant.expires_at
    await session.commit()
