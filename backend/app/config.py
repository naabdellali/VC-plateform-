"""
Central configuration. Every external integration is optional at boot time:
if a key is missing, the corresponding client runs in MOCK MODE (clearly
labelled in every Evidence object it produces) instead of crashing the app.
This lets the platform be cloned and run end-to-end before any API key
has been configured, per the "never fabricate silently" principle -
mock data is always tagged as such, never presented as verified evidence.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./vcip.db"
    cors_origins: str = "http://localhost:3000"
    secret_key: str = "change-me-in-production"

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-5"

    tavily_api_key: str | None = None
    pappers_api_key: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_available(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def search_available(self) -> bool:
        return bool(self.tavily_api_key)

    @property
    def pappers_available(self) -> bool:
        return bool(self.pappers_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
