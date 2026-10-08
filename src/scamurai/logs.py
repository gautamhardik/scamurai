"""JSON logging with secret redaction.

SerpApi takes the API key as a query parameter, and `requests` puts the full URL in
exception messages, so every log line and exception text is passed through `redact()`.
Message text supplied by users is never logged.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time

_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(api_key=)[^&\s'\"]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"sk-or-v1-[A-Za-z0-9]+"), "[REDACTED]"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+"), r"\1[REDACTED]"),
    (re.compile(r"\b[a-f0-9]{64}\b"), "[REDACTED]"),
]


def redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def mask_phone(value: str) -> str:
    """`+917000012345` -> `+91700001••45`; keeps enough to correlate, not to dial."""
    digits = re.sub(r"\D", "", value)
    if len(digits) < 6:
        return "••••"
    return f"+{digits[:-4]}••{digits[-2:]}" if value.startswith("+") else f"{digits[:-4]}••{digits[-2:]}"


class _JsonFormatter(logging.Formatter):
    _std = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in self._std and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return redact(json.dumps(payload, ensure_ascii=False, default=str))


_configured = False


def setup_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for noisy in ("urllib3", "requests", "httpx", "httpcore", "PIL", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True


def log_event(logger: logging.Logger, event: str, **fields: object) -> None:
    logger.info(event, extra={"event": event, **fields})
