"""Engine-specific response → common evidence fields. Tolerant: missing fields never crash,
malformed items are skipped and counted."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from urllib.parse import quote_plus

_TAGS = re.compile(r"<[^>]+>")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁦-⁩]")


def clean(text: Any, limit: int) -> str | None:
    if not isinstance(text, str):
        return None
    text = _CTRL.sub("", _TAGS.sub("", text))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def safe_url(url: Any) -> str | None:
    if isinstance(url, str) and re.match(r"^https?://", url, re.IGNORECASE) and len(url) <= 2048:
        return url
    return None


def parse_date(item: dict[str, Any]) -> date | None:
    iso = item.get("iso_date")
    if isinstance(iso, str):
        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    raw = item.get("date")
    if isinstance(raw, str):
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", raw)
        if m:
            try:
                return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
            except ValueError:
                return None
        for fmt in ("%b %d, %Y", "%d %b %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(raw.strip(), fmt).date()
            except ValueError:
                continue
    return None


def google(data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    kg = data.get("knowledge_graph")
    if isinstance(kg, dict) and kg.get("title"):
        phones = sorted({
            v for k, v in kg.items()
            if isinstance(v, str) and ("phone" in k or "customer_service" in k) and re.search(r"\d{3}", v)
        })
        out.append({
            "kind": "knowledge_graph",
            "title": clean(kg.get("title"), 200),
            "url": safe_url(kg.get("website")),
            "snippet": clean(kg.get("description") or kg.get("type"), 300),
            "position": 0,
            "data": {"type": clean(kg.get("type"), 80), "website": safe_url(kg.get("website")), "phones": phones},
        })
    for item in data.get("organic_results") or []:
        if not isinstance(item, dict) or not safe_url(item.get("link")):
            continue
        out.append({
            "kind": "organic",
            "title": clean(item.get("title"), 200) or clean(item.get("displayed_link"), 200) or "Result",
            "url": safe_url(item.get("link")),
            "snippet": clean(item.get("snippet"), 300),
            "position": item.get("position"),
            "published_at": parse_date(item),
            "data": {"source": clean(item.get("source"), 80)},
        })
    return out


def news(data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    flat: list[dict[str, Any]] = []
    for item in data.get("news_results") or []:
        if not isinstance(item, dict):
            continue
        if item.get("link"):
            flat.append(item)
        for story in item.get("stories") or []:
            if isinstance(story, dict) and story.get("link"):
                flat.append(story)
    for pos, item in enumerate(flat, start=1):
        if not safe_url(item.get("link")):
            continue
        source = item.get("source")
        source_name = source.get("name") if isinstance(source, dict) else source
        out.append({
            "kind": "news",
            "title": clean(item.get("title"), 200) or "News article",
            "url": safe_url(item.get("link")),
            "snippet": clean(item.get("snippet"), 300),
            "position": pos,
            "published_at": parse_date(item),
            "data": {"source": clean(source_name, 80)},
        })
    return out


def lens(data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in (data.get("exact_matches") or []) + (data.get("visual_matches") or []):
        if not isinstance(item, dict) or not safe_url(item.get("link")):
            continue
        price = item.get("price") if isinstance(item.get("price"), dict) else {}
        currency = price.get("currency")
        value = price.get("extracted_value")
        out.append({
            "kind": "lens_match",
            "title": clean(item.get("title"), 200) or "Image match",
            "url": safe_url(item.get("link")),
            "snippet": None,
            "position": item.get("position"),
            "thumbnail": safe_url(item.get("thumbnail")),
            "data": {
                "source": clean(item.get("source"), 80),
                "price_inr": float(value) if currency == "₹" and isinstance(value, (int, float)) else None,
                "price_text": clean(price.get("value"), 30),
                "in_stock": item.get("in_stock"),
            },
        })
    return out


def shopping(data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in data.get("shopping_results") or []:
        if not isinstance(item, dict):
            continue
        price = item.get("extracted_price")
        url = safe_url(item.get("link")) or safe_url(item.get("product_link"))
        if not url:
            continue
        out.append({
            "kind": "shopping_offer",
            "title": clean(item.get("title"), 200) or "Listing",
            "url": url,
            "snippet": None,
            "position": item.get("position"),
            "thumbnail": safe_url(item.get("serpapi_thumbnail") or item.get("thumbnail")),
            "data": {
                "source": clean(item.get("source"), 80),
                "price_inr": float(price) if isinstance(price, (int, float)) else None,
                "price_text": clean(item.get("price"), 30),
                "rating": item.get("rating"),
            },
        })
    return out


def jobs(data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pos, item in enumerate(data.get("jobs_results") or [], start=1):
        if not isinstance(item, dict):
            continue
        apply = [o for o in item.get("apply_options") or [] if isinstance(o, dict) and safe_url(o.get("link"))]
        url = safe_url(apply[0]["link"]) if apply else safe_url(item.get("share_link"))
        ext = item.get("detected_extensions") if isinstance(item.get("detected_extensions"), dict) else {}
        out.append({
            "kind": "job",
            "title": clean(item.get("title"), 200) or "Job listing",
            "url": url,
            "snippet": clean(item.get("description"), 240),
            "position": pos,
            "data": {
                "company": clean(item.get("company_name"), 120),
                "location": clean(item.get("location"), 120),
                "via": clean(item.get("via"), 80),
                "salary": clean(ext.get("salary"), 60),
                "posted_at": clean(ext.get("posted_at"), 40),
                "apply_links": [safe_url(o.get("link")) for o in apply[:5]],
            },
        })
    return out


def maps(data: dict[str, Any]) -> list[dict[str, Any]]:
    places: list[dict[str, Any]] = []
    if isinstance(data.get("place_results"), dict):
        places.append(data["place_results"])
    places.extend(p for p in data.get("local_results") or [] if isinstance(p, dict))
    out: list[dict[str, Any]] = []
    for pos, place in enumerate(places, start=1):
        title = clean(place.get("title"), 160)
        if not title:
            continue
        address = clean(place.get("address"), 200)
        types = place.get("types") if isinstance(place.get("types"), list) else []
        maps_url = "https://www.google.com/maps/search/?api=1&query=" + quote_plus(f"{title} {address or ''}".strip())
        out.append({
            "kind": "place",
            "title": title,
            "url": maps_url,
            "snippet": address,
            "position": place.get("position") or pos,
            "data": {
                "address": address,
                "type": clean(place.get("type"), 80),
                "types": [clean(t, 60) for t in types[:6] if isinstance(t, str)],
                "website": safe_url(place.get("website")),
                "phone": clean(place.get("phone"), 40),
                "rating": place.get("rating"),
                "reviews": place.get("reviews"),
            },
        })
    return out


NORMALIZERS = {
    "google": google,
    "google_news": news,
    "google_lens": lens,
    "google_shopping": shopping,
    "google_jobs": jobs,
    "google_maps": maps,
}
