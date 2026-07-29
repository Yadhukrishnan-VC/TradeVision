"""
TradeVision AI — Abstract AI provider interface and request/response contracts.

The AI layer is a structured reasoning engine. Providers receive a fully
rendered prompt string assembled by the ContextBuilder (Phase 4) and return
raw text. Parsing and validation are handled by ``AIResponseValidator``.

Frozen dataclasses enforce immutability for all data transfer objects.
All datetime fields are validated as timezone-aware in ``__post_init__``.
"""

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar

from core.ai.exceptions import AIProviderError
from core.constants import CostTier, LatencyTier, RecommendationDirection, RecommendationTimeHorizon, RiskLevel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request and response dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AIRequest:
    """
    A fully prepared AI inference request.

    The ``prompt`` field contains the rendered prompt string assembled by
    the ContextBuilder from an IntelligencePacket. Providers must not modify
    the prompt — they send it verbatim to the underlying LLM.

    Attributes:
        id:              Unique request identifier (UUID4).
        prompt:          Fully rendered prompt string (constructed in Phase 4).
        event_type:      String value of the EventType that triggered this call.
        symbol:          The NSE/BSE stock symbol being analysed.
        prompt_version:  Version tag of the prompt template used (e.g. ``"v1.0"``).
        max_tokens:      Maximum output tokens requested from the provider.
        timestamp:       UTC datetime when the request was created.
        correlation_id:  Correlation UUID for tracing across the event chain.
    """

    id: uuid.UUID
    prompt: str
    event_type: str
    symbol: str
    prompt_version: str
    max_tokens: int
    timestamp: datetime
    correlation_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError(
                "AIRequest.timestamp must be timezone-aware. "
                f"Got naive datetime: {self.timestamp!r}"
            )
        if not self.prompt:
            raise ValueError("AIRequest.prompt must not be empty.")
        if self.max_tokens < 1:
            raise ValueError(
                f"AIRequest.max_tokens must be a positive integer, got {self.max_tokens}."
            )


@dataclass(frozen=True)
class AIRawResponse:
    """
    The unprocessed response returned by an AI provider.

    Contains the raw LLM output text alongside metadata required for
    cost tracking, latency measurement, and audit logging. The
    ``AIResponseValidator`` parses this into a structured ``AIRecommendation``.

    Attributes:
        request_id:          Links back to the originating ``AIRequest.id``.
        provider:            Provider name string (e.g. ``"gemini"``).
        raw_text:            Raw output text from the LLM.
        input_tokens:        Number of tokens consumed by the prompt.
        output_tokens:       Number of tokens in the response.
        latency_ms:          Total provider round-trip latency in milliseconds.
        estimated_cost_usd:  Estimated USD cost for this call (Decimal precision).
        timestamp:           UTC datetime when the response was received.
    """

    request_id: uuid.UUID
    provider: str
    raw_text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    estimated_cost_usd: Decimal
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError(
                "AIRawResponse.timestamp must be timezone-aware. "
                f"Got naive datetime: {self.timestamp!r}"
            )
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("Token counts must be non-negative.")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must be non-negative.")

    @property
    def total_tokens(self) -> int:
        """Return the total token count for this response."""
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class AIRecommendation:
    """
    A fully parsed and validated AI recommendation.

    Produced by parsing an ``AIRawResponse`` through ``AIResponseValidator``
    and stored in ``TraderMemory`` as the permanent record of an AI inference.

    Attributes:
        request_id:           Links to the originating ``AIRequest``.
        direction:            Recommended action (BUY / SELL / WATCH / AVOID).
        confidence_score:     Model confidence in [0.0, 1.0].
        reasoning:            Human-readable explanation of the recommendation.
        risk_level:           Assessed risk level from the Risk Agent.
        risk_explanation:     Narrative explanation of risk factors.
        key_factors:          Ordered tuple of supporting evidence strings.
        contradicting_factors: Tuple of evidence that argues against the direction.
        time_horizon:         Intended holding period for this recommendation.
        follow_up_triggers:   Conditions that should prompt a re-evaluation.
        prompt_version:       Version of the prompt template that generated this.
        provider:             AI provider that generated this recommendation.
        data_quality_flagged: True if the IntelligencePacket quality was below threshold.
        timestamp:            UTC datetime when the recommendation was produced.
    """

    request_id: uuid.UUID
    direction: RecommendationDirection
    confidence_score: float
    reasoning: str
    risk_level: RiskLevel
    risk_explanation: str
    key_factors: tuple[str, ...]
    contradicting_factors: tuple[str, ...]
    time_horizon: RecommendationTimeHorizon
    follow_up_triggers: tuple[str, ...]
    prompt_version: str
    provider: str
    data_quality_flagged: bool
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError(
                "AIRecommendation.timestamp must be timezone-aware. "
                f"Got naive datetime: {self.timestamp!r}"
            )
        if not 0.0 <= self.confidence_score <= 1.0:
            raise ValueError(
                f"confidence_score must be in [0.0, 1.0], got {self.confidence_score}."
            )
        if not self.reasoning:
            raise ValueError("AIRecommendation.reasoning must not be empty.")


# ---------------------------------------------------------------------------
# Provider capabilities
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderCapabilities:
    """Static capability profile of an AI provider/model.

    Defaults are conservative (JSON-only, no streaming/vision/function-calling).
    Real values are maintained in ``model_router.PROVIDER_CAPABILITIES``.
    """

    supports_structured_json: bool = True
    supports_streaming: bool = False
    supports_vision: bool = False
    supports_function_calling: bool = False
    context_window_tokens: int = 8192
    max_output_tokens: int = 4096
    latency_tier: LatencyTier = LatencyTier.STANDARD
    cost_tier: CostTier = CostTier.MEDIUM


# ---------------------------------------------------------------------------
# Abstract provider interface
# ---------------------------------------------------------------------------


class BaseAIProvider(ABC):
    """
    Abstract interface for all AI inference providers.

    Every concrete provider (Gemini, OpenAI, Claude, Ollama) must implement
    the full lifecycle contract defined here. The factory returns a
    ``BaseAIProvider`` instance — application code never imports concrete
    provider classes.

    Lifecycle::

        provider = AIProviderFactory.get_provider()   # obtain singleton
        ok = provider.validate_connection()            # verify credentials
        status = provider.health_check()               # check availability
        raw = provider.complete(request)               # inference (Phase 4)
        provider.close()                               # release resources

    Class attributes:
        provider_name: Unique string identifier matching ``settings.AI_PROVIDER``.
    """

    provider_name: ClassVar[str]

    @abstractmethod
    def validate_connection(self) -> bool:
        """
        Perform a lightweight check to verify credentials and connectivity.

        Returns:
            ``True`` if the provider is reachable and credentials are valid.

        Raises:
            AIAuthenticationError: If the provider rejects credentials.
            AIConnectionError:     If the provider is unreachable.
        """

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """
        Return a health status dictionary for this provider.

        The returned dict must include at minimum:
            - ``status``:     ``"healthy"`` | ``"degraded"`` | ``"unhealthy"``
            - ``provider``:   ``self.provider_name``
            - ``latency_ms``: float, provider round-trip time

        Returns:
            Status dictionary suitable for inclusion in a ``HealthResponse``.
        """

    @abstractmethod
    def complete(self, request: AIRequest) -> AIRawResponse:
        """
        Submit the prompt in ``request`` to the AI provider and return raw output.

        This method is implemented in Phase 4 alongside the ContextBuilder,
        ResponseParser, budget enforcement, and deduplication logic.

        Args:
            request: A fully populated ``AIRequest`` with a rendered prompt.

        Returns:
            ``AIRawResponse`` containing the raw LLM text and token metadata.

        Raises:
            AIProviderError:           On any provider-side error.
            AIRateLimitError:          When the provider rate limits the request.
            AIQuotaExceededError:      When provider quota is exhausted.
            AIResponseValidationError: If the response cannot be parsed.
            NotImplementedError:       In Phase 0 stubs.
        """

    @abstractmethod
    def close(self) -> None:
        """
        Release all resources held by this provider.

        Called by ``AIProviderFactory.reset()`` and at application shutdown.
        Implementations should close HTTP sessions, nullify client references,
        and perform any other cleanup required by the underlying SDK.
        """

    def capabilities(self) -> ProviderCapabilities:
        """
        Return this provider's static capability profile.

        Concrete providers may override to report their actual capabilities.
        The default is conservative — subclasses that do not override are
        assumed to support only JSON output with an 8K context window.

        Returns:
            ``ProviderCapabilities`` with conservative defaults.
        """
        return ProviderCapabilities()

    def __repr__(self) -> str:
        """Return an unambiguous developer representation."""
        return f"<{self.__class__.__name__} provider={self.provider_name!r}>"
