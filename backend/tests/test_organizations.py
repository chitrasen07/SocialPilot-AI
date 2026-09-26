import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import require_role
from app.main import create_app
from app.models import Role
from tests.conftest import member_headers


def test_list_only_returns_callers_organizations(api, verifier, db):
    headers, mine = member_headers(db, verifier, Role.VIEWER, name="Mine")
    member_headers(db, verifier, Role.OWNER, name="Someone else's")

    body = api.get("/api/organizations", headers=headers).json()

    assert [item["id"] for item in body["items"]] == [str(mine.id)]


def test_member_can_read_organization(api, verifier, db):
    headers, organization = member_headers(db, verifier, Role.VIEWER, name="Acme")
    response = api.get(f"/api/organizations/{organization.id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Acme"
    assert response.json()["role"] == "viewer"


@pytest.mark.parametrize("target", ["other", "missing"])
def test_non_member_is_denied(api, verifier, db, target):
    headers, _ = member_headers(db, verifier, Role.OWNER)
    _, other = member_headers(db, verifier, Role.OWNER)
    organization_id = other.id if target == "other" else uuid.uuid4()

    for method in ("get", "patch"):
        response = api.request(
            method, f"/api/organizations/{organization_id}", headers=headers, json={"name": "x"}
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "ORGANIZATION_ACCESS_DENIED"


@pytest.mark.parametrize(
    ("role", "allowed"),
    [(Role.VIEWER, False), (Role.AGENT, False), (Role.ADMIN, True), (Role.OWNER, True)],
)
def test_renaming_organization_requires_admin(api, verifier, db, role, allowed):
    headers, organization = member_headers(db, verifier, role, name="Before")
    url = f"/api/organizations/{organization.id}"

    response = api.patch(url, headers=headers, json={"name": "  After  "})

    if allowed:
        assert response.status_code == 200
        assert response.json()["name"] == "After"
    else:
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"
    expected = "After" if allowed else "Before"
    assert api.get(url, headers=headers).json()["name"] == expected


def test_rename_validates_name(api, verifier, db):
    headers, organization = member_headers(db, verifier, Role.OWNER)
    response = api.patch(
        f"/api/organizations/{organization.id}", headers=headers, json={"name": "   "}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.fixture
def agent_route_client(db, verifier):
    """An app with a representative agent-level operation that resolves the organization
    from the X-Organization-Id header, as future org-scoped endpoints will."""
    from fastapi import Depends

    app = create_app()

    @app.post("/api/_agent-action", dependencies=[Depends(require_role(Role.AGENT))])
    async def agent_action() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        app.state.token_verifier = verifier
        yield client


@pytest.mark.parametrize(
    ("role", "status"),
    [(Role.VIEWER, 403), (Role.AGENT, 200), (Role.ADMIN, 200), (Role.OWNER, 200)],
)
def test_agent_operations_via_organization_header(agent_route_client, verifier, db, role, status):
    headers, organization = member_headers(db, verifier, role)
    response = agent_route_client.post(
        "/api/_agent-action", headers=headers | {"X-Organization-Id": str(organization.id)}
    )
    assert response.status_code == status


@pytest.mark.parametrize(
    ("header", "code"),
    [(None, "ORGANIZATION_REQUIRED"), ("not-a-uuid", "INVALID_ORGANIZATION_ID")],
)
def test_organization_header_must_be_valid(agent_route_client, verifier, db, header, code):
    headers, _ = member_headers(db, verifier, Role.OWNER)
    if header:
        headers["X-Organization-Id"] = header
    response = agent_route_client.post("/api/_agent-action", headers=headers)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == code
