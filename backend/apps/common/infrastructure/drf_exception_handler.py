from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.common.domain.exceptions import (
    ConcurrencyError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF exception handler that maps domain errors to HTTP responses.

    Args:
        exc: The exception instance.
        context: The DRF exception context.

    Returns:
        A DRF Response with a structured error body, or None to let
        DRF's default handler process the exception.
    """
    response = exception_handler(exc, context)

    if response is not None:
        return response

    if isinstance(exc, ValidationError):
        return _build_error_response(400, exc.code or "validation_error", str(exc), exc.details)
    if isinstance(exc, PermissionDeniedError):
        return _build_error_response(403, exc.code or "permission_denied", str(exc), exc.details)
    if isinstance(exc, NotFoundError):
        return _build_error_response(404, exc.code or "not_found", str(exc), exc.details)
    if isinstance(exc, ConcurrencyError):
        return _build_error_response(409, exc.code or "concurrency_error", str(exc), exc.details)
    if isinstance(exc, DomainError):
        return _build_error_response(400, exc.code or "domain_error", str(exc), exc.details)

    return None


def _build_error_response(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> Response:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
        }
    }
    if details:
        body["error"]["details"] = details
    return Response(body, status=status)
