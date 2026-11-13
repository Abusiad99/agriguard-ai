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
from starlette.routing import Match

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
    """Sliding-window limiter keyed by (client_ip, route group).

    A route group is one of the specially limited paths (login, register, scan upload,
    outbreak prediction) or the API resource the request belongs to ("diagnoses",
    "media", "agri-reports", ...); everything else is "other". Keys are therefore
    bounded per client: counting per exact URL would give every distinct URL its own
    allowance (no real limit) and let anyone grow this table without bound by
    requesting made-up paths. Idle keys are dropped periodically.
    """

    _AUTH_PATHS = ("/api/v1/auth/login", "/api/v1/auth/register")
    _SCAN_PATHS = ("/api/v1/scans",)  # follow-up scans of tracked plants use this path too
    _PREDICTION_PATHS = ("/api/v1/outbreak/predictions",)
    _MAX_WINDOW_SECONDS = 3600
    _PRUNE_EVERY = 2000  # requests between sweeps of idle keys

    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, deque] = defaultdict(deque)
        self._prefix = settings.api_prefix.rstrip("/") + "/"
        self._resources: set[str] = set()  # API resources seen to match a registered route
        self._since_prune = 0

    def _limit_for(self, path: str) -> tuple[int, int]:
        if path in self._AUTH_PATHS:
            return settings.rate_limit_auth_per_5min, 300
        if path in self._SCAN_PATHS:
            return settings.rate_limit_scan_per_hour, 3600
        if path in self._PREDICTION_PATHS:
            return settings.rate_limit_prediction_per_hour, 3600
        return settings.rate_limit_default_per_5min, 300

    def _group_for(self, request: Request) -> str:
        path = request.url.path
        if path in self._AUTH_PATHS or path in self._SCAN_PATHS or path in self._PREDICTION_PATHS:
            return path
        if path.startswith(self._prefix):
            resource = path[len(self._prefix):].split("/", 1)[0]
            if resource in self._resources:
                return resource
            # A resource name counts only once a registered route matches it, so made-up
            # paths can never add groups. (No route has a parameter in this position.)
            if resource and any(route.matches(request.scope)[0] != Match.NONE for route in request.app.routes):
                self._resources.add(resource)
                return resource
        return "other"

    def _prune(self, now: float) -> None:
        cutoff = now - self._MAX_WINDOW_SECONDS
        for key in [k for k, window in self._hits.items() if not window or window[-1] < cutoff]:
            del self._hits[key]

    async def dispatch(self, request: Request, call_next):
        # Behind nginx this is only the real visitor IP if uvicorn trusts the proxy's
        # X-Forwarded-For (FORWARDED_ALLOW_IPS, set in docker-compose.yml); otherwise
        # every request shares nginx's IP and one bucket.
        client_ip = request.client.host if request.client else "unknown"
        limit, window_seconds = self._limit_for(request.url.path)
        key = f"{client_ip}:{self._group_for(request)}"

        now = time.monotonic()
        self._since_prune += 1
        if self._since_prune >= self._PRUNE_EVERY:
            self._since_prune = 0
            self._prune(now)

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
