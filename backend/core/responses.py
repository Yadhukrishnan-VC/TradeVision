"""
TradeVision AI — Standard API response schemas.

These frozen dataclasses define the canonical shape of every API response
in the system. Views and serializers should produce responses that conform
to one of these schemas, ensuring consistency across all endpoints.

Usage::

    from core.responses import SuccessResponse, HealthResponse, ServiceHealthStatus

    def my_view(request):
        response = SuccessResponse(data={"symbol": "RELIANCE"})
        return JsonResponse({"data": response.data, "message": response.message})
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Standard API responses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SuccessResponse:
    """
    Wraps a successful API response payload.

    Attributes:
        data:        The primary response payload.
        message:     Human-readable status message.
        status_code: HTTP status code (informational — HTTP layer sets the real code).
    """

    data: Any
    message: str = "success"
    status_code: int = 200

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a flat dict suitable for ``JsonResponse``."""
        return {
            "data": self.data,
            "message": self.message,
        }


@dataclass(frozen=True)
class ErrorResponse:
    """
    Wraps an error response payload.

    Attributes:
        message:    Human-readable summary of the error.
        status_code: HTTP status code.
        detail:     Optional structured detail (e.g. field errors).
        error_code: Optional machine-readable error identifier.
    """

    message: str
    status_code: int = 400
    detail: Any = None
    error_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a flat dict suitable for ``JsonResponse``."""
        payload: dict[str, Any] = {
            "error": {
                "message": self.message,
                "status_code": self.status_code,
            }
        }
        if self.error_code:
            payload["error"]["code"] = self.error_code
        if self.detail is not None:
            payload["error"]["detail"] = self.detail
        return payload


@dataclass(frozen=True)
class ValidationErrorResponse:
    """
    Wraps a 422 Unprocessable Entity response from request validation.

    Attributes:
        errors:     Field-level error map, e.g. ``{"email": ["Invalid email"]}``.
        message:    Top-level human-readable summary.
        status_code: Always 422.
    """

    errors: dict[str, list[str]]
    message: str = "Validation failed"
    status_code: int = 422

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a flat dict suitable for ``JsonResponse``."""
        return {
            "error": {
                "message": self.message,
                "status_code": self.status_code,
                "detail": self.errors,
            }
        }


@dataclass(frozen=True)
class PaginatedResponse:
    """
    Wraps a paginated list response.

    Matches the envelope produced by ``core.pagination.StandardResultsPagination``.

    Attributes:
        count:    Total number of items across all pages.
        next:     URL of the next page, or ``None`` if on the last page.
        previous: URL of the previous page, or ``None`` if on the first page.
        results:  Items on the current page.
    """

    count: int
    next: str | None
    previous: str | None
    results: list[Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a flat dict suitable for ``JsonResponse``."""
        return {
            "count": self.count,
            "next": self.next,
            "previous": self.previous,
            "results": self.results,
        }


# ---------------------------------------------------------------------------
# Health check responses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ServiceHealthStatus:
    """
    The result of a single service health probe.

    Attributes:
        status:     ``"healthy"`` | ``"degraded"`` | ``"unhealthy"``
        latency_ms: Round-trip probe latency in milliseconds.
        message:    Human-readable message (populated on failure).
        detail:     Optional structured detail (e.g. active worker count).
    """

    status: str
    latency_ms: float | None = None
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a flat dict, omitting empty optional fields."""
        payload: dict[str, Any] = {"status": self.status}
        if self.latency_ms is not None:
            payload["latency_ms"] = round(self.latency_ms, 2)
        if self.message:
            payload["message"] = self.message
        if self.detail:
            payload["detail"] = self.detail
        return payload


@dataclass(frozen=True)
class HealthResponse:
    """
    Aggregate health check response returned by ``/api/v1/health/system/``.

    Attributes:
        status:          Overall system status (worst-case of all checks).
        checks:          Per-service status map.
        version:         Application version string.
        uptime_seconds:  Seconds since the application process started.
    """

    status: str
    checks: dict[str, ServiceHealthStatus]
    version: str
    uptime_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise the full health response to a JSON-compatible dict."""
        return {
            "status": self.status,
            "version": self.version,
            "uptime_seconds": self.uptime_seconds,
            "checks": {
                name: service.to_dict()
                for name, service in self.checks.items()
            },
        }
