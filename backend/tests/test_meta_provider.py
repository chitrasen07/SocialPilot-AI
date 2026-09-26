import asyncio
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.integrations.instagram.meta import MetaInstagramProvider
from app.integrations.instagram.provider import InstagramProviderError
from tests.conftest import make_settings


def run_with(handler, call):
    """Runs `call(provider)` against a mocked Meta API served by `handler(request)`."""
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(record)) as http:
            return await call(MetaInstagramProvider(make_settings(), http))

    return asyncio.run(go()), requests


def test_authorization_url_uses_configured_app_and_scopes():
    provider = MetaInstagramProvider(make_settings(), httpx.AsyncClient())
    url = urlparse(provider.authorization_url("state-123"))
    query = parse_qs(url.query)

    assert f"{url.scheme}://{url.netloc}{url.path}" == "https://www.instagram.com/oauth/authorize"
    assert query == {
        "client_id": ["123"],
        "redirect_uri": ["https://app.example.com/api/instagram/callback"],
        "response_type": ["code"],
        "scope": [
            "instagram_business_basic,instagram_business_manage_messages,"
            "instagram_business_manage_comments"
        ],
        "state": ["state-123"],
    }


@pytest.mark.parametrize(
    "short_lived",
    [
        {"data": [{"access_token": "short", "user_id": "1", "permissions": "a,b"}]},
        {"access_token": "short", "user_id": "1", "permissions": ["a", "b"]},
    ],
)
def test_exchange_code_upgrades_to_long_lived_token(short_lived):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.instagram.com":
            return httpx.Response(200, json=short_lived)
        return httpx.Response(
            200, json={"access_token": "long", "token_type": "bearer", "expires_in": 5184000}
        )

    grant, requests = run_with(handler, lambda p: p.exchange_code("the-code"))

    token_request, long_request = requests
    assert token_request.method == "POST"
    assert parse_qs(token_request.content.decode()) == {
        "client_id": ["123"],
        "client_secret": ["test-app-secret"],
        "grant_type": ["authorization_code"],
        "redirect_uri": ["https://app.example.com/api/instagram/callback"],
        "code": ["the-code"],
    }
    assert long_request.url.path == "/access_token"
    assert long_request.url.params["grant_type"] == "ig_exchange_token"
    assert long_request.url.params["access_token"] == "short"
    assert grant.access_token == "long"
    assert grant.scopes == ["a", "b"]
    assert grant.expires_at is not None
    assert abs(grant.expires_at - (datetime.now(UTC) + timedelta(days=60))) < timedelta(minutes=1)


def test_profile_and_subscription_use_bearer_auth_on_versioned_graph():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/me"):
            return httpx.Response(
                200,
                json={
                    "id": "app-scoped",
                    "user_id": "17841",
                    "username": "acme",
                    "account_type": "BUSINESS",
                },
            )
        return httpx.Response(200, json={"success": True})

    async def call(provider):
        profile = await provider.get_profile("tok")
        await provider.subscribe_webhooks("tok")
        return profile

    profile, (me, subscribe) = run_with(handler, call)

    assert (profile.account_id, profile.username) == ("17841", "acme")
    assert me.url.path == "/v23.0/me"
    assert me.headers["authorization"] == "Bearer tok"
    assert "access_token" not in me.url.params
    assert subscribe.method == "POST"
    assert subscribe.url.path == "/v23.0/me/subscribed_apps"
    assert subscribe.url.params["subscribed_fields"] == "comments,messages"


def test_invalid_token_error_requests_reauth_without_leaking_token():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "Error validating access token",
                    "type": "OAuthException",
                    "code": 190,
                }
            },
        )

    with pytest.raises(InstagramProviderError) as exc_info:
        run_with(handler, lambda p: p.refresh_token("secret-token"))

    assert exc_info.value.needs_reauth is True
    assert "secret-token" not in str(exc_info.value)


def test_network_failure_is_wrapped():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(InstagramProviderError) as exc_info:
        run_with(handler, lambda p: p.get_profile("tok"))
    assert exc_info.value.needs_reauth is False
