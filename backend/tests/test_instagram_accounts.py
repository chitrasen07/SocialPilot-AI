from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import undefer

from app.db.base import utcnow
from app.models import ConnectionStatus, InstagramAccount, Role
from app.services.instagram import refresh_expiring_tokens
from tests.conftest import add_instagram_account, member_headers


def org_headers(headers, organization):
    return headers | {"X-Organization-Id": str(organization.id)}


def load(db, account_id) -> InstagramAccount:
    async def query(session):
        return await session.scalar(
            select(InstagramAccount)
            .options(undefer(InstagramAccount.access_token_ciphertext))
            .where(InstagramAccount.id == account_id)
        )

    return db.run(query)


def test_accounts_are_isolated_per_organization(api, verifier, db):
    headers_a, org_a = member_headers(db, verifier, Role.VIEWER)
    headers_b, org_b = member_headers(db, verifier, Role.VIEWER)
    add_instagram_account(db, org_a)

    mine = api.get("/api/instagram/accounts", headers=org_headers(headers_a, org_a)).json()
    theirs = api.get("/api/instagram/accounts", headers=org_headers(headers_b, org_b)).json()
    peek = api.get("/api/instagram/accounts", headers=org_headers(headers_b, org_a))

    assert [a["username"] for a in mine["items"]] == ["acme.store"]
    assert theirs["items"] == []
    assert peek.status_code == 403


def test_disconnect_requires_admin(api, verifier, db):
    headers, organization = member_headers(db, verifier, Role.AGENT)
    account = add_instagram_account(db, organization)
    response = api.delete(
        f"/api/instagram/accounts/{account.id}", headers=org_headers(headers, organization)
    )
    assert response.status_code == 403


def test_cannot_disconnect_another_organizations_account(api, verifier, db):
    headers, organization = member_headers(db, verifier, Role.OWNER)
    _, other = member_headers(db, verifier, Role.OWNER)
    account = add_instagram_account(db, other)

    response = api.delete(
        f"/api/instagram/accounts/{account.id}", headers=org_headers(headers, organization)
    )

    assert response.status_code == 404
    assert load(db, account.id).connection_status == ConnectionStatus.CONNECTED


def test_disconnect_destroys_token_and_frees_the_account(api, verifier, db):
    headers, organization = member_headers(db, verifier, Role.ADMIN)
    account = add_instagram_account(db, organization, access_token_ciphertext="encrypted")

    response = api.delete(
        f"/api/instagram/accounts/{account.id}", headers=org_headers(headers, organization)
    )

    assert response.status_code == 204
    stored = load(db, account.id)
    assert stored.connection_status == ConnectionStatus.DISCONNECTED
    assert stored.access_token_ciphertext is None
    assert stored.disconnected_at is not None
    listed = api.get("/api/instagram/accounts", headers=org_headers(headers, organization))
    assert listed.json()["items"] == []
    # Another organization may now connect the same Instagram account.
    _, other = member_headers(db, verifier, Role.OWNER)
    add_instagram_account(db, other)


@pytest.mark.parametrize(
    ("fail", "expires_in", "expected_status", "refreshed"),
    [
        (False, timedelta(days=3), ConnectionStatus.CONNECTED, True),
        (True, timedelta(days=3), ConnectionStatus.NEEDS_REAUTH, False),
        (False, timedelta(days=-1), ConnectionStatus.NEEDS_REAUTH, False),
        (False, timedelta(days=30), ConnectionStatus.CONNECTED, False),
    ],
)
def test_token_refresh(
    db, verifier, instagram, instagram_provider, fail, expires_in, expected_status, refreshed
):
    _, organization = member_headers(db, verifier, Role.OWNER)
    account = add_instagram_account(
        db,
        organization,
        access_token_ciphertext=instagram.cipher.encrypt("old-token"),
        token_expires_at=utcnow() + expires_in,
    )
    if fail:
        instagram_provider.fail_on = "refresh_token"

    db.run(lambda session: refresh_expiring_tokens(session, instagram))

    stored = load(db, account.id)
    assert stored.connection_status == expected_status
    token = instagram.cipher.decrypt(stored.access_token_ciphertext)
    assert token == ("old-token-refreshed" if refreshed else "old-token")
