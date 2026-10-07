"""Failure injection: the pipeline must degrade, never crash or invent evidence."""

import pytest

from asli.config import Settings
from asli.ingest.validate import validate_input
from asli.investigate.orchestrator import Investigator
from asli.serp import client as serp_client
from asli.store import Store


@pytest.fixture
def live_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("ASLI_MODE", "live")
    monkeypatch.setenv("ASLI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    return Settings(_env_file=None)


TEXT = ("Dear customer your SBI account will be blocked today. Update KYC at sbi-kyc-update.in or call "
        "+91 70000 12345 immediately and share the OTP.")


def _patch(monkeypatch, fn):
    async def no_credits(self, max_age_s=600):
        return None

    monkeypatch.setattr(serp_client.SerpClient, "credits_left", no_credits)
    monkeypatch.setattr(serp_client.SerpClient, "_call", fn)
    monkeypatch.setattr(serp_client.asyncio, "sleep", _fast_sleep)


async def _fast_sleep(_s):
    return None


async def test_all_searches_time_out(live_settings, monkeypatch):
    calls = []

    def timeout(self, request, timeout):
        calls.append(request["engine"])
        raise serp_client._Failed("timeout", retryable=True)

    _patch(monkeypatch, timeout)
    report, _ = await Investigator(live_settings, Store(live_settings.db_path)).run(validate_input(text=TEXT))
    assert all(c.status == "failed" for c in report.checks)
    assert not any(f.polarity == "trust" for f in report.flags)
    # deterministic message + link analysis still works without search
    ids = {f.signal_id for f in report.flags}
    assert {"brand_lookalike_domain", "credential_request"} <= ids
    assert report.level == "HIGH_RISK"
    assert len(calls) == 2 * len(report.checks)  # one retry each, no loops


async def test_quota_stops_further_searches(live_settings, monkeypatch):
    calls = []

    def quota(self, request, timeout):
        calls.append(request["engine"])
        raise serp_client._Quota()

    _patch(monkeypatch, quota)
    live_settings.asli_serp_concurrency = 1
    report, _ = await Investigator(live_settings, Store(live_settings.db_path)).run(validate_input(text=TEXT))
    assert len(calls) == 1
    assert {c.status for c in report.checks} == {"skipped_quota"}


async def test_no_results_everywhere(live_settings, monkeypatch):
    def empty(self, request, timeout):
        return {"error": "Google hasn't returned any results for this query."}

    _patch(monkeypatch, empty)
    text = "Hello, please call 70000 12345 regarding your parcel."
    report, _ = await Investigator(live_settings, Store(live_settings.db_path)).run(validate_input(text=text))
    assert report.level in ("UNVERIFIED", "LOW_RISK", "SUSPICIOUS")
    assert report.level != "HIGH_RISK"


async def test_searches_are_cached(live_settings, monkeypatch):
    calls = []

    def ok(self, request, timeout):
        calls.append(request["engine"])
        return {"organic_results": [{"position": 1, "title": "Something", "link": "https://example.org/x",
                                     "snippet": "nothing relevant"}],
                "news_results": [{"title": "n", "link": "https://news.example/a"}]}

    _patch(monkeypatch, ok)
    store = Store(live_settings.db_path)
    inv = Investigator(live_settings, store)
    await inv.run(validate_input(text=TEXT))
    first = len(calls)
    report, _ = await inv.run(validate_input(text=TEXT))
    assert first > 0 and len(calls) == first  # second run: zero new searches
    assert report.stats.cache_hits == report.stats.searches_run and report.stats.credits_spent == 0


async def test_budget_cap(live_settings, monkeypatch):
    calls = []

    def ok(self, request, timeout):
        calls.append(request)
        return {"organic_results": [{"position": 1, "title": "t", "link": "https://example.org/x"}]}

    _patch(monkeypatch, ok)
    live_settings.asli_max_searches = 3
    many = "Call 7000012341, 7000012342, 7000012343. Visit a1-offer.top, b2-offer.top, c3-offer.top. Amazon refund."
    report, _ = await Investigator(live_settings, Store(live_settings.db_path)).run(validate_input(text=many))
    assert len(calls) <= 3 and report.stats.searches_run <= 3
