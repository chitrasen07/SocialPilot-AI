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


def ai_rate_limited() -> AppError:
    return AppError(
        "AI_RATE_LIMITED",
        "AI request limit reached. Please try again later.",
        429,
    )
