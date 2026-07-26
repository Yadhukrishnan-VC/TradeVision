from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    """Return the current correlation ID or None if not set."""
    return correlation_id_var.get()


def set_correlation_id(value: str) -> None:
    """Set the correlation ID for the current execution context."""
    correlation_id_var.set(value)


class CorrelationIdFilter(logging.Filter):
    """Logging filter that injects the current correlation_id into log records."""

    def filter(self, record: Any) -> bool:
        record.correlation_id = get_correlation_id() or ""
        return True
