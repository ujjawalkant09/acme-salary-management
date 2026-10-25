from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables (or a local `.env`)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Required. The sync form (`postgresql+psycopg://…`), which Alembic uses as is.
    database_url: str
    # Required: the app refuses to start without it. Signs the session cookie and file links.
    secret_key: str = Field(min_length=16)
    session_cookie_secure: bool = True
    session_max_age_seconds: int = 60 * 60 * 12

    # Used only by the seed script to create the two demo logins.
    demo_admin_password: str | None = None
    demo_viewer_password: str | None = None

    fx_api_url: str = "https://api.frankfurter.dev/v1/latest"
    storage_dir: Path = Path("./storage")
    max_upload_mb: int = 10
    max_import_rows: int = 20_000
    rate_limit_enabled: bool = True
    rate_limit_storage_url: str = "memory://"
    cors_origins: list[str] = []
    log_level: str = "INFO"
    frontend_dist: Path = Path("../frontend/dist")
    # Set in the image at build time; empty when running from source.
    git_commit: str | None = None

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
