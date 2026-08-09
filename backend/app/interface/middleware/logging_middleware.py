"""
Logging middleware (requirement #12, NFR-OBS-1). Attaches a correlation id to every
request, logs method/path/status/duration as structured JSON-friendly fields, and
never logs raw request bodies (which could contain images or passwords).
"""
from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("agriguard.requests")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_id=%s method=%s path=%s status=%s duration_ms=%s client=%s",
            request_id, request.method, request.url.path, response.status_code,
            duration_ms, request.client.host if request.client else "unknown",
        )
        return response
