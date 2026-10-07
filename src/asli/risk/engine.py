"""Deterministic risk engine.

    R = 1 − Π(1 − w·c) over risk signals        (noisy-OR: independent warning signs add up)
    T = 1 − Π(1 − v·c) over trust signals
    score = round(100 · R · (1 − 0.75·T))       (risk points, not a probability)

Gates keep weak evidence from producing strong verdicts:
  G1  HIGH needs an identity/web signal with c ≥ .6 and w·c ≥ .25, or a critical message signal.
  G2  With no identity/web signal and no critical signal, the score is capped at 55.
  G3  Official confirmation + risk evidence on the same entity → at most SUSPICIOUS ("mixed").
  G4  LOW needs positive confirmation (a trust signal with w·c ≥ .3); otherwise a low score is UNVERIFIED.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from asli.models import Signal
from asli.risk.signals import REGISTRY

HIGH_THRESHOLD = 65
SUSPICIOUS_THRESHOLD = 35
MESSAGE_ONLY_CAP = 55
TRUST_FLOOR = 0.3  # w·c of the weakest trust signal that can support a "no major warning signs" verdict
CONTRADICTING = {"phone_reported", "domain_reported", "brand_lookalike_domain", "official_domain_mismatch"}


@dataclass
class Evaluation:
    level: str
    score: int
    confidence: str
    caps: list[str] = field(default_factory=list)
    contradiction: bool = False
    risk_points: float = 0.0
    trust_points: float = 0.0


def _noisy_or(values: list[float]) -> float:
    return 1 - math.prod(1 - max(0.0, min(1.0, v)) for v in values)


def evaluate(
    signals: list[Signal],
    *,
    coverage: float,
    verifiable: int,
    checks_with_results: int,
    independent_sources: int,
) -> Evaluation:
    risk = [s for s in signals if s.polarity == "risk"]
    trust = [s for s in signals if s.polarity == "trust"]
    r = _noisy_or([s.contribution for s in risk])
    t = _noisy_or([s.contribution for s in trust])
    raw = 100 * r * (1 - 0.75 * t)
    caps: list[str] = []

    evidence_signals = [s for s in risk if REGISTRY[s.id].category in ("identity", "web")]
    critical = any(REGISTRY[s.id].critical for s in risk)
    strong = any(s.confidence >= 0.6 and s.contribution >= 0.25 for s in evidence_signals)

    if not evidence_signals and not critical and raw > MESSAGE_ONLY_CAP:
        raw = MESSAGE_ONLY_CAP
        caps.append("message_only_cap")

    contradiction = False
    for ts in trust:
        if ts.id in ("phone_on_official_site", "domain_official") and ts.contribution >= 0.5:
            for rs in risk:
                if rs.id in CONTRADICTING and set(rs.entity_ids) & set(ts.entity_ids):
                    contradiction = True
    score = int(round(raw))

    if score >= HIGH_THRESHOLD:
        if contradiction:
            level = "SUSPICIOUS"
            caps.append("contradiction_cap")
        elif strong or critical:
            level = "HIGH_RISK"
        else:
            level = "SUSPICIOUS"
            caps.append("gate_demotion")
    elif score >= SUSPICIOUS_THRESHOLD:
        level = "SUSPICIOUS"
        if contradiction:
            caps.append("contradiction_cap")
    elif coverage >= 0.6 and verifiable >= 1 and checks_with_results >= 1 and any(
            s.contribution >= TRUST_FLOOR for s in trust):
        # Reassurance needs positive confirmation (official page, official domain, a real listing).
        # Searches that merely returned something prove nothing, and a plausible price or a Maps pin
        # alone is too weak: an unconfirmed message stays UNVERIFIED.
        level = "LOW_RISK"
    else:
        level = "UNVERIFIED"

    deterministic_identity = any(
        REGISTRY[s.id].category == "identity" and s.confidence >= 0.85 for s in risk
    )
    if level == "UNVERIFIED" or contradiction:
        confidence = "low"
    elif coverage >= 0.8 and (independent_sources >= 2 or deterministic_identity
                              or (level == "LOW_RISK" and any(s.contribution >= 0.5 for s in trust))):
        confidence = "high"
    elif coverage >= 0.5:
        confidence = "medium"
    else:
        confidence = "low"

    return Evaluation(level, score, confidence, caps, contradiction, round(r, 4), round(t, 4))
