"""Deterministic investigation planner: claim graph → SerpApi searches.

Queries are built only from grounded entities (sanitized) and curated templates. Round 1 runs
independent checks in parallel; round 2 runs checks that need round-1 facts (official domain,
Lens prices). The total never exceeds the per-investigation budget.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from asli.knowledge.patterns import news_query, sanitize_query_term, upi_is_requested
from asli.models import ClaimGraph, Entity, SearchSpec, SkippedCheck

LABELS = {
    "org_lookup": "Finding the official website of {name}",
    "phone_reputation": "Searching the web for reports about {name}",
    "domain_reputation": "Checking what the web says about {name}",
    "pattern_news": "Looking for news reports of this kind of message",
    "lens": "Finding where else this photo appears, and at what price",
    "price_lookup": "Checking the real price of {name}",
    "job_listing": "Checking if {name} is really hiring for this role",
    "address_check": "Checking the address on Google Maps",
    "official_phone_check": "Checking if {official} lists this number",
    "upi_reputation": "Searching the web for reports about UPI ID {name}",
}


@dataclass
class Plan:
    round1: list[SearchSpec] = field(default_factory=list)
    skipped: list[SkippedCheck] = field(default_factory=list)
    reason: str = ""


def _main_org(graph: ClaimGraph) -> Entity | None:
    if graph.scam_type == "job_offer":
        return graph.first("company") or graph.first("org")
    return graph.first("org") or graph.first("company")


def suspicious_domains(graph: ClaimGraph) -> list[Entity]:
    """URL/email domains worth a reputation search (not official, not big platforms, not shorteners)."""
    out: list[Entity] = []
    seen: set[str] = set()
    for e in graph.of("url"):
        reg = e.attrs.get("registrable")
        if not reg or reg in seen or e.attrs.get("official_org") or e.attrs.get("known_platform") \
                or e.attrs.get("shortener") or e.attrs.get("gov"):
            continue
        seen.add(reg)
        out.append(e)
    for e in graph.of("email"):
        reg = e.attrs.get("registrable")
        if not reg or reg in seen or e.attrs.get("free_mail"):
            continue
        from asli.knowledge import domains

        if domains.org_for_domain(reg) or domains.known_platform(reg):
            continue
        seen.add(reg)
        out.append(e)
    return out


# "sneakerhub.outlet.india", "@earnfast_hr", "zentrixhiring.com": a seller's handle or a bare domain has no
# "official website" to find (and domains get their own reputation search). Lower-case only, so a name
# like "J.P.Morgan" still gets its lookup.
_HANDLE = re.compile(r"@?[a-z0-9]+(?:[._][a-z0-9]+)+|@[a-z0-9_]{2,}")


def is_handle(value: str) -> bool:
    return bool(_HANDLE.fullmatch(value.strip()))


def phone_query(phone: Entity) -> dict[str, str]:
    variants = phone.attrs.get("variants") or [phone.value]
    return {"q": " OR ".join(f'"{v}"' for v in variants[:3])}


def entity_searches(graph: ClaimGraph) -> list[tuple[str, dict[str, str]]]:
    """Searches that need only what the deterministic extractors find (numbers, UPI IDs, links), so they
    can start before the AI has read the message. Each is one round 1 will plan for the same graph, with
    identical parameters, and there are few enough (≤ 4) that the budget never trims them."""
    out = [("google", phone_query(p)) for p in graph.of("phone")[:2]]
    out += [("google", {"q": f'"{u.value}"'}) for u in requested_upis(graph)[:1]]
    out += [("google", {"q": f'"{d.attrs["registrable"]}"'}) for d in suspicious_domains(graph)[:1]]
    return out


def requested_upis(graph: ClaimGraph) -> list[Entity]:
    """UPI IDs the reader is asked to pay. A payee named in a transaction notice is not one."""
    return [u for u in graph.of("upi_id") if upi_is_requested(graph.haystack, u.raw)]


def _city(address: str | None) -> str | None:
    if not address:
        return None
    parts = [p.strip() for p in address.split(",") if p.strip()]
    for p in reversed(parts):
        if re.search(r"\d{6}", p):
            continue
        if re.fullmatch(r"[A-Za-z .]{3,30}", p):
            return p
    return None


def plan_round1(graph: ClaimGraph, max_searches: int, *, has_image: bool, image_url: str | None) -> Plan:
    plan = Plan()
    specs: list[SearchSpec] = []
    n = iter(range(1, 100))

    def spec(engine: str, params: dict[str, str], purpose: str, label_name: str, entity_ids: list[str],
             priority: int) -> None:
        specs.append(SearchSpec(
            id=f"s{next(n)}", engine=engine, params=params, purpose=purpose,  # type: ignore[arg-type]
            label=LABELS[purpose].format(name=label_name, official=label_name), entity_ids=entity_ids,
            priority=priority, round=1,
        ))

    org = _main_org(graph)
    org_name = sanitize_query_term(org.value, 60) if org else None
    curated = bool(org and org.attrs.get("curated"))

    # P1 — identity
    if org and org_name and not curated and not is_handle(org.value):
        spec("google", {"q": f'"{org_name}" official website'}, "org_lookup", org_name, [org.id], 1)
    elif org and curated:
        plan.skipped.append(SkippedCheck(purpose="org_lookup", reason="official domain known"))
    elif org and is_handle(org.value):
        plan.skipped.append(SkippedCheck(purpose="org_lookup", reason="a handle or domain, not an organisation name"))

    product = graph.first("product")
    if graph.scam_type == "shopping_deal" and (has_image or image_url):
        img = graph.first("image")
        spec("google_lens", {}, "lens", "", [img.id] if img else [], 1)

    # P2 — reputation & claims
    for phone in graph.of("phone")[:2]:
        spec("google", phone_query(phone), "phone_reputation", phone.attrs.get("display") or phone.value, [phone.id], 2)

    for upi in requested_upis(graph)[:1]:
        spec("google", {"q": f'"{upi.value}"'}, "upi_reputation", upi.value, [upi.id], 2)

    for dom in suspicious_domains(graph)[:2]:
        reg = dom.attrs["registrable"]
        spec("google", {"q": f'"{reg}"'}, "domain_reputation", reg, [dom.id], 2)

    if graph.scam_type == "job_offer":
        company = graph.first("company") or graph.first("org")
        role = graph.first("job_role")
        address = graph.first("address")
        if company:
            city = _city(address.value if address else None) or (address.attrs.get("city_hint") if address else None)
            parts = [sanitize_query_term(role.value, 50) if role else "", sanitize_query_term(company.value, 50),
                     sanitize_query_term(city, 30) if city else ""]
            q = " ".join(p for p in parts if p)
            spec("google_jobs", {"q": q}, "job_listing", sanitize_query_term(company.value, 50),
                 [company.id] + ([role.id] if role else []), 2)
        if address:
            spec("google_maps", {"q": sanitize_query_term(address.value, 120)}, "address_check", "",
                 [address.id], 2)

    # P3 — context
    company = graph.first("company")
    brand = (product.attrs.get("brand") if product else None) or (org.value if org and graph.scam_type == "shopping_deal" else None)
    app = graph.first("app")
    known_org = org.attrs.get("official_name") or org.value if org and org.attrs.get("curated") else None
    q = news_query(
        graph.scheme,
        org=known_org,
        company=company.value if company else (org.value if org and graph.scam_type == "job_offer" else None),
        brand=brand,
        app=app.value if app else None,
    )
    if q:
        spec("google_news", {"q": q}, "pattern_news", "", [], 3)

    # Budget: keep highest priority; leave room for round 2 when it'll be needed.
    reserve = 1 if (graph.of("phone") and org) else 0
    reserve += 1 if (product and graph.scam_type == "shopping_deal") else 0
    limit = max(1, max_searches - reserve)
    specs.sort(key=lambda s: (s.priority, int(s.id[1:])))
    for s in specs[limit:]:
        plan.skipped.append(SkippedCheck(purpose=s.purpose, reason="budget"))
    plan.round1 = specs[:limit]
    plan.reason = _reason(graph, plan.round1)
    return plan


def plan_round2(
    graph: ClaimGraph,
    *,
    official_domains: list[str],
    official_name: str | None,
    lens_prices: int,
    remaining: int,
    start_index: int,
    phone_confirmed: bool,
) -> list[SearchSpec]:
    specs: list[SearchSpec] = []
    n = iter(range(start_index, start_index + 10))
    phones = graph.of("phone")
    # The official-number check only makes sense when the number is presented as the organisation's
    # own (a helpline, an alert); a seller's WhatsApp number in a deal isn't claimed to be Nike's.
    if (phones and official_domains and not phone_confirmed and graph.scam_type != "shopping_deal"
            and remaining > len(specs)):
        phone = phones[0]
        variants = (phone.attrs.get("variants") or [phone.value])[:2]
        alts = " OR ".join(f'"{v}"' for v in variants)
        domain = official_domains[0]
        # Banks are moving to .bank.in (SBI's contact pages now live on sbi.bank.in): search both.
        sites = [domain] + [d for d in official_domains[1:] if d.endswith(".bank.in")][:1]
        site_q = f"site:{domain}" if len(sites) == 1 else "(" + " OR ".join(f"site:{d}" for d in sites) + ")"
        specs.append(SearchSpec(
            id=f"s{next(n)}", engine="google", params={"q": f"{site_q} ({alts})"},
            purpose="official_phone_check",
            label=LABELS["official_phone_check"].format(official=official_name or domain, name=""),
            entity_ids=[phone.id], priority=1, round=2,
        ))
    product = graph.first("product")
    if graph.scam_type == "shopping_deal" and product and lens_prices < 3 and remaining > len(specs):
        brand = product.attrs.get("brand")
        q = sanitize_query_term(product.value, 80)
        if brand and brand.lower() not in q.lower():
            q = f"{sanitize_query_term(brand, 30)} {q}"
        specs.append(SearchSpec(
            id=f"s{next(n)}", engine="google_shopping", params={"q": q}, purpose="price_lookup",
            label=LABELS["price_lookup"].format(name=sanitize_query_term(product.value, 60)),
            entity_ids=[product.id], priority=2, round=2,
        ))
    return specs[:remaining]


def _reason(graph: ClaimGraph, specs: list[SearchSpec]) -> str:
    kinds = {
        "impersonation": "Message claiming to be an organisation",
        "fake_customer_care": "Customer-care number",
        "shopping_deal": "Shopping deal",
        "job_offer": "Job offer",
        "loan_app": "Loan app",
        "investment": "Investment tip",
    }
    head = kinds.get(graph.scam_type, "Message")
    return f"{head}: {len(specs)} checks planned"
