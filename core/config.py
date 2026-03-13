"""
core/config.py
--------------
All configuration read from environment variables / .env file.
Import the `settings` singleton wherever config values are needed.
"""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────────────
    POSTGRES_USER:     str = Field(default="storageuser")
    POSTGRES_PASSWORD: str = Field(default="storagepass")
    POSTGRES_DB:       str = Field(default="ministorage")
    POSTGRES_HOST:     str = Field(default="db")
    POSTGRES_PORT:     int = Field(default=5432)

    # ── Storage ───────────────────────────────────────────────────────────────
    STORAGE_ROOT:       str = Field(default="/app/storage")
    MAX_UPLOAD_SIZE_MB: int = Field(default=100)     # per-file hard limit

    # ── App ───────────────────────────────────────────────────────────────────
    APP_ENV:   str = Field(default="development")
    LOG_LEVEL: str = Field(default="INFO")

    # ── Pagination ────────────────────────────────────────────────────────────
    DEFAULT_PAGE_SIZE: int = Field(default=20)
    MAX_PAGE_SIZE:     int = Field(default=100)

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def MAX_UPLOAD_BYTES(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Single instance imported everywhere
settings = Settings()
