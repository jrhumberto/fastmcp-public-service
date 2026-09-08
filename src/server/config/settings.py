"""
Application settings via Pydantic BaseSettings.
All values can be overridden via environment variables or .env file.
"""

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Server
    service_name: str = "fastmcp-production-template"
    service_description: str = (
        "Production-grade MCP server with async DB, observability, and security"
    )
    port: int = 8000
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql://user:password@localhost:5432/mcpdb"
    db_pool_min: int = 5
    db_pool_max: int = 20

    # Security
    allowlist_path: str = "config/allowlist.yaml"
    api_key_enabled: bool = True
    api_key: str = "change-me-in-production"

    # Observability
    otel_enabled: bool = True
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "fastmcp-production-template"

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith(("postgresql://", "postgres://")):
            raise ValueError("DATABASE_URL must be a valid PostgreSQL connection string")
        return v

    @model_validator(mode="after")
    def validate_api_key_in_production(self) -> "Settings":
        if (
            self.api_key_enabled
            and self.log_level.upper() != "DEBUG"
            and self.api_key == "change-me-in-production"
        ):
            raise ValueError(
                "API_KEY must be changed from the default value before running in production. "
                "Set LOG_LEVEL=DEBUG to bypass this check in development."
            )
        return self
