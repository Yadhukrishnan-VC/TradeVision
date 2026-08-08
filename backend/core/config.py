"""
TradeVision AI — Centralised, typed configuration interface.

Application code should import ``config`` from this module rather than
accessing ``django.conf.settings`` directly. This provides:
    - A single point of change if a setting is renamed
    - Typed property access with explicit defaults
    - Clear documentation of every setting the application depends on

All AI providers and market data providers must use this config singleton::

    from core.config import config

    api_key = config.gemini_api_key
    provider = config.ai_provider

Never scatter ``from django.conf import settings`` throughout the codebase.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class TradeVisionConfig:
    """
    Typed, centralised interface to all TradeVision AI settings.

    Each property reads from ``django.conf.settings`` with a sensible default
    so the application starts cleanly even with a minimal ``.env`` file.
    Import and use the module-level ``config`` singleton rather than
    instantiating this class directly.
    """

    # ---------------------------------------------------------------------------
    # AI provider
    # ---------------------------------------------------------------------------

    @property
    def ai_provider(self) -> str:
        """Active AI provider name. Matches a key in the provider map."""
        from django.conf import settings

        return getattr(settings, "AI_PROVIDER", "gemini").lower()

    @property
    def gemini_api_key(self) -> str:
        """Google Gemini API key."""
        from django.conf import settings

        return getattr(settings, "GEMINI_API_KEY", "")

    @property
    def gemini_model(self) -> str:
        """Gemini model identifier (e.g. ``gemini-1.5-pro``)."""
        from django.conf import settings

        return getattr(settings, "GEMINI_MODEL", "gemini-1.5-pro")

    @property
    def openai_api_key(self) -> str:
        """OpenAI API key."""
        from django.conf import settings

        return getattr(settings, "OPENAI_API_KEY", "")

    @property
    def openai_model(self) -> str:
        """OpenAI model identifier (e.g. ``gpt-4o``)."""
        from django.conf import settings

        return getattr(settings, "OPENAI_MODEL", "gpt-4o")

    @property
    def anthropic_api_key(self) -> str:
        """Anthropic Claude API key."""
        from django.conf import settings

        return getattr(settings, "ANTHROPIC_API_KEY", "")

    @property
    def anthropic_model(self) -> str:
        """Anthropic model identifier (e.g. ``claude-3-5-sonnet-20241022``)."""
        from django.conf import settings

        return getattr(settings, "ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

    @property
    def ollama_base_url(self) -> str:
        """Base URL for the local Ollama server."""
        from django.conf import settings

        return getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")

    @property
    def ollama_model(self) -> str:
        """Ollama model identifier (e.g. ``llama3.2``)."""
        from django.conf import settings

        return getattr(settings, "OLLAMA_MODEL", "llama3.2")

    @property
    def deepseek_api_key(self) -> str:
        """DeepSeek API key."""
        from django.conf import settings

        return getattr(settings, "DEEPSEEK_API_KEY", "")

    @property
    def deepseek_model(self) -> str:
        """DeepSeek model identifier (e.g. ``deepseek-chat``)."""
        from django.conf import settings

        return getattr(settings, "DEEPSEEK_MODEL", "deepseek-chat")

    @property
    def deepseek_base_url(self) -> str:
        """Base URL for the DeepSeek API."""
        from django.conf import settings

        return getattr(settings, "DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    # ---------------------------------------------------------------------------
    # AI governance
    # ---------------------------------------------------------------------------

    @property
    def ai_confidence_floor(self) -> float:
        """Minimum confidence score required to deliver a recommendation."""
        from django.conf import settings

        return float(getattr(settings, "AI_CONFIDENCE_FLOOR", 0.55))

    @property
    def ai_daily_budget_usd(self) -> float:
        """Hard daily AI spend limit in USD enforced via Redis counter."""
        from django.conf import settings

        return float(getattr(settings, "AI_DAILY_BUDGET_USD", 10.0))

    @property
    def ai_dedup_window_seconds(self) -> int:
        """
        Seconds within which a second AI call for the same symbol and event
        type is suppressed.
        """
        from django.conf import settings

        return int(getattr(settings, "AI_DEDUP_WINDOW_SECONDS", 300))

    @property
    def ai_provider_priority(self) -> list[str]:
        """Ordered default provider priority, most-preferred first.

        Read from a comma-separated env var ``AI_PROVIDER_PRIORITY``.
        """
        from django.conf import settings

        raw = getattr(
            settings, "AI_PROVIDER_PRIORITY", "claude,gemini,openai,deepseek,ollama"
        )
        return [p.strip() for p in raw.split(",")]

    @property
    def ai_provider_disabled(self) -> set[str]:
        """Providers manually disabled regardless of circuit state (ops kill-switch).

        Comma-separated env var ``AI_PROVIDER_DISABLED``, default empty.
        """
        from django.conf import settings

        raw = getattr(settings, "AI_PROVIDER_DISABLED", "")
        return {p.strip() for p in raw.split(",") if p.strip()}

    @property
    def ai_routing_fast_tier_threshold_ms(self) -> int:
        """Latency budget in ms below which only ``FAST`` tier providers are eligible."""
        from django.conf import settings

        return int(getattr(settings, "AI_ROUTING_FAST_TIER_THRESHOLD_MS", 1500))

    @property
    def ai_cost_tier_ceilings(self) -> dict[str, str]:
        """Static mapping from ``CostTier`` value to per-call USD ceiling (as string).

        Used by ``ModelRouter`` to exclude high-cost providers when
        ``RoutingRequest.cost_budget_usd`` is set.
        """
        return {
            "FREE": "0.000",
            "LOW": "0.005",
            "MEDIUM": "0.015",
            "HIGH": "0.050",
        }

    @property
    def ai_health_degraded_threshold_ms(self) -> float:
        """
        Latency threshold in milliseconds above which a provider's health
        status is reported as ``"degraded"`` instead of ``"healthy"``.
        """
        from django.conf import settings

        return float(getattr(settings, "AI_HEALTH_DEGRADED_THRESHOLD_MS", 2000.0))

    @property
    def ai_max_tokens(self) -> int:
        """Maximum tokens per AI prompt."""
        from django.conf import settings

        return int(getattr(settings, "AI_MAX_TOKENS", 4096))

    # ---------------------------------------------------------------------------
    # Market data provider
    # ---------------------------------------------------------------------------

    @property
    def market_data_provider(self) -> str:
        """Active market data provider name (e.g. ``mock``, ``paper``, ``zerodha``)."""
        from django.conf import settings

        return getattr(settings, "MARKET_DATA_PROVIDER", "mock").lower()

    @property
    def zerodha_api_key(self) -> str:
        """Zerodha Kite Connect API key."""
        from django.conf import settings

        return getattr(settings, "ZERODHA_API_KEY", "")

    @property
    def zerodha_access_token(self) -> str:
        """Zerodha Kite Connect access token (short-lived; generated out-of-band
        via the Kite login flow — this batch does not implement that flow).
        """
        from django.conf import settings

        return getattr(settings, "ZERODHA_ACCESS_TOKEN", "")

    # ---------------------------------------------------------------------------
    # Batch M4 — REST polling bridge
    # ---------------------------------------------------------------------------

    @property
    def market_data_poll_timeframe(self) -> str:
        """Candle timeframe polled by the REST polling bridge (e.g. ``1min``)."""
        from django.conf import settings

        return str(getattr(settings, "MARKET_DATA_POLL_TIMEFRAME", "1min"))

    @property
    def market_data_poll_interval_seconds(self) -> int:
        """Seconds between REST polling bridge beat executions."""
        from django.conf import settings

        return int(getattr(settings, "MARKET_DATA_POLL_INTERVAL_SECONDS", 60))

    @property
    def market_data_poll_staleness_seconds(self) -> int:
        """Maximum age in seconds of a candle before the bridge skips it as stale."""
        from django.conf import settings

        return int(getattr(settings, "MARKET_DATA_POLL_STALENESS_SECONDS", 180))

    @property
    def market_data_poll_window_seconds(self) -> int:
        """Historical window in seconds fetched per watchlist symbol on each poll."""
        from django.conf import settings

        return int(getattr(settings, "MARKET_DATA_POLL_WINDOW_SECONDS", 600))

    @property
    def market_data_poll_watchlist(self) -> list[tuple[str, str]]:
        """Watchlist of ``(exchange, tradingsymbol)`` pairs polled by the bridge."""
        from django.conf import settings

        return list(getattr(settings, "MARKET_DATA_POLL_WATCHLIST", []) or [])

    # ---------------------------------------------------------------------------
    # Market and exchange
    # ---------------------------------------------------------------------------

    @property
    def market_timezone(self) -> str:
        """IANA timezone string for all market operations (e.g. ``Asia/Kolkata``)."""
        from django.conf import settings

        return getattr(settings, "MARKET_TIMEZONE", "Asia/Kolkata")

    @property
    def default_exchange(self) -> str:
        """Primary exchange for the platform (``NSE`` or ``BSE``)."""
        from django.conf import settings

        return getattr(settings, "MARKET_EXCHANGE", "NSE")

    # ---------------------------------------------------------------------------
    # Data quality thresholds
    # ---------------------------------------------------------------------------

    @property
    def tick_freshness_threshold_seconds(self) -> int:
        """Maximum age in seconds for tick data before it is considered stale."""
        from django.conf import settings

        return int(getattr(settings, "TICK_FRESHNESS_THRESHOLD_SECONDS", 120))

    @property
    def indicator_freshness_threshold_seconds(self) -> int:
        """Maximum age in seconds for computed indicators before considered stale."""
        from django.conf import settings

        return int(getattr(settings, "INDICATOR_FRESHNESS_THRESHOLD_SECONDS", 300))

    @property
    def intelligence_min_quality_score(self) -> float:
        """Minimum IntelligencePacket quality score to allow rule evaluation."""
        from django.conf import settings

        return float(getattr(settings, "INTELLIGENCE_MIN_QUALITY_SCORE", 0.60))

    # ---------------------------------------------------------------------------
    # Resilience
    # ---------------------------------------------------------------------------

    @property
    def circuit_breaker_failure_threshold(self) -> int:
        """Consecutive failures before a circuit breaker opens."""
        from django.conf import settings

        return int(getattr(settings, "CIRCUIT_BREAKER_FAILURE_THRESHOLD", 5))

    @property
    def circuit_breaker_recovery_timeout(self) -> int:
        """Seconds a circuit breaker stays open before transitioning to half-open."""
        from django.conf import settings

        return int(getattr(settings, "CIRCUIT_BREAKER_RECOVERY_TIMEOUT", 60))

    # ---------------------------------------------------------------------------
    # Infrastructure
    # ---------------------------------------------------------------------------

    @property
    def redis_url(self) -> str:
        """Redis connection URL for direct client use outside the cache framework."""
        from django.conf import settings

        return getattr(settings, "REDIS_URL", "redis://redis:6379/0")

    # ---------------------------------------------------------------------------
    # Cache timeouts
    # ---------------------------------------------------------------------------

    @property
    def cache_timeouts(self) -> dict[str, int]:
        """
        Standard cache timeout values in seconds, keyed by use-case name.

        Use these constants rather than hardcoded integers to ensure
        consistent cache behaviour across the codebase.
        """
        return {
            "short": 60,
            "medium": 300,
            "long": 3600,
            "indicators": 300,
            "intelligence_packet": 120,
            "news": 900,
            "announcements": 1800,
            "global_markets": 600,
        }

    # ---------------------------------------------------------------------------
    # Batch B kill switches
    # ---------------------------------------------------------------------------

    @property
    def strategy_registry_enabled(self) -> bool:
        """Kill switch for Strategy Registry (B.3)."""
        from django.conf import settings

        return bool(getattr(settings, "STRATEGY_REGISTRY_ENABLED", False))

    @property
    def prompt_versioning_persistence_enabled(self) -> bool:
        """Kill switch for DB-backed prompt versioning (B.2)."""
        from django.conf import settings

        return bool(getattr(settings, "PROMPT_VERSIONING_PERSISTENCE_ENABLED", False))

    @property
    def confidence_engine_v2_enabled(self) -> bool:
        """Kill switch for Confidence Engine V2 (B.4)."""
        from django.conf import settings

        return bool(getattr(settings, "CONFIDENCE_ENGINE_V2_ENABLED", False))

    @property
    def model_router_preferred_provider_enabled(self) -> bool:
        """Kill switch for preferred provider hint in Model Router (B.1)."""
        from django.conf import settings

        return bool(getattr(settings, "MODEL_ROUTER_PREFERRED_PROVIDER_ENABLED", False))

    # ---------------------------------------------------------------------------
    # Celery queue names
    # ---------------------------------------------------------------------------

    @property
    def celery_queue_names(self) -> dict[str, str]:
        """
        All named Celery queue identifiers, keyed by logical role.

        Use ``from core.constants import QueueName`` for typed access to the
        same values in task routing decorators.
        """
        from core.constants import QueueName

        return {q.name.lower(): q.value for q in QueueName}


# ---------------------------------------------------------------------------
# Module-level singleton — import this, not the class
# ---------------------------------------------------------------------------

config: TradeVisionConfig = TradeVisionConfig()
