import itertools

import pytest

from asli.risk.engine import evaluate
from asli.risk.signals import REGISTRY, make


def sig(signal_id, confidence=0.9, entities=None, weight=None):
    return make(signal_id, confidence=confidence, evidence_ids=["v1"], entity_ids=entities or [], weight=weight)


def run(signals, coverage=1.0, verifiable=2, with_results=2, sources=2):
    return evaluate(signals, coverage=coverage, verifiable=verifiable, checks_with_results=with_results,
                    independent_sources=sources)


def test_electricity_scam_is_high_risk():
    s = [sig("authority_unofficial_domain", 0.75), sig("known_scam_pattern", 0.85), sig("payment_request"),
         sig("threat_or_urgency"), sig("suspicious_tld")]
    e = run(s)
    assert e.level == "HIGH_RISK" and e.score == 70 and e.confidence == "high"


def test_official_confirmation_is_low_risk():
    e = run([sig("phone_on_official_site", 0.9, ["e1"])])
    assert e.level == "LOW_RISK" and e.score == 0


def test_nothing_to_check_is_unverified():
    e = run([], coverage=0.0, verifiable=0, with_results=0, sources=0)
    assert e.level == "UNVERIFIED" and e.confidence == "low"


def test_message_patterns_alone_are_capped():
    s = [sig("threat_or_urgency"), sig("payment_request"), sig("suspicious_tld"), sig("too_good_to_be_true"),
         sig("url_shortener"), sig("ai_injection_text")]
    e = run(s)
    assert e.score <= 55 and "message_only_cap" in e.caps and e.level != "HIGH_RISK"


def test_critical_message_signal_can_be_high_risk_without_web_evidence():
    e = run([sig("credential_request", 0.95), sig("threat_or_urgency")], verifiable=0)
    assert e.level == "HIGH_RISK"


def test_weak_web_signals_cannot_reach_high_risk():
    # absence-of-evidence signals only: high points but no strong evidence → demoted
    s = [sig("domain_no_footprint", 0.7), sig("company_no_footprint", 0.7), sig("job_not_listed", 0.6),
         sig("threat_or_urgency"), sig("payment_request"), sig("suspicious_tld"), sig("too_good_to_be_true"),
         sig("address_mismatch", 0.5)]
    e = run(s)
    assert e.score >= 65 and e.level == "SUSPICIOUS" and "gate_demotion" in e.caps


def test_contradiction_caps_at_suspicious():
    s = [sig("phone_on_official_site", 0.9, ["e1"]), sig("phone_reported", 0.95, ["e1"]),
         sig("credential_request", 0.95), sig("known_scam_pattern", 0.85)]
    e = run(s)
    assert e.contradiction and e.level == "SUSPICIOUS" and e.confidence == "low"


def test_low_coverage_is_never_low_risk():
    e = run([], coverage=0.3, verifiable=3, with_results=0, sources=0)
    assert e.level == "UNVERIFIED"


RISK_IDS = [k for k, d in REGISTRY.items() if d.polarity == "risk"]
TRUST_IDS = [k for k, d in REGISTRY.items() if d.polarity == "trust"]


@pytest.mark.parametrize("combo", list(itertools.combinations(RISK_IDS, 2))[:120])
def test_adding_risk_never_lowers_points(combo):
    base = run([sig(combo[0])])
    more = run([sig(combo[0]), sig(combo[1])])
    assert more.risk_points >= base.risk_points


@pytest.mark.parametrize("trust", TRUST_IDS)
def test_adding_trust_never_raises_score(trust):
    risk = [sig("known_scam_pattern"), sig("threat_or_urgency"), sig("official_contact_mismatch")]
    assert run(risk + [sig(trust)]).score <= run(risk).score


def test_score_is_deterministic():
    s = [sig("brand_lookalike_domain", 0.95), sig("price_anomaly", 0.9, weight=0.65), sig("image_reused", 0.8)]
    assert run(s).score == run(list(reversed(s))).score
