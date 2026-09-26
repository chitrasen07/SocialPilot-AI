from app.core.config import Settings


def test_plain_postgres_url_uses_asyncpg_driver(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db:5432/app")
    assert str(Settings().database_url).startswith("postgresql+asyncpg://")


def test_blank_credentials_count_as_unconfigured(monkeypatch):
    monkeypatch.setenv("META_APP_SECRET", "")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEYS", "  ")
    settings = Settings()
    assert settings.meta_app_secret is None
    assert settings.token_encryption_keys is None


def test_cors_origins_accepts_comma_separated_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com, http://localhost:5173")
    assert Settings().cors_origins == ["https://app.example.com", "http://localhost:5173"]
