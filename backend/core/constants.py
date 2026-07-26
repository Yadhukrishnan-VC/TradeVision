"""
TradeVision AI — Project-wide constants and enumerations.

All string constants used across modules are centralised here to prevent
typo-based bugs and to provide a single source of truth for valid values.

Import convention::

    from core.constants import MarketStatus, QueueName, RecommendationDirection
"""

from enum import Enum


# ---------------------------------------------------------------------------
# Market state
# ---------------------------------------------------------------------------


class MarketStatus(str, Enum):
    """Current operational state of the exchange."""

    OPEN = "open"
    """Continuous trading session is active (09:15–15:30 IST)."""

    CLOSED = "closed"
    """Exchange is closed (evenings, nights, weekends)."""

    PRE_OPEN = "pre_open"
    """Pre-open call auction session (09:00–09:15 IST)."""

    POST_CLOSE = "post_close"
    """Post-close session (15:30–16:00 IST)."""

    HOLIDAY = "holiday"
    """Exchange holiday — no trading."""

    SUSPENDED = "suspended"
    """Trading suspended by regulatory or technical action."""


# ---------------------------------------------------------------------------
# AI recommendation outputs
# ---------------------------------------------------------------------------


class RecommendationDirection(str, Enum):
    """Possible directional outputs from the AI Recommendation Engine."""

    BUY = "BUY"
    """Evidence supports a long position or adding to an existing position."""

    SELL = "SELL"
    """Evidence supports reducing or exiting a long position."""

    WATCH = "WATCH"
    """Signal is significant but inconclusive — monitor closely."""

    AVOID = "AVOID"
    """Risk factors make the instrument unsuitable at this time."""


class RecommendationTimeHorizon(str, Enum):
    """Intended holding period implied by an AI recommendation."""

    INTRADAY = "INTRADAY"
    SHORT = "SHORT"
    """1–5 trading sessions."""

    MEDIUM = "MEDIUM"
    """1–4 weeks."""

    LONG = "LONG"
    """1+ months."""


class RecommendationOutcome(str, Enum):
    """Result of a recommendation evaluated by the backtesting module."""

    PENDING = "PENDING"
    """Evaluation window has not yet closed."""

    CORRECT = "CORRECT"
    """Price moved in the recommended direction above the success threshold."""

    INCORRECT = "INCORRECT"
    """Price moved against the recommended direction."""

    PARTIAL = "PARTIAL"
    """Price moved in the right direction but below the success threshold."""

    INCONCLUSIVE = "INCONCLUSIVE"
    """Market conditions prevented a clear evaluation (halted, circuit, etc.)."""


# ---------------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------------


class RiskLevel(str, Enum):
    """Assessed risk level attached to a recommendation by the Risk Agent."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class NotificationType(str, Enum):
    """Category of notification delivered to a user."""

    RECOMMENDATION = "recommendation"
    """New AI-generated trading recommendation."""

    PRICE_ALERT = "price_alert"
    """User-configured price threshold crossed."""

    ANNOUNCEMENT = "announcement"
    """High-materiality corporate announcement."""

    EARNINGS = "earnings"
    """Quarterly results published or imminent."""

    CIRCUIT = "circuit"
    """Upper or lower circuit breaker triggered."""

    MACRO_EVENT = "macro_event"
    """Scheduled macro event (RBI, Fed, budget, etc.)."""

    PORTFOLIO_ALERT = "portfolio_alert"
    """Portfolio drawdown, position limit, or expiry warning."""

    FEED_DEGRADED = "feed_degraded"
    """A data source circuit breaker has opened (operational — admin only)."""

    AI_BUDGET_WARNING = "ai_budget_warning"
    """AI cost at 80% of daily budget (operational — admin only)."""

    STALE_DATA = "stale_data"
    """Symbol data has exceeded its freshness threshold (operational — admin only)."""

    SYSTEM = "system"
    """General operational / system message."""


# ---------------------------------------------------------------------------
# AI providers
# ---------------------------------------------------------------------------


class AIProviderName(str, Enum):
    """Registered AI provider identifiers — must match ``settings.AI_PROVIDER``."""

    GEMINI = "gemini"
    OPENAI = "openai"
    CLAUDE = "claude"
    OLLAMA = "ollama"
    DEEPSEEK = "deepseek"


# ---------------------------------------------------------------------------
# Celery task names
# ---------------------------------------------------------------------------


class TaskName(str, Enum):
    """
    Canonical Celery task name strings.

    Using these constants prevents silent routing failures caused by
    task name typos. Every ``@app.task(name=...)`` must use the
    corresponding value from this enum.
    """

    INGEST_MARKET_DATA = "tradevision.market_data.ingest"
    INGEST_NEWS = "tradevision.news_feed.ingest"
    INGEST_ANNOUNCEMENTS = "tradevision.announcements.ingest"
    INGEST_GLOBAL_MARKETS = "tradevision.global_markets.ingest"

    COMPUTE_INDICATORS = "tradevision.technical_analysis.compute"
    ANALYZE_OPTIONS = "tradevision.options_chain.analyze"
    COMPUTE_BREADTH = "tradevision.market_breadth.compute"
    PROCESS_NLP = "tradevision.news_feed.process_nlp"

    ASSEMBLE_INTELLIGENCE_PACKET = "tradevision.intelligence.assemble"

    EVALUATE_RULES = "tradevision.rule_engine.evaluate"

    CALL_AI_PROVIDER = "tradevision.ai_engine.call"
    STORE_RECOMMENDATION = "tradevision.recommendations.store"

    DISPATCH_NOTIFICATION = "tradevision.notifications.dispatch"
    SEND_EMAIL = "tradevision.notifications.send_email"

    TRACK_RECOMMENDATION_OUTCOME = "tradevision.backtesting.track_outcome"
    RUN_CALIBRATION = "tradevision.backtesting.calibrate"


# ---------------------------------------------------------------------------
# Queue names
# ---------------------------------------------------------------------------


class QueueName(str, Enum):
    """
    Celery queue name strings — must match the queues defined in ``config/celery.py``.

    Use these constants instead of bare strings to prevent routing bugs::

        @app.task(queue=QueueName.AI)
        def call_ai_provider(...): ...
    """

    MARKET_DATA = "market_data"
    PROCESSING = "processing"
    INTELLIGENCE = "intelligence"
    RULE_ENGINE = "rule_engine"
    AI = "ai"
    NOTIFICATIONS = "notifications"
    ANALYTICS = "analytics"
    DEFAULT = "default"
