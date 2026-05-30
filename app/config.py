"""Application configuration loaded from environment variables.

All settings are evaluated once at startup. Missing required values fail
fast so we never silently run with bad defaults.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────
    app_name: str = "uod-backend"
    environment: str = Field(
        default="development", description="development | staging | production"
    )
    debug: bool = False

    # ── Database ─────────────────────────────────────────────────────
    # async URL form, e.g. postgresql+asyncpg://user:pwd@host/db
    database_url: str = Field(..., description="Postgres async DSN (postgresql+asyncpg://...)")

    # ── Auth ─────────────────────────────────────────────────────────
    # Reuse Studio's NextAuth secret so the same JWT validates here.
    # In Phase A.3 we'll switch verification to NextAuth's JWE format.
    # For now the test suite issues HS256 JWS tokens against this secret.
    nextauth_secret: str = Field(
        ..., description="HMAC secret shared with Studio for JWT verification"
    )
    jwt_algorithm: str = "HS256"
    jwt_audience: str | None = None

    # ── CORS ─────────────────────────────────────────────────────────
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="Studio origins permitted to call this API",
    )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton accessor — kept inside a function so tests can override."""
    return Settings()  # type: ignore[call-arg]
