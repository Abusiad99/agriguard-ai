"""
Custom exception hierarchy. The exception-handling middleware
(app/interface/middleware/exception_middleware.py) catches these and maps them to the
standard error response shape + status codes defined in
docs/02-system-design/13-api-specification.md §1.1/1.2.
"""
from __future__ import annotations


class AgriGuardError(Exception):
    """Base class for all application-defined errors."""

    code: str = "INTERNAL_ERROR"
    status_code: int = 500

    def __init__(self, message: str, details: list | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or []


class ValidationError(AgriGuardError):
    code = "VALIDATION_ERROR"
    status_code = 400


class AuthenticationError(AgriGuardError):
    code = "INVALID_CREDENTIALS"
    status_code = 401


class TokenExpiredOrInvalidError(AgriGuardError):
    code = "INVALID_OR_REVOKED_TOKEN"
    status_code = 401


class AuthorizationError(AgriGuardError):
    code = "FORBIDDEN"
    status_code = 403


class NotFoundError(AgriGuardError):
    code = "NOT_FOUND"
    status_code = 404


class ConflictError(AgriGuardError):
    code = "CONFLICT"
    status_code = 409


class UnprocessableEntityError(AgriGuardError):
    code = "UNPROCESSABLE_ENTITY"
    status_code = 422


class InvalidImageError(UnprocessableEntityError):
    code = "INVALID_IMAGE"


class FileTooLargeError(AgriGuardError):
    code = "FILE_TOO_LARGE"
    status_code = 413


class RateLimitedError(AgriGuardError):
    code = "RATE_LIMITED"
    status_code = 429


class ServiceUnavailableError(AgriGuardError):
    code = "SERVICE_UNAVAILABLE"
    status_code = 503


class DosageSourceRequiredError(UnprocessableEntityError):
    code = "DOSAGE_SOURCE_REQUIRED"
