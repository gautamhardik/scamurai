"""Evidence engine: normalized search results → classified, de-duplicated, ranked evidence.

Entity and scam-word matches are computed per result (same title/snippet), never per page,
and independence is counted by registrable domain.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rapidfuzz import fuzz

from asli.knowledge import domains
from asli.knowledge.lexicon import lexicon_hits
from asli.models import ClaimGraph, Entity, EvidenceItem

SOURCE_WEIGHT = {
    "official": 1.0, "government": 1.0, "news": 0.9, "complaint_forum": 0.8, "registry": 0.7,
    "marketplace": 0.7, "job_board": 0.7, "maps_place": 0.7, "social": 0.5, "message": 0.6, "other": 0.4,
}


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith(("utm_", "fbclid", "gclid"))])
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), (parts.hostname or "").lower(), path, query, ""))


def _norm_title(t: str) -> set[str]:
    return set(re.findall(r"[a-z0-9ऀ-ॿ]+", t.lower()))


def _squash(text: str) -> str:
    """Remove spaces/hyphens/dots between digits so 98765-43210 and 98765 43210 both match."""
    return re.sub(r"(?<=\d)[\s\-.()]+(?=\d)", "", text)


class EvidenceBook:
    def __init__(self, graph: ClaimGraph) -> None:
        self.graph = graph
        self.items: dict[str, EvidenceItem] = {}
        self.by_search: dict[str, list[str]] = {}
        self._canon: dict[str, str] = {}
        self._n = 0
        self.official_domains: set[str] = set()
        self.message_domains: set[str] = {
            e.attrs["registrable"] for e in graph.of("url", "email") if e.attrs.get("registrable")
            and not e.attrs.get("free_mail") and not e.attrs.get("official_org") and not e.attrs.get("known_platform")
        }
        self.malformed = 0

    def _next_id(self) -> str:
        self._n += 1
        return f"v{self._n}"

    # ------------------------------------------------------------------ adding
    def add_search(self, search_id: str, engine: str, raw_items: list[dict[str, Any]], *, cached: bool) -> list[EvidenceItem]:
        ids: list[str] = []
        for raw in raw_items:
            try:
                item = self._make(search_id, engine, raw, cached)
            except Exception:  # noqa: BLE001 — malformed result: skip, count
                self.malformed += 1
                continue
            canon = canonical_url(item.url) if item.url else None
            if canon and canon in self._canon and item.kind not in ("place", "job", "lens_match", "shopping_offer"):
                existing = self.items[self._canon[canon]]
                existing.position = min(existing.position or 99, item.position or 99)
                ids.append(existing.id)
                continue
            self.items[item.id] = item
            if canon:
                self._canon[canon] = item.id
            ids.append(item.id)
        self.by_search[search_id] = ids
        return [self.items[i] for i in ids]

    def add_message_span(self, quote: str, entity_ids: list[str] | None = None) -> EvidenceItem:
        for item in self.items.values():
            if item.kind == "message_span" and item.title == quote:
                return item
        item = EvidenceItem(
            id=self._next_id(), engine="message", kind="message_span", title=quote[:200],
            source_class="message", matched_entities=entity_ids or [], relevance=0.6, clickable=False,
        )
        self.items[item.id] = item
        return item

    def add_reference(self, title: str, url: str, snippet: str | None = None) -> EvidenceItem:
        for item in self.items.values():
            if item.kind == "reference" and item.url == url:
                return item
        host = domains.host_of(url) or ""
        item = EvidenceItem(
            id=self._next_id(), engine="asli", kind="reference", title=title, url=url,
            domain=domains.registrable(host), snippet=snippet, source_class="official", relevance=0.9,
        )
        self.items[item.id] = item
        return item

    def _make(self, search_id: str, engine: str, raw: dict[str, Any], cached: bool) -> EvidenceItem:
        url = raw.get("url")
        host = domains.host_of(url) if url else None
        reg = domains.registrable(host) if host else None
        if raw["kind"] == "shopping_offer" and reg in ("google.com", "google.co.in"):
            reg = None  # Google Shopping product page: the seller is in data["source"]
        text = " ".join(x for x in (raw.get("title"), raw.get("snippet")) if x)
        item = EvidenceItem(
            id=self._next_id(),
            engine=engine,
            search_id=search_id,
            kind=raw["kind"],
            title=raw.get("title") or "Result",
            url=url,
            domain=reg,
            snippet=raw.get("snippet"),
            published_at=raw.get("published_at"),
            position=raw.get("position") if isinstance(raw.get("position"), int) else None,
            data=raw.get("data") or {},
            thumbnail=raw.get("thumbnail"),
            cached=cached,
        )
        item.source_class = self._classify(item, engine, reg)
        item.matched_entities = self._match(text)
        item.lexicon_hits = lexicon_hits(text)
        item.clickable = not (reg and reg in self.message_domains)
        item.relevance = self._relevance(item)
        return item

    # ------------------------------------------------------------------ classification
    def _classify(self, item: EvidenceItem, engine: str, reg: str | None) -> str:
        if item.kind == "place":
            return "maps_place"
        if item.kind == "job":
            return "job_board"
        if item.kind == "shopping_offer" and reg is None:
            return "marketplace"
        if engine == "google_news":
            return "news"
        if reg is None:
            return "other"
        if reg in self.official_domains:
            return "official"
        host = domains.host_of(item.url or "") or ""
        if domains.is_gov(host):
            return "government"
        cls = domains.source_classes().get(reg)
        if cls:
            return cls  # type: ignore[return-value]
        # another well-known organisation's own site (not the one the message claims to be)
        return "official" if domains.org_for_domain(reg) else "other"

    def mark_official(self, official: list[str]) -> None:
        self.official_domains.update(official)
        for item in self.items.values():
            if item.domain and item.kind not in ("message_span", "place", "job") and item.engine != "google_news":
                if any(item.domain == d or item.domain.endswith("." + d) for d in official):
                    item.source_class = "official"
                    item.relevance = self._relevance(item)

    # ------------------------------------------------------------------ matching
    def _match(self, text: str) -> list[str]:
        if not text:
            return []
        low = domains.refang(text.lower())
        squashed = _squash(low)
        matched: list[str] = []
        for e in self.graph.entities:
            if e.type == "phone":
                digits = re.sub(r"\D", "", e.value)
                national = digits[-10:] if e.value.startswith("+91") else digits
                if national and national in squashed:
                    matched.append(e.id)
            elif e.type in ("url", "email"):
                reg = e.attrs.get("registrable")
                if reg and reg in low:
                    matched.append(e.id)
            elif e.type in ("org", "company"):
                name = e.value.lower()
                if len(name) >= 3 and (re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", low)
                                       or (len(name) > 5 and fuzz.partial_ratio(name, low) >= 90)):
                    matched.append(e.id)
        return matched

    def _relevance(self, item: EvidenceItem) -> float:
        entity = 1.0 if item.matched_entities else 0.0
        lex = 1.0 if item.lexicon_hits else 0.0
        src = SOURCE_WEIGHT.get(item.source_class, 0.4)
        rank = 1 - (min(item.position or 10, 10) - 1) / 10
        if item.engine == "google_news" and item.published_at:
            age = (date.today() - item.published_at).days
            recency = 1.0 if age <= 90 else 0.7 if age <= 365 else 0.4 if age <= 730 else 0.2
        else:
            recency = 0.5
        return round(0.45 * entity + 0.25 * lex + 0.15 * src + 0.10 * rank + 0.05 * recency, 3)

    # ------------------------------------------------------------------ queries
    def for_search(self, search_id: str) -> list[EvidenceItem]:
        return [self.items[i] for i in self.by_search.get(search_id, [])]

    def get(self, ids: list[str]) -> list[EvidenceItem]:
        return [self.items[i] for i in ids if i in self.items]

    @staticmethod
    def independent(items: list[EvidenceItem]) -> list[EvidenceItem]:
        """One item per registrable domain (best relevance first)."""
        best: dict[str, EvidenceItem] = {}
        for it in sorted(items, key=lambda x: -x.relevance):
            key = it.domain or it.data.get("source") or it.id
            best.setdefault(key, it)
        return list(best.values())

    @staticmethod
    def similar_title(a: str, b: str) -> bool:
        ta, tb = _norm_title(a), _norm_title(b)
        return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.8


def entity_by_id(graph: ClaimGraph, eid: str) -> Entity | None:
    return next((e for e in graph.entities if e.id == eid), None)
