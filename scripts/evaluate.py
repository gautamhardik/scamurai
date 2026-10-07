"""Run the evaluation set (eval/messages.json) and report how often Asli gets it right.

    uv run python scripts/evaluate.py                 # rules only: no AI reader, no searches (free)
    uv run python scripts/evaluate.py --live --ids g01_sbi_debit,s07_paytm_kyc_call   # real APIs

Scoring:
  scam       detected when HIGH_RISK or SUSPICIOUS
  genuine    a false alarm when HIGH_RISK or SUSPICIOUS; "confirmed" when LOW_RISK
  ambiguous  correct when UNVERIFIED or SUSPICIOUS (never a confident HIGH_RISK or LOW_RISK)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLAGGED = {"HIGH_RISK", "SUSPICIOUS"}


def correct(label: str, level: str) -> bool:
    if label == "scam":
        return level in FLAGGED
    if label == "genuine":
        return level not in FLAGGED
    return level in ("UNVERIFIED", "SUSPICIOUS")


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true", help="use the real AI reader and SerpApi (spends credits)")
    ap.add_argument("--ids", help="comma-separated message ids to run (default: all)")
    ap.add_argument("--out", help="write results JSON here")
    args = ap.parse_args()

    if not args.live:  # isolate: no keys, throwaway data dir, so nothing is spent or cached
        os.environ.update({"ASLI_MODE": "live", "SERPAPI_API_KEY": "", "OPENROUTER_API_KEY": "",
                           "ASLI_DATA_DIR": tempfile.mkdtemp(prefix="asli-eval-")})
    sys.path.insert(0, str(ROOT / "src"))
    from asli.config import Settings
    from asli.ingest.validate import validate_input
    from asli.investigate.orchestrator import Investigator
    from asli.store import Store

    settings = Settings(_env_file=None) if not args.live else Settings()
    investigator = Investigator(settings, Store(settings.db_path))
    messages = json.loads((ROOT / "eval" / "messages.json").read_text(encoding="utf-8"))["messages"]
    if args.ids:
        wanted = set(args.ids.split(","))
        messages = [m for m in messages if m["id"] in wanted]

    rows = []
    for m in messages:
        started = time.perf_counter()
        report, _ = await investigator.run(validate_input(text=m["text"]))
        rows.append({
            "id": m["id"], "label": m["label"], "lang": m["lang"], "level": report.level, "score": report.score,
            "correct": correct(m["label"], report.level), "flags": [f.code for f in report.flags],
            "searches": report.stats.searches_run, "credits": report.stats.credits_spent,
            "reader": report.stats.extraction, "seconds": round(time.perf_counter() - started, 1),
        })
        r = rows[-1]
        print(f"{'ok ' if r['correct'] else 'BAD'} {r['id']:<28} {r['label']:<9} {r['level']:<10} {r['score']:>3}  "
              f"{' '.join(r['flags'])}", flush=True)

    def count(label: str, pred) -> tuple[int, int]:
        sel = [r for r in rows if r["label"] == label]
        return sum(1 for r in sel if pred(r)), len(sel)

    caught, scams = count("scam", lambda r: r["level"] in FLAGGED)
    alarms, genuine = count("genuine", lambda r: r["level"] in FLAGGED)
    confirmed, _ = count("genuine", lambda r: r["level"] == "LOW_RISK")
    amb_ok, amb = count("ambiguous", lambda r: r["correct"])
    flagged = [r for r in rows if r["level"] in FLAGGED]
    precision = sum(1 for r in flagged if r["label"] == "scam") / len(flagged) if flagged else None
    summary = {
        "mode": "live" if args.live else "rules-only (no AI reader, no searches)",
        "scam_recall": f"{caught}/{scams}", "genuine_false_alarms": f"{alarms}/{genuine}",
        "genuine_confirmed_low_risk": f"{confirmed}/{genuine}", "ambiguous_handled": f"{amb_ok}/{amb}",
        "precision_of_flags": None if precision is None else round(precision, 2),
        "credits": sum(r["credits"] for r in rows), "searches": sum(r["searches"] for r in rows),
    }
    print("\n" + json.dumps(summary, indent=2, ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
