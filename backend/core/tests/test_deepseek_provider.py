"""
Tests for DeepSeekProvider — Phase 0 unit tests with httpx mocked.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from core.ai.base_provider import AIRequest
from core.ai.exceptions import (
    AIAuthenticationError,
    AIConnectionError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
)


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_request() -> AIRequest:
    return AIRequest(
        id=uuid.uuid4(),
        prompt="Test prompt content — not empty",
        event_type="price_movement",
        symbol="RELIANCE",
        prompt_version="v1.0",
        max_tokens=256,
        timestamp=_utc_now(),
    )


@pytest.fixture
def mock_httpx_client() -> MagicMock:
    """Return a mock httpx.Client pre-configured for success."""
    mock = MagicMock(spec=httpx.Client)
    mock.get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"data": [{"id": "deepseek-chat"}]},
    )
    return mock


@pytest.fixture
def deepseek_provider(mock_httpx_client: MagicMock):
    """Instantiate DeepSeekProvider with httpx.Client fully mocked."""
    with patch("core.ai.providers.deepseek_provider.httpx.Client", return_value=mock_httpx_client):
        from core.ai.providers.deepseek_provider import DeepSeekProvider

        provider = DeepSeekProvider(
            api_key="test-key",
            base_url="https://api.deepseek.com",
            model_name="deepseek-chat",
        )
        yield provider


class TestDeepSeekProviderInit:
    """Construction-time behaviour."""

    def test_init_raises_on_empty_api_key(self) -> None:
        from core.ai.providers.deepseek_provider import DeepSeekProvider

        with pytest.raises(AIAuthenticationError, match="API key"):
            DeepSeekProvider(api_key="", base_url="https://api.deepseek.com", model_name="deepseek-chat")

    def test_init_success_stores_config(self, deepseek_provider) -> None:
        assert deepseek_provider._api_key == "test-key"
        assert deepseek_provider._base_url == "https://api.deepseek.com"
        assert deepseek_provider._model_name == "deepseek-chat"
        assert deepseek_provider._client is not None
        assert deepseek_provider.provider_name == "deepseek"


class TestDeepSeekProviderValidateConnection:
    """validate_connection() — httpx mocked."""

    def test_validate_connection_success(self, deepseek_provider) -> None:
        result = deepseek_provider.validate_connection()
        assert result is True
        deepseek_provider._client.get.assert_called_once_with("/v1/models")

    def test_validate_connection_raises_authentication_error_on_401(self, deepseek_provider) -> None:
        deepseek_provider._client.get.return_value = MagicMock(status_code=401)
        with pytest.raises(AIAuthenticationError, match="API key"):
            deepseek_provider.validate_connection()

    def test_validate_connection_raises_authentication_error_on_403(self, deepseek_provider) -> None:
        deepseek_provider._client.get.return_value = MagicMock(status_code=403)
        with pytest.raises(AIAuthenticationError, match="API key"):
            deepseek_provider.validate_connection()

    def test_validate_connection_raises_connection_error_on_unreachable_host(self, deepseek_provider) -> None:
        deepseek_provider._client.get.side_effect = httpx.ConnectError("DNS failure")
        with pytest.raises(AIConnectionError, match="unreachable"):
            deepseek_provider.validate_connection()

    def test_validate_connection_raises_timeout_error(self, deepseek_provider) -> None:
        deepseek_provider._client.get.side_effect = httpx.TimeoutException("Request timed out")
        with pytest.raises(AITimeoutError, match="timed out"):
            deepseek_provider.validate_connection()

    def test_validate_connection_raises_rate_limit_error_on_429(self, deepseek_provider) -> None:
        deepseek_provider._client.get.return_value = MagicMock(status_code=429)
        with pytest.raises(AIRateLimitError, match="rate limit"):
            deepseek_provider.validate_connection()

    def test_validate_connection_raises_provider_error_on_non_200(self, deepseek_provider) -> None:
        deepseek_provider._client.get.return_value = MagicMock(status_code=500, text="Internal error")
        with pytest.raises(AIProviderError, match="500"):
            deepseek_provider.validate_connection()

    def test_validate_connection_raises_provider_error_on_no_client(self) -> None:
        with patch("core.ai.providers.deepseek_provider.httpx.Client", return_value=MagicMock()):
            from core.ai.providers.deepseek_provider import DeepSeekProvider
            provider = DeepSeekProvider(
                api_key="test-key",
                base_url="https://api.deepseek.com",
                model_name="deepseek-chat",
            )
            provider._client = None
            with pytest.raises(AIProviderError, match="not initialised"):
                provider.validate_connection()


class TestDeepSeekProviderHealthCheck:
    """health_check() — returns dict, never raises."""

    def test_health_check_returns_healthy_shape(self, deepseek_provider) -> None:
        status = deepseek_provider.health_check()
        assert status["status"] == "healthy"
        assert status["provider"] == "deepseek"
        assert isinstance(status["latency_ms"], float)

    def test_health_check_returns_unhealthy_on_failure(self, deepseek_provider) -> None:
        deepseek_provider._client.get.side_effect = httpx.ConnectError("Network failure")
        status = deepseek_provider.health_check()
        assert status["status"] == "unhealthy"
        assert "error" in status

    def test_health_check_returns_degraded_above_latency_threshold(self, deepseek_provider) -> None:
        with patch("core.ai.providers.deepseek_provider.config") as mock_config:
            mock_config.ai_health_degraded_threshold_ms = 1.0
            with patch("core.ai.providers.deepseek_provider.time.monotonic") as mock_time:
                mock_time.side_effect = [0.0, 5.0]
                status = deepseek_provider.health_check()
        assert status["status"] == "degraded"

    def test_health_check_contains_required_keys(self, deepseek_provider) -> None:
        status = deepseek_provider.health_check()
        assert "status" in status
        assert "provider" in status
        assert "latency_ms" in status


class TestDeepSeekProviderComplete:
    """complete() — raises NotImplementedError in Phase 0."""

    def test_complete_raises_not_implemented(self, deepseek_provider) -> None:
        request = _make_request()
        with pytest.raises(NotImplementedError, match="Phase 0"):
            deepseek_provider.complete(request)


class TestDeepSeekProviderClose:
    """close() — releases client, idempotent."""

    def test_close_releases_client_and_is_idempotent(self, deepseek_provider) -> None:
        assert deepseek_provider._client is not None
        deepseek_provider.close()
        assert deepseek_provider._client is None
        deepseek_provider.close()

    def test_close_calls_client_close(self, deepseek_provider) -> None:
        mock_client = deepseek_provider._client
        deepseek_provider.close()
        mock_client.close.assert_called_once()

    def test_is_base_provider_subclass(self, deepseek_provider) -> None:
        from core.ai.base_provider import BaseAIProvider
        assert isinstance(deepseek_provider, BaseAIProvider)
