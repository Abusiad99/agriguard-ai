"""
Security middleware (requirement #10): security response headers (defense-in-depth
alongside NGINX's TLS termination) and a simple in-memory sliding-window rate limiter
implementing NFR-SEC-5's limits. The in-memory limiter is per-process; the documented
production upgrade path is Redis-backed counters (same ICache interface used by
WeatherService) once running multiple backend replicas, so limits are shared across
instances — noted here rather than silently pretended-away.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import get_settings

settings = get_settings()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.app_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window limiter keyed by (client_ip, route_group)."""

    _AUTH_PATHS = ("/api/v1/auth/login", "/api/v1/auth/register")
    _SCAN_PATHS = ("/api/v1/scans",)

    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, deque] = defaultdict(deque)

    def _limit_for(self, path: str) -> tuple[int, int] | None:
        if path in self._AUTH_PATHS:
            return settings.rate_limit_auth_per_5min, 300
        if path in self._SCAN_PATHS:
            return settings.rate_limit_scan_per_hour, 3600
        return settings.rate_limit_default_per_5min, 300

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        limit, window_seconds = self._limit_for(request.url.path)
        key = f"{client_ip}:{request.url.path}"

        now = time.monotonic()
        window = self._hits[key]
        while window and window[0] < now - window_seconds:
            window.popleft()

        if len(window) >= limit:
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "RATE_LIMITED",
                                    "message": "Too many requests. Please try again later.", "details": []},
                         "request_id": getattr(request.state, "request_id", None)},
            )

        window.append(now)
        return await call_next(request)
