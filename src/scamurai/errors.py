"""Error codes surfaced to the UI. Messages are user-facing and never include internals."""

from __future__ import annotations


class ScamuraiError(Exception):
    def __init__(self, code: str, message: str, *, status: int = 400, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable

    def as_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message, "retryable": self.retryable}


class InputError(ScamuraiError):
    pass


class QuotaExhausted(ScamuraiError):
    def __init__(self, message: str = "Live search limit reached. Showing what could be checked.") -> None:
        super().__init__("quota_exhausted", message, status=429, retryable=False)


class ConfigError(ScamuraiError):
    pass
