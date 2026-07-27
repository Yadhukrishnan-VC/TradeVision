"""
Tests for AI provider interface compliance.

Verifies that every provider implements BaseAIProvider, that lifecycle
methods behave correctly in Phase 0 (GeminiProvider auth-only, stubs raise
NotImplementedError), and that the request/response dataclasses enforce
their contracts.
"""

import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from core.ai.base_provider import AIRawResponse, AIRequest, AIRecommendation, BaseAIProvider
from core.ai.exceptions import AIProviderError
from core.constants import RecommendationDirection, RecommendationTimeHorizon, RiskLevel


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    """Return a timezone-aware UTC datetime for test construction."""
    return datetime.now(tz=timezone.utc)


def _make_request() -> AIRequest:
    """Build a minimal valid AIRequest for testing."""
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
def mock_genai_module() -> MagicMock:
    """Provide a fully mocked google.generativeai module."""
    mock = MagicMock()
    mock.list_models.return_value = ["gemini-1.5-pro"]
    mock.GenerativeModel.return_value = MagicMock()
    return mock


@pytest.fixture
def gemini_provider(mock_genai_module: MagicMock):
    """Instantiate GeminiProvider with the Gemini SDK fully mocked."""
    google_mock = MagicMock()
    google_mock.generativeai = mock_genai_module
    with patch.dict(sys.modules, {
        "google": google_mock,
        "google.generativeai": mock_genai_module,
    }):
        from core.ai.providers.gemini_provider import GeminiProvider
        yield GeminiProvider(api_key="test-api-key", model_name="gemini-1.5-pro")


# ---------------------------------------------------------------------------
# GeminiProvider contract
# ---------------------------------------------------------------------------


class TestGeminiProviderContract:
    """GeminiProvider must implement BaseAIProvider and expose Phase 0 behaviour."""

    def test_is_base_provider_subclass(self, gemini_provider: BaseAIProvider) -> None:
        assert isinstance(gemini_provider, BaseAIProvider)

    def test_provider_name_is_gemini(self, gemini_provider: BaseAIProvider) -> None:
        assert gemini_provider.provider_name == "gemini"

    def test_validate_connection_returns_true(
        self, gemini_provider: BaseAIProvider
    ) -> None:
        result = gemini_provider.validate_connection()
        assert result is True

    def test_validate_connection_returns_bool(
        self, gemini_provider: BaseAIProvider
    ) -> None:
        result = gemini_provider.validate_connection()
        assert isinstance(result, bool)

    def test_health_check_returns_dict(self, gemini_provider: BaseAIProvider) -> None:
        status = gemini_provider.health_check()
        assert isinstance(status, dict)

    def test_health_check_has_required_keys(self, gemini_provider: BaseAIProvider) -> None:
        status = gemini_provider.health_check()
        assert "status" in status
        assert "provider" in status
        assert "latency_ms" in status

    def test_health_check_provider_is_gemini(
        self, gemini_provider: BaseAIProvider
    ) -> None:
        status = gemini_provider.health_check()
        assert status["provider"] == "gemini"

    def test_health_check_latency_is_numeric(
        self, gemini_provider: BaseAIProvider
    ) -> None:
        status = gemini_provider.health_check()
        assert isinstance(status["latency_ms"], (int, float))

    def test_complete_raises_not_implemented_in_phase_0(
        self, gemini_provider: BaseAIProvider
    ) -> None:
        request = _make_request()
        with pytest.raises(NotImplementedError):
            gemini_provider.complete(request)

    def test_close_sets_client_to_none(self, gemini_provider) -> None:
        gemini_provider.close()
        assert gemini_provider._client is None

    def test_repr_contains_provider_name(self, gemini_provider: BaseAIProvider) -> None:
        assert "gemini" in repr(gemini_provider)

    def test_health_check_returns_healthy_on_success(
        self, gemini_provider: BaseAIProvider
    ) -> None:
        status = gemini_provider.health_check()
        assert status["status"] == "healthy"

    def test_health_check_returns_unhealthy_on_error(self) -> None:
        mock_genai = MagicMock()
        mock_genai.list_models.side_effect = Exception("Network error")
        google_mock = MagicMock()
        google_mock.generativeai = mock_genai
        with patch.dict(sys.modules, {
            "google": google_mock,
            "google.generativeai": mock_genai,
        }):
            from core.ai.providers.gemini_provider import GeminiProvider
            provider = GeminiProvider(api_key="test-key", model_name="gemini-1.5-pro")
            status = provider.health_check()
            assert status["status"] == "unhealthy"
            assert "error" in status


# ---------------------------------------------------------------------------
# Stub providers
# ---------------------------------------------------------------------------


class TestDeepSeekProviderContract:
    """DeepSeekProvider must implement BaseAIProvider and expose Phase 0 behaviour."""

    @pytest.fixture
    def deepseek_provider(self):
        with patch("core.ai.providers.deepseek_provider.httpx.Client") as mock_client:
            mock_client.return_value = MagicMock()
            from core.ai.providers.deepseek_provider import DeepSeekProvider
            yield DeepSeekProvider(
                api_key="test-key",
                base_url="https://api.deepseek.com",
                model_name="deepseek-chat",
            )

    def test_is_base_provider_subclass(self, deepseek_provider) -> None:
        assert isinstance(deepseek_provider, BaseAIProvider)

    def test_provider_name_is_deepseek(self, deepseek_provider) -> None:
        assert deepseek_provider.provider_name == "deepseek"

    def test_validate_connection_returns_bool(self, deepseek_provider) -> None:
        deepseek_provider._client.get.return_value = MagicMock(
            status_code=200, json=lambda: {"data": [{"id": "deepseek-chat"}]}
        )
        result = deepseek_provider.validate_connection()
        assert isinstance(result, bool)

    def test_health_check_has_required_keys(self, deepseek_provider) -> None:
        deepseek_provider._client.get.return_value = MagicMock(
            status_code=200, json=lambda: {"data": [{"id": "deepseek-chat"}]}
        )
        status = deepseek_provider.health_check()
        assert "status" in status
        assert "provider" in status
        assert "latency_ms" in status

    def test_health_check_provider_is_deepseek(self, deepseek_provider) -> None:
        deepseek_provider._client.get.return_value = MagicMock(
            status_code=200, json=lambda: {"data": [{"id": "deepseek-chat"}]}
        )
        status = deepseek_provider.health_check()
        assert status["provider"] == "deepseek"

    def test_complete_raises_not_implemented_in_phase_0(self, deepseek_provider) -> None:
        request = _make_request()
        with pytest.raises(NotImplementedError):
            deepseek_provider.complete(request)

    def test_close_sets_client_to_none(self, deepseek_provider) -> None:
        deepseek_provider.close()
        assert deepseek_provider._client is None

    def test_repr_contains_provider_name(self, deepseek_provider) -> None:
        assert "deepseek" in repr(deepseek_provider)


class TestStubProviders:
    """OpenAI, Claude, and Ollama providers must be typed stubs raising NotImplementedError."""

    @pytest.fixture(params=["openai", "claude", "ollama"])
    def stub_provider(self, request) -> BaseAIProvider:
        """Parametrised fixture returning each stub provider instance."""
        from core.ai.providers.openai_provider import OpenAIProvider
        from core.ai.providers.claude_provider import ClaudeProvider
        from core.ai.providers.ollama_provider import OllamaProvider

        mapping = {
            "openai": OpenAIProvider,
            "claude": ClaudeProvider,
            "ollama": OllamaProvider,
        }
        return mapping[request.param]()

    def test_is_base_provider_instance(self, stub_provider: BaseAIProvider) -> None:
        assert isinstance(stub_provider, BaseAIProvider)

    def test_validate_connection_raises_not_implemented(
        self, stub_provider: BaseAIProvider
    ) -> None:
        with pytest.raises(NotImplementedError):
            stub_provider.validate_connection()

    def test_health_check_raises_not_implemented(
        self, stub_provider: BaseAIProvider
    ) -> None:
        with pytest.raises(NotImplementedError):
            stub_provider.health_check()

    def test_complete_raises_not_implemented(
        self, stub_provider: BaseAIProvider
    ) -> None:
        with pytest.raises(NotImplementedError):
            stub_provider.complete(_make_request())

    def test_close_does_not_raise(self, stub_provider: BaseAIProvider) -> None:
        stub_provider.close()

    def test_openai_provider_name(self) -> None:
        from core.ai.providers.openai_provider import OpenAIProvider
        assert OpenAIProvider.provider_name == "openai"

    def test_claude_provider_name(self) -> None:
        from core.ai.providers.claude_provider import ClaudeProvider
        assert ClaudeProvider.provider_name == "claude"

    def test_ollama_provider_name(self) -> None:
        from core.ai.providers.ollama_provider import OllamaProvider
        assert OllamaProvider.provider_name == "ollama"


# ---------------------------------------------------------------------------
# AIRequest dataclass contracts
# ---------------------------------------------------------------------------


class TestAIRequestContracts:
    """AIRequest must be frozen and enforce its invariants in __post_init__."""

    def test_valid_construction(self) -> None:
        request = _make_request()
        assert request.symbol == "RELIANCE"
        assert request.max_tokens == 256

    def test_frozen_prevents_mutation(self) -> None:
        request = _make_request()
        with pytest.raises((AttributeError, TypeError)):
            request.symbol = "OTHER"  # type: ignore[misc]

    def test_naive_timestamp_raises(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            AIRequest(
                id=uuid.uuid4(),
                prompt="test",
                event_type="test",
                symbol="TEST",
                prompt_version="v1",
                max_tokens=100,
                timestamp=datetime.now(),
            )

    def test_empty_prompt_raises(self) -> None:
        with pytest.raises(ValueError, match="prompt"):
            AIRequest(
                id=uuid.uuid4(),
                prompt="",
                event_type="test",
                symbol="TEST",
                prompt_version="v1",
                max_tokens=100,
                timestamp=_utc_now(),
            )

    def test_zero_max_tokens_raises(self) -> None:
        with pytest.raises(ValueError):
            AIRequest(
                id=uuid.uuid4(),
                prompt="valid prompt",
                event_type="test",
                symbol="TEST",
                prompt_version="v1",
                max_tokens=0,
                timestamp=_utc_now(),
            )


# ---------------------------------------------------------------------------
# AIRawResponse dataclass contracts
# ---------------------------------------------------------------------------


class TestAIRawResponseContracts:
    """AIRawResponse must be frozen and validate its invariants."""

    def _make_response(self) -> AIRawResponse:
        return AIRawResponse(
            request_id=uuid.uuid4(),
            provider="gemini",
            raw_text='{"direction": "BUY"}',
            input_tokens=100,
            output_tokens=50,
            latency_ms=1250.5,
            estimated_cost_usd=Decimal("0.0012"),
            timestamp=_utc_now(),
        )

    def test_valid_construction(self) -> None:
        response = self._make_response()
        assert response.provider == "gemini"
        assert response.total_tokens == 150

    def test_frozen_prevents_mutation(self) -> None:
        response = self._make_response()
        with pytest.raises((AttributeError, TypeError)):
            response.provider = "openai"  # type: ignore[misc]

    def test_naive_timestamp_raises(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            AIRawResponse(
                request_id=uuid.uuid4(),
                provider="gemini",
                raw_text="{}",
                input_tokens=10,
                output_tokens=5,
                latency_ms=100.0,
                estimated_cost_usd=Decimal("0.001"),
                timestamp=datetime.now(),
            )

    def test_negative_tokens_raises(self) -> None:
        with pytest.raises(ValueError):
            AIRawResponse(
                request_id=uuid.uuid4(),
                provider="gemini",
                raw_text="{}",
                input_tokens=-1,
                output_tokens=5,
                latency_ms=100.0,
                estimated_cost_usd=Decimal("0.001"),
                timestamp=_utc_now(),
            )

    def test_total_tokens_property(self) -> None:
        response = self._make_response()
        assert response.total_tokens == response.input_tokens + response.output_tokens
