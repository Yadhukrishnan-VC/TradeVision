"""
Tests for BaseAIProvider interface — Phase 0 contract and capabilities.
"""

from core.ai.base_provider import BaseAIProvider, ProviderCapabilities
from core.constants import CostTier, LatencyTier


def test_base_provider_capabilities_returns_conservative_defaults() -> None:
    """Any provider not overriding ``capabilities()`` gets conservative defaults:
    JSON-only, no streaming/vision/function-calling, 8K context, STANDARD latency,
    MEDIUM cost.
    """

    class MinimalProvider(BaseAIProvider):
        provider_name = "test_minimal"

        def validate_connection(self) -> bool:
            return True

        def health_check(self) -> dict:
            return {"status": "healthy"}

        def complete(self, request) -> None:
            raise NotImplementedError

        def close(self) -> None:
            return

    provider = MinimalProvider()
    caps = provider.capabilities()

    assert isinstance(caps, ProviderCapabilities)
    assert caps.supports_structured_json is True
    assert caps.supports_streaming is False
    assert caps.supports_vision is False
    assert caps.supports_function_calling is False
    assert caps.context_window_tokens == 8192
    assert caps.max_output_tokens == 4096
    assert caps.latency_tier == LatencyTier.STANDARD
    assert caps.cost_tier == CostTier.MEDIUM
