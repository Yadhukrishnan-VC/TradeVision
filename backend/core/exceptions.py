"""
TradeVision AI — Application exception hierarchy.

All custom exceptions descend from TradeVisionError, enabling catch-all
handlers while preserving the ability to catch specific error classes.
The custom DRF exception handler wraps responses in a consistent envelope.
"""

import logging
from typing import Any

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import exception_handler as _drf_exception_handler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Base exception
# ---------------------------------------------------------------------------


class TradeVisionError(Exception):
    """Base class for all TradeVision AI application errors."""


# ---------------------------------------------------------------------------
# Data layer exceptions
# ---------------------------------------------------------------------------


class DataIngestionError(TradeVisionError):
    """Raised when a market data ingestion operation fails."""


class DataFreshnessError(TradeVisionError):
    """
    Raised when data exceeds the configured freshness threshold.

    The rule engine raises this before evaluating stale data so that
    recommendations are never produced from outdated signals.
    """


class DataQualityError(TradeVisionError):
    """Raised when an IntelligencePacket quality score is below the minimum threshold."""


class DataProviderError(TradeVisionError):
    """Raised when a market data provider returns an error or unexpected response."""


# ---------------------------------------------------------------------------
# Resilience exceptions
# ---------------------------------------------------------------------------


class CircuitBreakerOpenError(TradeVisionError):
    """
    Raised when a call is attempted on an open circuit breaker.

    Callers should catch this and return a cached or degraded response
    rather than propagating it to the user.
    """

    def __init__(self, breaker_name: str) -> None:
        """Initialise with the name of the open circuit breaker."""
        self.breaker_name = breaker_name
        super().__init__(
            f"Circuit breaker '{breaker_name}' is OPEN — rejecting call."
        )


# ---------------------------------------------------------------------------
# AI layer exceptions
# ---------------------------------------------------------------------------


class AIProviderError(TradeVisionError):
    """Raised when an AI provider call fails (network error, API error, timeout)."""


class AIResponseValidationError(TradeVisionError):
    """Raised when the AI provider response fails schema or sanity validation."""


class AIBudgetExhaustedError(TradeVisionError):
    """Raised when the daily AI cost budget has been reached."""


class AIRateLimitError(TradeVisionError):
    """Raised when the AI provider rate limit is exceeded."""


# ---------------------------------------------------------------------------
# Rule engine exceptions
# ---------------------------------------------------------------------------


class RuleEngineError(TradeVisionError):
    """Raised when rule evaluation encounters an unrecoverable error."""


class RuleConfigurationError(TradeVisionError):
    """Raised when a rule is misconfigured (e.g. invalid threshold values)."""


# ---------------------------------------------------------------------------
# Market calendar exceptions
# ---------------------------------------------------------------------------


class MarketCalendarError(TradeVisionError):
    """Raised when market calendar data is unavailable or malformed."""


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class InstrumentNotFoundError(TradeVisionError):
    """Raised when a requested stock symbol does not exist in the system."""


class WatchlistError(TradeVisionError):
    """Raised when a watchlist operation fails (e.g. symbol limit exceeded)."""


class PortfolioError(TradeVisionError):
    """Raised when a portfolio operation fails."""


# ---------------------------------------------------------------------------
# DRF exception handler — wraps all responses in a consistent JSON envelope
# ---------------------------------------------------------------------------


def _extract_message(data: Any) -> str:
    """
    Extract a human-readable message from DRF error data.

    DRF error payloads can be strings, lists, or dicts. This normalises
    them into a single top-level message string.
    """
    if isinstance(data, str):
        return data
    if isinstance(data, list) and data:
        return str(data[0])
    if isinstance(data, dict):
        for key in ("detail", "non_field_errors", "message"):
            if key in data:
                return _extract_message(data[key])
        # Return the first value found
        first_value = next(iter(data.values()), "")
        return _extract_message(first_value)
    return "An error occurred."


def custom_exception_handler(exc: Exception, context: dict) -> Response | None:
    """
    DRF exception handler that normalises all error responses.

    Wraps the standard DRF response in::

        {
            "error": {
                "status_code": 400,
                "message": "Human-readable summary",
                "detail": <original DRF error payload>
            }
        }

    Unhandled exceptions (not DRF exceptions) are logged and return None,
    allowing Django's standard 500 handler to take over.
    """
    response = _drf_exception_handler(exc, context)

    if response is not None:
        original_data = response.data
        response.data = {
            "error": {
                "status_code": response.status_code,
                "message": _extract_message(original_data),
                "detail": original_data,
            }
        }
        logger.warning(
            "API error response",
            extra={
                "status_code": response.status_code,
                "exception_type": type(exc).__name__,
                "message": response.data["error"]["message"],
            },
        )
    else:
        # Unhandled exception — log at ERROR level; Sentry will capture it
        logger.error(
            "Unhandled exception in view",
            exc_info=exc,
            extra={"exception_type": type(exc).__name__},
        )

    return response
