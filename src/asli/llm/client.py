"""OpenRouter client for free models: one JSON request per investigation, cached, with
server-side model fallback and a single retry on shared-pool rate limits."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from asli.config import Settings
from asli.logs import log_event
from asli.store import Store

log = logging.getLogger("asli.llm")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
FREE_DAILY_LIMIT = 50


@dataclass
class LLMResult:
    data: dict[str, Any] | None
    model: str | None = None
    error: str | None = None
    cached: bool = False
    latency_ms: int = 0


def parse_json_lenient(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        value = json.loads(text[start: end + 1])
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


class LLMClient:
    def __init__(self, settings: Settings, store: Store, replay_llm: dict[str, dict] | None = None) -> None:
        self.settings = settings
        self.store = store
        self.replay = settings.asli_mode == "replay"
        self.replay_llm = replay_llm or {}

    @property
    def configured(self) -> bool:
        return self.settings.llm_configured

    async def complete_json(
        self,
        *,
        system: str,
        user_text: str,
        image_jpeg: bytes | None,
        cache_key: str,
        replay_key: str,
        prompt_version: str,
    ) -> LLMResult:
        if self.replay:
            rec = self.replay_llm.get(replay_key)
            if rec is None:
                return LLMResult(None, error="not_recorded")
            return LLMResult(rec.get("data"), model=rec.get("model"), cached=True)

        cached = self.store.llm_get(cache_key)
        if cached is not None:
            return LLMResult(cached.get("data"), model=cached.get("model"), cached=True)

        if not self.configured:
            return LLMResult(None, error="llm_not_configured")
        if self.store.usage_get()["llm_calls"] >= FREE_DAILY_LIMIT - 2:
            return LLMResult(None, error="llm_daily_limit")

        content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
        if image_jpeg is not None:
            content.append({
                "type": "image_url",
                "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(image_jpeg).decode()},
            })
        models = self.settings.asli_vision_models if image_jpeg is not None else self.settings.asli_text_models
        body = {
            "models": models[:3],
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": self.settings.asli_llm_max_tokens,
            "reasoning": ({"enabled": False} if self.settings.asli_llm_reasoning == "off"
                          else {"effort": self.settings.asli_llm_reasoning}),
        }
        headers = {
            "Authorization": "Bearer " + self.settings.openrouter_api_key.get_secret_value().strip(),  # type: ignore[union-attr]
            "HTTP-Referer": "https://github.com/gautamhardik/asli",
            "X-Title": "Asli",
        }
        started = time.perf_counter()
        deadline = started + self.settings.asli_llm_timeout_s  # one budget for both attempts
        error = "unknown"
        async with httpx.AsyncClient(timeout=self.settings.asli_llm_timeout_s) as client:
            for attempt in range(2):
                remaining = deadline - time.perf_counter()
                if remaining < 10:
                    error = "llm_timeout"
                    break
                try:
                    r = await client.post(OPENROUTER_URL, json=body, headers=headers, timeout=remaining)
                except httpx.TimeoutException:
                    error = "llm_timeout"
                    break
                except httpx.HTTPError as exc:
                    error = f"llm_network:{type(exc).__name__}"
                    break
                if r.status_code == 429 and attempt == 0:
                    error = "llm_rate_limited"
                    await asyncio.sleep(4)
                    continue
                if r.status_code != 200:
                    error = "llm_rate_limited" if r.status_code == 429 else f"llm_http_{r.status_code}"
                    break
                try:
                    payload = r.json()
                except ValueError:
                    payload = None
                if not isinstance(payload, dict):  # e.g. an HTML error page from an upstream proxy
                    error = "llm_bad_response"
                    break
                choice = (payload.get("choices") or [{}])[0]
                choice = choice if isinstance(choice, dict) else {}
                message = choice.get("message") or {}
                data = parse_json_lenient(message.get("content"))
                self.store.usage_incr(llm=1)
                if data is None:
                    error = "llm_bad_json" if message.get("content") else f"llm_empty:{choice.get('finish_reason')}"
                    log_event(log, "llm_unusable", model=payload.get("model"), error=error, attempt=attempt + 1)
                    if attempt == 0:  # reasoning models sometimes spend the budget thinking: retry once
                        body["max_tokens"] = int(body["max_tokens"] * 1.5)
                        continue
                    break
                model = payload.get("model")
                latency = int((time.perf_counter() - started) * 1000)
                self.store.llm_put(cache_key, model, prompt_version, {"data": data, "model": model})
                log_event(log, "llm_call", model=model, latency_ms=latency, attempt=attempt + 1)
                return LLMResult(data, model=model, latency_ms=latency)
        log_event(log, "llm_failed", error=error)
        return LLMResult(None, error=error, latency_ms=int((time.perf_counter() - started) * 1000))
