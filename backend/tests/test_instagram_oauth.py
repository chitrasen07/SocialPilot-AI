from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import undefer

from app.models import ConnectionStatus, InstagramAccount, OrganizationMember, Role
from tests.conftest import member_headers, redis_run

FRONTEND = "http://localhost:5173/integrations"


def start(api, headers, organization):
    response = api.post(
        "/api/instagram/connect", headers=headers | {"X-Organization-Id": str(organization.id)}
    )
    assert response.status_code == 200, response.text
    url = response.json()["authorization_url"]
    return parse_qs(urlparse(url).query)["state"][0]


def callback(api, **params):
    response = api.get("/api/instagram/callback", params=params, follow_redirects=False)
    assert response.status_code == 303
    return response.headers["location"]


def load_accounts(db):
    async def query(session):
        result = await session.scalars(
            select(InstagramAccount).options(undefer(InstagramAccount.access_token_ciphertext))
        )
        return list(result)

    return db.run(query)


@pytest.mark.parametrize("role", [Role.VIEWER, Role.AGENT])
def test_connect_requires_admin(api, verifier, db, role):
    headers, organization = member_headers(db, verifier, role)
    response = api.post(
        "/api/instagram/connect", headers=headers | {"X-Organization-Id": str(organization.id)}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"


def test_connect_issues_single_use_state_and_browser_binding_cookie(api, verifier, db):
    headers, organization = member_headers(db, verifier, Role.ADMIN)
    response = api.post(
        "/api/instagram/connect", headers=headers | {"X-Organization-Id": str(organization.id)}
    )

    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "Path=/api/instagram/callback" in cookie
    assert "samesite=lax" in cookie.lower()
    state = parse_qs(urlparse(response.json()["authorization_url"]).query)["state"][0]
    assert len(state) >= 43
    ttl = redis_run(lambda r: r.ttl(f"oauth:instagram:{state}"))
    assert 0 < ttl <= 600


def test_connect_when_not_configured(api, verifier, db):
    api.app.state.instagram = None
    headers, organization = member_headers(db, verifier, Role.OWNER)
    response = api.post(
        "/api/instagram/connect", headers=headers | {"X-Organization-Id": str(organization.id)}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "INSTAGRAM_NOT_CONFIGURED"


def test_successful_callback_stores_encrypted_token_and_subscribes(
    api, verifier, db, instagram, instagram_provider
):
    headers, organization = member_headers(db, verifier, Role.OWNER)
    state = start(api, headers, organization)

    assert callback(api, state=state, code="abc") == f"{FRONTEND}?instagram=connected"

    [account] = load_accounts(db)
    assert account.organization_id == organization.id
    assert account.username == "acme.store"
    assert account.connection_status == ConnectionStatus.CONNECTED
    assert account.access_token_ciphertext != "ig-token-abc"
    assert instagram.cipher.decrypt(account.access_token_ciphertext) == "ig-token-abc"
    assert instagram_provider.subscribed == ["ig-token-abc"]

    listed = api.get(
        "/api/instagram/accounts", headers=headers | {"X-Organization-Id": str(organization.id)}
    )
    assert listed.json()["items"][0]["username"] == "acme.store"
    assert "ig-token" not in listed.text
    assert "ciphertext" not in listed.text


def test_state_cannot_be_replayed(api, verifier, db):
    headers, organization = member_headers(db, verifier, Role.OWNER)
    state = start(api, headers, organization)
    callback(api, state=state, code="abc")
    assert "OAUTH_STATE_INVALID" in callback(api, state=state, code="abc")


def test_unknown_or_missing_state_is_rejected(api, db, redis_db):
    assert callback(api, state="made-up", code="abc").endswith(
        "instagram_error=OAUTH_STATE_INVALID"
    )
    assert callback(api, code="abc").endswith("instagram_error=OAUTH_STATE_INVALID")


def test_callback_from_another_browser_is_rejected(api, verifier, db):
    headers, organization = member_headers(db, verifier, Role.OWNER)
    state = start(api, headers, organization)
    api.cookies.clear()

    assert callback(api, state=state, code="abc").endswith("instagram_error=OAUTH_STATE_MISMATCH")
    assert load_accounts(db) == []


def test_denied_authorization_consumes_state(api, verifier, db):
    headers, organization = member_headers(db, verifier, Role.OWNER)
    state = start(api, headers, organization)

    location = callback(api, state=state, error="access_denied", error_reason="user_denied")

    assert location.endswith("instagram_error=INSTAGRAM_AUTHORIZATION_DENIED")
    assert redis_run(lambda r: r.exists(f"oauth:instagram:{state}")) == 0
    assert load_accounts(db) == []


def test_role_is_rechecked_at_callback(api, verifier, db):
    headers, organization = member_headers(db, verifier, Role.ADMIN)
    state = start(api, headers, organization)

    async def demote(session):
        await session.execute(update(OrganizationMember).values(role=Role.VIEWER))
        await session.commit()

    db.run(demote)
    assert callback(api, state=state, code="abc").endswith(
        "instagram_error=ORGANIZATION_ACCESS_DENIED"
    )
    assert load_accounts(db) == []


def test_account_connected_to_another_organization_is_rejected(api, verifier, db):
    headers_a, org_a = member_headers(db, verifier, Role.OWNER)
    headers_b, org_b = member_headers(db, verifier, Role.OWNER)
    callback(api, state=start(api, headers_a, org_a), code="a")

    location = callback(api, state=start(api, headers_b, org_b), code="b")

    assert location.endswith("instagram_error=INSTAGRAM_ACCOUNT_IN_USE")
    [account] = load_accounts(db)
    assert account.organization_id == org_a.id


def test_reconnecting_updates_the_existing_account(api, verifier, db, instagram):
    headers, organization = member_headers(db, verifier, Role.OWNER)
    callback(api, state=start(api, headers, organization), code="first")
    callback(api, state=start(api, headers, organization), code="second")

    [account] = load_accounts(db)
    assert instagram.cipher.decrypt(account.access_token_ciphertext) == "ig-token-second"


@pytest.mark.parametrize(
    ("failing", "code"),
    [
        ("exchange_code", "INSTAGRAM_CONNECTION_FAILED"),
        ("get_profile", "INSTAGRAM_CONNECTION_FAILED"),
        ("subscribe_webhooks", "INSTAGRAM_WEBHOOK_SUBSCRIPTION_FAILED"),
    ],
)
def test_provider_failures_are_reported_without_saving(
    api, verifier, db, instagram_provider, failing, code
):
    headers, organization = member_headers(db, verifier, Role.OWNER)
    state = start(api, headers, organization)
    instagram_provider.fail_on = failing

    assert callback(api, state=state, code="abc").endswith(f"instagram_error={code}")
    assert load_accounts(db) == []
