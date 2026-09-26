import logging
from dataclasses import dataclass
from typing import Protocol

import firebase_admin
from firebase_admin import auth, credentials
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.errors import AppError

logger = logging.getLogger("socialpilot.auth")

FIREBASE_APP_NAME = "socialpilot"


@dataclass(frozen=True)
class VerifiedIdentity:
    uid: str
    email: str | None
    email_verified: bool
    name: str | None
    picture: str | None


class TokenVerifier(Protocol):
    async def verify(self, token: str) -> VerifiedIdentity: ...


class FirebaseTokenVerifier:
    def __init__(self, app: firebase_admin.App) -> None:
        self._app = app

    async def verify(self, token: str) -> VerifiedIdentity:
        try:
            # Blocking call (fetches Google's cached public certs); keep it off the event loop.
            claims = await run_in_threadpool(auth.verify_id_token, token, app=self._app)
        except auth.ExpiredIdTokenError as exc:
            raise AppError(
                "TOKEN_EXPIRED", "Your session has expired. Sign in again.", 401
            ) from exc
        except auth.CertificateFetchError as exc:
            logger.error("firebase_cert_fetch_failed")
            raise AppError(
                "AUTH_UNAVAILABLE", "Authentication is temporarily unavailable.", 503
            ) from exc
        except (auth.InvalidIdTokenError, ValueError) as exc:
            raise AppError("INVALID_TOKEN", "The authentication token is invalid.", 401) from exc

        return VerifiedIdentity(
            uid=claims["uid"],
            email=claims.get("email"),
            email_verified=bool(claims.get("email_verified", False)),
            name=claims.get("name"),
            picture=claims.get("picture"),
        )


def create_token_verifier(settings: Settings) -> FirebaseTokenVerifier | None:
    """Returns None when Firebase Admin credentials are not configured."""
    project_id = settings.firebase_project_id
    client_email = settings.firebase_client_email
    private_key = settings.firebase_private_key
    if not (project_id and client_email and private_key):
        return None

    try:
        app = firebase_admin.get_app(FIREBASE_APP_NAME)
    except ValueError:
        credential = credentials.Certificate(
            {
                "type": "service_account",
                "project_id": project_id,
                "client_email": client_email,
                # .env files usually store the PEM on one line with literal "\n" sequences.
                "private_key": private_key.get_secret_value().replace("\\n", "\n"),
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        )
        app = firebase_admin.initialize_app(
            credential, {"projectId": project_id}, name=FIREBASE_APP_NAME
        )
    return FirebaseTokenVerifier(app)
