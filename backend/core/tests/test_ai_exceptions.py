"""
Tests for AI exception hierarchy.

Verifies inheritance chains, field presence, and proper construction.
"""

import pytest

from core.exceptions import TradeVisionError, AIProviderError
from core.ai.exceptions import (
    AIAuthenticationError,
    AIConnectionError,
    AIQuotaExceededError,
    AITimeoutError,
    AIProviderError as ReExportedAIProviderError,
    AIResponseValidationError,
    AIRateLimitError,
    AIBudgetExhaustedError,
)


class TestAIExceptionHierarchy:
    """Verify the exception inheritance chain."""

    def test_ai_provider_error_is_trade_vision_error(self) -> None:
        assert issubclass(AIProviderError, TradeVisionError)

    def test_ai_authentication_error_is_ai_provider_error(self) -> None:
        assert issubclass(AIAuthenticationError, AIProviderError)

    def test_ai_connection_error_is_ai_provider_error(self) -> None:
        assert issubclass(AIConnectionError, AIProviderError)

    def test_ai_timeout_error_is_ai_provider_error(self) -> None:
        assert issubclass(AITimeoutError, AIProviderError)

    def test_ai_quota_exceeded_error_is_ai_provider_error(self) -> None:
        assert issubclass(AIQuotaExceededError, AIProviderError)

    def test_reexported_matches_original(self) -> None:
        assert ReExportedAIProviderError is AIProviderError
        assert AIResponseValidationError is not None
        assert AIRateLimitError is not None
        assert AIBudgetExhaustedError is not None


class TestAIExceptionFields:
    """Verify that exception constructors set fields correctly."""

    def test_authentication_error_has_provider(self) -> None:
        exc = AIAuthenticationError(provider="gemini")
        assert exc.provider == "gemini"
        assert "gemini" in str(exc)

    def test_connection_error_has_provider(self) -> None:
        exc = AIConnectionError(provider="openai")
        assert exc.provider == "openai"

    def test_timeout_error_has_fields(self) -> None:
        exc = AITimeoutError(provider="claude", timeout_seconds=30.0)
        assert exc.provider == "claude"
        assert exc.timeout_seconds == 30.0

    def test_quota_exceeded_error_has_provider(self) -> None:
        exc = AIQuotaExceededError(provider="gemini")
        assert exc.provider == "gemini"
