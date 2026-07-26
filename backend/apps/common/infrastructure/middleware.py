from __future__ import annotations

import uuid
from typing import Any

from django.http import HttpRequest

from apps.common.infrastructure.logging_context import set_correlation_id


class CorrelationIdMiddleware:
    """Middleware that ensures every request has a correlation ID.

    Reads the X-Correlation-ID header from the incoming request, or
    generates a new UUID if none is present, and sets it in the
    logging context for structured log correlation.
    """

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> Any:
        correlation_id = request.META.get("HTTP_X_CORRELATION_ID") or str(uuid.uuid4())
        request.correlation_id = correlation_id  # type: ignore[attr-defined]
        set_correlation_id(correlation_id)
        response = self.get_response(request)
        response["X-Correlation-ID"] = correlation_id
        return response
