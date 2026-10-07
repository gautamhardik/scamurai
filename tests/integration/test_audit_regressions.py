"""Regressions for issues found in the adversarial audit (see docs/AUDIT.md). Tests for fixed bugs
reproduced the failure before the fix; the hostile-upload tests pin behaviour that was already correct."""

import io
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from asli.config import Settings, get_settings
from asli.errors import AsliError
from asli.ingest import regex_extract as rx
from asli.ingest.images import prepare_image
from asli.ingest.validate import validate_input
from asli.investigate.orchestrator import Investigator
from asli.llm import client as llm_client
from asli.serp import client as serp_client
from asli.store import Store

NO_RESULTS = {"error": "Google hasn't returned any results for this query."}


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("ASLI_MODE", "live")
    monkeypatch.setenv("ASLI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    get_settings.cache_clear()
    yield Settings(_env_file=None)
    get_settings.cache_clear()


def _serp(monkeypatch, responder):
    async def no_credits(self, max_age_s=600):
        return None

    monkeypatch.setattr(serp_client.SerpClient, "credits_left", no_credits)
    monkeypatch.setattr(serp_client.SerpClient, "_call", lambda self, request, timeout: responder(request))


def _llm(monkeypatch, data):
    async def fake(self, **kw):
        return llm_client.LLMResult(data, model="test-model")

    monkeypatch.setattr(llm_client.LLMClient, "complete_json", fake)


async def _run(settings, text):
    report, _ = await Investigator(settings, Store(settings.db_path)).run(validate_input(text=text))
    return report


# ----------------------------------------------------------------------------- trust poisoning (P0)
async def test_a_message_domain_cannot_confirm_itself(live, monkeypatch):
    """A made-up company's own site ranks first for its own name; it must not become 'official'."""
    _llm(monkeypatch, {"scheme": "job_offer", "language": "en",
                       "claimed_org": {"name": "Zentrix Hiring Solutions", "category": "employer"},
                       "job": {"company": "Zentrix Hiring Solutions", "role": "Data Entry"}})

    def responder(req):
        q = req.get("q", "")
        if "official website" in q:
            return {"organic_results": [{"position": 1, "title": "Zentrix Hiring Solutions - Official Site",
                                         "link": "https://zentrixhiring.com/", "snippet": "Welcome"}]}
        if q.startswith("site:"):
            return {"organic_results": [{"position": 1, "title": "Contact Us", "link": "https://zentrixhiring.com/contact",
                                         "snippet": "HR 98111 22334"}]}
        return NO_RESULTS

    _serp(monkeypatch, responder)
    report = await _run(live, "Dear Candidate, you are selected at Zentrix Hiring Solutions for Data Entry. "
                              "Complete onboarding at zentrixhiring.com and call HR on 98111 22334.")
    assert not [f for f in report.flags if f.polarity == "trust"]
    assert report.level != "LOW_RISK"


async def test_number_on_a_marketplace_product_page_is_not_official(live, monkeypatch):
    """Scammers plant 'helpline' numbers in product listings and Q&A on big platforms."""
    _llm(monkeypatch, {"scheme": "customer_care", "language": "en",
                       "claimed_org": {"name": "Amazon", "category": "ecommerce"}})

    def responder(req):
        q = req.get("q", "")
        if "98765" in q and not q.startswith("site:"):
            return {"organic_results": [{"position": 1, "title": "Boat Rockerz 450 : Amazon.in: Electronics",
                                         "link": "https://www.amazon.in/dp/B07XYZ",
                                         "snippet": "Customer questions: call 98765 11111"}]}
        return NO_RESULTS

    _serp(monkeypatch, responder)
    report = await _run(live, "Amazon customer care number 98765 11111. Call now for your refund, it expires today.")
    assert "phone_on_official_site" not in {f.signal_id for f in report.flags}
    assert report.level != "LOW_RISK"


async def test_unrelated_results_are_not_reassurance(live, monkeypatch):
    """'No major warning signs' needs positive confirmation, not merely non-empty searches."""
    _llm(monkeypatch, {"scheme": "courier_customs", "language": "en", "claimed_org": {"name": None}})

    def responder(req):
        if req["engine"] == "google_news":
            return {"news_results": [{"title": "Monsoon update", "link": "https://news.example/a"}]}
        return {"organic_results": [{"position": i, "title": f"Unrelated {i}", "link": f"https://site{i}.example/",
                                     "snippet": "nothing about this"} for i in range(1, 9)]}

    _serp(monkeypatch, responder)
    report = await _run(live, "Hi, this is Priya from the courier office. Please call 98222 33444 about your parcel.")
    assert report.level == "UNVERIFIED"


# ----------------------------------------------------------------------------- LLM failure (P1)
async def test_unparseable_llm_response_degrades_to_rules(live, monkeypatch):
    class HtmlPage:
        status_code = 200

        def json(self):
            raise ValueError("not json")

    async def post(self, *a, **k):
        return HtmlPage()

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    settings = Settings(_env_file=None)
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    _serp(monkeypatch, lambda req: NO_RESULTS)
    report = await _run(settings, "Your SBI KYC is pending. Update at sbi-kyc.top now or your account is blocked.")
    assert report.stats.extraction == "regex_fallback"
    assert any(n.startswith("llm:") for n in report.notes)
    assert "brand_lookalike_domain" in {f.signal_id for f in report.flags}


# ----------------------------------------------------------------------------- web security (P1)
@pytest.fixture
def client(replay_settings):
    from asli.web.app import create_app

    with TestClient(create_app(), base_url="http://127.0.0.1:8000") as c:
        yield c


def test_cross_site_posts_are_refused(client):
    data = {"text": "Amazon customer care number 9876501234. Call now for the refund of your cancelled order, "
                    "refund will expire today.", "example_id": "customer_care_amazon"}
    assert client.post("/api/investigations", data=data, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/investigations", data=data, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.post("/api/investigations", data=data, headers={"Origin": "null"}).status_code == 403
    ok = client.post("/api/investigations", data=data, headers={"Origin": "http://127.0.0.1:8000"})
    assert ok.status_code == 200


def test_foreign_host_header_is_refused(replay_settings):
    from asli.web.app import create_app

    app = create_app()
    with TestClient(app, base_url="http://attacker.example") as c:
        assert c.get("/api/health").status_code == 400
    with TestClient(app, base_url="http://localhost:8000") as c:
        assert c.get("/api/health").status_code == 200


# ----------------------------------------------------------------------------- inputs
def test_amount_regex_is_linear_and_reads_hindi_prefix():
    started = time.perf_counter()
    rx.amounts("1" * 4000)
    rx.emails("a.b@" * 1000)
    assert time.perf_counter() - started < 0.2
    assert [f.value for f in rx.amounts("रु. 500 जमा करें")] == ["50000"]
    assert [f.value for f in rx.amounts("salary 45,000/- per month")] == ["4500000"]


@pytest.mark.parametrize("data", [
    pytest.param(lambda: _png(20000, 20000), id="decompression-bomb"),
    pytest.param(lambda: b"\xff\xd8\xff\xe0" + b"<script>alert(1)</script>" * 40, id="jpeg-html-polyglot"),
    pytest.param(lambda: _png(64, 64)[:60], id="truncated-png"),
    pytest.param(lambda: b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>", id="svg"),
])
def test_hostile_uploads_are_rejected(data):
    with pytest.raises(AsliError):
        prepare_image(data())


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("1", (w, h)).save(buf, "PNG")
    return buf.getvalue()


def test_prune_drops_expired_search_cache(tmp_path):
    store = Store(tmp_path / "s.sqlite3")
    store.cache_put("old", "google", {"q": "98765 11111"}, {"organic_results": []}, ttl_s=-1)
    store.cache_put("new", "google", {"q": "x"}, {"organic_results": []}, ttl_s=3600)
    store.prune()
    rows = {r[0] for r in store._conn.execute("SELECT key FROM search_cache")}
    assert rows == {"new"}


# ----------------------------------------------------------------------------- live-eval false alarm (P1)
async def test_genuine_bank_alert_does_not_inherit_scam_headlines(live, monkeypatch):
    """Live eval: a real SBI debit alert scored HIGH_RISK 65 from helpline-directory 'reports',
    SBI-scam news and a merchant UPI ID. None of those are evidence about this message."""
    _llm(monkeypatch, {"scheme": "bank_account_block", "language": "en",
                       "claimed_org": {"name": "SBI", "category": "bank"}})

    def responder(req):
        q = req.get("q", "")
        if req["engine"] == "google_news":
            return {"news_results": [{"title": f"SBI fake message alert {i}: do not fall for account blocked scam",
                                      "link": f"https://news{i}.example/sbi", "source": {"name": f"News {i}"},
                                      "iso_date": "2026-09-01T00:00:00Z"} for i in range(1, 6)]}
        if q.startswith("(site:") or q.startswith("site:"):
            assert "sbi.bank.in" in q  # the official-number check covers SBI's new domain
            return NO_RESULTS
        return {"organic_results": [
            {"position": 1, "title": "SBI Banking Customer Care Number", "link": "https://www.facebook.com/sbi-help",
             "snippet": "1800 11 2211 is also listed for other fraud reports and complaints."},
            {"position": 2, "title": "SBI Complaint 1800 11 2211", "link": "https://complaintmitra.in/sbi",
             "snippet": "Use the complaint number 1800 11 2211."}]}

    _serp(monkeypatch, responder)
    report = await _run(live, "Dear Customer, Rs 1,250.00 debited from A/c XX4521 on 05-10-26 to VPA swiggy@icici. "
                              "Not you? Call 1800 11 2211 to block. -SBI")
    ids = {f.signal_id for f in report.flags}
    assert not ids & {"phone_reported", "known_scam_pattern", "org_impersonation_reports", "payment_request",
                      "authority_personal_upi"}
    assert report.level not in ("HIGH_RISK", "SUSPICIOUS")
    assert {"Phone": "1800 11 2211"}.items() <= {c.label: c.value for c in report.claims_summary}.items()


def test_upi_payee_in_a_transaction_notice_is_not_a_request():
    from asli.knowledge.patterns import upi_is_requested

    assert not upi_is_requested("Rs 1,250.00 debited from A/c XX4521 to VPA swiggy@icici. Not you? Call 1800 11 2211.",
                                "swiggy@icici")
    assert not upi_is_requested("Rs 300 received from rahul@okaxis. UPI Ref 1234", "rahul@okaxis")
    assert upi_is_requested("Rs 5,000 credited by mistake. Please return it to refund.desk@ybl", "refund.desk@ybl")
    assert upi_is_requested("50,000 rupaye is UPI par bhejiye: cbi.verify@ybl", "cbi.verify@ybl")
    assert upi_is_requested("रजिस्ट्रेशन शुल्क ₹1,999 इस UPI पर भेजें: amazonhr.jobs@ybl", "amazonhr.jobs@ybl")


def test_toll_free_numbers_keep_their_grouping():
    assert rx.phone_display("1800112211") == "1800 11 2211"
    assert rx.phone_display("18004253800") == "1800 425 3800"


def test_upi_id_is_not_mistaken_for_a_website():
    """'amazonhr.jobs@ybl' produced a 'website has no track record' flag for amazonhr.jobs."""
    assert rx.urls("Registration fee via UPI: amazonhr.jobs@ybl") == []
    assert [f.value for f in rx.urls("Pay at sbi-kyc.top or UPI pay.kyc@ybl")] == ["sbi-kyc.top"]
