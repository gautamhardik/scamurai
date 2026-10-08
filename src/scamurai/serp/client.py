"""SerpApi access: the only place Scamurai talks to SerpApi.

- Official `serpapi` SDK (sync) run in worker threads, bounded concurrency.
- SQLite cache keyed by engine + canonical params (never the API key); Lens is keyed by the
  image's content hash because upload `image_id`s expire after 10 minutes.
- Per-investigation budget, daily cap and a credit reserve; 429/quota stops further searches.
- Replay mode serves recorded real responses, so demos and tests need no key or network.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import httpx
import serpapi

from scamurai.config import Settings
from scamurai.ingest.images import PreparedImage
from scamurai.logs import log_event, redact
from scamurai.store import Store

log = logging.getLogger("scamurai.serp")

TTL_HOURS = {
    "google": 24,
    "google_news": 12,
    "google_lens": 24,
    "google_shopping": 24,
    "google_jobs": 24,
    "google_maps": 168,
}
BASE_PARAMS: dict[str, dict[str, str]] = {
    "google": {"gl": "in", "hl": "en", "google_domain": "google.co.in"},
    "google_news": {"gl": "in", "hl": "en"},
    "google_lens": {"country": "in", "hl": "en"},
    "google_shopping": {"gl": "in", "hl": "en", "location": "India"},
    "google_jobs": {"gl": "in", "hl": "en"},
    "google_maps": {"type": "search", "gl": "in", "hl": "en"},
}
# Only the fields Scamurai reads are stored (smaller cache, no account metadata in recordings).
KEEP_KEYS = {
    "google": ("knowledge_graph", "organic_results", "search_information", "error"),
    "google_news": ("news_results", "error"),
    "google_lens": ("visual_matches", "exact_matches", "error"),
    "google_shopping": ("shopping_results", "error"),
    "google_jobs": ("jobs_results", "error"),
    "google_maps": ("local_results", "place_results", "error"),
}
_IGNORED_PARAMS = {"api_key", "no_cache", "async", "output", "image_id", "url"}
_NO_RESULTS_MARKERS = ("hasn't returned any results", "no results", "returned no results")
_QUOTA_MARKERS = ("run out of searches", "out of searches", "plan searches", "exceeded")


@dataclass
class SerpOutcome:
    status: Literal["done", "no_results", "failed", "skipped_quota", "skipped_budget"]
    data: dict[str, Any] = field(default_factory=dict)
    cached: bool = False
    latency_ms: int = 0
    error: str | None = None
    credits: int = 0
    key: str = ""


@dataclass
class Budget:
    """Per-investigation search budget."""

    max_searches: int
    used: int = 0
    live: int = 0
    cache_hits: int = 0
    quota_exhausted: bool = False


def _norm_q(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).lower().split())


def cache_key(engine: str, params: dict[str, str], extra: str | None = None) -> str:
    canon = {k: (_norm_q(v) if k == "q" else str(v)) for k, v in params.items() if k not in _IGNORED_PARAMS}
    canon["engine"] = engine
    if extra:
        canon["_extra"] = extra
    blob = json.dumps(canon, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def trim(engine: str, data: dict[str, Any]) -> dict[str, Any]:
    out = {k: data[k] for k in KEEP_KEYS.get(engine, ()) if k in data}
    created = (data.get("search_metadata") or {}).get("created_at")
    if created:
        out["_searched_at"] = created
    return out


class Recordings:
    """Recorded real SerpApi responses + LLM extractions (`src/scamurai/demo/recordings/*.json`)."""

    def __init__(self, directory: Path) -> None:
        self.searches: dict[str, dict[str, Any]] = {}
        self.llm: dict[str, dict[str, Any]] = {}
        self.meta: dict[str, dict[str, Any]] = {}
        if directory.exists():
            for path in sorted(directory.glob("*.json")):
                rec = json.loads(path.read_text(encoding="utf-8"))
                for key, item in rec.get("searches", {}).items():
                    self.searches[key] = item["response"]
                if rec.get("input_hash") and rec.get("llm"):
                    self.llm[rec["input_hash"]] = rec["llm"]
                if rec.get("input_hash"):
                    self.meta[rec["input_hash"]] = {"scenario": rec.get("scenario"), "recorded_at": rec.get("recorded_at")}


class Recorder:
    """Collects every response an investigation used, for `scamurai record`."""

    def __init__(self) -> None:
        self.searches: dict[str, dict[str, Any]] = {}

    def add(self, key: str, engine: str, params: dict[str, str], response: dict[str, Any]) -> None:
        safe = {k: v for k, v in params.items() if k not in {"api_key", "image_id"}}
        self.searches[key] = {"engine": engine, "params": safe, "response": response}


class SerpClient:
    def __init__(self, settings: Settings, store: Store, recordings: Recordings | None = None) -> None:
        self.settings = settings
        self.store = store
        self.replay = settings.scamurai_mode == "replay"
        self.recordings = recordings
        self._sem = asyncio.Semaphore(settings.scamurai_serp_concurrency)
        self._credits: tuple[float, int | None] = (0.0, None)
        self._inflight: dict[str, asyncio.Future[SerpOutcome]] = {}

    @property
    def _key(self) -> str | None:
        k = self.settings.serpapi_api_key
        return k.get_secret_value().strip() if k else None

    # ------------------------------------------------------------------ public
    async def search(
        self,
        engine: str,
        params: dict[str, str],
        budget: Budget,
        *,
        image: PreparedImage | None = None,
        image_url: str | None = None,
        recorder: Recorder | None = None,
    ) -> SerpOutcome:
        full = {**BASE_PARAMS.get(engine, {}), **params}
        extra = None
        if engine == "google_lens":
            extra = image.sha256 if image else hashlib.sha256((image_url or "").encode()).hexdigest()
        key = cache_key(engine, full, extra)

        if key in self._inflight:  # same query twice in one investigation → one request
            return await asyncio.shield(self._inflight[key])
        fut: asyncio.Future[SerpOutcome] = asyncio.get_running_loop().create_future()
        self._inflight[key] = fut
        try:
            outcome = await self._search(engine, full, key, budget, image, image_url)
            if recorder is not None and outcome.status in ("done", "no_results"):
                recorder.add(key, engine, full, outcome.data)
            fut.set_result(outcome)
            return outcome
        except BaseException as exc:
            fut.set_exception(exc)
            raise
        finally:
            self._inflight.pop(key, None)
            if not fut.done():
                fut.cancel()

    async def credits_left(self, max_age_s: float = 600) -> int | None:
        if self.replay or not self._key:
            return None
        ts, value = self._credits
        if time.time() - ts < max_age_s and value is not None:
            return value
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get("https://serpapi.com/account.json", params={"api_key": self._key})
            value = int(r.json().get("total_searches_left")) if r.status_code == 200 else None
        except Exception:  # noqa: BLE001 — informational only
            value = None
        self._credits = (time.time(), value)
        return value

    # ------------------------------------------------------------------ internals
    async def _search(
        self,
        engine: str,
        params: dict[str, str],
        key: str,
        budget: Budget,
        image: PreparedImage | None,
        image_url: str | None,
    ) -> SerpOutcome:
        started = time.perf_counter()

        if self.replay:
            data = (self.recordings.searches.get(key) if self.recordings else None)
            if data is None:
                return SerpOutcome("failed", error="not_recorded", key=key)
            budget.used += 1
            budget.cache_hits += 1
            return SerpOutcome(self._status_of(data), data, cached=True, key=key)

        cached = self.store.cache_get(key)
        if cached is not None:
            budget.used += 1
            budget.cache_hits += 1
            return SerpOutcome(self._status_of(cached), cached, cached=True, key=key,
                               latency_ms=int((time.perf_counter() - started) * 1000))

        if budget.quota_exhausted:
            return SerpOutcome("skipped_quota", key=key)
        if budget.used >= budget.max_searches:
            return SerpOutcome("skipped_budget", key=key)
        if not self._key:
            return SerpOutcome("failed", error="serpapi_not_configured", key=key)
        if self.store.usage_get()["serp_calls"] >= self.settings.scamurai_daily_search_cap:
            budget.quota_exhausted = True
            return SerpOutcome("skipped_quota", error="daily_cap", key=key)
        credits = await self.credits_left()
        if credits is not None and credits <= self.settings.scamurai_min_credits_reserve:
            budget.quota_exhausted = True
            return SerpOutcome("skipped_quota", error="credit_reserve", key=key)

        budget.used += 1
        timeout = {
            "google_lens": self.settings.scamurai_lens_timeout_s,
            "google_jobs": self.settings.scamurai_jobs_timeout_s,
        }.get(engine, self.settings.scamurai_serp_timeout_s)
        request = {"engine": engine, **params}
        if self.settings.scamurai_serpapi_no_cache:
            request["no_cache"] = "true"
        try:
            async with self._sem:
                if budget.quota_exhausted:  # another search hit the quota while this one was queued
                    budget.used -= 1
                    return SerpOutcome("skipped_quota", key=key)
                if engine == "google_lens":
                    if image is not None:
                        request["image_id"] = await self._upload(image, timeout)
                    elif image_url:
                        request["url"] = image_url
                    else:
                        return SerpOutcome("failed", error="no_image", key=key)
                data = await self._call_with_retry(request, timeout)
        except _Quota:
            budget.quota_exhausted = True
            log_event(log, "serp_quota", engine=engine)
            return SerpOutcome("skipped_quota", error="quota", key=key)
        except _Failed as exc:
            log_event(log, "serp_failed", engine=engine, reason=exc.reason)
            return SerpOutcome("failed", error=exc.reason, key=key,
                               latency_ms=int((time.perf_counter() - started) * 1000))

        budget.live += 1
        self.store.usage_incr(serp=1)
        if self._credits[1] is not None:
            self._credits = (self._credits[0], self._credits[1] - 1)
        trimmed = trim(engine, data)
        status = self._status_of(trimmed)
        if status in ("done", "no_results"):
            ttl_h = self.settings.scamurai_cache_ttl_hours or TTL_HOURS.get(engine, 24)
            self.store.cache_put(key, engine, {k: v for k, v in params.items() if k not in _IGNORED_PARAMS},
                                 trimmed, ttl_h * 3600)
        latency = int((time.perf_counter() - started) * 1000)
        log_event(log, "serp_search", engine=engine, status=status, latency_ms=latency, cached=False)
        return SerpOutcome(status, trimmed, cached=False, latency_ms=latency, credits=1, key=key)

    @staticmethod
    def _status_of(data: dict[str, Any]) -> Literal["done", "no_results", "failed"]:
        err = (data.get("error") or "").lower()
        if err:
            return "no_results" if any(m in err for m in _NO_RESULTS_MARKERS) else "failed"
        has_any = any(isinstance(v, (list, dict)) and v for k, v in data.items() if not k.startswith("_"))
        return "done" if has_any else "no_results"

    async def _upload(self, image: PreparedImage, timeout: float) -> str:
        def _do() -> dict[str, Any]:
            client = serpapi.Client(api_key=self._key, timeout=timeout)
            import io

            return client.upload_image(io.BytesIO(image.serp_jpeg))

        try:
            res = await asyncio.wait_for(asyncio.to_thread(_do), timeout + 5)
        except Exception as exc:  # noqa: BLE001
            raise _Failed(f"image_upload: {type(exc).__name__}") from None
        image_id = res.get("image_id") if isinstance(res, dict) else None
        if not image_id:
            raise _Failed("image_upload: " + redact(str((res or {}).get("error", "no image_id")))[:120])
        return image_id

    async def _call_with_retry(self, request: dict[str, str], timeout: float) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(2):
            try:
                return await asyncio.wait_for(asyncio.to_thread(self._call, dict(request), timeout), timeout + 5)
            except (_Quota, _Auth):
                raise
            except _Failed as exc:
                if not exc.retryable or attempt == 1:
                    raise
                last = exc
            except TimeoutError:
                last = _Failed("timeout", retryable=True)
                if attempt == 1:
                    raise last from None
            await asyncio.sleep(1.5)
        raise last or _Failed("unknown")

    def _call(self, request: dict[str, str], timeout: float) -> dict[str, Any]:
        client = serpapi.Client(api_key=self._key, timeout=timeout)
        try:
            res = client.search(request)
        except serpapi.HTTPError as exc:  # message contains the URL (with key): never surface str(exc)
            status = getattr(exc, "status_code", -1)
            err = (getattr(exc, "error", None) or "").lower()
            if status == 401:
                raise _Auth() from None
            if status == 429 or any(m in err for m in _QUOTA_MARKERS):
                raise _Quota() from None
            if status == 400 and any(m in err for m in _NO_RESULTS_MARKERS):
                return {"error": err}
            raise _Failed(f"http_{status}", retryable=status >= 500 or status == -1) from None
        except serpapi.TimeoutError:
            raise _Failed("timeout", retryable=True) from None
        except Exception as exc:  # noqa: BLE001
            raise _Failed(type(exc).__name__, retryable=True) from None
        data = dict(res)
        err = (data.get("error") or "").lower()
        if err and any(m in err for m in _QUOTA_MARKERS):
            raise _Quota()
        # A retry after a timeout can return the same search still "Processing", with no results yet.
        # That must count as a failure, never as "no results" (which would be cached for a day).
        status = (data.get("search_metadata") or {}).get("status")
        if status and status != "Success" and not err:
            raise _Failed(f"serpapi_status_{str(status).lower()}", retryable=True)
        return data


class _Failed(Exception):
    def __init__(self, reason: str, retryable: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable


class _Quota(Exception):
    pass


class _Auth(_Failed):
    def __init__(self) -> None:
        super().__init__("serpapi_auth", retryable=False)
