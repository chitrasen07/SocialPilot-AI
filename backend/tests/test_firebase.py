import asyncio

import pytest
from firebase_admin import auth

from app.core import firebase
from app.core.config import Settings
from app.core.errors import AppError
from app.core.firebase import FirebaseTokenVerifier, create_token_verifier


def verify_with(monkeypatch, behaviour) -> firebase.VerifiedIdentity:
    def fake_verify_id_token(token, app=None):
        if isinstance(behaviour, Exception):
            raise behaviour
        return behaviour

    monkeypatch.setattr(auth, "verify_id_token", fake_verify_id_token)
    return asyncio.run(FirebaseTokenVerifier(app=object()).verify("id-token"))


def test_valid_token_maps_claims_to_identity(monkeypatch):
    identity = verify_with(
        monkeypatch,
        {
            "uid": "uid-1",
            "email": "a@example.com",
            "email_verified": True,
            "name": "Asha",
            "picture": "https://img.example.com/a.png",
        },
    )
    assert identity == firebase.VerifiedIdentity(
        uid="uid-1",
        email="a@example.com",
        email_verified=True,
        name="Asha",
        picture="https://img.example.com/a.png",
    )


@pytest.mark.parametrize(
    ("error", "code", "status"),
    [
        (auth.InvalidIdTokenError("sdk: bad signature"), "INVALID_TOKEN", 401),
        (auth.ExpiredIdTokenError("sdk: token expired", cause=None), "TOKEN_EXPIRED", 401),
        (ValueError("sdk: empty token"), "INVALID_TOKEN", 401),
        (auth.CertificateFetchError("sdk: network", cause=None), "AUTH_UNAVAILABLE", 503),
    ],
)
def test_firebase_errors_map_to_safe_app_errors(monkeypatch, error, code, status):
    with pytest.raises(AppError) as exc_info:
        verify_with(monkeypatch, error)
    assert (exc_info.value.code, exc_info.value.status_code) == (code, status)
    assert str(error) not in exc_info.value.message


def test_verifier_is_not_created_without_credentials():
    assert create_token_verifier(Settings(firebase_project_id="p")) is None


def test_private_key_escaped_newlines_are_restored(monkeypatch):
    captured = {}

    def fake_get_app(name):
        raise ValueError("no app")

    monkeypatch.setattr(firebase.firebase_admin, "get_app", fake_get_app)
    monkeypatch.setattr(firebase.credentials, "Certificate", lambda info: captured.update(info))
    monkeypatch.setattr(
        firebase.firebase_admin, "initialize_app", lambda cred, options, name: object()
    )
    settings = Settings(
        firebase_project_id="p",
        firebase_client_email="svc@p.iam.gserviceaccount.com",
        firebase_private_key="-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n",
    )

    assert create_token_verifier(settings) is not None
    assert (
        captured["private_key"] == "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n"
    )
