"""
TradeVision AI — Abstract AI provider interface.

Defines the ``BaseAIProvider`` ABC that every AI provider must implement,
along with the request/response data contracts used throughout the AI layer.

Lifecycle::

    provider = GeminiProvider(api_key="...", model="gemini-1.5-pro")
    provider.validate_connection()   # → True
    status = provider.health_check() # → {"status": "healthy", ...}
    response = provider.complete(request)
    provider.close()
"""

import abc
import dataclasses
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from core.ai.exceptions import AIProviderError
from core.constants import RecommendationDirection, RiskLevel


# ---------------------------------------------------------------------------
# Request / Response dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AIRequest:
    """
    A structured request to an AI provider for analysis.

    Attributes:
        event_type:      Classification of the market event.
        symbol:          NSE/BSE stock symbol.
        prompt:          Rendered Jinja2 prompt string.
        trigger_data:    Rule-specific data that triggered this request.
        correlation_id:  Unique ID for request tracing.
        max_tokens:      Maximum tokens in the AI response.
        temperature:     Sampling temperature (0.0–2.0).
    """

    event_type: str
    symbol: str
    prompt: str
    trigger_data: dict[str, Any] = dataclasses.field(default_factory=dict)
    correlation_id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    max_tokens: int = 4096
    temperature: float = 0.3


@dataclass(frozen=True)
class AIRawResponse:
    """
    The raw, unvalidated response from an AI provider.

    Attributes:
        provider:          Name of the provider that produced this response.
        content:           Raw text content from the AI.
        model:             Model identifier that generated the response.
        token_usage:       Dict with prompt_tokens, completion_tokens, total_tokens.
        latency_ms:        Round-trip time in milliseconds.
        correlation_id:    Matches the originating request.
        raw_metadata:      Provider-specific metadata dict.
    """

    provider: str
    content: str
    model: str
    token_usage: dict[str, int] = dataclasses.field(default_factory=dict)
    latency_ms: float = 0.0
    correlation_id: str = ""
    raw_metadata: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclass(frozen=True)
class AIRecommendation:
    """
    A validated, structured recommendation parsed from an AI response.

    Attributes:
        direction:          BUY, SELL, WATCH, or AVOID.
        confidence:         0.0–1.0 confidence score.
        reasoning:          Human-readable explanation.
        risk_level:         LOW, MEDIUM, HIGH, VERY_HIGH.
        time_horizon:       INTRADAY, SHORT, MEDIUM, LONG.
        target_price:       Optional target price.
        stop_loss:          Optional stop-loss price.
        key_factors:        List of key contributing factors.
        provider:           AI provider name.
        model:              Model identifier.
        correlation_id:     Tracing ID.
    """

    direction: RecommendationDirection
    confidence: Decimal
    reasoning: str
    risk_level: RiskLevel
    time_horizon: str = "SHORT"
    target_price: Decimal | None = None
    stop_loss: Decimal | None = None
    key_factors: tuple[str, ...] = ()
    provider: str = ""
    model: str = ""
    correlation_id: str = ""


# ---------------------------------------------------------------------------
# Abstract base provider
# ---------------------------------------------------------------------------


class BaseAIProvider(abc.ABC):
    """
    Abstract interface for all AI providers.

    Subclasses must implement the four lifecycle methods. The provider
    factory calls these methods in order during provider initialization
    and shutdown.

    Class Attributes:
        provider_name:  Unique identifier (e.g. ``"gemini"``, ``"openai"``).
    """

    provider_name: str

    @abc.abstractmethod
    def validate_connection(self) -> bool:
        """
        Verify that the provider is reachable and credentials are valid.

        Returns:
            True if the connection is valid.

        Raises:
            AIAuthenticationError: If credentials are rejected.
            AIConnectionError:     If the provider is unreachable.
        """

    @abc.abstractmethod
    def health_check(self) -> dict[str, Any]:
        """
        Return a health status dict for the provider.

        Returns:
            A dict with at minimum ``{"status": "healthy"|"degraded"|"unhealthy"}``
            and optionally ``latency_ms``, ``model``, ``detail`` keys.
        """

    @abc.abstractmethod
    def complete(self, request: AIRequest) -> AIRawResponse:
        """
        Send a prompt to the AI provider and return the raw response.

        Args:
            request: The structured AI request.

        Returns:
            An ``AIRawResponse`` with the raw provider output.

        Raises:
            AIProviderError: On any provider-level failure.
            NotImplementedError: On stub providers not yet implemented.
        """

    @abc.abstractmethod
    def close(self) -> None:
        """Release any resources held by the provider (HTTP clients, etc.)."""
