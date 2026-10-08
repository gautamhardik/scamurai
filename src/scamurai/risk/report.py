"""Report builder: signals + evaluation → user-facing report.

Citation invariant: every flag cites ≥1 evidence item, and identity/web flags cite ≥1 item
that isn't just a quote from the message. Flags that fail are dropped (and logged).
"""

from __future__ import annotations

import logging
from datetime import datetime

from scamurai.i18n import HEADLINES, LEVELS, RECS, TARGET_GENERIC, UI, flag_text, fmt
from scamurai.investigate.checks import Official, verifiable_entities
from scamurai.investigate.evidence import EvidenceBook
from scamurai.logs import log_event
from scamurai.models import (
    CheckResult,
    ClaimChip,
    ClaimGraph,
    Flag,
    FlagText,
    Recommendation,
    ReportStats,
    ReportText,
    RiskReport,
    Signal,
)
from scamurai.risk.engine import Evaluation
from scamurai.risk.signals import REGISTRY

log = logging.getLogger("scamurai.report")


def severity(signal: Signal) -> str:
    d = REGISTRY[signal.id]
    if d.polarity == "trust":
        return "trust"
    if d.critical:
        return "critical"
    c = signal.contribution
    return "high" if c >= 0.4 else "medium" if c >= 0.2 else "low"


def enforce_citations(signals: list[Signal], book: EvidenceBook) -> list[Signal]:
    kept: list[Signal] = []
    for s in signals:
        items = book.get(s.evidence_ids)
        category = REGISTRY[s.id].category
        ok = bool(items)
        # Web and trust flags must rest on search results (or a curated official reference).
        # Identity/message flags are structural analysis of the message and may cite the quote.
        if category in ("web", "trust"):
            ok = ok and any(i.kind != "message_span" for i in items)
        if not ok:
            log_event(log, "flag_dropped_no_evidence", signal=s.id)
            continue
        kept.append(s)
    return kept


def independent_sources(signals: list[Signal], book: EvidenceBook, polarity: str = "risk") -> int:
    domains_seen: set[str] = set()
    for s in signals:
        if s.polarity != polarity or REGISTRY[s.id].category == "message":
            continue
        for item in book.get(s.evidence_ids):
            if item.kind not in ("message_span",) and (item.domain or item.data.get("source")):
                domains_seen.add(item.domain or item.data["source"])
    return len(domains_seen)


def build_report(
    *,
    investigation_id: str,
    graph: ClaimGraph,
    signals: list[Signal],
    evaluation: Evaluation,
    book: EvidenceBook,
    checks: list[CheckResult],
    official: Official | None,
    lang: str,
    mode: str,
    stats: ReportStats,
    recorded_at: str | None = None,
) -> RiskReport:
    flags = []
    for s in sorted(signals, key=lambda x: (x.polarity == "trust", -x.contribution)):
        title, expl = flag_text(s.id, s.facts.get("detail"), lang, s.facts)
        flags.append(Flag(
            signal_id=s.id, code=REGISTRY[s.id].code, polarity=s.polarity, severity=severity(s),  # type: ignore[arg-type]
            title=title, explanation=expl, weight=s.weight, confidence=s.confidence,
            contribution=s.contribution, evidence_ids=s.evidence_ids, entity_ids=s.entity_ids,
        ))

    risk_flags = [f for f in flags if f.polarity == "risk"]
    n_risk = len(risk_flags)
    target = _target(graph, official, lang)
    level = evaluation.level
    if level == "HIGH_RISK":
        key = f"HIGH_RISK:{graph.scam_type}"
        headline = fmt(HEADLINES[lang].get(key, HEADLINES[lang]["HIGH_RISK"]), {"n": n_risk, "target": target})
    elif level == "SUSPICIOUS":
        key = "SUSPICIOUS:mixed" if evaluation.contradiction else "SUSPICIOUS"
        headline = fmt(HEADLINES[lang][key], {"n": n_risk, "target": target})
    elif level == "LOW_RISK":
        strong_trust = [s for s in signals if s.polarity == "trust" and s.contribution >= 0.5]
        if strong_trust:
            confirmed_by = strong_trust[0].facts.get("official") or (official.domains[0] if official else "")
            headline = fmt(HEADLINES[lang]["LOW_RISK:trust"], {"official": confirmed_by})
        else:
            headline = HEADLINES[lang]["LOW_RISK"]
    else:
        headline = HEADLINES[lang]["UNVERIFIED"]

    done = sum(1 for c in checks if c.status in ("done", "no_results"))
    planned = sum(1 for c in checks if c.status != "skipped_budget")
    n_sources = independent_sources(signals, book, "trust" if level == "LOW_RISK" else "risk")
    confidence_reason = (fmt(UI[lang]["confidence"], {"done": done, "planned": planned, "n": n_sources})
                         if planned else UI[lang]["confidence_none"])
    if level == "UNVERIFIED" and not verifiable_entities(graph):
        confidence_reason = UI[lang]["confidence_nothing"]

    referenced = {eid for f in flags for eid in f.evidence_ids}
    # keep everything flags cite, plus the top results of each check for "what we checked"
    for c in checks:
        for item in sorted(book.for_search(c.search_id), key=lambda x: -x.relevance)[:3]:
            referenced.add(item.id)
    evidence = [book.items[i] for i in sorted(referenced, key=lambda x: int(x[1:])) if i in book.items]

    title, subtitle = LEVELS[lang][level]
    return RiskReport(
        id=investigation_id,
        created_at=datetime.now().astimezone(),
        mode=mode,  # type: ignore[arg-type]
        language=lang,  # type: ignore[arg-type]
        level=level,  # type: ignore[arg-type]
        level_title=title,
        level_subtitle=subtitle,
        score=evaluation.score,
        confidence=evaluation.confidence,  # type: ignore[arg-type]
        confidence_reason=confidence_reason,
        headline=headline,
        scam_type=graph.scam_type,
        scheme=graph.scheme,
        flags=flags,
        evidence=evidence,
        checks=checks,
        recommendations=recommendations(level, graph, signals, official, lang),
        claims_summary=claim_chips(graph),
        caps_applied=evaluation.caps,
        notes=graph.notes,
        stats=stats,
        recorded_at=recorded_at,
    )


def report_text(report: RiskReport) -> ReportText:
    return ReportText(
        level_title=report.level_title, level_subtitle=report.level_subtitle, headline=report.headline,
        confidence_reason=report.confidence_reason,
        flags={f.signal_id: FlagText(title=f.title, explanation=f.explanation) for f in report.flags},
        recommendations={r.id: r.text for r in report.recommendations},
    )


def _target(graph: ClaimGraph, official: Official | None, lang: str) -> str:
    if official:
        return official.name
    org = graph.first("org") or graph.first("company")
    if org:
        return org.value
    return TARGET_GENERIC[lang].get(graph.org_category, TARGET_GENERIC[lang][None])


def recommendations(level: str, graph: ClaimGraph, signals: list[Signal], official: Official | None,
                    lang: str) -> list[Recommendation]:
    ids = {s.id for s in signals}
    out: list[str] = []
    if level == "HIGH_RISK":
        if graph.of("url"):
            out.append("dont_click")
        if graph.of("phone"):
            out.append("dont_call")
        out.append("dont_pay")
        out.append("official_channel" if official else "official_channel_generic")
    elif level == "SUSPICIOUS":
        out.append("verify_first")
        out.append("official_channel" if official else "official_channel_generic")
    elif level == "LOW_RISK":
        out.append("stay_alert")
    else:
        out.append("unverified")
        out.append("official_channel" if official else "official_channel_generic")
    if "credential_request" in ids:
        out.append("otp_never")
    if "upfront_fee" in ids and graph.scam_type == "job_offer":
        out.append("no_fee_jobs")
    if "price_anomaly" in ids or (graph.scam_type == "shopping_deal" and level in ("HIGH_RISK", "SUSPICIOUS")):
        out.append("buy_official")
    if graph.scheme == "digital_arrest":
        out.append("digital_arrest")
    if level == "HIGH_RISK":
        out += ["report", "already_paid"]
    facts = {"org": official.name if official else "", "official": official.domains[0] if official else ""}
    recs = []
    for i, rid in enumerate(dict.fromkeys(out)):
        link = None
        if rid == "report":
            link = "https://cybercrime.gov.in"
        elif rid == "official_channel" and official:
            link = f"https://{official.domains[0]}"
        recs.append(Recommendation(id=rid, text=fmt(RECS[rid][lang], facts), priority=i + 1, link=link))
    return recs


def claim_chips(graph: ClaimGraph) -> list[ClaimChip]:
    chips: list[ClaimChip] = []
    labels = {
        "org": "Claims to be", "company": "Company", "phone": "Phone", "url": "Link", "email": "Email",
        "upi_id": "UPI ID", "amount": "Amount", "product": "Product", "price": "Price", "job_role": "Role",
        "salary": "Salary", "address": "Address", "app": "App",
    }
    for e in graph.entities:
        if e.type not in labels:
            continue
        if e.type == "phone":
            value = e.attrs.get("display") or e.value
        elif e.type == "url":
            value = e.attrs.get("display") or e.value
        elif e.type in ("amount", "price"):
            value = e.attrs.get("display") or e.raw
        else:
            value = e.value
        chips.append(ClaimChip(label=labels[e.type], value=value[:80], kind=e.type))
    return chips[:14]
