"""Typed contracts shared across the pipeline: input → claim graph → plan → evidence → report."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- enums
Scheme = Literal[
    "electricity_disconnection",
    "kyc_update",
    "bank_account_block",
    "courier_customs",
    "digital_arrest",
    "tax_refund",
    "job_offer",
    "task_scam",
    "shopping_deal",
    "customer_care",
    "loan_app",
    "investment_tips",
    "lottery_prize",
    "other",
]
SCHEMES: tuple[str, ...] = Scheme.__args__  # type: ignore[attr-defined]

ScamType = Literal[
    "impersonation", "fake_customer_care", "shopping_deal", "job_offer", "loan_app", "investment", "other"
]

SCHEME_TO_TYPE: dict[str, str] = {
    "electricity_disconnection": "impersonation",
    "kyc_update": "impersonation",
    "bank_account_block": "impersonation",
    "courier_customs": "impersonation",
    "digital_arrest": "impersonation",
    "tax_refund": "impersonation",
    "lottery_prize": "impersonation",
    "job_offer": "job_offer",
    "task_scam": "job_offer",
    "shopping_deal": "shopping_deal",
    "customer_care": "fake_customer_care",
    "loan_app": "loan_app",
    "investment_tips": "investment",
    "other": "other",
}

OrgCategory = Literal[
    "bank", "government", "utility", "telecom", "courier", "ecommerce", "employer", "fintech", "brand", "other"
]
Language = Literal["en", "hi", "hinglish", "mixed", "other"]
ReportLanguage = Literal["en", "hi", "hinglish"]
Engine = Literal["google", "google_news", "google_lens", "google_shopping", "google_jobs", "google_maps"]

EntityType = Literal[
    "org", "phone", "email", "url", "upi_id", "amount", "product", "price",
    "job_role", "salary", "company", "address", "app", "image",
]


# --------------------------------------------------------------------------- input
class InvestigationInput(BaseModel):
    text: str | None = None
    image: bytes | None = None
    image_url: str | None = None  # passed to Google Lens as-is; Asli never fetches it
    url: str | None = None
    phone: str | None = None
    lang: Literal["auto", "en", "hi", "hinglish"] = "auto"
    example_id: str | None = None

    @property
    def kinds(self) -> list[str]:
        return [k for k in ("text", "image", "image_url", "url", "phone") if getattr(self, k)]


# --------------------------------------------------------------------------- claim graph
class Entity(BaseModel):
    id: str
    type: EntityType
    raw: str
    value: str
    source: Literal["text", "ocr", "field", "image"] = "text"
    found_by: Literal["regex", "llm", "both", "field"] = "regex"
    attrs: dict[str, Any] = Field(default_factory=dict)


class Action(BaseModel):
    type: Literal["pay", "click_link", "call", "share_otp", "install_app", "reply", "video_call", "visit", "other"]
    quote: str


class Pressure(BaseModel):
    type: Literal["urgency", "threat", "reward", "secrecy"]
    quote: str


class ClaimGraph(BaseModel):
    language: Language = "en"
    content_kind: str = "other"
    scheme: Scheme = "other"
    scam_type: ScamType = "other"
    org_category: OrgCategory | None = None
    entities: list[Entity] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)
    pressure: list[Pressure] = Field(default_factory=list)
    ai_directed_text: list[str] = Field(default_factory=list)
    ocr_text: str = ""
    extraction: Literal["llm", "regex_fallback"] = "regex_fallback"
    llm_model: str | None = None
    ungrounded_dropped: int = 0
    notes: list[str] = Field(default_factory=list)
    # Everything the user supplied that can be quoted: text + screenshot transcript + fields.
    haystack: str = ""

    def of(self, *types: str) -> list[Entity]:
        return [e for e in self.entities if e.type in types]

    def first(self, *types: str) -> Entity | None:
        found = self.of(*types)
        return found[0] if found else None


# --------------------------------------------------------------------------- plan
class SearchSpec(BaseModel):
    id: str
    engine: Engine
    params: dict[str, str]
    purpose: str
    label: str
    entity_ids: list[str] = Field(default_factory=list)
    priority: int = 2
    round: int = 1
    cache_extra: str | None = None  # e.g. image hash for Lens (image_id changes per upload)


class SkippedCheck(BaseModel):
    purpose: str
    reason: str


class InvestigationPlan(BaseModel):
    scam_type: str
    scheme: str
    reason: str
    searches: list[SearchSpec] = Field(default_factory=list)
    skipped: list[SkippedCheck] = Field(default_factory=list)


# --------------------------------------------------------------------------- evidence
SourceClass = Literal[
    "official", "government", "news", "complaint_forum", "registry", "marketplace",
    "job_board", "social", "maps_place", "message", "other",
]


class EvidenceItem(BaseModel):
    id: str
    engine: str
    search_id: str | None = None
    kind: Literal[
        "organic", "knowledge_graph", "news", "lens_match", "shopping_offer", "job", "place", "message_span",
        "reference", "search",  # "search": the query itself, cited by absence findings so they can be re-run
    ]
    title: str
    url: str | None = None
    domain: str | None = None
    snippet: str | None = None
    published_at: date | None = None
    position: int | None = None
    source_class: SourceClass = "other"
    data: dict[str, Any] = Field(default_factory=dict)
    matched_entities: list[str] = Field(default_factory=list)
    lexicon_hits: list[str] = Field(default_factory=list)
    relevance: float = 0.0
    cached: bool = False
    clickable: bool = True
    thumbnail: str | None = None


# --------------------------------------------------------------------------- signals & report
class Signal(BaseModel):
    id: str
    polarity: Literal["risk", "trust"]
    weight: float
    confidence: float
    evidence_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)

    @property
    def contribution(self) -> float:
        return round(self.weight * self.confidence, 4)


class Flag(BaseModel):
    signal_id: str
    code: str
    polarity: Literal["risk", "trust"]
    severity: Literal["critical", "high", "medium", "low", "trust"]
    title: str
    explanation: str
    weight: float
    confidence: float
    contribution: float
    evidence_ids: list[str]
    entity_ids: list[str] = Field(default_factory=list)


class CheckResult(BaseModel):
    search_id: str
    engine: str
    purpose: str
    label: str
    status: Literal["done", "no_results", "failed", "skipped_budget", "skipped_quota", "pending"] = "pending"
    cached: bool = False
    n_results: int = 0
    latency_ms: int = 0
    error: str | None = None


class Recommendation(BaseModel):
    id: str
    text: str
    priority: int = 2
    link: str | None = None


class ClaimChip(BaseModel):
    label: str
    value: str
    kind: str


class ReportStats(BaseModel):
    searches_planned: int = 0
    searches_run: int = 0
    cache_hits: int = 0
    credits_spent: int = 0
    llm_model: str | None = None
    extraction: str = "regex_fallback"
    latency_ms: int = 0


class RiskReport(BaseModel):
    id: str
    created_at: datetime
    mode: Literal["live", "replay"]
    language: ReportLanguage
    level: Literal["HIGH_RISK", "SUSPICIOUS", "LOW_RISK", "UNVERIFIED"]
    level_title: str
    level_subtitle: str
    score: int
    confidence: Literal["high", "medium", "low"]
    confidence_reason: str
    headline: str
    scam_type: str
    scheme: str
    flags: list[Flag]
    evidence: list[EvidenceItem]
    checks: list[CheckResult]
    recommendations: list[Recommendation]
    claims_summary: list[ClaimChip]
    caps_applied: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    stats: ReportStats = Field(default_factory=ReportStats)
    recorded_at: str | None = None
