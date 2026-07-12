"""
TradeVision AI — AI-specific exception hierarchy.

All AI provider code must import exceptions from this module rather than
from ``core.exceptions`` directly. This ensures a single point of change
if exceptions are renamed or restructured.

Hierarchy::

    TradeVisionError (core.exceptions)
    └── AIProviderError (core.exceptions)
        ├── AIAuthenticationError      — credentials rejected by provider
        ├── AIConnectionError          — network unreachable or timeout
        ├── AITimeoutError             — provider did not respond in time
        ├── AIQuotaExceededError       — provider-side quota or rate limit hit
        ├── AIRateLimitError           — re-exported from core.exceptions
        ├── AIResponseValidationError  — re-exported from core.exceptions
        └── AIBudgetExhaustedError     — re-exported from core.exceptions
"""

from core.exceptions import (
    AIBudgetExhaustedError,
    AIProviderError,
    AIRateLimitError,
    AIResponseValidationError,
)

__all__ = [
    "AIProviderError",
    "AIAuthenticationError",
    "AIConnectionError",
    "AITimeoutError",
    "AIQuotaExceededError",
    "AIRateLimitError",
    "AIResponseValidationError",
    "AIBudgetExhaustedError",
]


class AIAuthenticationError(AIProviderError):
    """
    Raised when the AI provider rejects the supplied API credentials.

    Triggers on: invalid API key, expired token, insufficient permissions.
    Resolution: verify GEMINI_API_KEY (or equivalent) in environment settings.
    """


class AIConnectionError(AIProviderError):
    """
    Raised when a network connection to the AI provider cannot be established.

    Triggers on: DNS failure, refused connection, unreachable host.
    The circuit breaker in ``core.resilience`` tracks these failures.
    """


class AITimeoutError(AIProviderError):
    """
    Raised when the AI provider does not respond within the configured timeout.

    Distinct from ``AIConnectionError`` — the connection was established but
    the provider did not return a response in the allowed window.
    """


class AIQuotaExceededError(AIProviderError):
    """
    Raised when the AI provider reports that its own quota or rate limit is exhausted.

    Distinct from ``AIBudgetExhaustedError`` (our internal spend limit) —
    this indicates the provider's side limit has been reached.
    """
