"""Guard against committing API keys: scans every tracked (or, outside git, every project) text file."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [
    re.compile(r"sk-or-v1-[a-f0-9]{32,}"),             # OpenRouter
    re.compile(r"(?<![a-f0-9])[a-f0-9]{64}(?![a-f0-9])"),  # SerpApi keys are 64 hex chars
    re.compile(r"(?i)api_key=[a-z0-9]{20,}"),
]
ALLOW = {"uv.lock"}


def tracked_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [ROOT / p for p in out.splitlines()]
    except Exception:  # noqa: BLE001
        return [p for p in ROOT.rglob("*") if p.is_file() and ".venv" not in p.parts and ".git" not in p.parts]


def test_no_api_keys_in_repository():
    offenders = []
    for path in tracked_files():
        if path.name in ALLOW or path.name == ".env" or path.suffix in {".jpg", ".png", ".webp"} or not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for rx in PATTERNS:
            for m in rx.finditer(text):
                offenders.append(f"{path.relative_to(ROOT)}: {m.group(0)[:12]}…")
    assert not offenders, offenders


def test_env_is_ignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in gitignore
