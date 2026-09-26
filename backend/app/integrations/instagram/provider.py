from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class TokenGrant:
    access_token: str
    expires_at: datetime | None
    scopes: list[str]


@dataclass(frozen=True)
class InstagramProfile:
    account_id: str
    username: str
    account_type: str | None


class InstagramProviderError(Exception):
    """A failed call to the Instagram platform. `message` is safe to log; never contains tokens."""

    def __init__(self, message: str, *, needs_reauth: bool = False) -> None:
        super().__init__(message)
        self.needs_reauth = needs_reauth


class InstagramProvider(Protocol):
    def authorization_url(self, state: str) -> str: ...

    async def exchange_code(self, code: str) -> TokenGrant: ...

    async def refresh_token(self, access_token: str) -> TokenGrant: ...

    async def get_profile(self, access_token: str) -> InstagramProfile: ...

    async def subscribe_webhooks(self, access_token: str) -> None: ...
