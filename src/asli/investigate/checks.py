"""Checks: evidence → signals. Each signal cites the evidence it rests on."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import date

from rapidfuzz import fuzz

from asli.ingest import regex_extract as rx
from asli.investigate.evidence import EvidenceBook
from asli.investigate.planner import requested_upis, suspicious_domains
from asli.knowledge import domains
from asli.knowledge.lexicon import report_hits
from asli.knowledge.patterns import SCHEME_NEWS_KEYWORDS, detect_message_patterns
from asli.models import ClaimGraph, Entity, EvidenceItem, SearchSpec, Signal
from asli.risk.signals import ladder, make
from asli.serp.client import SerpOutcome

AUTHORITY_CATEGORIES = {"government", "utility", "bank", "telecom"}
AUTHORITY_SCHEMES = {"digital_arrest", "electricity_disconnection", "kyc_update", "bank_account_block", "tax_refund",
                     "courier_customs"}
# Handles of consumer UPI apps (Google Pay, PhonePe, Paytm, Amazon Pay, BHIM…): personal accounts.
PERSONAL_UPI = {"okaxis", "okhdfcbank", "oksbi", "okicici", "ybl", "ibl", "axl", "paytm", "ptyes", "ptaxis", "pthdfc",
                "ptsbi", "apl", "yapl", "upi", "fam", "freecharge", "jupiteraxis", "slc", "naviaxis", "superyes"}
RESIDENTIAL_TYPES = (
    "apartment", "housing society", "residential", "condominium", "hostel", "paying guest", "pg ",
    "guest house", "hotel", "homestay", "society",
)
PATTERN_WINDOW_DAYS = 5 * 365
_CONTACT_PAGE = re.compile(
    r"contact|help|support|customer[-_ ]?(care|service)|grievance|reach[-_ ]?us|toll[-_ ]?free|helpline|"
    r"call[-_ ]?us|get[-_ ]?in[-_ ]?touch|customer-care|important-numbers|faq",
    re.IGNORECASE,
)


@dataclass
class Official:
    name: str
    domains: list[str]
    confidence: float
    evidence_ids: list[str]
    phones: list[str] = field(default_factory=list)
    source: str = "curated"


@dataclass
class Ctx:
    graph: ClaimGraph
    book: EvidenceBook
    outcomes: dict[str, tuple[SearchSpec, SerpOutcome]] = field(default_factory=dict)
    official: Official | None = None

    def by_purpose(self, purpose: str) -> list[tuple[SearchSpec, SerpOutcome]]:
        return [(s, o) for s, o in self.outcomes.values() if s.purpose == purpose]

    def ok(self, purpose: str) -> list[tuple[SearchSpec, SerpOutcome]]:
        return [(s, o) for s, o in self.by_purpose(purpose) if o.status in ("done", "no_results")]


REPORT_CLASSES = {"complaint_forum", "news", "government"}


def report_confidence(independent: list[EvidenceItem]) -> float:
    """Reports on complaint forums, news or government sites count fully; mentions on arbitrary pages
    (blogs, SEO pages, other scam-checkers' examples) can't reach the strong-evidence gate on their own."""
    if any(i.source_class in REPORT_CLASSES for i in independent):
        return ladder(len(independent))
    return 0.5


def _top(items: list[EvidenceItem], n: int = 5) -> list[str]:
    return [i.id for i in sorted(items, key=lambda x: -x.relevance)[:n]]


# =========================================================================== official identity
def resolve_official(ctx: Ctx) -> Official | None:
    g = ctx.graph
    org = (g.first("company") or g.first("org")) if g.scam_type == "job_offer" else (g.first("org") or g.first("company"))
    if org is None:
        return None
    curated_key = org.attrs.get("curated")
    if curated_key:
        org_def = next(o for o in domains.orgs() if o.key == curated_key)
        ref = ctx.book.add_reference(
            f"Official website of {org_def.name}: {org_def.domains[0]}", f"https://{org_def.domains[0]}",
            "From Asli's list of verified official domains.",
        )
        off = Official(org_def.name, domains.official_domains_for(org_def), 0.95, [ref.id], source="curated")
        ctx.book.mark_official(off.domains)
        return off
    # A domain the message itself supplies can't vouch for the message: a scammer's site ranks first
    # for its own made-up company name, and would otherwise "confirm" its own link and number.
    self_supplied = ctx.book.message_domains
    for spec, _outcome in ctx.ok("org_lookup"):
        items = ctx.book.for_search(spec.id)
        kg = next((i for i in items if i.kind == "knowledge_graph" and i.data.get("website")), None)
        if kg and fuzz.token_set_ratio(kg.title.lower(), org.value.lower()) >= 70:
            host = domains.host_of(kg.data["website"])
            reg = domains.registrable(host) if host else None
            usable = reg and reg not in self_supplied and (not domains.known_platform(reg) or domains.org_for_domain(reg))
            if usable:
                off = Official(kg.title, [reg], 0.85, [kg.id], phones=kg.data.get("phones") or [], source="knowledge_graph")
                ctx.book.mark_official(off.domains)
                return off
        for it in sorted((i for i in items if i.kind == "organic"), key=lambda x: x.position or 99)[:3]:
            if not it.domain or it.source_class in ("news", "complaint_forum", "social", "job_board", "marketplace"):
                continue
            if it.domain in self_supplied:
                continue
            label = domains.label_of(it.domain)
            name = re.sub(r"[^a-z0-9]", "", org.value.lower())
            if fuzz.partial_ratio(name, label) >= 80 or fuzz.token_set_ratio(org.value.lower(), it.title.lower()) >= 80:
                off = Official(org.value, [it.domain], 0.70, [it.id], source="top_result")
                ctx.book.mark_official(off.domains)
                return off
    return None


# =========================================================================== message-level
def message_signals(ctx: Ctx) -> list[Signal]:
    g, book = ctx.graph, ctx.book
    out: list[Signal] = []
    seen: set[str] = set()
    for hit in detect_message_patterns(g.haystack):
        span = book.add_message_span(hit.quote)
        weight = None
        if hit.signal == "payment_request" and requested_upis(g):
            weight = 0.25
        if hit.signal == "too_good_to_be_true" and hit.detail == "task":
            weight = 0.5  # paid likes/reviews/tasks: the task-scam hook, not just optimistic marketing
        out.append(make(hit.signal, confidence=0.95 if hit.signal == "credential_request" else 0.9,
                        evidence_ids=[span.id], weight=weight, quote=hit.quote, detail=hit.detail))
        seen.add(hit.signal)
    if "ai_injection_text" not in seen and g.ai_directed_text:
        span = book.add_message_span(g.ai_directed_text[0])
        out.append(make("ai_injection_text", confidence=0.85, evidence_ids=[span.id], quote=g.ai_directed_text[0]))
        seen.add("ai_injection_text")
    # An amount the model labelled as a fee, in a job/loan/prize context, is an upfront fee.
    if "upfront_fee" not in seen and (g.scam_type in ("job_offer", "loan_app") or g.scheme == "lottery_prize"):
        for amt in g.of("amount"):
            if amt.attrs.get("purpose") == "fee" and "upfront_fee" not in seen:
                span = book.add_message_span(_context(g.haystack, amt.raw))
                out.append(make("upfront_fee", confidence=0.8, evidence_ids=[span.id], entity_ids=[amt.id],
                                quote=span.title, amount=amt.attrs.get("display")))
                seen.add("upfront_fee")
    # payment request also implied by a UPI ID handed out in the message
    if "payment_request" not in seen and requested_upis(g):
        upi = requested_upis(g)[0]
        span = book.add_message_span(_context(g.haystack, upi.raw), [upi.id])
        out.append(make("payment_request", confidence=0.85, weight=0.25, evidence_ids=[span.id],
                        entity_ids=[upi.id], quote=span.title))
    return out


def _context(text: str, needle: str, width: int = 70) -> str:
    i = text.find(needle)
    if i < 0:
        return needle
    lo, hi = max(0, i - width), min(len(text), i + len(needle) + width)
    snippet = re.sub(r"\s+", " ", text[lo:hi]).strip()
    return ("…" if lo else "") + snippet + ("…" if hi < len(text) else "")


# =========================================================================== identity
def identity_signals(ctx: Ctx) -> list[Signal]:
    g, book, off = ctx.graph, ctx.book, ctx.official
    out: list[Signal] = []
    urls = g.of("url")
    org = g.first("org") or g.first("company")

    for u in urls:
        a = u.attrs
        span = book.add_message_span(_context(g.haystack, u.raw), [u.id])
        if a.get("punycode"):
            out.append(make("punycode_homograph", confidence=0.9, evidence_ids=[span.id], entity_ids=[u.id],
                            domain=a.get("display")))
        if a.get("suspicious_tld"):
            out.append(make("suspicious_tld", confidence=0.9, evidence_ids=[span.id], entity_ids=[u.id],
                            domain=a.get("display"), tld="." + str(a.get("suffix", "")).split(".")[-1]))
        if a.get("shortener"):
            out.append(make("url_shortener", confidence=0.95, evidence_ids=[span.id], entity_ids=[u.id],
                            domain=a.get("display")))
        brand_key = a.get("brand_org") or a.get("lookalike_org")
        if brand_key and not a.get("official_org"):
            org_def = next(o for o in domains.orgs() if o.key == brand_key)
            ref = book.add_reference(
                f"Official website of {org_def.name}: {org_def.domains[0]}", f"https://{org_def.domains[0]}",
                "From Asli's list of verified official domains.",
            )
            out.append(make("brand_lookalike_domain", confidence=0.95, evidence_ids=[span.id, ref.id],
                            entity_ids=[u.id], domain=a.get("display"), brand=org_def.name,
                            official=org_def.domains[0]))
            continue
        if off and a.get("registrable") and not a.get("known_platform") and not a.get("gov"):
            if not domains.domain_matches(a["registrable"], off.domains):
                out.append(make("official_domain_mismatch", confidence=off.confidence if off.source != "curated" else 0.9,
                                evidence_ids=[span.id, *off.evidence_ids], entity_ids=[u.id],
                                domain=a.get("display"), org=off.name, official=off.domains[0]))
                continue
        if (not off and g.org_category in AUTHORITY_CATEGORIES and not a.get("official_org")
                and not a.get("gov") and not a.get("bank_tld") and not a.get("known_platform") and not a.get("shortener")):
            out.append(make("authority_unofficial_domain", confidence=0.75, evidence_ids=[span.id],
                            entity_ids=[u.id], domain=a.get("display"), category=g.org_category))

    for e in g.of("email"):
        if e.attrs.get("free_mail") and (org or g.scam_type == "job_offer") and g.org_category != "other":
            span = book.add_message_span(_context(g.haystack, e.raw), [e.id])
            ev = [span.id] + (off.evidence_ids if off else [])
            out.append(make("free_email_corporate", confidence=0.95, evidence_ids=ev, entity_ids=[e.id],
                            email=e.value, provider=e.attrs.get("domain"),
                            org=off.name if off else (org.value if org else None),
                            official=off.domains[0] if off else None))
        elif off and e.attrs.get("registrable") and not e.attrs.get("free_mail") \
                and not domains.domain_matches(e.attrs["registrable"], off.domains):
            span = book.add_message_span(_context(g.haystack, e.raw), [e.id])
            out.append(make("official_domain_mismatch", confidence=off.confidence, evidence_ids=[span.id, *off.evidence_ids],
                            entity_ids=[e.id], domain=e.attrs["registrable"], org=off.name, official=off.domains[0]))

    # Authorities, banks and utilities don't collect money into personal UPI accounts.
    if g.org_category in AUTHORITY_CATEGORIES or g.scheme in AUTHORITY_SCHEMES:
        for upi in requested_upis(g):
            span = book.add_message_span(_context(g.haystack, upi.raw), [upi.id])
            personal = upi.attrs.get("handle") in PERSONAL_UPI
            out.append(make("authority_personal_upi", confidence=0.85 if personal else 0.7, evidence_ids=[span.id],
                            entity_ids=[upi.id], upi=upi.value, category=g.org_category or "government"))
            break

    # Trust: every link/email domain in the message is official.
    linked = [e for e in g.of("url", "email") if e.attrs.get("registrable") and not e.attrs.get("free_mail")]
    if off and linked and all(domains.domain_matches(e.attrs["registrable"], off.domains) for e in linked):
        out.append(make("domain_official", confidence=0.9 if off.source == "curated" else 0.8,
                        evidence_ids=off.evidence_ids, entity_ids=[e.id for e in linked],
                        org=off.name, official=off.domains[0]))
    return out


# =========================================================================== phones
def phone_signals(ctx: Ctx) -> list[Signal]:
    g, book, off = ctx.graph, ctx.book, ctx.official
    out: list[Signal] = []
    confirmed: set[str] = set()

    # Official confirmation (KG phones or site: search on the official domain)
    for phone in g.of("phone"):
        digits = re.sub(r"\D", "", phone.value)[-10:]
        if off and any(digits and digits in re.sub(r"\D", "", p) for p in off.phones):
            out.append(make("phone_on_official_site", confidence=0.85, evidence_ids=off.evidence_ids,
                            entity_ids=[phone.id], phone=phone.attrs.get("display"), official=off.domains[0]))
            confirmed.add(phone.id)
    for spec, _outcome in ctx.ok("official_phone_check"):
        pid = spec.entity_ids[0]
        phone = next(e for e in g.entities if e.id == pid)
        if pid in confirmed:
            continue
        # Google matched the quoted number inside the official site, but snippets often omit it, so a
        # result counts when it's a contact/help page (marketplaces also host third-party listings).
        official_items = [i for i in book.for_search(spec.id) if i.source_class == "official"]
        contact_pages = [i for i in official_items if _CONTACT_PAGE.search(f"{i.url or ''} {i.title}")]
        if contact_pages:
            shown = [i for i in contact_pages if pid in i.matched_entities]
            out.append(make("phone_on_official_site", confidence=0.9 if shown else 0.85,
                            evidence_ids=_top(shown or contact_pages, 3), entity_ids=[pid],
                            phone=phone.attrs.get("display"), official=(shown or contact_pages)[0].domain))
            confirmed.add(pid)
        elif off:
            # Absence on the official site is weaker for toll-free numbers: they're registered to
            # businesses, so scammers rarely hold one.
            conf = 0.45 if phone.attrs.get("kind") == "toll_free" else 0.7
            out.append(make("official_contact_mismatch", confidence=conf, evidence_ids=list(off.evidence_ids),
                            entity_ids=[pid], phone=phone.attrs.get("display"), official=off.domains[0], org=off.name,
                            query=spec.params.get("q"), other_pages=len(official_items)))

    # Big organisations publish toll-free/landline helplines; a personal mobile number is a red flag.
    # Without a named organisation ("your electricity will be cut, call our officer on 98…") the same
    # holds for any utility, bank or authority, so the generic form cites the message alone.
    helpline_schemes = ("customer_care", "kyc_update", "bank_account_block", "courier_customs",
                        "electricity_disconnection", "tax_refund")
    authority_claim = g.org_category in AUTHORITY_CATEGORIES or g.scheme in AUTHORITY_SCHEMES
    if g.scheme in helpline_schemes and (off or authority_claim):
        for phone in g.of("phone"):
            if phone.attrs.get("kind") == "mobile" and phone.id not in confirmed:
                span = book.add_message_span(_context(g.haystack, phone.raw), [phone.id])
                if off:
                    out.append(make("helpline_is_mobile", confidence=0.6, evidence_ids=[span.id, *off.evidence_ids],
                                    entity_ids=[phone.id], phone=phone.attrs.get("display"), org=off.name,
                                    official=off.domains[0]))
                else:
                    out.append(make("helpline_is_mobile", confidence=0.6, evidence_ids=[span.id],
                                    entity_ids=[phone.id], phone=phone.attrs.get("display"), detail="generic"))

    # Whose number is this? A clean mention on a well-known organisation's own contact/help page (not a
    # warning page, and not a product or seller page: marketplaces host third-party text scammers can plant).
    for spec, _outcome in ctx.ok("phone_reputation"):
        pid = spec.entity_ids[0]
        if pid in confirmed:
            continue
        phone = next(e for e in g.entities if e.id == pid)
        owners = [i for i in book.for_search(spec.id)
                  if pid in i.matched_entities and not i.lexicon_hits and i.domain
                  and i.domain not in book.message_domains
                  and (i.source_class == "official" or domains.org_for_domain(i.domain))
                  and _CONTACT_PAGE.search(f"{i.url or ''} {i.title}")
                  and (off is None or domains.domain_matches(i.domain, off.domains))]
        if owners:
            owner = domains.org_for_domain(owners[0].domain)
            out.append(make("phone_on_official_site", confidence=0.85, evidence_ids=_top(owners, 3), entity_ids=[pid],
                            phone=phone.attrs.get("display"), official=owners[0].domain,
                            org=owner.name if owner else owners[0].domain))
            confirmed.add(pid)

    # Reputation: same result must contain the number AND a scam word, on another site.
    # Official numbers get quoted in fraud warnings ("report fraud at 1800…"), so once a number
    # is confirmed on the official site it takes 3+ independent reports to flag it.
    for spec, _outcome in ctx.ok("phone_reputation"):
        pid = spec.entity_ids[0]
        phone = next(e for e in g.entities if e.id == pid)
        items = [i for i in book.for_search(spec.id)
                 if pid in i.matched_entities and report_hits(i.lexicon_hits) and i.source_class != "official"]
        independent = EvidenceBook.independent(items)
        if pid in confirmed and len(independent) < 3:
            continue
        if independent:
            out.append(make("phone_reported", confidence=report_confidence(independent), evidence_ids=_top(independent),
                            entity_ids=[pid], phone=phone.attrs.get("display"), n=len(independent),
                            sites=_sites(independent)))
    return out


def upi_signals(ctx: Ctx) -> list[Signal]:
    g, book = ctx.graph, ctx.book
    out: list[Signal] = []
    for spec, _outcome in ctx.ok("upi_reputation"):
        uid = spec.entity_ids[0]
        upi = next(e for e in g.entities if e.id == uid)
        items = [i for i in book.for_search(spec.id) if uid in i.matched_entities and report_hits(i.lexicon_hits)]
        independent = EvidenceBook.independent(items)
        if independent:
            out.append(make("upi_reported", confidence=report_confidence(independent), evidence_ids=_top(independent),
                            entity_ids=[uid], upi=upi.value, n=len(independent), sites=_sites(independent)))
    return out


# =========================================================================== domains
def domain_signals(ctx: Ctx) -> list[Signal]:
    g, book = ctx.graph, ctx.book
    out: list[Signal] = []
    for spec, _outcome in ctx.ok("domain_reputation"):
        eid = spec.entity_ids[0]
        ent = next(e for e in g.entities if e.id == eid)
        reg = ent.attrs.get("registrable")
        items = book.for_search(spec.id)
        mentioning = [i for i in items if eid in i.matched_entities]
        reports = [i for i in mentioning if i.lexicon_hits and i.domain != reg]
        independent = EvidenceBook.independent(reports)
        display = domains.defang(reg) if reg else ent.value
        if independent:
            out.append(make("domain_reported", confidence=report_confidence(independent), evidence_ids=_top(independent),
                            entity_ids=[eid], domain=display, n=len(independent), sites=_sites(independent)))
        elif not mentioning:
            span = book.add_message_span(_context(g.haystack, ent.raw), [eid])
            ref = book.add_search_ref(spec.id, spec.engine, spec.params.get("q", ""), len(items))
            out.append(make("domain_no_footprint", confidence=0.7, evidence_ids=[span.id, ref.id], entity_ids=[eid],
                            domain=display, query=spec.params.get("q")))
    return out


# =========================================================================== patterns (news)
def pattern_signals(ctx: Ctx) -> list[Signal]:
    g, book = ctx.graph, ctx.book
    out: list[Signal] = []
    keywords = SCHEME_NEWS_KEYWORDS.get(g.scheme, [])
    for spec, _outcome in ctx.ok("pattern_news"):
        items = book.for_search(spec.id)
        today = date.today()
        relevant = []
        for i in items:
            text = f"{i.title} {i.snippet or ''}".lower()
            fresh = i.published_at is None or (today - i.published_at).days <= PATTERN_WINDOW_DAYS
            if fresh and i.lexicon_hits and any(k in text for k in keywords):
                relevant.append(i)
        independent = EvidenceBook.independent(relevant)
        if len(independent) >= 2:
            out.append(make("known_scam_pattern", confidence=0.85 if len(independent) >= 3 else 0.7,
                            evidence_ids=_top(independent, 5), n=len(independent), sites=_sites(independent),
                            scheme=g.scheme))
        org = g.first("org") or g.first("company")
        if org:
            about_org = EvidenceBook.independent([i for i in relevant if org.id in i.matched_entities])
            if len(about_org) >= 2:
                out.append(make("org_impersonation_reports", confidence=0.7, evidence_ids=_top(about_org, 3),
                                entity_ids=[org.id], org=org.value, n=len(about_org)))
    return out


# =========================================================================== shopping
def shopping_signals(ctx: Ctx) -> list[Signal]:
    g, book = ctx.graph, ctx.book
    out: list[Signal] = []
    if g.scam_type != "shopping_deal":
        return out
    price_ent = g.first("price")
    if price_ent is None:
        amounts = g.of("amount")
        price_ent = min(amounts, key=lambda e: int(e.value)) if amounts else None
    product = g.first("product")

    lens_items: list[EvidenceItem] = []
    for spec, _ in ctx.ok("lens"):
        lens_items = [i for i in book.for_search(spec.id) if i.domain not in book.message_domains]
    priced = [i for i in lens_items if i.data.get("price_inr")]
    if product:  # visually similar ≠ same product: keep listings whose title names this product
        same = [i for i in priced if _same_product(product.value, i.title)]
        priced = same if len(same) >= 3 else priced
    basis = "lens"
    if len(priced) < 3:
        for spec, _ in ctx.ok("price_lookup"):
            offers = [i for i in book.for_search(spec.id) if i.data.get("price_inr")]
            if product:
                offers = [i for i in offers if fuzz.token_set_ratio(product.value.lower(), i.title.lower()) >= 70]
            if len(offers) >= 3:
                priced, basis = offers, "shopping"
    if price_ent and len(priced) >= 3:
        prices = _iqr_filter([float(i.data["price_inr"]) for i in priced])
        kept = [i for i in priced if float(i.data["price_inr"]) in prices]
        median = statistics.median(prices)
        claimed = int(price_ent.value) / 100
        ratio = claimed / median if median else 1.0
        spread = (statistics.quantiles(prices, n=4)[2] - statistics.quantiles(prices, n=4)[0]) / median if len(prices) >= 4 and median else 1.0
        conf = 0.9 if len(prices) >= 5 and spread <= 0.5 else 0.75
        cards = sorted(EvidenceBook.independent(kept), key=lambda i: (i.source_class not in ("official", "marketplace"), -i.relevance))
        facts = dict(claimed=rx.rupees(int(claimed * 100)), median=rx.rupees(int(median * 100)), n=len(prices),
                     pct_below=round((1 - ratio) * 100), basis=basis)
        if ratio < 0.4:
            out.append(make("price_anomaly", confidence=conf, weight=0.65 if ratio < 0.2 else 0.5,
                            evidence_ids=[c.id for c in cards[:6]], entity_ids=[price_ent.id], **facts))
        elif 0.6 <= ratio <= 1.4:
            out.append(make("price_plausible", confidence=0.8, evidence_ids=[c.id for c in cards[:4]],
                            entity_ids=[price_ent.id], **facts))
    # Same photo on several other shops, including brand/marketplace listings.
    if lens_items:
        independent = EvidenceBook.independent(lens_items)
        strong = [i for i in independent if i.source_class in ("official", "marketplace")]
        if len(independent) >= 2 and strong:
            ordered = strong + [i for i in independent if i not in strong]
            out.append(make("image_reused", confidence=0.8, evidence_ids=[i.id for i in ordered[:6]],
                            n=len(independent), sites=_sites(ordered)))
    return out


_PRODUCT_STOP = {"men", "mens", "women", "womens", "for", "the", "and", "shoes", "shoe", "sneakers", "sneaker",
                 "casual", "buy", "online", "india", "new", "original", "with", "box", "s"}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _PRODUCT_STOP}




def _same_product(product: str, title: str) -> bool:
    want, have = _tokens(product), _tokens(title)
    # "Jordan 1 Low" vs "Jordan 1 High": a different variant word means a different product
    want_var = want & {"low", "mid", "high"}
    if want_var and (have & {"low", "mid", "high"}) - want_var:
        return False
    if len(want) < 3:
        return fuzz.token_set_ratio(product.lower(), title.lower()) >= 80
    return len(want & have) / len(want) >= 0.75


def _iqr_filter(values: list[float]) -> list[float]:
    if len(values) < 4:
        return values
    q1, _, q3 = statistics.quantiles(values, n=4)
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    kept = [v for v in values if lo <= v <= hi]
    return kept or values


# =========================================================================== jobs & places
def job_signals(ctx: Ctx) -> list[Signal]:
    g, book = ctx.graph, ctx.book
    out: list[Signal] = []
    if g.scam_type != "job_offer":
        return out
    company = g.first("company") or g.first("org")
    role = g.first("job_role")
    for spec, _outcome in ctx.ok("job_listing"):
        items = book.for_search(spec.id)
        matches = [i for i in items if company and fuzz.token_set_ratio(company.value.lower(),
                                                                        (i.data.get("company") or "").lower()) >= 85]
        if role:
            matches = [i for i in matches if fuzz.token_set_ratio(role.value.lower(), i.title.lower()) >= 60]
        if matches:
            out.append(make("job_listing_match", confidence=0.8, evidence_ids=_top(matches, 3),
                            entity_ids=[company.id] if company else [], company=company.value if company else "",
                            n=len(matches)))
        else:
            ref = ctx.official.evidence_ids if ctx.official else []
            span = book.add_message_span(_context(g.haystack, role.raw if role else (company.raw if company else "")))
            search = book.add_search_ref(spec.id, spec.engine, spec.params.get("q", ""), len(items))
            out.append(make("job_not_listed", confidence=0.6, evidence_ids=[span.id, search.id, *ref],
                            entity_ids=[company.id] if company else [], company=company.value if company else "",
                            role=role.value if role else "", query=spec.params.get("q"), n_results=len(items)))
    # Company with no web presence at all (only for non-curated names).
    if company and not company.attrs.get("curated") and ctx.official is None:
        for spec, _outcome in ctx.ok("org_lookup"):
            items = book.for_search(spec.id)
            if not any(company.id in i.matched_entities and i.source_class != "complaint_forum" for i in items):
                span = book.add_message_span(_context(g.haystack, company.raw), [company.id])
                ref = book.add_search_ref(spec.id, spec.engine, spec.params.get("q", ""), len(items))
                out.append(make("company_no_footprint", confidence=0.7, evidence_ids=[span.id, ref.id],
                                entity_ids=[company.id], company=company.value))
    return out


def place_signals(ctx: Ctx) -> list[Signal]:
    g, book = ctx.graph, ctx.book
    out: list[Signal] = []
    company = g.first("company") or g.first("org")
    for spec, _outcome in ctx.ok("address_check"):
        address = next(e for e in g.entities if e.id == spec.entity_ids[0])
        places = book.for_search(spec.id)
        if company:
            match = [p for p in places if fuzz.token_set_ratio(company.value.lower(), p.title.lower()) >= 80
                     or (ctx.official and p.data.get("website")
                         and domains.registrable(domains.host_of(p.data["website"]) or "") in ctx.official.domains)]
            if match:
                out.append(make("maps_business_match", confidence=0.7, evidence_ids=_top(match, 2),
                                entity_ids=[address.id, company.id], company=company.value))
                continue
        top = places[:5]
        residential = [p for p in top if any(t in " ".join([p.data.get("type") or "", *p.data.get("types", [])]).lower()
                                             for t in RESIDENTIAL_TYPES)]
        span = book.add_message_span(_context(g.haystack, address.raw), [address.id])
        out.append(make("address_mismatch", confidence=0.7 if residential else (0.6 if places else 0.5),
                        evidence_ids=[span.id] + [p.id for p in (residential or top)[:3]],
                        entity_ids=[address.id] + ([company.id] if company else []),
                        company=company.value if company else "", n_places=len(places),
                        n_residential=len(residential), address=address.value))
    return out


def _sites(items: list[EvidenceItem], n: int = 3) -> str:
    names = []
    for i in items:
        name = i.data.get("source") or i.domain
        if name and name not in names:
            names.append(name)
    return ", ".join(names[:n])


def all_signals(ctx: Ctx) -> list[Signal]:
    signals = (
        message_signals(ctx) + identity_signals(ctx) + phone_signals(ctx) + upi_signals(ctx) + domain_signals(ctx)
        + pattern_signals(ctx) + shopping_signals(ctx) + job_signals(ctx) + place_signals(ctx)
    )
    # one signal per (id, entities) — keep the most confident
    best: dict[tuple[str, tuple[str, ...]], Signal] = {}
    for s in signals:
        key = (s.id, tuple(sorted(s.entity_ids)))
        if key not in best or s.contribution > best[key].contribution:
            best[key] = s
    out = list(best.values())
    # News about a *kind* of scam is context, not evidence about this message: it only counts when the
    # message itself shows the scam's mechanics (a request, an identity mismatch, a report…). Otherwise a
    # genuine SBI alert would inherit every "SBI scam" headline. Urgency and "not found" don't qualify.
    if not any(s.polarity == "risk" and s.id not in CONTEXT_SIGNALS | NOT_A_HOOK for s in out):
        out = [s for s in out if s.id not in CONTEXT_SIGNALS]
    return out


CONTEXT_SIGNALS = {"known_scam_pattern", "org_impersonation_reports"}
NOT_A_HOOK = {"threat_or_urgency", "official_contact_mismatch", "domain_no_footprint", "company_no_footprint",
              "job_not_listed"}


def verifiable_entities(graph: ClaimGraph) -> list[Entity]:
    return graph.of("org", "company", "phone", "url", "email", "address", "product", "image", "upi_id")


__all__ = ["Ctx", "Official", "resolve_official", "all_signals", "verifiable_entities", "suspicious_domains"]
