"""End-to-end: every demo scenario, replayed from recorded real SerpApi responses + LLM output."""

import pytest

from scamurai.cli import _scenario_input
from scamurai.investigate.orchestrator import Investigator
from scamurai.risk.signals import REGISTRY
from scamurai.store import Store
from tests.conftest import scenarios

SCENARIOS = scenarios()


@pytest.mark.parametrize("sc", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
async def test_scenario(sc, replay_settings):
    store = Store(replay_settings.db_path)
    events: list[dict] = []

    async def emit(e):
        events.append(e)

    report, extra = await Investigator(replay_settings, store).run(_scenario_input(sc), emit)
    exp = sc["expect"]
    flags = {f.signal_id for f in report.flags}

    assert report.level in exp["level"], (report.level, report.headline, flags)
    for s in exp.get("must", []):
        assert s in flags, f"missing {s}: {flags}"
    if exp.get("must_any"):
        assert flags & set(exp["must_any"]), flags
    for s in exp.get("forbid", []):
        assert s not in flags, f"unexpected {s}"
    if exp.get("forbid_trust"):
        assert not [f for f in report.flags if f.polarity == "trust"]
    assert report.level not in exp.get("forbid_level", [])

    # Invariants
    ev = {e.id: e for e in report.evidence}
    for f in report.flags:
        items = [ev[i] for i in f.evidence_ids]
        assert items, f"{f.signal_id} has no evidence"
        if REGISTRY[f.signal_id].category in ("web", "trust"):
            assert any(i.kind != "message_span" for i in items), f"{f.signal_id} lacks web evidence"
    assert report.stats.searches_run <= replay_settings.scamurai_max_searches
    assert report.stats.credits_spent == 0  # replay never spends credits
    assert events[0]["type"] == "accepted" and any(e["type"] == "claims" for e in events)
    assert "score" not in (extra.get("llm") or {}).get("data", {})  # the LLM never scores


async def test_replay_is_deterministic(replay_settings):
    sc = next(s for s in SCENARIOS if s["id"] == "nike_deal")
    store = Store(replay_settings.db_path)
    a, _ = await Investigator(replay_settings, store).run(_scenario_input(sc))
    b, _ = await Investigator(replay_settings, store).run(_scenario_input(sc))
    assert (a.level, a.score, [f.signal_id for f in a.flags]) == (b.level, b.score, [f.signal_id for f in b.flags])


async def test_report_language_follows_message(replay_settings):
    store = Store(replay_settings.db_path)
    hi = next(s for s in SCENARIOS if s["id"] == "electricity_hi")
    report, _ = await Investigator(replay_settings, store).run(_scenario_input(hi))
    assert report.language == "hi"
    assert any("ऀ" <= ch <= "ॿ" for ch in report.headline)
