"""Runs one investigation end to end and streams progress events.

read → plan → search (round 1, then round 2) → weigh → report. No LLM in the loop after
extraction; no unbounded search loops (≤ max_searches, ≤ 2 rounds, phase time budget).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from asli.config import Settings
from asli.errors import AsliError
from asli.ingest.images import PreparedImage, prepare_image
from asli.investigate import planner
from asli.investigate.checks import Ctx, all_signals, resolve_official, verifiable_entities
from asli.investigate.evidence import EvidenceBook
from asli.llm.client import LLMClient
from asli.llm.extract import extract_claims
from asli.logs import log_event
from asli.models import CheckResult, ClaimGraph, InvestigationInput, ReportStats, RiskReport, SearchSpec
from asli.risk.engine import evaluate
from asli.risk.report import build_report, claim_chips, enforce_citations, independent_sources
from asli.serp.client import Budget, Recorder, Recordings, SerpClient, SerpOutcome
from asli.serp.normalize import NORMALIZERS
from asli.store import Store
from asli.i18n import report_language

log = logging.getLogger("asli.investigate")

Emit = Callable[[dict[str, Any]], Awaitable[None]]


async def _noop(_: dict[str, Any]) -> None:
    return None


class Investigator:
    def __init__(self, settings: Settings, store: Store, recordings: Recordings | None = None) -> None:
        self.settings = settings
        self.store = store
        self.recordings = recordings or (Recordings(settings.asli_recordings_dir) if settings.asli_mode == "replay" else None)
        self.serp = SerpClient(settings, store, self.recordings)
        self.llm = LLMClient(settings, store, self.recordings.llm if self.recordings else None)

    async def run(
        self,
        inp: InvestigationInput,
        emit: Emit = _noop,
        *,
        recorder: Recorder | None = None,
        investigation_id: str | None = None,
    ) -> tuple[RiskReport, dict[str, Any]]:
        started = time.perf_counter()
        inv_id = investigation_id or uuid.uuid4().hex[:12]
        await emit({"type": "accepted", "id": inv_id, "mode": self.settings.asli_mode})

        # ---------------------------------------------------------------- read
        await emit({"type": "stage", "name": "read", "status": "running"})
        image: PreparedImage | None = prepare_image(inp.image) if inp.image else None
        graph, llm_record = await extract_claims(inp, image, self.llm)
        lang = report_language(graph.language, inp.lang, graph.haystack)
        await emit({
            "type": "claims", "language": lang, "scheme": graph.scheme, "scam_type": graph.scam_type,
            "extraction": graph.extraction, "chips": [c.model_dump() for c in claim_chips(graph)],
        })
        await emit({"type": "stage", "name": "read", "status": "done"})

        # ---------------------------------------------------------------- plan + search
        await emit({"type": "stage", "name": "search", "status": "running"})
        book = EvidenceBook(graph)
        ctx = Ctx(graph=graph, book=book)
        budget = Budget(max_searches=self.settings.asli_max_searches)
        plan = planner.plan_round1(graph, self.settings.asli_max_searches, has_image=image is not None,
                                   image_url=inp.image_url)
        checks: dict[str, CheckResult] = {}
        await self._announce(plan.round1, checks, emit, plan.reason)
        deadline = time.perf_counter() + self.settings.asli_search_phase_budget_s
        await self._run_specs(plan.round1, ctx, checks, budget, image, inp.image_url, emit, recorder, deadline)

        ctx.official = resolve_official(ctx)
        lens_prices = sum(1 for spec, _ in ctx.ok("lens") for i in book.for_search(spec.id) if i.data.get("price_inr"))
        phone_confirmed = bool(ctx.official and ctx.official.phones and any(
            p.value[-10:] in "".join(ch for ch in "".join(ctx.official.phones) if ch.isdigit())
            for p in graph.of("phone")))
        round2 = planner.plan_round2(
            graph,
            official_domains=ctx.official.domains if ctx.official else [],
            official_name=ctx.official.name if ctx.official else None,
            lens_prices=lens_prices,
            remaining=max(0, budget.max_searches - budget.used),
            start_index=len(plan.round1) + 1,
            phone_confirmed=phone_confirmed,
        )
        if round2 and time.perf_counter() < deadline:
            await self._announce(round2, checks, emit, None)
            await self._run_specs(round2, ctx, checks, budget, image, inp.image_url, emit, recorder, deadline)
        await emit({"type": "stage", "name": "search", "status": "done"})

        # ---------------------------------------------------------------- weigh
        await emit({"type": "stage", "name": "weigh", "status": "running"})
        signals = enforce_citations(all_signals(ctx), book)
        check_list = list(checks.values())
        attempted = [c for c in check_list if c.status not in ("skipped_budget",)]
        completed = [c for c in attempted if c.status in ("done", "no_results")]
        coverage = (len(completed) / len(attempted)) if attempted else (1.0 if verifiable_entities(graph) else 0.0)
        evaluation = evaluate(
            signals,
            coverage=coverage,
            verifiable=len(verifiable_entities(graph)),
            checks_with_results=sum(1 for c in completed if c.n_results > 0),
            independent_sources=independent_sources(signals, book),
        )
        stats = ReportStats(
            searches_planned=len(check_list),
            searches_run=budget.used,
            cache_hits=budget.cache_hits,
            credits_spent=budget.live,
            llm_model=graph.llm_model,
            extraction=graph.extraction,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        recorded_at = None
        if self.recordings and llm_record.get("input_hash") in self.recordings.meta:
            recorded_at = self.recordings.meta[llm_record["input_hash"]].get("recorded_at")
        report = build_report(
            investigation_id=inv_id, graph=graph, signals=signals, evaluation=evaluation, book=book,
            checks=check_list, official=ctx.official, lang=lang, mode=self.settings.asli_mode, stats=stats,
            recorded_at=recorded_at,
        )
        await emit({"type": "stage", "name": "weigh", "status": "done"})

        log_event(
            log, "investigation", investigation_id=inv_id, input_kinds=inp.kinds, scam_type=graph.scam_type,
            scheme=graph.scheme, language=lang, extraction=graph.extraction, llm_model=graph.llm_model,
            engines=sorted({c.engine for c in check_list}), searches=budget.used, cache_hits=budget.cache_hits,
            credits=budget.live, evidence=len(book.items), flags=[f.code for f in report.flags],
            level=report.level, score=report.score, confidence=report.confidence,
            latency_ms=stats.latency_ms, errors=[c.error for c in check_list if c.error] + graph.notes,
        )
        if self.settings.asli_store_reports:
            self.store.save_investigation(
                {"id": inv_id, "input_kinds": inp.kinds, "scam_type": graph.scam_type, "level": report.level,
                 "score": report.score, "confidence": report.confidence, "searches": budget.used,
                 "cache_hits": budget.cache_hits, "latency_ms": stats.latency_ms,
                 "errors": [c.error for c in check_list if c.error]},
                report.model_dump(mode="json"),
            )
        return report, {"graph": graph, **llm_record}

    async def _announce(self, specs: list[SearchSpec], checks: dict[str, CheckResult], emit: Emit,
                        reason: str | None) -> None:
        for s in specs:
            checks[s.id] = CheckResult(search_id=s.id, engine=s.engine, purpose=s.purpose, label=s.label)
        await emit({
            "type": "plan", "reason": reason,
            "checks": [{"id": s.id, "engine": s.engine, "label": s.label, "purpose": s.purpose} for s in specs],
        })

    async def _run_specs(self, specs: list[SearchSpec], ctx: Ctx, checks: dict[str, CheckResult], budget: Budget,
                         image: PreparedImage | None, image_url: str | None, emit: Emit,
                         recorder: Recorder | None, deadline: float) -> None:
        async def one(spec: SearchSpec) -> None:
            await emit({"type": "check", "id": spec.id, "status": "running"})
            outcome = await self.serp.search(spec.engine, spec.params, budget, image=image, image_url=image_url,
                                             recorder=recorder)
            self._record(spec, outcome, ctx, checks)
            c = checks[spec.id]
            await emit({"type": "check", "id": spec.id, "status": c.status, "cached": c.cached,
                        "n_results": c.n_results, "error": c.error})

        if not specs:
            return
        tasks = [asyncio.create_task(one(s)) for s in specs]
        remaining = max(1.0, deadline - time.perf_counter())
        done, pending = await asyncio.wait(tasks, timeout=remaining)
        for t in pending:
            t.cancel()
        for spec in specs:
            c = checks[spec.id]
            if c.status == "pending":
                c.status, c.error = "failed", "timeout"
                await emit({"type": "check", "id": spec.id, "status": "failed", "error": "timeout"})
        for t in done:
            if t.exception() is not None:  # never let one check crash the investigation
                log_event(log, "check_crashed", error=type(t.exception()).__name__)

    def _record(self, spec: SearchSpec, outcome: SerpOutcome, ctx: Ctx, checks: dict[str, CheckResult]) -> None:
        c = checks[spec.id]
        c.status = outcome.status
        c.cached = outcome.cached
        c.latency_ms = outcome.latency_ms
        c.error = outcome.error
        ctx.outcomes[spec.id] = (spec, outcome)
        if outcome.status in ("done", "no_results"):
            raw = NORMALIZERS[spec.engine](outcome.data)
            items = ctx.book.add_search(spec.id, spec.engine, raw, cached=outcome.cached)
            c.n_results = len(items)
            if c.n_results == 0:
                c.status = "no_results"


def graph_summary(graph: ClaimGraph) -> dict[str, Any]:
    return {
        "language": graph.language, "scheme": graph.scheme, "scam_type": graph.scam_type,
        "org_category": graph.org_category, "extraction": graph.extraction,
        "entities": [{"id": e.id, "type": e.type, "value": e.value} for e in graph.entities],
        "notes": graph.notes,
    }


__all__ = ["Investigator", "AsliError", "graph_summary"]
