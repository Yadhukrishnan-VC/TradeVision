"""
TradeVision AI — Django middleware.

Provides two middleware classes:

1. ``CorrelationIDMiddleware`` — Generates or propagates a UUID4 correlation
   ID for every request. If the incoming request contains an
   ``X-Correlation-ID`` header, it is used; otherwise a new UUID is generated.

2. ``RequestLoggingMiddleware`` — Logs request method, path, and status code
   using the structured logger.
"""

import time
from typing import Callable

from django.http import HttpRequest, HttpResponse

from core.logging import get_logger, bind_context, clear_context
from core.utils import generate_correlation_id, get_now

logger = get_logger(__name__)

CORRELATION_HEADER = "X-Correlation-ID"


class CorrelationIDMiddleware:
    """
    Generate or propagate a correlation ID for every request.

    If the incoming request has an ``X-Correlation-ID`` header, its value
    is used. Otherwise, a new UUID4 is generated. The ID is bound to the
    structlog context and set on the response header.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        correlation_id = request.headers.get(CORRELATION_HEADER) or generate_correlation_id()
        request.correlation_id = correlation_id  # type: ignore[attr-defined]
        bind_context(correlation_id=correlation_id)

        response = self.get_response(request)
        response[CORRELATION_HEADER] = correlation_id

        clear_context()
        return response


class RequestLoggingMiddleware:
    """
    Log request method, path, status code, and duration using structured logging.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = (time.monotonic() - start) * 1000

        logger.info(
            "http_request",
            extra={
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        return response
