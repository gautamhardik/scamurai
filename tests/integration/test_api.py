import json

import pytest
from fastapi.testclient import TestClient

from asli.config import get_settings


@pytest.fixture
def client(replay_settings):
    get_settings.cache_clear()
    from asli.web.app import create_app

    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def test_health_and_security_headers(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["mode"] == "replay"
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "access-control-allow-origin" not in r.headers


def test_index_and_examples(client):
    assert "Ask Asli" in client.get("/").text
    assert client.get("/static/app.css").headers["cache-control"] == "no-cache"
    ex = client.get("/api/examples").json()
    assert {e["id"] for e in ex} >= {"electricity_hi", "nike_deal", "sbi_alert_genuine"}


def test_input_errors_are_friendly(client):
    r = client.post("/api/investigations", data={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "empty_input"
    r = client.post("/api/investigations", files={"image": ("x.svg", b"<svg onload=alert(1)>", "image/svg+xml")})
    assert r.status_code == 415


def test_streams_a_report(client):
    data = {"text": "Amazon customer care number 9876501234. Call now for the refund of your cancelled order, "
                    "refund will expire today.", "example_id": "customer_care_amazon"}
    r = client.post("/api/investigations", data=data)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in r.text.splitlines() if line.strip()]
    types = [e["type"] for e in events]
    assert types[0] == "accepted" and types[-1] == "report"
    assert "claims" in types and "plan" in types and "check" in types
    report = events[-1]["report"]
    assert report["level"] in ("HIGH_RISK", "SUSPICIOUS")
    again = client.get(f"/api/investigations/{report['id']}").json()
    assert again["id"] == report["id"]


def test_oversized_body_rejected_before_parsing(client):
    big = b"\xff\xd8\xff" + b"0" * (6 * 1024 * 1024)
    r = client.post("/api/investigations", files={"image": ("big.jpg", big, "image/jpeg")})
    assert r.status_code == 413 and r.json()["error"]["code"] == "image_too_large"


def test_report_ids_are_validated(client):
    assert client.get("/api/investigations/..%2F..%2Fetc").status_code == 404
