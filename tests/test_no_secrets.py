"""Guard against committing API keys.

1. If a local .env exists, its actual key values must not appear in any tracked file.
2. Generic patterns (OpenRouter keys, `api_key=` query strings, bare 64-hex SerpApi-style keys)
   must not appear either. Recordings are exempt from the bare-hex rule because their cache
   keys are SHA-256 digests.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERIC = [re.compile(r"sk-or-v1-[a-f0-9]{32,}"), re.compile(r"(?i)api_key=[a-z0-9]{20,}")]
BARE_HEX = re.compile(r"(?<![a-f0-9])[a-f0-9]{64}(?![a-f0-9])")
SKIP_SUFFIX = {".jpg", ".png", ".webp", ".lock"}


def tracked_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [ROOT / p for p in out.splitlines()]
    except Exception:  # noqa: BLE001
        return [p for p in ROOT.rglob("*") if p.is_file() and not {".venv", ".git", "data"} & set(p.parts)]


def local_secrets() -> list[str]:
    env = ROOT / ".env"
    if not env.exists():
        return []
    values = []
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            value = line.split("=", 1)[1].strip().strip("\"'")
            if len(value) >= 20:
                values.append(value)
    return values


def test_no_api_keys_in_repository():
    secrets = local_secrets()
    offenders = []
    for path in tracked_files():
        if path.name == ".env" or path.suffix in SKIP_SUFFIX or not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if any(s in text for s in secrets):
            offenders.append(f"{rel}: contains a key from .env")
        patterns = GENERIC + ([] if "/demo/recordings/" in f"/{rel}" or rel.startswith("tests/fixtures/") else [BARE_HEX])
        for rx in patterns:
            if rx.search(text):
                offenders.append(f"{rel}: matches {rx.pattern[:20]}")
    assert not offenders, offenders


def test_env_is_ignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in gitignore
