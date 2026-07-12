"""
Tests for core/ai/exceptions.py — AI-specific exception hierarchy.

Verifies that all AI exceptions inherit from the correct base classes,
carry the expected messages, and can be caught at the appropriate level.
"""

import pytest

from core.ai.exceptions import (
    AIAuthenticationError,
    AIBudgetExhaustedError,
    AIConnectionError,
    AIProviderError,
    AIQuotaExceededError,
    AIRateLimitError,
    AIResponseValidationError,
    AITimeoutError,
)
from core.exceptions import TradeVisionError


class TestAIExceptionInheritance:
    """All AI exceptions must descend from TradeVisionError."""

    def test_authentication_error_inherits_provider_error(self) -> None:
        assert issubclass(AIAuthenticationError, AIProviderError)

    def test_connection_error_inherits_provider_error(self) -> None:
        assert issubclass(AIConnectionError, AIProviderError)

    def test_timeout_error_inherits_provider_error(self) -> None:
        assert issubclass(AITimeoutError, AIProviderError)

    def test_quota_exceeded_error_inherits_provider_error(self) -> None:
        assert issubclass(AIQuotaExceededError, AIProviderError)

    def test_rate_limit_error_inherits_tradevision_error(self) -> None:
        assert issubclass(AIRateLimitError, TradeVisionError)

    def test_response_validation_error_inherits_tradevision_error(self) -> None:
        assert issubclass(AIResponseValidationError, TradeVisionError)

    def test_budget_exhausted_error_inherits_tradevision_error(self) -> None:
        assert issubclass(AIBudgetExhaustedError, TradeVisionError)

    def test_all_errors_inherit_from_tradevision_error(self) -> None:
        error_classes = [
            AIAuthenticationError,
            AIConnectionError,
            AITimeoutError,
            AIQuotaExceededError,
            AIRateLimitError,
            AIResponseValidationError,
            AIBudgetExhaustedError,
        ]
        for cls in error_classes:
            assert issubclass(cls, TradeVisionError), (
                f"{cls.__name__} does not inherit from TradeVisionError"
            )


class TestAIExceptionRaising:
    """Verify exceptions can be raised and caught at each level."""

    def test_authentication_error_raised_as_provider_error(self) -> None:
        with pytest.raises(AIProviderError):
            raise AIAuthenticationError("Invalid API key")

    def test_connection_error_raised_as_provider_error(self) -> None:
        with pytest.raises(AIProviderError):
            raise AIConnectionError("Connection refused")

    def test_timeout_error_raised_as_provider_error(self) -> None:
        with pytest.raises(AIProviderError):
            raise AITimeoutError("Request timed out after 30s")

    def test_quota_exceeded_raised_as_provider_error(self) -> None:
        with pytest.raises(AIProviderError):
            raise AIQuotaExceededError("Daily quota exhausted")

    def test_all_ai_errors_caught_as_tradevision_error(self) -> None:
        for exc_cls in (
            AIAuthenticationError,
            AIConnectionError,
            AITimeoutError,
            AIQuotaExceededError,
        ):
            with pytest.raises(TradeVisionError):
                raise exc_cls("test message")

    def test_authentication_error_preserves_message(self) -> None:
        msg = "GEMINI_API_KEY is invalid or expired"
        exc = AIAuthenticationError(msg)
        assert str(exc) == msg

    def test_connection_error_preserves_message(self) -> None:
        msg = "Failed to reach generativeai.googleapis.com"
        exc = AIConnectionError(msg)
        assert str(exc) == msg

    def test_can_catch_specific_subtype_from_provider_error_handler(self) -> None:
        """Raising AIAuthenticationError is catchable as AIAuthenticationError."""
        with pytest.raises(AIAuthenticationError) as exc_info:
            raise AIAuthenticationError("Specific auth failure")
        assert isinstance(exc_info.value, AIAuthenticationError)
        assert isinstance(exc_info.value, AIProviderError)
        assert isinstance(exc_info.value, TradeVisionError)


class TestAIExceptionChaining:
    """Verify exception chaining (raise ... from ...) is supported."""

    def test_exception_chaining_preserved(self) -> None:
        original = ConnectionRefusedError("Port 443 refused")
        try:
            raise AIConnectionError("Wrapped connection error") from original
        except AIConnectionError as exc:
            assert exc.__cause__ is original

    def test_quota_exceeded_chaining(self) -> None:
        original = ValueError("Rate limit header value: 429")
        try:
            raise AIQuotaExceededError("API quota exceeded") from original
        except AIQuotaExceededError as exc:
            assert exc.__cause__ is original
