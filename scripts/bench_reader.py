"""Compare AI reader configurations on the real extraction prompt (spends free OpenRouter requests).

    uv run python scripts/bench_reader.py --model nvidia/nemotron-3-super-120b-a12b:free --reasoning low off

Each configuration reads the same message once per --repeat and reports latency, tokens, and whether
the extraction found what the deterministic extractors can check (phones, links, UPI IDs, the claimed
organisation). Results are not cached.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEXT = ("Paytm KYC expired. Your wallet will be blocked in 24 hours. Call our KYC officer at 8001234567 "
                "now or pay ₹10 verification fee to kyc.paytm@ybl. Update at paytm-kyc-verify.in")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="append", required=True)
    ap.add_argument("--reasoning", nargs="+", default=["low"], help="low | medium | high | off")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--text", default=DEFAULT_TEXT)
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT / "src"))
    from scamurai.config import Settings
    from scamurai.llm.client import OPENROUTER_URL, parse_json_lenient
    from scamurai.llm.extract import SYSTEM_PROMPT

    key = Settings().openrouter_api_key.get_secret_value().strip()
    system = SYSTEM_PROMPT.replace("CONTENT-ID", "CONTENT-<id>").replace("END-ID", "END-<id>")
    user = f"Extract the claims from the content below.\n<<<CONTENT-bench>>>\n{args.text}\n<<<END-bench>>>"
    for model in args.model:
        for mode in args.reasoning:
            for _ in range(args.repeat):
                body = {
                    "model": model, "temperature": 0, "max_tokens": 6000,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "reasoning": {"enabled": False} if mode == "off" else {"effort": mode},
                }
                started = time.perf_counter()
                r = httpx.post(OPENROUTER_URL, json=body, timeout=180,
                               headers={"Authorization": f"Bearer {key}", "X-Title": "Scamurai bench"})
                seconds = time.perf_counter() - started
                payload = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                choice = (payload.get("choices") or [{}])[0]
                usage = payload.get("usage") or {}
                data = parse_json_lenient((choice.get("message") or {}).get("content")) or {}
                found = {
                    "phones": data.get("phones"), "urls": data.get("urls"), "upi_ids": data.get("upi_ids"),
                    "org": (data.get("claimed_org") or {}).get("name"), "scheme": data.get("scheme"),
                    "actions": len(data.get("requested_actions") or []), "pressure": len(data.get("pressure") or []),
                }
                print(json.dumps({
                    "model": model.split("/")[-1], "reasoning": mode, "http": r.status_code, "seconds": round(seconds, 1),
                    "finish": choice.get("finish_reason"), "completion_tokens": usage.get("completion_tokens"),
                    "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                    "valid_json": bool(data), "found": found,
                    "error": (payload.get("error") or {}).get("message") if r.status_code != 200 else None,
                }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
