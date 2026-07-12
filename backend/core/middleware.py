"""
TradeVision AI — Request-scoped middleware.

``CorrelationIDMiddleware`` must appear BEFORE ``RequestLoggingMiddleware``
in ``settings.MIDDLEWARE`` so that the correlation ID is available to the
logger when the request started event is emitted.

Registration in ``settings/base.py``::

    MIDDLEWARE = [
        ...
        "core.middleware.CorrelationIDMiddleware",
        "core.middleware.RequestLoggingMiddleware",
        ...
    ]
"""

import logging
import time
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from core.logging import bind_context, clear_context, get_logger
from core.utils import get_now

logger = get_logger(__name__)

CORRELATION_ID_HEADER: str = "X-Correlation-ID"
REQUEST_ID_HEADER: str = "X-Request-ID"


class CorrelationIDMiddleware:
    """
    Attaches a Correlation ID to every inbound request.

    If the upstream caller (load balancer, API gateway, or client) supplies
    an ``X-Correlation-ID`` header, that value is used. Otherwise a new
    UUID4 is generated. The correlation ID is:
    - Stored on ``request.correlation_id`` for access by views and services
    - Bound into the structlog context so all log calls include it
    - Echoed back in the ``X-Correlation-ID`` response header

    Must be the first TradeVision-specific middleware in the stack.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self._get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Process the request, attach correlation ID, and echo it in the response."""
        correlation_id: str = (
            request.headers.get(CORRELATION_ID_HEADER) or str(uuid.uuid4())
        )
        request.correlation_id = correlation_id  # type: ignore[attr-defined]
        bind_context(correlation_id=correlation_id)

        response: HttpResponse = self._get_response(request)

        response[CORRELATION_ID_HEADER] = correlation_id
        return response


class RequestLoggingMiddleware:
    """
    Logs the start and completion of every HTTP request.

    Emits structured ``request_started`` and ``request_completed`` (or
    ``request_error``) log events with method, path, status code, and
    wall-clock duration in milliseconds.

    Must appear AFTER ``CorrelationIDMiddleware`` so that the correlation
    ID is already bound when the ``request_started`` event is logged.

    Clears the structlog context after each request to prevent context
    leakage between requests on the same thread.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self._get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Log the request lifecycle and clear context on completion."""
        start: float = time.monotonic()

        logger.info(
            "request_started",
            extra={
                "method": request.method,
                "path": request.path,
                "query_string": request.META.get("QUERY_STRING", ""),
                "correlation_id": getattr(request, "correlation_id", ""),
                "remote_addr": request.META.get("REMOTE_ADDR", ""),
            },
        )

        try:
            response: HttpResponse = self._get_response(request)
        except Exception as exc:
            duration_ms: float = round((time.monotonic() - start) * 1000, 2)
            logger.error(
                "request_error",
                exc_info=exc,
                extra={
                    "method": request.method,
                    "path": request.path,
                    "duration_ms": duration_ms,
                    "exception_type": type(exc).__name__,
                },
            )
            raise
        finally:
            clear_context()

        duration_ms = round((time.monotonic() - start) * 1000, 2)
        logger.info(
            "request_completed",
            extra={
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
