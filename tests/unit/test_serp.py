from asli.serp.client import SerpClient, cache_key, trim
from asli.serp.normalize import NORMALIZERS, clean, safe_url
from tests.conftest import load_fixture


def test_cache_key_ignores_api_key_and_normalizes_query():
    a = cache_key("google", {"q": "  Infosys   OFFICIAL website", "gl": "in", "api_key": "secret1"})
    b = cache_key("google", {"q": "infosys official website", "gl": "in", "api_key": "secret2"})
    assert a == b
    assert cache_key("google", {"q": "x"}) != cache_key("google_news", {"q": "x"})


def test_lens_cache_key_uses_image_hash_not_upload_id():
    a = cache_key("google_lens", {"country": "in", "image_id": "id-1"}, extra="sha-abc")
    b = cache_key("google_lens", {"country": "in", "image_id": "id-2"}, extra="sha-abc")
    assert a == b


def test_trim_keeps_only_used_fields():
    data = {"organic_results": [1], "search_metadata": {"created_at": "t", "id": "x", "json_endpoint": "u"},
            "search_parameters": {"api_key": "no"}, "pagination": {}}
    out = trim("google", data)
    assert out == {"organic_results": [1], "_searched_at": "t"}


def test_status_detection():
    assert SerpClient._status_of({"error": "Google hasn't returned any results for this query."}) == "no_results"
    assert SerpClient._status_of({"error": "Invalid API key"}) == "failed"
    assert SerpClient._status_of({"organic_results": [{"x": 1}]}) == "done"
    assert SerpClient._status_of({}) == "no_results"


def test_news_normalizer():
    items = NORMALIZERS["google_news"](load_fixture("google_news_electricity.json"))
    assert len(items) > 20
    assert all(i["url"].startswith("http") for i in items)
    assert any("electricity" in i["title"].lower() for i in items)
    assert any(i["published_at"] for i in items)


def test_lens_normalizer_extracts_rupee_prices():
    items = NORMALIZERS["google_lens"](load_fixture("google_lens_nike.json"))
    priced = [i for i in items if i["data"]["price_inr"]]
    assert len(priced) >= 5
    assert any(i["data"]["source"] == "Myntra" for i in priced)


def test_shopping_normalizer():
    items = NORMALIZERS["google_shopping"](load_fixture("google_shopping_nike.json"))
    assert len(items) == 40 and items[0]["data"]["price_inr"] == 8995


def test_maps_normalizer_types():
    items = NORMALIZERS["google_maps"](load_fixture("google_maps_noida.json"))
    assert items and items[0]["url"].startswith("https://www.google.com/maps/search/")
    assert any("Apartment" in (i["data"]["type"] or "") for i in items)


def test_jobs_no_results_fixture():
    assert NORMALIZERS["google_jobs"](load_fixture("google_jobs_infosys.json")) == []


def test_sanitizers():
    assert clean("<b>Hello</b>‮ world", 50) == "Hello world"
    assert safe_url("javascript:alert(1)") is None
    assert safe_url("https://ok.example/x") == "https://ok.example/x"
