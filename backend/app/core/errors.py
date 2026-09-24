"""App-level exceptions.

Anything that should become a specific HTTP response raises one of these.
The handlers in main.py turn them into {"error": {...}} JSON. Kept free of
FastAPI imports so the agent and billing code can raise them too.
"""

from __future__ import annotations


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, code: str | None = None, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.headers = headers or {}


class BadRequest(AppError):
    status_code = 400
    code = "bad_request"


class AuthError(AppError):
    status_code = 401
    code = "unauthorized"


class PermissionDenied(AppError):
    status_code = 403
    code = "forbidden"


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_failed"


class QuotaExceeded(AppError):
    # 402 because it's a plan problem, not a "slow down" problem (that's 429)
    status_code = 402
    code = "quota_exceeded"


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"


class ServiceUnavailable(AppError):
    status_code = 503
    code = "service_unavailable"
