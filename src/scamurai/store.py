"""SQLite store: SerpApi cache, LLM cache, investigation records and daily usage counters.

One file, stdlib only. Calls are short and serialized with a lock, so they're safe to make
from the event loop.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import zlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS search_cache (
    key TEXT PRIMARY KEY,
    engine TEXT NOT NULL,
    params TEXT NOT NULL,
    body BLOB NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    hits INTEGER NOT NULL DEFAULT 0,
    last_hit_at INTEGER
);
CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY,
    model TEXT,
    prompt_version TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS investigations (
    id TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL,
    input_kinds TEXT NOT NULL,
    scam_type TEXT,
    level TEXT,
    score INTEGER,
    confidence TEXT,
    searches INTEGER,
    cache_hits INTEGER,
    latency_ms INTEGER,
    errors TEXT,
    report BLOB
);
CREATE TABLE IF NOT EXISTS usage (
    day TEXT PRIMARY KEY,
    serp_calls INTEGER NOT NULL DEFAULT 0,
    llm_calls INTEGER NOT NULL DEFAULT 0
);
"""

LLM_CACHE_TTL_S = 7 * 24 * 3600


def _pack(obj: Any) -> bytes:
    return zlib.compress(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _unpack(blob: bytes) -> Any:
    return json.loads(zlib.decompress(blob).decode("utf-8"))


class Store:
    def __init__(self, path: Path | str) -> None:
        path = Path(path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        with self._lock:
            if str(path) != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_SCHEMA)

    # ---------------------------------------------------------------- search cache
    def cache_get(self, key: str) -> dict | None:
        now = int(time.time())
        with self._lock:
            row = self._conn.execute(
                "SELECT body, expires_at FROM search_cache WHERE key = ?", (key,)
            ).fetchone()
            if row is None or row[1] < now:
                return None
            self._conn.execute(
                "UPDATE search_cache SET hits = hits + 1, last_hit_at = ? WHERE key = ?", (now, key)
            )
        return _unpack(row[0])

    def cache_put(self, key: str, engine: str, params: dict, body: dict, ttl_s: float) -> None:
        now = int(time.time())
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO search_cache (key, engine, params, body, created_at, expires_at, hits)"
                " VALUES (?, ?, ?, ?, ?, ?, 0)",
                (key, engine, json.dumps(params, sort_keys=True), _pack(body), now, now + int(ttl_s)),
            )

    def cache_clear(self, engine: str | None = None) -> int:
        with self._lock:
            if engine:
                cur = self._conn.execute("DELETE FROM search_cache WHERE engine = ?", (engine,))
            else:
                cur = self._conn.execute("DELETE FROM search_cache")
            return cur.rowcount

    # ---------------------------------------------------------------- llm cache
    def llm_get(self, key: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT body, created_at FROM llm_cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None or row[1] + LLM_CACHE_TTL_S < time.time():
            return None
        return json.loads(row[0])

    def llm_put(self, key: str, model: str | None, prompt_version: str, body: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO llm_cache (key, model, prompt_version, body, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (key, model, prompt_version, json.dumps(body, ensure_ascii=False), int(time.time())),
            )

    # ---------------------------------------------------------------- investigations
    def save_investigation(self, row: dict[str, Any], report: dict | None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO investigations (id, created_at, input_kinds, scam_type, level, score,"
                " confidence, searches, cache_hits, latency_ms, errors, report)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row["id"],
                    int(time.time()),
                    ",".join(row.get("input_kinds", [])),
                    row.get("scam_type"),
                    row.get("level"),
                    row.get("score"),
                    row.get("confidence"),
                    row.get("searches"),
                    row.get("cache_hits"),
                    row.get("latency_ms"),
                    json.dumps(row.get("errors", [])),
                    _pack(report) if report is not None else None,
                ),
            )

    def get_report(self, investigation_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT report FROM investigations WHERE id = ?", (investigation_id,)
            ).fetchone()
        if row is None or row[0] is None:
            return None
        return _unpack(row[0])

    # ---------------------------------------------------------------- usage
    @staticmethod
    def usage_day() -> str:
        """The counters' day is the UTC date: OpenRouter's free allowance resets at 00:00 UTC (05:30 IST)."""
        return datetime.now(UTC).date().isoformat()

    def usage_incr(self, *, serp: int = 0, llm: int = 0, day: str | None = None) -> None:
        day = day or self.usage_day()
        with self._lock:
            self._conn.execute(
                "INSERT INTO usage (day, serp_calls, llm_calls) VALUES (?, ?, ?)"
                " ON CONFLICT(day) DO UPDATE SET serp_calls = serp_calls + excluded.serp_calls,"
                " llm_calls = llm_calls + excluded.llm_calls",
                (day, serp, llm),
            )

    def usage_get(self, day: str | None = None) -> dict[str, int]:
        day = day or self.usage_day()
        with self._lock:
            row = self._conn.execute(
                "SELECT serp_calls, llm_calls FROM usage WHERE day = ?", (day,)
            ).fetchone()
        return {"serp_calls": row[0], "llm_calls": row[1]} if row else {"serp_calls": 0, "llm_calls": 0}

    # ---------------------------------------------------------------- maintenance
    def prune(self, *, max_cache_rows: int = 5000, retention_days: int = 7) -> None:
        now = int(time.time())
        with self._lock:
            # expired results still hold the searched numbers/IDs in their params: don't keep them
            self._conn.execute("DELETE FROM search_cache WHERE expires_at < ?", (now,))
            self._conn.execute(
                "DELETE FROM search_cache WHERE key IN (SELECT key FROM search_cache"
                " ORDER BY COALESCE(last_hit_at, created_at) DESC LIMIT -1 OFFSET ?)",
                (max_cache_rows,),
            )
            self._conn.execute(
                "DELETE FROM investigations WHERE created_at < ?", (now - retention_days * 86400,)
            )
            self._conn.execute("DELETE FROM llm_cache WHERE created_at < ?", (now - LLM_CACHE_TTL_S,))

    def close(self) -> None:
        with self._lock:
            self._conn.close()
