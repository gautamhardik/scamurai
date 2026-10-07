"""Runtime configuration, read from environment variables and `.env`."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent

# Free OpenRouter models, tried in order (OpenRouter `models` fallback). Free models churn:
# `asli doctor` verifies these still exist.
VISION_MODELS = [
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "dots-studio/dots-3-note-preview:free",
]
TEXT_MODELS = [
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "dots-studio/dots-3-note-preview:free",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    serpapi_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None

    asli_mode: Literal["live", "replay"] = "live"
    asli_data_dir: Path = Path("data")
    asli_recordings_dir: Path = PACKAGE_DIR / "demo" / "recordings"

    # SerpApi budget
    asli_max_searches: int = 8
    asli_daily_search_cap: int = 80
    asli_min_credits_reserve: int = 10
    asli_cache_ttl_hours: float | None = None
    asli_serp_concurrency: int = 4
    asli_serp_timeout_s: float = 25
    asli_lens_timeout_s: float = 40
    asli_jobs_timeout_s: float = 60  # Google Jobs routinely takes 25-50 s
    asli_search_phase_budget_s: float = 90

    # LLM
    asli_vision_models: list[str] = Field(default_factory=lambda: list(VISION_MODELS))
    asli_text_models: list[str] = Field(default_factory=lambda: list(TEXT_MODELS))
    asli_llm_timeout_s: float = 120
    asli_llm_max_tokens: int = 6000

    # Storage / privacy
    asli_store_reports: bool = True
    asli_report_retention_days: int = 7

    # Web
    asli_host: str = "127.0.0.1"
    asli_port: int = 8000
    asli_access_token: SecretStr | None = None
    asli_rate_limit_per_10min: int = 6
    asli_max_concurrent_investigations: int = 2

    @property
    def db_path(self) -> Path:
        return self.asli_data_dir / "asli.sqlite3"

    @property
    def serpapi_configured(self) -> bool:
        return bool(self.serpapi_api_key and self.serpapi_api_key.get_secret_value().strip())

    @property
    def llm_configured(self) -> bool:
        return bool(self.openrouter_api_key and self.openrouter_api_key.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
