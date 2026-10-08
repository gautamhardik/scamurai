"""Runtime configuration, read from environment variables and `.env`."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent

# Free OpenRouter models, tried in order (OpenRouter `models` fallback). Free models churn:
# `scamurai doctor` verifies these still exist.
VISION_MODELS = [
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "dots-studio/dots-3-note-preview:free",
]
# Nemotron first: it answered 46 of 49 live reads anyway (Gemma is usually rate-limited on the free pool,
# and took 41 s the one time it answered).
TEXT_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-31b-it:free",
    "dots-studio/dots-3-note-preview:free",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    serpapi_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None

    scamurai_mode: Literal["live", "replay"] = "live"
    scamurai_data_dir: Path = Path("data")
    scamurai_recordings_dir: Path = PACKAGE_DIR / "demo" / "recordings"

    # SerpApi budget
    scamurai_max_searches: int = 8
    scamurai_daily_search_cap: int = 80
    scamurai_min_credits_reserve: int = 10
    scamurai_cache_ttl_hours: float | None = None
    scamurai_serp_concurrency: int = 4
    scamurai_serp_timeout_s: float = 25
    # Ask SerpApi for fresh results instead of its own one-hour cache (costs a credit per search; for demos and benchmarks)
    scamurai_serpapi_no_cache: bool = False
    scamurai_lens_timeout_s: float = 90  # Lens on an uploaded screenshot measured 40-47 s
    scamurai_jobs_timeout_s: float = 60  # Google Jobs routinely takes 25-50 s
    scamurai_search_phase_budget_s: float = 110

    # LLM
    scamurai_vision_models: list[str] = Field(default_factory=lambda: list(VISION_MODELS))
    scamurai_text_models: list[str] = Field(default_factory=lambda: list(TEXT_MODELS))
    scamurai_llm_timeout_s: float = 120
    scamurai_llm_max_tokens: int = 6000
    # Extraction copies facts; it doesn't need the model to "think". Measured on the same message with
    # Nemotron: reasoning off 2.6 s / 317 tokens vs low 22.2 s / 2,061 tokens, with identical extraction.
    scamurai_llm_reasoning: Literal["off", "low", "medium", "high"] = "off"

    # Storage / privacy
    scamurai_store_reports: bool = True
    scamurai_report_retention_days: int = 7

    # Web
    scamurai_host: str = "127.0.0.1"
    scamurai_port: int = 8000
    scamurai_access_token: SecretStr | None = None
    # Extra Host names to serve besides 127.0.0.1/localhost (comma-separated), e.g. when deployed.
    scamurai_allowed_hosts: str = ""
    scamurai_rate_limit_per_10min: int = 6
    scamurai_max_concurrent_investigations: int = 2

    @property
    def db_path(self) -> Path:
        return self.scamurai_data_dir / "scamurai.sqlite3"

    @property
    def serpapi_configured(self) -> bool:
        return bool(self.serpapi_api_key and self.serpapi_api_key.get_secret_value().strip())

    @property
    def llm_configured(self) -> bool:
        return bool(self.openrouter_api_key and self.openrouter_api_key.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
