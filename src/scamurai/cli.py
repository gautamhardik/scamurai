"""Command line: `scamurai serve | demo | check | record | cache | doctor`."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from scamurai.config import PACKAGE_DIR, get_settings
from scamurai.logs import setup_logging


def _settings(mode: str | None = None):
    if mode:
        os.environ["SCAMURAI_MODE"] = mode
    get_settings.cache_clear()
    return get_settings()


def cmd_serve(args: argparse.Namespace, *, mode: str | None = None) -> None:
    import uvicorn

    settings = _settings(mode)
    host = args.host or settings.scamurai_host
    port = args.port or settings.scamurai_port
    if host not in ("127.0.0.1", "localhost", "::1") and not settings.scamurai_access_token:
        sys.exit("Refusing to listen on a public interface without SCAMURAI_ACCESS_TOKEN set.")
    print(f"\n  Scamurai ({settings.scamurai_mode} mode) → http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}\n")
    uvicorn.run("scamurai.web.app:create_app", factory=True, host=host, port=port, log_level="warning")


def _load_scenarios() -> list[dict]:
    return json.loads((PACKAGE_DIR / "demo" / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]


def _scenario_input(sc: dict):
    from scamurai.ingest.validate import validate_input

    image = None
    if sc.get("image"):
        image = (PACKAGE_DIR / "web" / "static" / "examples" / sc["image"]).read_bytes()
    return validate_input(text=sc.get("text"), image=image, image_url=sc.get("image_url"), url=sc.get("url"),
                          phone=sc.get("phone"), lang=sc.get("lang", "auto"), example_id=sc["id"])


def _print_report(report, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=1))
        return
    print(f"\n{report.level_title.upper()}  ·  score {report.score}  ·  confidence {report.confidence}")
    print(f"{report.headline}\n{report.confidence_reason}")
    if report.caps_applied:
        print("caps:", ", ".join(report.caps_applied))
    ev = {e.id: e for e in report.evidence}
    for f in report.flags:
        print(f"\n  [{f.code} {f.severity:<8}] {f.title}  (w{f.weight}·c{f.confidence}={f.contribution})")
        print(f"      {f.explanation}")
        for eid in f.evidence_ids[:3]:
            e = ev.get(eid)
            if e:
                print(f"        - {e.source_class:<15} {e.title[:70]}  {e.url or ''}"[:160])
    print("\n  checks:")
    for c in report.checks:
        print(f"    {c.engine:<16} {c.status:<12} cached={c.cached!s:<5} n={c.n_results:<3} {c.label}")
    print("\n  what to do:")
    for r in report.recommendations:
        print("    •", r.text)
    s = report.stats
    print(f"\n  searches={s.searches_run} cache_hits={s.cache_hits} credits={s.credits_spent} "
          f"llm={s.llm_model or s.extraction} latency={s.latency_ms}ms notes={report.notes}")


def cmd_check(args: argparse.Namespace) -> None:
    from scamurai.ingest.validate import validate_input
    from scamurai.investigate.orchestrator import Investigator
    from scamurai.store import Store

    settings = _settings("replay" if args.replay else None)
    if args.scenario:
        sc = next((s for s in _load_scenarios() if s["id"] == args.scenario), None)
        if sc is None:
            sys.exit(f"unknown scenario {args.scenario}")
        inp = _scenario_input(sc)
    else:
        image = Path(args.image).read_bytes() if args.image else None
        inp = validate_input(text=args.text, image=image, url=args.url, phone=args.phone, image_url=args.image_url,
                             lang=args.lang)
    store = Store(settings.db_path)

    async def emit(event: dict) -> None:
        if args.verbose:
            print("  ·", json.dumps(event, ensure_ascii=False)[:200], file=sys.stderr)

    report, _ = asyncio.run(Investigator(settings, store).run(inp, emit))
    _print_report(report, args.json)


def cmd_record(args: argparse.Namespace) -> None:
    from scamurai.investigate.orchestrator import Investigator
    from scamurai.serp.client import Recorder
    from scamurai.store import Store

    settings = _settings("live")
    store = Store(settings.db_path)
    out_dir = settings.scamurai_recordings_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    scenarios = _load_scenarios()
    ids = [s["id"] for s in scenarios] if args.all else args.ids
    for sid in ids:
        sc = next(s for s in scenarios if s["id"] == sid)
        recorder = Recorder()
        report, extra = asyncio.run(Investigator(settings, store).run(_scenario_input(sc), recorder=recorder))
        if not extra.get("llm"):
            print(f"! {sid}: no LLM extraction recorded (notes: {report.notes}); replay will use regex fallback")
        record = {
            "scenario": sid,
            "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "input_hash": extra["input_hash"],
            "llm": extra.get("llm") or None,
            "expected": {"level": report.level, "flags": sorted(f.signal_id for f in report.flags)},
            "searches": recorder.searches,
        }
        path = out_dir / f"{sid}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"✓ {sid}: {report.level} score={report.score} searches={len(recorder.searches)} "
              f"credits={report.stats.credits_spent} → {path.name}")


def cmd_cache(args: argparse.Namespace) -> None:
    from scamurai.store import Store

    settings = _settings()
    n = Store(settings.db_path).cache_clear(args.engine)
    print(f"cleared {n} cached searches")


def cmd_doctor(args: argparse.Namespace) -> None:
    import httpx

    settings = _settings()
    print(f"mode: {settings.scamurai_mode}")
    print(f"SerpApi key: {'set' if settings.serpapi_configured else 'MISSING'}")
    print(f"OpenRouter key: {'set' if settings.llm_configured else 'missing (regex-only extraction)'}")
    if settings.serpapi_configured:
        from scamurai.serp.client import SerpClient
        from scamurai.store import Store

        credits = asyncio.run(SerpClient(settings, Store(settings.db_path)).credits_left(0))
        print(f"SerpApi searches left: {credits}")
    try:
        models = {m["id"] for m in httpx.get("https://openrouter.ai/api/v1/models", timeout=20).json()["data"]}
        for m in dict.fromkeys(settings.scamurai_vision_models + settings.scamurai_text_models):
            print(f"  model {m}: {'ok' if m in models else 'NOT FOUND — update SCAMURAI_*_MODELS'}")
    except Exception as exc:  # noqa: BLE001
        print(f"could not list OpenRouter models: {type(exc).__name__}")


def main(argv: list[str] | None = None) -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
            sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass
    setup_logging(os.environ.get("SCAMURAI_LOG_LEVEL", "WARNING"))
    p = argparse.ArgumentParser(prog="scamurai", description="Scamurai — is this real?")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name, helptext in (("serve", "run the web app (live mode)"), ("demo", "run the web app on recorded evidence")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--host")
        sp.add_argument("--port", type=int)

    c = sub.add_parser("check", help="investigate from the command line")
    c.add_argument("text", nargs="?")
    c.add_argument("--image")
    c.add_argument("--image-url")
    c.add_argument("--url")
    c.add_argument("--phone")
    c.add_argument("--lang", default="auto")
    c.add_argument("--scenario")
    c.add_argument("--replay", action="store_true")
    c.add_argument("--json", action="store_true")
    c.add_argument("-v", "--verbose", action="store_true")

    r = sub.add_parser("record", help="record demo scenarios from live searches")
    r.add_argument("ids", nargs="*")
    r.add_argument("--all", action="store_true")

    k = sub.add_parser("cache", help="clear the search cache")
    k.add_argument("--engine")

    sub.add_parser("doctor", help="check configuration, quotas and model availability")

    args = p.parse_args(argv)
    if args.cmd == "serve":
        cmd_serve(args)
    elif args.cmd == "demo":
        cmd_serve(args, mode="replay")
    elif args.cmd == "check":
        cmd_check(args)
    elif args.cmd == "record":
        cmd_record(args)
    elif args.cmd == "cache":
        cmd_cache(args)
    elif args.cmd == "doctor":
        cmd_doctor(args)
