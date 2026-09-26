import pytest
from fastapi.testclient import TestClient

from app.main import create_app


class FakeRedis:
    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy

    async def ping(self) -> bool:
        if not self.healthy:
            raise ConnectionError("redis down")
        return True

    async def aclose(self) -> None:
        pass


class FakeConnection:
    def __init__(self, has_vector: bool) -> None:
        self.has_vector = has_vector

    async def __aenter__(self) -> "FakeConnection":
        return self

    async def __aexit__(self, *exc: object) -> None:
        pass

    async def scalar(self, _statement: object) -> bool:
        return self.has_vector


class FakeEngine:
    def __init__(self, healthy: bool = True, has_vector: bool = True) -> None:
        self.healthy = healthy
        self.has_vector = has_vector

    def connect(self) -> FakeConnection:
        if not self.healthy:
            raise ConnectionError("database down")
        return FakeConnection(self.has_vector)

    async def dispose(self) -> None:
        pass


@pytest.fixture
def client():
    app = create_app()

    @app.get("/api/_boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    with TestClient(app) as test_client:
        app.state.engine = FakeEngine()
        app.state.redis = FakeRedis()
        yield test_client


def test_liveness_returns_generated_request_id(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(response.headers["x-request-id"]) == 32


def test_incoming_request_id_is_echoed(client):
    response = client.get("/api/health", headers={"x-request-id": "abc123"})
    assert response.headers["x-request-id"] == "abc123"


def test_unknown_route_uses_error_envelope(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "NOT_FOUND", "message": "Not Found"}}


def test_unhandled_exception_hides_internals_and_keeps_request_id(client):
    response = client.get("/api/_boom", headers={"x-request-id": "req-1"})
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}
    }
    assert "secret internal detail" not in response.text
    assert response.headers["x-request-id"] == "req-1"


def test_readiness_ok_when_dependencies_healthy(client):
    response = client.get("/api/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


@pytest.mark.parametrize(
    ("engine", "redis", "expected"),
    [
        (FakeEngine(healthy=False), FakeRedis(), {"database": "unavailable", "redis": "ok"}),
        (
            FakeEngine(has_vector=False),
            FakeRedis(),
            {"database": "pgvector_missing", "redis": "ok"},
        ),
        (FakeEngine(), FakeRedis(healthy=False), {"database": "ok", "redis": "unavailable"}),
    ],
)
def test_readiness_reports_unhealthy_dependencies(client, engine, redis, expected):
    client.app.state.engine = engine
    client.app.state.redis = redis
    response = client.get("/api/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert response.json()["error"]["details"] == expected
