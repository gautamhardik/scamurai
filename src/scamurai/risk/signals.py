"""Signal registry: every risk/trust signal Scamurai can raise, with its weight and category.

Weights are expert-set and calibrated on the scenario suite (tests/e2e), not learned.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scamurai.models import Signal

Category = Literal["identity", "web", "message", "trust"]


@dataclass(frozen=True)
class SignalDef:
    id: str
    code: str
    category: Category
    weight: float
    critical: bool = False

    @property
    def polarity(self) -> str:
        return "trust" if self.category == "trust" else "risk"


REGISTRY: dict[str, SignalDef] = {
    d.id: d
    for d in [
        # identity — who the message claims to be vs. where it actually points
        SignalDef("brand_lookalike_domain", "I1", "identity", 0.60),
        SignalDef("official_domain_mismatch", "I2", "identity", 0.45),
        SignalDef("authority_unofficial_domain", "I3", "identity", 0.40),
        SignalDef("free_email_corporate", "I4", "identity", 0.35),
        SignalDef("punycode_homograph", "I5", "identity", 0.50),
        SignalDef("helpline_is_mobile", "I6", "identity", 0.30),
        SignalDef("authority_personal_upi", "I7", "identity", 0.45),
        # web evidence — what live search found
        SignalDef("phone_reported", "W1", "web", 0.60),
        SignalDef("domain_reported", "W2", "web", 0.60),
        SignalDef("official_contact_mismatch", "W3", "web", 0.30),
        SignalDef("domain_no_footprint", "W4", "web", 0.20),
        SignalDef("company_no_footprint", "W5", "web", 0.35),
        SignalDef("known_scam_pattern", "W6", "web", 0.35),
        SignalDef("org_impersonation_reports", "W7", "web", 0.15),
        SignalDef("price_anomaly", "W8", "web", 0.50),
        SignalDef("image_reused", "W9", "web", 0.30),
        SignalDef("job_not_listed", "W10", "web", 0.15),
        SignalDef("address_mismatch", "W11", "web", 0.30),
        SignalDef("upi_reported", "W12", "web", 0.60),
        # message patterns — deterministic, quoted from the message
        SignalDef("credential_request", "M1", "message", 0.65, critical=True),
        SignalDef("upfront_fee", "M2", "message", 0.60, critical=True),
        SignalDef("threat_or_urgency", "M3", "message", 0.15),
        SignalDef("payment_request", "M4", "message", 0.20),
        SignalDef("ai_injection_text", "M5", "message", 0.30),
        SignalDef("suspicious_tld", "M6", "message", 0.15),
        SignalDef("url_shortener", "M7", "message", 0.10),
        SignalDef("too_good_to_be_true", "M8", "message", 0.25),
        SignalDef("extortion_threat", "M9", "message", 0.65, critical=True),
        # trust — official confirmation
        SignalDef("phone_on_official_site", "T1", "trust", 0.75),
        SignalDef("domain_official", "T2", "trust", 0.70),
        SignalDef("job_listing_match", "T3", "trust", 0.40),
        SignalDef("maps_business_match", "T4", "trust", 0.25),
        SignalDef("price_plausible", "T5", "trust", 0.15),
    ]
}


def make(
    signal_id: str,
    *,
    confidence: float,
    evidence_ids: list[str],
    entity_ids: list[str] | None = None,
    weight: float | None = None,
    **facts: object,
) -> Signal:
    d = REGISTRY[signal_id]
    return Signal(
        id=signal_id,
        polarity=d.polarity,  # type: ignore[arg-type]
        weight=d.weight if weight is None else weight,
        confidence=round(max(0.0, min(1.0, confidence)), 3),
        evidence_ids=evidence_ids,
        entity_ids=entity_ids or [],
        facts=dict(facts),
    )


def ladder(independent_sources: int) -> float:
    """Confidence from the number of independent sites reporting the same thing."""
    if independent_sources >= 3:
        return 0.95
    if independent_sources == 2:
        return 0.80
    return 0.60
