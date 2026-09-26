"""Instagram API with Instagram Login (official Meta platform).

Flow: authorize on instagram.com -> exchange the code for a short-lived token ->
exchange that for a long-lived token -> read the professional account profile ->
subscribe the app to the account's webhook fields. Endpoints, API version, scopes and
webhook fields all come from settings so they can follow Meta's changes without code edits.
"""

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.integrations.instagram.provider import (
    InstagramProfile,
    InstagramProviderError,
    TokenGrant,
)

logger = logging.getLogger("socialpilot.instagram")

# Graph API error code for invalid/expired OAuth access tokens.
INVALID_TOKEN_ERROR_CODE = 190


class MetaInstagramProvider:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        assert settings.meta_app_id and settings.meta_app_secret and settings.meta_redirect_uri
        self._settings = settings
        self._app_id = settings.meta_app_id
        self._app_secret = settings.meta_app_secret.get_secret_value()
        self._redirect_uri = settings.meta_redirect_uri
        self._http = http

    def _graph(self, path: str, versioned: bool = True) -> str:
        base = self._settings.meta_graph_url.rstrip("/")
        return f"{base}/{self._settings.meta_api_version}{path}" if versioned else f"{base}{path}"

    def authorization_url(self, state: str) -> str:
        query = urlencode(
            {
                "client_id": self._app_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": ",".join(self._settings.meta_scopes),
                "state": state,
            }
        )
        return f"{self._settings.meta_authorize_url}?{query}"

    async def exchange_code(self, code: str) -> TokenGrant:
        short = await self._request(
            "POST",
            self._settings.meta_token_url,
            "exchange_code",
            data={
                "client_id": self._app_id,
                "client_secret": self._app_secret,
                "grant_type": "authorization_code",
                "redirect_uri": self._redirect_uri,
                "code": code,
            },
        )
        # Documented as {"data": [{...}]}; older responses were a flat object.
        record = short["data"][0] if isinstance(short.get("data"), list) else short
        permissions = record.get("permissions") or []
        if isinstance(permissions, str):
            permissions = [p for p in permissions.split(",") if p]

        long_lived = await self._request(
            "GET",
            self._graph("/access_token", versioned=False),
            "exchange_long_lived_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": self._app_secret,
                "access_token": record["access_token"],
            },
        )
        return self._grant(long_lived, scopes=list(permissions))

    async def refresh_token(self, access_token: str) -> TokenGrant:
        refreshed = await self._request(
            "GET",
            self._graph("/refresh_access_token", versioned=False),
            "refresh_token",
            params={"grant_type": "ig_refresh_token", "access_token": access_token},
        )
        return self._grant(refreshed, scopes=[])

    async def get_profile(self, access_token: str) -> InstagramProfile:
        body = await self._request(
            "GET",
            self._graph("/me"),
            "get_profile",
            params={"fields": "user_id,username,account_type"},
            token=access_token,
        )
        # `user_id` is the professional account ID used in webhooks; `id` is app-scoped.
        return InstagramProfile(
            account_id=str(body.get("user_id") or body["id"]),
            username=body["username"],
            account_type=body.get("account_type"),
        )

    async def subscribe_webhooks(self, access_token: str) -> None:
        body = await self._request(
            "POST",
            self._graph("/me/subscribed_apps"),
            "subscribe_webhooks",
            params={"subscribed_fields": ",".join(self._settings.meta_webhook_fields)},
            token=access_token,
        )
        if body.get("success") is not True:
            raise InstagramProviderError("subscribe_webhooks: unexpected response")

    @staticmethod
    def _grant(body: dict[str, Any], scopes: list[str]) -> TokenGrant:
        expires_in = body.get("expires_in")
        expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in)) if expires_in else None
        return TokenGrant(access_token=body["access_token"], expires_at=expires_at, scopes=scopes)

    async def _request(
        self,
        method: str,
        url: str,
        operation: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}"} if token else None
        start = time.perf_counter()
        try:
            response = await self._http.request(
                method, url, params=params, data=data, headers=headers
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "instagram_api_unreachable",
                extra={"fields": {"operation": operation, "error": type(exc).__name__}},
            )
            raise InstagramProviderError(f"{operation}: Instagram API unreachable") from exc

        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        try:
            body = response.json()
        except ValueError:
            body = {}

        if response.is_success and isinstance(body, dict):
            logger.info(
                "instagram_api_call",
                extra={"fields": {"operation": operation, "duration_ms": duration_ms}},
            )
            return body

        # Graph errors: {"error": {...}}; the OAuth token endpoint uses flat error_* keys.
        error = body.get("error") if isinstance(body, dict) else None
        error = error if isinstance(error, dict) else (body if isinstance(body, dict) else {})
        code = error.get("code")
        logger.warning(
            "instagram_api_error",
            extra={
                "fields": {
                    "operation": operation,
                    "status": response.status_code,
                    "error_type": error.get("type") or error.get("error_type"),
                    "error_code": code,
                    "error_subcode": error.get("error_subcode"),
                    "fbtrace_id": error.get("fbtrace_id"),
                    "duration_ms": duration_ms,
                }
            },
        )
        raise InstagramProviderError(
            f"{operation}: Instagram API returned {response.status_code}",
            needs_reauth=code == INVALID_TOKEN_ERROR_CODE,
        )
