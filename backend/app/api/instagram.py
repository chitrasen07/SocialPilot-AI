import logging
import uuid
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse

from app.api.deps import SessionDep, require_role
from app.core.errors import AppError
from app.models import OrganizationMember, Role
from app.schemas.instagram import ConnectResponse, InstagramAccountList, InstagramAccountOut
from app.services import instagram as service
from app.services.instagram import InstagramClients

router = APIRouter(prefix="/api/instagram", tags=["instagram"])
logger = logging.getLogger("socialpilot.instagram")

OAUTH_COOKIE = "sp_ig_oauth"
CALLBACK_PATH = "/api/instagram/callback"

Viewer = Annotated[OrganizationMember, Depends(require_role(Role.VIEWER))]
Manager = Annotated[OrganizationMember, Depends(require_role(service.MANAGE_ROLE))]


def get_clients(request: Request) -> InstagramClients:
    clients: InstagramClients | None = request.app.state.instagram
    if clients is None:
        raise AppError(
            "INSTAGRAM_NOT_CONFIGURED",
            "Instagram integration is not configured on this server.",
            503,
        )
    return clients


Clients = Annotated[InstagramClients, Depends(get_clients)]


@router.post("/connect")
async def connect(
    request: Request, response: Response, membership: Manager, clients: Clients
) -> ConnectResponse:
    pending = await service.start_connection(request.app.state.redis, clients.provider, membership)
    response.set_cookie(
        OAUTH_COOKIE,
        pending.browser_nonce,
        max_age=service.OAUTH_STATE_TTL_SECONDS,
        path=CALLBACK_PATH,
        httponly=True,
        secure=request.app.state.settings.is_production,
        # Lax is required: the callback is a top-level cross-site navigation from Instagram.
        samesite="lax",
    )
    return ConnectResponse(authorization_url=pending.authorization_url)


@router.get("/callback", include_in_schema=False)
async def callback(
    request: Request,
    session: SessionDep,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Browser redirect target from Instagram. Always redirects back to the frontend with a
    result code; never renders tokens or provider error details."""
    result: dict[str, str] = {"instagram": "connected"}
    try:
        clients = get_clients(request)
        context = await service.consume_state(
            request.app.state.redis, state, request.cookies.get(OAUTH_COOKIE)
        )
        if error:
            raise AppError(
                "INSTAGRAM_AUTHORIZATION_DENIED", "Instagram authorization was cancelled."
            )
        if not code:
            raise AppError("OAUTH_CODE_MISSING", "Instagram did not return an authorization code.")
        await service.complete_connection(session, clients, context, code)
    except AppError as exc:
        logger.warning("instagram_connect_failed", extra={"fields": {"code": exc.code}})
        result = {"instagram_error": exc.code}

    frontend = request.app.state.settings.frontend_url.rstrip("/")
    redirect = RedirectResponse(f"{frontend}/integrations?{urlencode(result)}", status_code=303)
    redirect.delete_cookie(OAUTH_COOKIE, path=CALLBACK_PATH)
    return redirect


@router.get("/accounts")
async def list_accounts(membership: Viewer, session: SessionDep) -> InstagramAccountList:
    accounts = await service.list_accounts(session, membership.organization_id)
    return InstagramAccountList(items=[InstagramAccountOut.model_validate(a) for a in accounts])


@router.delete("/accounts/{account_id}", status_code=204)
async def disconnect(account_id: uuid.UUID, membership: Manager, session: SessionDep) -> None:
    await service.disconnect_account(session, membership.organization_id, account_id)
