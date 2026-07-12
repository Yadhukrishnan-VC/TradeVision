"""
TradeVision AI — AI-specific exception hierarchy.

These exceptions inherit from the base classes in ``core.exceptions`` and
add AI-provider-specific error categories. All AI provider code imports
exclusively from this module — never directly from ``core.exceptions``.

Hierarchy::

    TradeVisionError (core.exceptions)
      └── AIProviderError (core.exceptions)
            ├── AIAuthenticationError    (this module)
            ├── AIConnectionError        (this module)
            ├── AITimeoutError           (this module)
            ├── AIRateLimitError         (re-exported from core.exceptions)
            ├── AIQuotaExceededError     (this module)
            └── AIResponseValidationError (re-exported from core.exceptions)
"""

from core.exceptions import (  # noqa: F401 — re-exported for provider imports
    AIBudgetExhaustedError,
    AIProviderError,
    AIResponseValidationError,
    AIRateLimitError,
)


class AIAuthenticationError(AIProviderError):
    """Raised when the AI provider rejects authentication credentials."""

    def __init__(self, provider: str, message: str = "") -> None:
        self.provider = provider
        super().__init__(
            message or f"Authentication failed for AI provider '{provider}'."
        )


class AIConnectionError(AIProviderError):
    """Raised when a network-level connection to the AI provider fails."""

    def __init__(self, provider: str, message: str = "") -> None:
        self.provider = provider
        super().__init__(
            message or f"Connection failed for AI provider '{provider}'."
        )


class AITimeoutError(AIProviderError):
    """Raised when the AI provider does not respond within the configured timeout."""

    def __init__(self, provider: str, timeout_seconds: float = 0) -> None:
        self.provider = provider
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Timeout ({timeout_seconds}s) waiting for AI provider '{provider}'."
        )


class AIQuotaExceededError(AIProviderError):
    """Raised when the AI provider quota or rate limit is exceeded."""

    def __init__(self, provider: str, message: str = "") -> None:
        self.provider = provider
        super().__init__(
            message or f"Quota exceeded for AI provider '{provider}'."
        )
