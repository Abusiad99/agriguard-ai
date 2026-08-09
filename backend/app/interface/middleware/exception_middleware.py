"""
Centralized exception handling (requirement #11). Registered as FastAPI exception
handlers (not raw middleware) since that is the correct, documented way to intercept
exceptions raised inside route handlers/dependencies while still letting FastAPI's
own request lifecycle (including successful responses) run untouched.

Maps every `AgriGuardError` subclass to the standard error envelope defined in
docs/02-system-design/13-api-specification.md §1.1, attaches a request correlation id
(NFR-OBS-1), and converts unhandled exceptions into a safe generic 500 — no internal
stack trace or exception message is ever leaked to the client for unexpected errors.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AgriGuardError

logger = logging.getLogger("agriguard.exceptions")


def _error_body(code: str, message: str, details: list, request_id: str) -> dict:
    return {"error": {"code": code, "message": message, "details": details}, "request_id": request_id}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AgriGuardError)
    async def handle_agriguard_error(request: Request, exc: AgriGuardError):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.warning("Handled error [%s] %s: %s (request_id=%s)",
                        exc.code, request.url.path, exc.message, request_id)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, exc.details, request_id),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_pydantic_validation_error(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        details = [
            {"field": ".".join(str(p) for p in err["loc"] if p != "body"), "issue": err["msg"]}
            for err in exc.errors()
        ]
        logger.warning("Request validation failed on %s (request_id=%s): %s",
                        request.url.path, request_id, details)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_error_body("VALIDATION_ERROR", "Request validation failed.", details, request_id),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.exception("Unhandled exception on %s (request_id=%s)", request.url.path, request_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body("INTERNAL_ERROR", "An unexpected error occurred.", [], request_id),
        )
