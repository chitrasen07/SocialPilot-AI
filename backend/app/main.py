import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.ai.factory import build_ai
from app.ai.orchestrator import AIOrchestrator
from app.api import (
    ai,
    analytics,
    auth,
    automation,
    channels,
    conversations,
    customers,
    health,
    instagram,
    intelligence,
    knowledge,
    notifications,
    organizations,
    suggestions,
    tasks,
    webhooks,
)
from app.api.deps import ORGANIZATION_HEADER
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.firebase import create_token_verifier
from app.core.observability import REQUEST_ID_HEADER, RequestContextMiddleware, configure_logging
from app.db.session import create_engine, create_sessionmaker
from app.integrations.http import create_http_client
from app.services.instagram import create_instagram_clients

logger = logging.getLogger("socialpilot.app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.token_verifier = create_token_verifier(settings)
        if app.state.token_verifier is None:
            if settings.is_production:
                raise RuntimeError("Firebase Admin credentials are required in production.")
            logger.warning("firebase_not_configured")
        app.state.engine = create_engine(settings)
        app.state.sessionmaker = create_sessionmaker(app.state.engine)
        app.state.redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
        app.state.http = create_http_client()
        app.state.instagram = create_instagram_clients(settings, app.state.http)
        if app.state.instagram is None:
            logger.warning("instagram_not_configured")
        built = build_ai(settings)
        provider, embeddings = built if built else (None, None)
        app.state.ai_orchestrator = AIOrchestrator(provider, embeddings, settings)
        try:
            yield
        finally:
            await app.state.http.aclose()
            await app.state.redis.aclose()
            await app.state.engine.dispose()

    app = FastAPI(
        title="SocialPilot AI",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/api/openapi.json",
    )
    app.state.settings = settings

    # Starlette wraps middleware in reverse order: CORS is outermost so error responses keep
    # CORS headers.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER, ORGANIZATION_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )
    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(organizations.router)
    app.include_router(instagram.router)
    app.include_router(webhooks.router)
    app.include_router(customers.router)
    app.include_router(suggestions.router)
    app.include_router(analytics.router)
    app.include_router(intelligence.router)
    app.include_router(channels.router)
    app.include_router(automation.router)
    app.include_router(tasks.router)
    app.include_router(notifications.router)
    app.include_router(conversations.router)
    app.include_router(knowledge.router)
    app.include_router(ai.router)
    return app


app = create_app()
