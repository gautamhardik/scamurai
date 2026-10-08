"""Latency benchmark for the investigation pipeline with simulated AI and SerpApi delays.

Delays default to the medians measured on real checks (AI reader 13 s; Google Search 4.9 s, News 4.3 s),
scaled down by --scale so the run is quick. It compares the pipeline with and without starting the
number/link/UPI searches while the AI reads. No network, no credits, no AI calls.

    uv run python scripts/bench_latency.py --scale 0.1 --runs 5
    uv run python scripts/bench_latency.py --samples latencies.json   # draw from observed latencies

With --samples (a JSON map of engine -> observed seconds), each search's delay is drawn from what was
observed, keyed by run and query, so both variants see the same delay for the same search.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MESSAGES = [
    "Paytm KYC expired. Your wallet will be blocked in 24 hours. Call our KYC officer at 8001234567 now.",
    "SBI: Dear customer your YONO account will be suspended today. Update PAN immediately at sbi-yono-kyc.top/login",
    "Main CBI officer bol raha hoon. Video call par rahiye aur 50,000 rupaye is UPI par bhejiye: cbi.verify@ybl",
]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=0.1)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--samples", help="JSON map of engine -> observed latencies in seconds")
    args = ap.parse_args()
    os.environ.update({"SCAMURAI_MODE": "live", "SERPAPI_API_KEY": "bench", "OPENROUTER_API_KEY": "bench"})
    sys.path.insert(0, str(ROOT / "src"))
    from scamurai.config import Settings
    from scamurai.ingest.validate import validate_input
    from scamurai.investigate.orchestrator import Investigator
    from scamurai.llm import client as llm_client
    from scamurai.serp import client as serp_client
    from scamurai.store import Store

    llm_s, search_s = 13.0 * args.scale, {"google": 4.9 * args.scale, "google_news": 4.3 * args.scale}

    async def fake_llm(self, **kw):
        await asyncio.sleep(llm_s)
        return llm_client.LLMResult({"scheme": "other", "language": "en"}, model="simulated")

    samples = json.loads(Path(args.samples).read_text()) if args.samples else None
    current_run = {"n": 0}

    def delay(request: dict) -> float:
        if not samples:
            return search_s.get(request["engine"], 4.9 * args.scale)
        rng = random.Random(f"{current_run['n']}:{request['engine']}:{request.get('q')}")
        return rng.choice(samples.get(request["engine"]) or samples["google"]) * args.scale

    def fake_call(self, request, timeout):
        time.sleep(delay(request))
        return {"organic_results": [{"position": 1, "title": "r", "link": "https://example.org/r"}],
                "news_results": [{"title": "n", "link": "https://news.example/n"}],
                "search_metadata": {"status": "Success"}}

    async def no_credits(self, max_age_s=600):
        return None

    llm_client.LLMClient.complete_json = fake_llm
    serp_client.SerpClient._call = fake_call
    serp_client.SerpClient.credits_left = no_credits
    original_prefetch = Investigator._prefetch

    async def no_prefetch(self, inp, budget, recorder):
        return {}

    results: dict[str, list[float]] = {"sequential (before)": [], "overlapped (after)": []}
    for label, prefetch in (("sequential (before)", no_prefetch), ("overlapped (after)", original_prefetch)):
        Investigator._prefetch = prefetch
        for run in range(args.runs):
            current_run["n"] = run
            for text in MESSAGES:
                settings = Settings(_env_file=None)
                settings.scamurai_data_dir = Path(tempfile.mkdtemp(prefix="scamurai-bench-"))  # cold cache every run
                started = time.perf_counter()
                await Investigator(settings, Store(settings.db_path)).run(validate_input(text=text))
                results[label].append((time.perf_counter() - started) / args.scale)
    for label, values in results.items():
        p90 = sorted(values)[int(0.9 * (len(values) - 1))]
        print(f"{label:22} median {statistics.median(values):5.1f} s   p90 {p90:5.1f} s   mean {statistics.mean(values):5.1f} s"
              f"   (n={len(values)}, real-time equivalent)")
    before, after = (statistics.mean(v) for v in results.values())
    print(f"mean saving: {before - after:.1f} s per check ({(1 - after / before) * 100:.0f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
