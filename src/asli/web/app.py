"""FastAPI app: static UI + streaming investigation API.

Local-first: binds 127.0.0.1 by default, same-origin only (no CORS), strict CSP, per-IP rate
limit and a cap on concurrent investigations to protect the free API quotas.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from asli import __version__
from asli.config import PACKAGE_DIR, get_settings
from asli.errors import AsliError, InputError
from asli.ingest.images import MAX_UPLOAD_BYTES, sniff
from asli.ingest.validate import validate_input
from asli.investigate.orchestrator import Investigator
from asli.logs import log_event, setup_logging
from asli.store import Store

log = logging.getLogger("asli.web")
STATIC = Path(__file__).resolve().parent / "static"

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data: blob: https://serpapi.com https://*.gstatic.com https://*.googleusercontent.com; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


class RateLimiter:
    def __init__(self, limit: int, window_s: float) -> None:
        self.limit, self.window = limit, window_s
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


def _err(exc: AsliError) -> JSONResponse:
    return JSONResponse({"error": exc.as_dict()}, status_code=exc.status)


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging()
    store = Store(settings.db_path)
    store.prune(retention_days=settings.asli_report_retention_days)
    investigator = Investigator(settings, store)
    limiter = RateLimiter(settings.asli_rate_limit_per_10min, 600)
    slots = asyncio.Semaphore(settings.asli_max_concurrent_investigations)
    token = settings.asli_access_token.get_secret_value() if settings.asli_access_token else None
    scenarios = json.loads((PACKAGE_DIR / "demo" / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]

    app = FastAPI(title="Asli", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def security(request: Request, call_next):  # type: ignore[no-untyped-def]
        if token and request.url.path.startswith("/api/"):
            supplied = request.headers.get("x-asli-token") or request.cookies.get("asli_token") or ""
            if not secrets.compare_digest(supplied, token):
                return JSONResponse({"error": {"code": "unauthorized", "message": "Access token required."}}, 401)
        response: Response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if token and request.url.path == "/" and request.query_params.get("token") == token:
            response.set_cookie("asli_token", token, httponly=True, samesite="strict")
        return response

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        credits = await investigator.serp.credits_left() if settings.asli_mode == "live" else None
        return {
            "status": "ok",
            "version": __version__,
            "mode": settings.asli_mode,
            "serpapi": {"configured": settings.serpapi_configured, "credits_left": credits},
            "llm": {"configured": settings.llm_configured},
            "today": store.usage_get(),
        }

    @app.get("/api/examples")
    async def examples() -> list[dict[str, Any]]:
        return [
            {
                "id": s["id"], "title": s["title"], "kind": s["kind"], "text": s.get("text"),
                "image": f"/static/examples/{s['image']}" if s.get("image") else None,
                "image_url": s.get("image_url"),
            }
            for s in scenarios if s["id"] != "electricity_injection"
        ]

    @app.get("/api/investigations/{investigation_id}")
    async def get_report(investigation_id: str) -> JSONResponse:
        if not investigation_id.isalnum() or len(investigation_id) > 32:
            return JSONResponse({"error": {"code": "not_found", "message": "Report not found."}}, 404)
        report = store.get_report(investigation_id)
        if report is None:
            return JSONResponse({"error": {"code": "not_found", "message": "Report not found or expired."}}, 404)
        return JSONResponse(report)

    @app.post("/api/investigations")
    async def investigate(
        request: Request,
        text: str | None = Form(None),
        url: str | None = Form(None),
        phone: str | None = Form(None),
        image_url: str | None = Form(None),
        lang: str = Form("auto"),
        example_id: str | None = Form(None),
        image: UploadFile | None = File(None),
    ) -> Response:
        client = request.client.host if request.client else "local"
        if not limiter.allow(client):
            return _err(AsliError("rate_limited", "Too many checks in a short time. Please wait a minute.",
                                  status=429, retryable=True))
        image_bytes: bytes | None = None
        if image is not None and image.filename:
            image_bytes = await image.read(MAX_UPLOAD_BYTES + 1)
            if len(image_bytes) > MAX_UPLOAD_BYTES:
                return _err(InputError("image_too_large", "That image is over 5 MB. Try a smaller screenshot.", status=413))
            if not image_bytes:
                image_bytes = None
            elif sniff(image_bytes) is None:
                return _err(InputError("invalid_image", "Asli can read PNG, JPG or WebP screenshots only.", status=415))
        try:
            inp = validate_input(text=text, image=image_bytes, image_url=image_url, url=url, phone=phone,
                                 lang=lang, example_id=example_id)
        except AsliError as exc:
            return _err(exc)

        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def emit(event: dict[str, Any]) -> None:
            await queue.put(event)

        async def runner() -> None:
            try:
                if slots.locked():
                    await emit({"type": "queued"})
                async with slots:
                    report, _ = await investigator.run(inp, emit)
                    await emit({"type": "report", "report": report.model_dump(mode="json")})
            except AsliError as exc:
                await emit({"type": "error", **exc.as_dict()})
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log_event(log, "investigation_crashed", error=type(exc).__name__)
                log.exception("investigation crashed")
                await emit({"type": "error", "code": "internal",
                            "message": "Something went wrong on our side. Please try again.", "retryable": True})
            finally:
                await queue.put(None)

        task = asyncio.create_task(runner())

        async def stream():  # type: ignore[no-untyped-def]
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=10)
                    except TimeoutError:
                        yield b'{"type":"ping"}\n'
                        continue
                    if event is None:
                        break
                    yield (json.dumps(event, ensure_ascii=False, default=str) + "\n").encode("utf-8")
            finally:
                if not task.done():
                    task.cancel()

        return StreamingResponse(stream(), media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    return app
