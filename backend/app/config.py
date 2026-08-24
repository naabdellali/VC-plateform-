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

    # Gemini (Google AI Studio) - free-tier LLM provider, kept as a fallback but
    # NO LONGER preferred (see mistral_api_key below) - in production this
    # platform hit gemini-2.5-flash being retired for new users within months,
    # then discovered gemini-3.6-flash's free tier caps at a hard 20
    # requests/DAY (GenerateRequestsPerDayPerProjectPerModel-FreeTier quota) -
    # too low for even a single deck upload's ~20-25 sequential LLM calls. See
    # llm_client.py's logging for how this was diagnosed from Render's log
    # stream. Left in place (not deleted) as a working fallback provider, not
    # because it's recommended.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"

    # Mistral AI - now the PREFERRED free-tier provider (checked first in
    # LlmClient.__init__), added after Gemini's free tier proved too
    # unreliable for this workload (see gemini_api_key comment above).
    # Mistral's free "Experiment" plan (console.mistral.ai / admin.mistral.ai,
    # no credit card - just phone verification) has a much higher published
    # ceiling (1 req/sec, 500K tokens/minute, 1B tokens/month at the time this
    # was added) than Gemini's free flash tier ever offered. IMPORTANT DATA
    # PRIVACY NOTE (verified directly against Mistral's help center, not
    # assumed): Experiment-plan data IS used to train Mistral's models BY
    # DEFAULT - there is a real opt-out toggle (admin.mistral.ai -> API ->
    # Privacy -> "Anonymous improvement data"), but it is OFF by default and
    # must be manually switched before sending confidential deck content.
    # This is a materially different default than Gemini's free tier, which
    # has no opt-out at all - so Mistral is not just "free" but "free with an
    # actual privacy control", provided that control is actually flipped.
    mistral_api_key: str | None = None
    # Versioned model id, not the "-latest" alias - Mistral's alias-resolution
    # behavior wasn't confirmed stable at the time this was added, and this
    # project has already been burned twice by an LLM provider silently
    # repointing/retiring a model name (see gemini_model history above).
    # Override via MISTRAL_MODEL if this specific version is retired later.
    mistral_model: str = "mistral-small-2603"

    tavily_api_key: str | None = None
    pappers_api_key: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_available(self) -> bool:
        return bool(self.mistral_api_key or self.gemini_api_key or self.anthropic_api_key)

    @property
    def search_available(self) -> bool:
        return bool(self.tavily_api_key)

    @property
    def pappers_available(self) -> bool:
        return bool(self.pappers_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
