from __future__ import annotations

import json
from pathlib import Path

import pytest

from scamurai.config import PACKAGE_DIR, Settings, get_settings

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / "serp" / name).read_text(encoding="utf-8"))


def scenarios() -> list[dict]:
    return json.loads((PACKAGE_DIR / "demo" / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]


@pytest.fixture
def replay_settings(tmp_path, monkeypatch) -> Settings:
    """Replay mode, isolated data dir, no keys: tests never touch the network."""
    monkeypatch.setenv("SCAMURAI_MODE", "replay")
    monkeypatch.setenv("SCAMURAI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SERPAPI_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    get_settings.cache_clear()
    settings = Settings(_env_file=None)
    yield settings
    get_settings.cache_clear()
