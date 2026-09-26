import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models import Organization, OrganizationMember, Role, User
from app.services.accounts import sync_user
from tests.conftest import make_identity

PROTECTED = [("get", "/api/me"), ("post", "/api/auth/sync"), ("get", "/api/organizations")]


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_missing_token_is_rejected(api, method, path):
    response = api.request(method, path)
    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "AUTHENTICATION_REQUIRED", "message": "Authentication is required."}
    }


def test_non_bearer_scheme_is_rejected(api):
    response = api.get("/api/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_unknown_token_is_rejected(api):
    response = api.get("/api/me", headers={"Authorization": "Bearer forged"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


def test_unconfigured_firebase_returns_503(api):
    api.app.state.token_verifier = None
    response = api.get("/api/me", headers={"Authorization": "Bearer anything"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"


def test_unverified_email_cannot_sync(api, verifier, db):
    headers = verifier.register(make_identity(email_verified=False))
    response = api.post("/api/auth/sync", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"
    assert db.count(User) == 0


def test_me_requires_prior_sync(api, verifier):
    response = api.get("/api/me", headers=verifier.register(make_identity()))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "USER_NOT_FOUND"


def test_first_sync_creates_user_workspace_and_owner_membership(api, verifier, db):
    headers = verifier.register(make_identity("uid-new", name="Asha Rao"))

    response = api.post("/api/auth/sync", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["is_new_user"] is True
    assert body["user"]["email"] == "uid-new@example.com"
    assert body["user"]["last_login_at"] is not None
    [organization] = body["organizations"]
    assert organization["name"] == "Asha Rao's Workspace"
    assert organization["role"] == "owner"
    assert organization["slug"].startswith("asha-rao-s-workspace-")
    assert (db.count(User), db.count(Organization), db.count(OrganizationMember)) == (1, 1, 1)


def test_repeat_sync_updates_login_without_duplicates(api, verifier, db):
    headers = verifier.register(make_identity("uid-1", name="Asha"))
    first = api.post("/api/auth/sync", headers=headers).json()

    # Email sign-up tokens can omit the name; the stored name must not be wiped.
    headers = verifier.register(make_identity("uid-1", name=None, picture="https://x/a.png"))
    second = api.post("/api/auth/sync", headers=headers).json()

    assert second["is_new_user"] is False
    assert second["user"]["id"] == first["user"]["id"]
    assert second["user"]["name"] == "Asha"
    assert second["user"]["avatar_url"] == "https://x/a.png"
    assert second["user"]["last_login_at"] > first["user"]["last_login_at"]
    assert second["organizations"] == first["organizations"]
    assert (db.count(User), db.count(Organization), db.count(OrganizationMember)) == (1, 1, 1)


def test_concurrent_first_logins_create_exactly_one_user_and_workspace(db):
    identity = make_identity("uid-race")

    async def race() -> list[bool]:
        engine = create_async_engine(db.url, poolclass=NullPool)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

        async def attempt() -> bool:
            async with sessionmaker() as session:
                _, is_new = await sync_user(session, identity)
                return is_new

        try:
            return await asyncio.gather(*(attempt() for _ in range(5)))
        finally:
            await engine.dispose()

    results = asyncio.run(race())

    assert results.count(True) == 1
    assert (db.count(User), db.count(Organization), db.count(OrganizationMember)) == (1, 1, 1)


def test_me_returns_all_memberships(api, verifier, db):
    headers = verifier.register(make_identity("uid-multi"))
    api.post("/api/auth/sync", headers=headers)

    async def load_user(session):
        return await session.scalar(select(User).where(User.firebase_uid == "uid-multi"))

    db.add_member(user=db.run(load_user), role=Role.AGENT, name="Client Co")

    body = api.get("/api/me", headers=headers).json()
    assert [(o["name"], o["role"]) for o in body["organizations"]] == [
        ("Asha Rao's Workspace", "owner"),
        ("Client Co", "agent"),
    ]
