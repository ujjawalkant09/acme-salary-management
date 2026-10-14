"""Per-user rate limits (per client IP before sign-in).

Counters live in memory in v1; `RATE_LIMIT_STORAGE_URL=redis://…` shares them across
instances without code changes.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.core.errors import error_body

READ = "120/minute"
WRITE = "30/minute"
UPLOAD = "10/minute"
HEAVY = "5/minute"  # imports and CSV export
INSIGHTS = "60/minute"
DOWNLOAD = "60/minute"
LOGIN = "5/minute"


def user_or_ip(request: Request) -> str:
    user_id = request.session.get("user_id") if "session" in request.scope else None
    return f"user:{user_id}" if user_id else f"ip:{get_remote_address(request)}"


_settings = get_settings()
limiter = Limiter(
    key_func=user_or_ip,
    storage_uri=_settings.rate_limit_storage_url,
    enabled=_settings.rate_limit_enabled,
)


def rate_limit_exceeded(_request: Request, exc: RateLimitExceeded) -> JSONResponse:
    retry_after = exc.limit.limit.get_expiry()
    return JSONResponse(
        status_code=429,
        content=error_body(
            "rate_limited",
            f"You're going a bit fast. Try again in {retry_after} seconds.",
            {"retry_after": retry_after},
        ),
        headers={"Retry-After": str(retry_after), "X-RateLimit-Remaining": "0"},
    )
