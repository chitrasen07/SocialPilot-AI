from app.core.errors import AppError


def ai_not_configured() -> AppError:
    return AppError(
        "AI_NOT_CONFIGURED",
        "AI is not configured yet.",
        503,
    )


def ai_disabled() -> AppError:
    return AppError("AI_DISABLED", "AI is turned off for this workspace.", 403)


def ai_timeout() -> AppError:
    return AppError("AI_PROVIDER_TIMEOUT", "AI service timed out. Please try again.", 504)


def ai_provider_failed() -> AppError:
    return AppError("AI_PROVIDER_ERROR", "The AI provider could not complete the request.", 502)


def ai_guardrail_blocked() -> AppError:
    return AppError(
        "AI_GUARDRAIL_BLOCKED",
        "AI draft could not be generated safely.",
        422,
    )


def draft_not_found() -> AppError:
    return AppError("DRAFT_NOT_FOUND", "Draft not found.", 404)


def draft_state() -> AppError:
    return AppError("DRAFT_STATE", "This draft can't be changed that way.", 409)


def draft_not_approvable() -> AppError:
    return AppError(
        "DRAFT_NOT_APPROVABLE",
        "This draft still needs changes before it can be approved.",
        422,
    )


def ai_rate_limited() -> AppError:
    return AppError(
        "AI_RATE_LIMITED",
        "AI request limit reached. Please try again later.",
        429,
    )
