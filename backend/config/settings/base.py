from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

from decouple import config
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-change-in-production")

DEBUG = False

ALLOWED_HOSTS: list[str] = []

# CORS — API authentication is header-based (JWT Bearer / Api-Key), so no
# cookies are exchanged and CORS_ALLOW_CREDENTIALS stays off. Cross-origin
# SPA origins must be listed explicitly here; production never allows all
# origins. Development overrides this with CORS_ALLOW_ALL_ORIGINS=True.
CORS_ALLOWED_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
CORS_ALLOW_CREDENTIALS: bool = False

# Custom user model — email-only auth, UUID pk, role-based RBAC.
# This replaces Django's default auth.User and activates the model defined
# in apps/accounts/models.py. Must be set before the first makemigrations run.
AUTH_USER_MODEL: str = "accounts.User"

# ---------------------------------------------------------------------------
# Installed applications
# ---------------------------------------------------------------------------
DJANGO_APPS: list[str] = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_celery_beat",
    "django_celery_results",
]

# Populated progressively as app modules are scaffolded in Batches 4-8.
# Each batch patches this list via str_replace without regenerating this file.
# Remediation R1.a — every implemented app under apps/ with real models or views.
# Order matters: common first (provides BaseModel used by other apps),
# accounts second (provides AUTH_USER_MODEL), health last (no models).
LOCAL_APPS: list[str] = [
    "apps.common",
    "apps.eventbus",
    "apps.accounts",
    "apps.health",
    "channels",
    "apps.dashboard",
    "apps.audit_log",
    "apps.journal",
    "apps.replay",
    # B.0 — AI/Intelligence apps
    "apps.ai_engine",
    "apps.intelligence",
    "apps.recommendations",
    "apps.strategy_registry",
    "apps.rule_engine",
    "apps.trader_memory",
    # M3 — Deterministic Risk Management
    "apps.risk_management",
    # M4 — Portfolio & Capital Management (authoritative portfolio state)
    "apps.portfolio",
    # Milestone B — Safe Paper Execution Engine (RiskApproved -> PaperBroker
    # -> Order lifecycle -> portfolio fills). Sits after portfolio because it
    # drives PositionLedgerService.record_fill.
    "apps.execution",
    # Ingestion — single front door for external webhook payloads
    # (TradingView alerts, Chartink scan results). Publishers the
    # ingestion.RawAlertReceived / ingestion.ScanResultReceived events that
    # the signals_engine consumes.
    "apps.ingestion",
    # Batch 2 — Signals Engine
    "apps.signals_engine",
    # Batch 3 — Technical Analysis
    "apps.technical_analysis",
    # Market Data — Historical OHLCV source consumed by the Pattern Engine
    "apps.market_data",
    # Batch AI-5 — Pattern Engine
    "apps.pattern_engine",
    # Batch M3 — Historical Replay & Backtesting. Sits after execution so its
    # replay drives the real RiskApproved -> PaperBroker -> fills pipeline.
    "apps.backtesting",
    # WATCH-1 — Per-account User Watchlist. Consumes market_data (read-only)
    # for best-effort quote enrichment.
    "apps.watchlist",
    # PIPELINE-HEALTH-1 — Forward paper-trading pipeline health & staleness
    # monitoring. Observability-only: consumes upstream events (read-only)
    # and publishes pipeline_health.StageStalled on HEALTHY->STALLED.
    "apps.pipeline_health",
    # PORTFOLIO-RECONCILE-1 — Dashboard read-model reconciliation against
    # the portfolio/execution source of truth. Detects and repairs drift in
    # the dashboard's PositionSnapshot/OrderSnapshot read model.
    "apps.portfolio_reconciliation",
    # MACRO-CONTEXT-1 — Point-in-time macro context from FRED/ALFRED.
    # Provider ingest + provenance store; consumed by the intelligence
    # context scoring as an additive context dimension.
    "apps.macro_context",
    # NEWS-FEED-1 — Licensed news provider (Marketaux). Ingested headlines +
    # provider sentiment; surfaces into IntelligencePacket.news_context.
    "apps.news_feed",
]

THIRD_PARTY_APPS = []

INSTALLED_APPS: list[str] = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE: list[str] = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.common.infrastructure.middleware.CorrelationIdMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "tradevision_db"),
        "USER": os.environ.get("POSTGRES_USER", "tradevision"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "ATOMIC_REQUESTS": True,
    }
}

import dj_database_url  # noqa: E402
db_url = os.environ.get("DATABASE_URL")
if db_url:
    DATABASES["default"] = dj_database_url.parse(db_url, conn_max_age=600)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ.get("REDIS_CACHE_URL", "redis://localhost:6379/3"),
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [os.environ.get("REDIS_CHANNELS_URL", "redis://localhost:6379/2")],
        },
    },
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    # JWT Bearer — interactive user/session authentication (login/refresh).
    # API Key — scoped data authorization (Authorization: Api-Key <raw_key>).
    # Both are registered so the existing API contracts work: session/identity
    # endpoints authenticate via JWT; scope-gated data endpoints require the
    # API key's scopes via the existing HasAPIKeyScope permission classes.
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "apps.accounts.infrastructure.authentication.APIKeyAuthentication",
    ),
    "DEFAULT_PARSER_CLASSES": ("rest_framework.parsers.JSONParser",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "EXCEPTION_HANDLER": "apps.common.infrastructure.drf_exception_handler.custom_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    # API rate limiting (WS2). Counters live in the configured cache backend
    # (Redis in production; DummyCache in tests is inert — a no-op that never
    # triggers). Rates are env-overridable per environment.
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.environ.get("THROTTLE_RATE_ANON", "120/hour"),
        "user": os.environ.get("THROTTLE_RATE_USER", "6000/hour"),
        "auth": os.environ.get("THROTTLE_RATE_AUTH", "15/min"),
        "api_keys": os.environ.get("THROTTLE_RATE_API_KEYS", "30/hour"),
    },
}

from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.environ.get("JWT_REFRESH_TOKEN_LIFETIME_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": os.environ.get("JWT_ALGORITHM", "HS256"),
    "SIGNING_KEY": os.environ.get("JWT_SECRET_KEY", SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

CELERY_APP = "config.celery"
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Kolkata"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60
CELERY_TASK_SOFT_TIME_LIMIT = 30
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

CELERY_TASK_ROUTES = {
    "apps.eventbus.infrastructure.tasks.dispatch_event_to_handler": {"queue": "maintenance"},
    "apps.eventbus.infrastructure.tasks.poll_event_streams": {"queue": "maintenance"},
    "apps.eventbus.infrastructure.tasks.replay_unpublished_events": {"queue": "maintenance"},
    "apps.accounts.infrastructure.tasks.purge_expired_tokens": {"queue": "maintenance"},
    "apps.journal.infrastructure.tasks.finalize_stale_entries": {"queue": "analytics"},
    # B.3 — Strategy Registry
    "tradevision.strategy_registry.match_packet": {"queue": "ai_reasoning"},
    # B.4 — Confidence Engine
    "tradevision.ai_engine.evaluate_confidence": {"queue": "ai_reasoning"},
    # B.5 — Recommendation Explanation
    "tradevision.recommendations.compose_explanation": {"queue": "ai_reasoning"},
    # Rule Engine
    "tradevision.rule_engine.evaluate_packet": {"queue": "rule_engine"},
    "tradevision.rule_engine.publish_rule_firing": {"queue": "rule_engine"},
    # Risk Management — M3
    "tradevision.risk_management.evaluate_rule_firing": {"queue": "decisions"},
    # Milestone B — Safe Paper Execution Engine. Request intake (RiskApproved
    # -> ExecutionRequest -> Order) runs on decisions; the broker simulation
    # (ExecutionEngine -> PaperBroker -> fills) runs on execution.
    "tradevision.execution.handle_risk_approved": {"queue": "decisions"},
    "tradevision.execution.process_order": {"queue": "execution"},
    # Recommendations
    "tradevision.recommendations.create_recommendation": {"queue": "ai_reasoning"},
    # Trader Memory
    "tradevision.trader_memory.record_memory_entry": {"queue": "analytics"},
    "tradevision.trader_memory.rebuild_projection": {"queue": "analytics"},
    # Pattern Engine — nightly precompute + triggered analysis both run on the
    # analytics queue (same profile as backtesting/calibration per §9.2).
    "tradevision.pattern_engine.precompute_historical_vectors": {"queue": "analytics"},
    "tradevision.pattern_engine.run_pattern_analysis": {"queue": "analytics"},
    # Backtesting — Batch M3 historical replay. Runs on the analytics queue
    # and MUST execute eagerly (see BacktestRunnerService / core.clock).
    "tradevision.backtesting.run_backtest": {"queue": "analytics"},
    # PIPELINE-HEALTH-1 — forward-pipeline health/staleness evaluation.
    "apps.pipeline_health.infrastructure.tasks.evaluate_pipeline_health": {"queue": "maintenance"},
}

CELERY_TASK_QUEUES = [
    "webhooks",
    "signals",
    "analysis",
    "ai_reasoning",
    "decisions",
    "execution",
    "monitoring",
    "portfolio",
    "analytics",
    "notifications",
    "maintenance",
    "market_data",
]

# ---------------------------------------------------------------------------
# Batch M4 — Real Market Data REST polling bridge
#
# One Celery Beat task polls the configured watchlist during market hours on
# ``MARKET_DATA_POLL_INTERVAL_SECONDS``, reusing HistoricalSyncService for
# candle persistence and a small candle->TA adapter to drive the existing
# TechnicalAnalysisIngestionService seam. Every poll setting is operator
# config here — nothing is hardcoded in application code.
# ---------------------------------------------------------------------------
VALID_MARKET_DATA_POLL_TIMEFRAMES: set[str] = {
    "1min", "3min", "5min", "10min", "15min", "30min", "1hr", "2hr", "4hr", "1D",
}


def _parse_poll_watchlist(raw: str) -> list[tuple[str, str]]:
    """Parse ``EXCHANGE:SYMBOL`` pairs from the env watchlist string.

    Keeps the watchlist a plain config value (not a Python literal list) so
    it can be supplied via environment variables in every deploy environment.
    """
    result: list[tuple[str, str]] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        exchange, sep, symbol = token.partition(":")
        if not sep or not exchange.strip() or not symbol.strip():
            raise ValueError(
                f"Invalid MARKET_DATA_POLL_WATCHLIST entry {token!r}. "
                "Expected 'EXCHANGE:SYMBOL' pairs separated by commas, "
                "e.g. 'NSE:RELIANCE,NSE:TCS'."
            )
        result.append((exchange.strip().upper(), symbol.strip().upper()))
    return result


MARKET_DATA_POLL_TIMEFRAME: str = config("MARKET_DATA_POLL_TIMEFRAME", default="1min")
MARKET_DATA_POLL_INTERVAL_SECONDS: int = config(
    "MARKET_DATA_POLL_INTERVAL_SECONDS", default=60, cast=int
)
MARKET_DATA_POLL_STALENESS_SECONDS: int = config(
    "MARKET_DATA_POLL_STALENESS_SECONDS", default=180, cast=int
)
MARKET_DATA_POLL_WINDOW_SECONDS: int = config(
    "MARKET_DATA_POLL_WINDOW_SECONDS", default=600, cast=int
)
MARKET_DATA_POLL_WATCHLIST: list[tuple[str, str]] = _parse_poll_watchlist(
    config("MARKET_DATA_POLL_WATCHLIST", default="")
)
# TTL of the Redis mutex guarding one ``poll_market_data_watchlist`` cycle
# (batch M4 remediation). Celery hard-kills the task at
# ``CELERY_TASK_TIME_LIMIT`` (60s); this is hard-kill time + safety margin, so
# a worker killed mid-cycle can never hold the lock past the point Celery
# would already have terminated it. Even in the worst case the lock
# self-expires and polling self-recovers within this window.
MARKET_DATA_POLL_LOCK_TTL_SECONDS: int = config(
    "MARKET_DATA_POLL_LOCK_TTL_SECONDS", default=90, cast=int
)

# ---------------------------------------------------------------------------
# Batch M5.1 — session-facts backfill frames
#
# Beyond the operating timeframe (MARKET_DATA_POLL_TIMEFRAME), the polling
# bridge conditionally backfills two longer frames that SessionFactsService
# derives session facts from (opening 15-minute candle, previous-day OHLC,
# rolling average daily volume). The windows below are trailing calendar days
# fetched for each symbol on the FIRST poll of a session (the backfill is
# self-limiting: once the current session's opening 15m candle / previous
# day's OHLC exist, the frame is skipped until the next session).
# ---------------------------------------------------------------------------
MARKET_DATA_POLL_15MIN_LOOKBACK_DAYS: int = config(
    "MARKET_DATA_POLL_15MIN_LOOKBACK_DAYS", default=20, cast=int
)
MARKET_DATA_POLL_1D_LOOKBACK_DAYS: int = config(
    "MARKET_DATA_POLL_1D_LOOKBACK_DAYS", default=30, cast=int
)

# ---------------------------------------------------------------------------
# PIPELINE-HEALTH-1 — per-stage max-silence expectations (seconds).
#
# A stage is considered stalled when it has produced no heartbeat for
# longer than its expectation during market hours. MARKET_DATA is derived
# from the poll cadence (3x — two missed poll cycles plus a heartbeat-cycle
# delay); the downstream stages are operator-configurable with sensible
# defaults matched to their natural cadence (TA is webhook-driven, the
# rule engine fires per evaluation, execution only on fills).
# ---------------------------------------------------------------------------
TECHNICAL_ANALYSIS_MAX_SILENCE_SECONDS: int = config(
    "TECHNICAL_ANALYSIS_MAX_SILENCE_SECONDS", default=300, cast=int
)
INTELLIGENCE_MAX_SILENCE_SECONDS: int = config(
    "INTELLIGENCE_MAX_SILENCE_SECONDS", default=300, cast=int
)
RULE_ENGINE_MAX_SILENCE_SECONDS: int = config(
    "RULE_ENGINE_MAX_SILENCE_SECONDS", default=300, cast=int
)
EXECUTION_MAX_SILENCE_SECONDS: int = config(
    "EXECUTION_MAX_SILENCE_SECONDS", default=600, cast=int
)

# ---------------------------------------------------------------------------
# PORTFOLIO-RECONCILE-1 — dashboard read-model reconciliation.
#
# RECONCILIATION_AVG_PRICE_TOLERANCE is the maximum absolute difference,
# in price-quote decimals, accepted between the write-model avg entry
# price and the read-model entry price before a position is classified
# STALE. The write model may carry more precision than the read-model
# field (max_digits=20, decimal_places=8 on both sides — in practice they
# match exactly); the tolerance exists purely for defensive correctness.
# ---------------------------------------------------------------------------
RECONCILIATION_AVG_PRICE_TOLERANCE: str = config(
    "RECONCILIATION_AVG_PRICE_TOLERANCE", default="0.00000001"
)
# Cadence of the fan-out task. Drift detection does not need
# pipeline_health's 30s cadence — projector lag of a few minutes is
# acceptable; this catches sustained drift, not transient in-flight state.
RECONCILIATION_BEAT_INTERVAL_SECONDS: int = config(
    "RECONCILIATION_BEAT_INTERVAL_SECONDS", default=300, cast=int
)

# ---------------------------------------------------------------------------
# NEWS-FEED-1 — beat cadence for the periodic news ingestion task.
#
# Defined before CELERY_BEAT_SCHEDULE (below) because the schedule entry
# references it directly. All other news settings live in their own block.
# ---------------------------------------------------------------------------
NEWS_POLL_INTERVAL_SECONDS: int = config(
    "NEWS_POLL_INTERVAL_SECONDS", default=900, cast=int
)

# ---------------------------------------------------------------------------
# Celery Beat schedule — market_data periodic tasks
#
# Only arg-free periodic tasks are scheduled here. ``refresh_candles`` and
# ``run_historical_sync`` require per-instrument ``instrument_token`` +
# ``timeframe`` arguments, so they are invoked on-demand (by other tasks or
# by orchestration) rather than on a global schedule — a beat entry without
# a concrete instrument would either crash or require fabricating a token.
# ---------------------------------------------------------------------------
CELERY_BEAT_SCHEDULE = {
    # Poll session state every 30s during market hours; publishes
    # marketdata.SessionStatusChanged only on an actual transition.
    "detect-session-transitions": {
        "task": "apps.market_data.infrastructure.tasks.detect_session_transitions",
        "schedule": 30.0,
        "options": {"queue": "market_data"},
    },
    # Batch M4 — REST polling bridge. Fetches the latest bars for the
    # configured MARKET_DATA_POLL_WATCHLIST during market hours and drives the
    # existing TA ingestion seam. No-ops when the watchlist is empty (the
    # default) or outside market hours.
    "poll-market-data-watchlist": {
        "task": "apps.market_data.infrastructure.polling_tasks.poll_market_data_watchlist",
        "schedule": MARKET_DATA_POLL_INTERVAL_SECONDS,
        "options": {"queue": "market_data"},
    },
    # Self-healing watchdog for the WebSocket tick manager.
    "reconnect-websocket-watchdog": {
        "task": "apps.market_data.infrastructure.tasks.reconnect_websocket_watchdog",
        "schedule": 300.0,
        "options": {"queue": "market_data"},
    },
    # Nightly instrument master sync after market close (IST ~22:30).
    "sync-instrument-master": {
        "task": "apps.market_data.infrastructure.tasks.sync_instrument_master",
        "schedule": "crontab(hour=22, minute=30)",
        "options": {"queue": "maintenance"},
    },
    # Event bus poller — reads mirrored domain events back off Redis Streams
    # and dispatches them to registered handlers. Scheduled every 2s, well
    # inside its 10s soft_time_limit, so delivery latency stays sub-second.
    "poll-event-streams": {
        "task": "apps.eventbus.infrastructure.tasks.poll_event_streams",
        "schedule": 2.0,
        "options": {"queue": "maintenance"},
    },
    # Safety net — re-mirrors StoredEvent rows that never made it into Redis
    # (mirrored_to_stream=False and older than 30s). Runs every 30s, matching
    # the 30s soft_time_limit of replay_unpublished_events.
    "replay-unpublished-events": {
        "task": "apps.eventbus.infrastructure.tasks.replay_unpublished_events",
        "schedule": 30.0,
        "options": {"queue": "maintenance"},
    },
    # EVENTBUS-RELIABILITY-1 — reclaims stream entries left pending in a
    # consumer group's Pending Entries List by a crashed/killed worker and
    # re-dispatches them (idempotent); dead-letters entries at MAX_RETRIES.
    # Runs every 30s, well inside the 60s time_limit of the reclaim task.
    "reclaim-stale-pending-events": {
        "task": "apps.eventbus.infrastructure.tasks.reclaim_stale_pending_events",
        "schedule": 30.0,
        "options": {"queue": "maintenance"},
    },
    # PIPELINE-HEALTH-1 — evaluates forward-pipeline health every 30s during
    # market hours and publishes pipeline_health.StageStalled only on a
    # HEALTHY->STALLED transition. No-ops outside market hours.
    "evaluate-pipeline-health": {
        "task": "apps.pipeline_health.infrastructure.tasks.evaluate_pipeline_health",
        "schedule": 30.0,
        "options": {"queue": "maintenance"},
    },
    # RISK-SOPHISTICATION-2 — auto-activates the ACCOUNT kill switch when a
    # realized daily/weekly loss breaches its configured share of capital.
    # No-ops when no threshold is configured or the ACCOUNT scope is already
    # active (idempotent — never spams the audit log).
    "evaluate-drawdown-kill-switch": {
        "task": "apps.risk_management.infrastructure.tasks.evaluate_drawdown_kill_switch",
        "schedule": 60.0,
        "options": {"queue": "maintenance"},
    },
    # PORTFOLIO-RECONCILE-1 — fan-out that runs a position + order
    # reconciliation pass for every account every 5 minutes, detecting and
    # repairing drift in the dashboard read model. Supersedes the old
    # dashboard reconcile_* count-only tasks (now deprecated).
    "reconcile-all-accounts": {
        "task": "apps.portfolio_reconciliation.infrastructure.tasks.reconcile_all_accounts",
        "schedule": RECONCILIATION_BEAT_INTERVAL_SECONDS,
        "options": {"queue": "maintenance"},
    },
    # MACRO-CONTEXT-1 — daily FRED/ALFRED vintage ingestion. Runs after US
    # morning releases (~14:00 UTC / 19:30 IST); idempotent on re-run.
    "ingest-macro-series": {
        "task": "apps.macro_context.infrastructure.tasks.ingest_macro_series",
        "schedule": crontab(hour=14, minute=5),
        "options": {"queue": "maintenance"},
    },
    # NEWS-FEED-1 — polls the licensed news provider (Marketaux) for the
    # configured NEWS_POLL_SYMBOLS every NEWS_POLL_INTERVAL_SECONDS (default
    # 15 min). Dedup on (source, url) makes re-runs idempotent; the daily
    # provider budget is enforced in the service, so an exhausted budget is a
    # logged skip, never an error.
    "ingest-news": {
        "task": "apps.news_feed.infrastructure.tasks.ingest_news",
        "schedule": NEWS_POLL_INTERVAL_SECONDS,
        "options": {"queue": "maintenance"},
    },
    # RISK-SOPHISTICATION-4 — daily calibration-drift pass: compares each rule's
    # live paper-trading win rate against its backtested expectation over a
    # rolling window and flags significant divergence. No-ops on no data.
    "evaluate-calibration-drift": {
        "task": "apps.trader_memory.infrastructure.tasks.evaluate_calibration_drift",
        "schedule": crontab(hour=10, minute=30),
        "options": {"queue": "analytics"},
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "correlation_id": {
            "()": "apps.common.infrastructure.logging_context.CorrelationIdFilter",
        },
    },
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "fmt": "%(asctime)s %(name)s %(levelname)s %(message)s %(correlation_id)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["correlation_id"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("LOG_LEVEL", "INFO"),
    },
}

FIELD_ENCRYPTION_KEY = os.environ.get("FIELD_ENCRYPTION_KEY", "")

EVENT_BUS_IMPLEMENTATION = os.environ.get("EVENT_BUS_IMPLEMENTATION", "redis")
# ---------------------------------------------------------------------------
# Market calendar
# ---------------------------------------------------------------------------
MARKET_TIMEZONE: str = config("MARKET_TIMEZONE", default="Asia/Kolkata")
MARKET_EXCHANGE: str = config("MARKET_EXCHANGE", default="NSE")

# ---------------------------------------------------------------------------
# Data quality thresholds (seconds)
# ---------------------------------------------------------------------------
TICK_FRESHNESS_THRESHOLD_SECONDS: int = config(
    "TICK_FRESHNESS_THRESHOLD_SECONDS", default=120, cast=int
)
INDICATOR_FRESHNESS_THRESHOLD_SECONDS: int = config(
    "INDICATOR_FRESHNESS_THRESHOLD_SECONDS", default=300, cast=int
)
INTELLIGENCE_MIN_QUALITY_SCORE: float = config(
    "INTELLIGENCE_MIN_QUALITY_SCORE", default=0.60, cast=float
)

# ---------------------------------------------------------------------------
# AI governance
# ---------------------------------------------------------------------------
AI_PROVIDER: str = config("AI_PROVIDER", default="gemini")
AI_CONFIDENCE_FLOOR: float = config("AI_CONFIDENCE_FLOOR", default=0.55, cast=float)
AI_DAILY_BUDGET_USD: float = config("AI_DAILY_BUDGET_USD", default=10.00, cast=float)
AI_DEDUP_WINDOW_SECONDS: int = config("AI_DEDUP_WINDOW_SECONDS", default=300, cast=int)
AI_MAX_TOKENS: int = config("AI_MAX_TOKENS", default=4096, cast=int)
AI_PROVIDER_PRIORITY: str = config(
    "AI_PROVIDER_PRIORITY", default="claude,gemini,openai,deepseek,ollama"
)
AI_PROVIDER_DISABLED: str = config("AI_PROVIDER_DISABLED", default="")
AI_ROUTING_FAST_TIER_THRESHOLD_MS: int = config(
    "AI_ROUTING_FAST_TIER_THRESHOLD_MS", default=1500, cast=int
)

GEMINI_API_KEY: str = config("GEMINI_API_KEY", default="")
GEMINI_MODEL: str = config("GEMINI_MODEL", default="gemini-1.5-pro")

OPENAI_API_KEY: str = config("OPENAI_API_KEY", default="")
OPENAI_MODEL: str = config("OPENAI_MODEL", default="gpt-4o")

ANTHROPIC_API_KEY: str = config("ANTHROPIC_API_KEY", default="")
ANTHROPIC_MODEL: str = config("ANTHROPIC_MODEL", default="claude-3-5-sonnet-20241022")

OLLAMA_BASE_URL: str = config("OLLAMA_BASE_URL", default="http://localhost:11434")
OLLAMA_MODEL: str = config("OLLAMA_MODEL", default="llama3.2")

DEEPSEEK_API_KEY: str = config("DEEPSEEK_API_KEY", default="")
DEEPSEEK_MODEL: str = config("DEEPSEEK_MODEL", default="deepseek-chat")
DEEPSEEK_BASE_URL: str = config("DEEPSEEK_BASE_URL", default="https://api.deepseek.com")

# ---------------------------------------------------------------------------
# Zerodha Kite Connect — short-lived access token obtained out-of-band via
# the Kite login flow (request_token → generate_session exchange). This batch
# does not implement that flow; the token must be provisioned by an operator.
# ---------------------------------------------------------------------------
ZERODHA_API_KEY: str = config("ZERODHA_API_KEY", default="")
ZERODHA_ACCESS_TOKEN: str = config("ZERODHA_ACCESS_TOKEN", default="")

# ---------------------------------------------------------------------------
# Broker execution — LIVE-BROKER-EXECUTION-1 (Phase 1 of 3: sandbox only).
#
# BROKER_ADAPTER selects the execution broker behind the settings-driven
# factory in apps.execution.infrastructure.brokers (paper | zerodha).
# BROKER_ENVIRONMENT is validated at Django startup (apps.execution.checks):
# Phase 1 ONLY supports `sandbox`; a `live` value fails startup until the
# Phase 2 explicit unlock exists (see docs/adr/ADR-030-*.md). The zerodha
# adapter falls back to the shared Kite sandbox demo app when the API
# key/secret are empty in sandbox mode — no real money is ever at risk.
# ---------------------------------------------------------------------------
BROKER_ADAPTER: str = config("BROKER_ADAPTER", default="paper")
BROKER_ENVIRONMENT: str = config("BROKER_ENVIRONMENT", default="sandbox")
ZERODHA_API_SECRET: str = config("ZERODHA_API_SECRET", default="")
ZERODHA_REQUEST_TOKEN: str = config("ZERODHA_REQUEST_TOKEN", default="")
ZERODHA_PRODUCT: str = config("ZERODHA_PRODUCT", default="MIS")

# ---------------------------------------------------------------------------
# Algo-registration gate (Risk Sophistication batch)
#
# ALGO_REGISTRATION_ID records the SEBI algotrading registration under which
# the operator is authorised to run algorithmic trading. It is EMPTY by
# default. Live (non-sandbox, non-paper) execution is refused whenever it is
# unset — this batch does not implement SEBI registration itself; it only
# makes live trading structurally impossible without an explicit, recorded
# decision (execution.E003 + the broker-adapter guard).
# ---------------------------------------------------------------------------
ALGO_REGISTRATION_ID: str = config("ALGO_REGISTRATION_ID", default="")

# ---------------------------------------------------------------------------
# Batch B kill switches — all default False until verified
# ---------------------------------------------------------------------------
STRATEGY_REGISTRY_ENABLED: bool = config("STRATEGY_REGISTRY_ENABLED", default=False, cast=bool)
PROMPT_VERSIONING_PERSISTENCE_ENABLED: bool = config(
    "PROMPT_VERSIONING_PERSISTENCE_ENABLED", default=False, cast=bool
)
CONFIDENCE_ENGINE_V2_ENABLED: bool = config("CONFIDENCE_ENGINE_V2_ENABLED", default=False, cast=bool)
EXECUTION_ENGINE_ENABLED: bool = config(
    "EXECUTION_ENGINE_ENABLED", default=False, cast=bool
)
# Below this historical recommendation accuracy the numeric pattern feed applies a
# percentage penalty to adjusted_confidence (mirrors the data-quality penalty block).
CONFIDENCE_ENGINE_PATTERN_ACCURACY_FLOOR: float = config(
    "CONFIDENCE_ENGINE_PATTERN_ACCURACY_FLOOR", default=0.50, cast=float
)
MODEL_ROUTER_PREFERRED_PROVIDER_ENABLED: bool = config(
    "MODEL_ROUTER_PREFERRED_PROVIDER_ENABLED", default=False, cast=bool
)
MARKET_CONTEXT_SCORING_ENABLED: bool = config(
    "MARKET_CONTEXT_SCORING_ENABLED", default=False, cast=bool
)
MARKET_CONTEXT_CACHE_TTL_SECONDS: int = config(
    "MARKET_CONTEXT_CACHE_TTL_SECONDS", default=900, cast=int
)

# ---------------------------------------------------------------------------
# MACRO-CONTEXT-1 — FRED/ALFRED point-in-time macro provider
# ---------------------------------------------------------------------------
# FRED API key (https://fred.stlouisfed.org/docs/api/api_key.html).
FRED_API_KEY: str = os.environ.get("FRED_API_KEY", "")
# Per-request HTTP timeout for FRED observations fetches (seconds).
FRED_REQUEST_TIMEOUT_SECONDS: int = int(
    os.environ.get("FRED_REQUEST_TIMEOUT_SECONDS", "20")
)
# Earliest vintage window for the daily backfill fetch (YYYY-MM-DD). FRED
# revision history is fetched wholesale from here on every run; the
# append-only store makes re-runs idempotent.
MACRO_BACKFILL_START_DATE: str = os.environ.get(
    "MACRO_BACKFILL_START_DATE", "1990-01-01"
)
# Kill switch for the daily ingestion task (off disables only the task).
MACRO_INGESTION_ENABLED: bool = config(
    "MACRO_INGESTION_ENABLED", default=True, cast=bool
)

# ---------------------------------------------------------------------------
# NEWS-FEED-1 — licensed news provider (Marketaux)
# ---------------------------------------------------------------------------
# Active provider implementation: "marketaux" (live API) or "fake" (canned
# headlines for tests/dev without an API key).
NEWS_PROVIDER: str = config("NEWS_PROVIDER", default="marketaux")
# Marketaux API key (https://www.marketaux.com). Free tier: 100 requests/day,
# ~3 articles per request.
NEWS_API_KEY: str = os.environ.get("NEWS_API_KEY", "")
# Marketaux API base URL (versioned root, without the endpoint path).
NEWS_API_BASE_URL: str = config(
    "NEWS_API_BASE_URL", default="https://api.marketaux.com/v1"
)
# Per-request HTTP timeout for news fetches (seconds).
NEWS_REQUEST_TIMEOUT_SECONDS: int = config(
    "NEWS_REQUEST_TIMEOUT_SECONDS", default=20, cast=int
)
# Kill switch for the periodic ingestion task (off disables only the task).
NEWS_INGESTION_ENABLED: bool = config(
    "NEWS_INGESTION_ENABLED", default=True, cast=bool
)
# Comma-separated symbols polled by the ingestion task (e.g. "RELIANCE,TCS").
NEWS_POLL_SYMBOLS: str = config("NEWS_POLL_SYMBOLS", default="")
# Articles requested per provider call (Marketaux free tier returns ≤3).
# Articles requested per provider call (Marketaux free tier returns ≤3).
NEWS_ARTICLES_PER_REQUEST: int = config(
    "NEWS_ARTICLES_PER_REQUEST", default=3, cast=int
)
# Rolling window (minutes) for which news is fetched/considered fresh. Also the
# IntelligencePacket NewsContext lookback window.
NEWS_LOOKBACK_MINUTES: int = config(
    "NEWS_LOOKBACK_MINUTES", default=1440, cast=int
)
# Hard daily provider call budget (Marketaux free tier = 100). Enforced by the
# ingestion service BEFORE any fetch; exhaustion is a logged skip, not an error.
NEWS_RATE_LIMIT_CALLS_PER_DAY: int = config(
    "NEWS_RATE_LIMIT_CALLS_PER_DAY", default=100, cast=int
)
# Max headlines surfaced into an IntelligencePacket NewsContext per symbol.
NEWS_MAX_HEADLINES: int = config("NEWS_MAX_HEADLINES", default=5, cast=int)
# Kill switch for the IntelligencePacket news-context lookup. Off → the packet
# carries the unchecked NewsContext() default and keeps missing:["news"]
# ("never checked", ADR-029 §5).
NEWS_CONTEXT_LOOKUP_ENABLED: bool = config(
    "NEWS_CONTEXT_LOOKUP_ENABLED", default=True, cast=bool
)

# ---------------------------------------------------------------------------
# Batch AI-5 — Pattern Engine
# ---------------------------------------------------------------------------
# Kill switch — the Pattern Engine ships dark until explicitly enabled.
PATTERN_ENGINE_ENABLED: bool = config(
    "PATTERN_ENGINE_ENABLED", default=False, cast=bool
)
# Number of most-similar historical sessions to retain (ADR-007 §5.2).
PATTERN_ENGINE_TOP_N: int = config(
    "PATTERN_ENGINE_TOP_N", default=5, cast=int
)
# Minimum weighted similarity for a historical session to be retained.
PATTERN_ENGINE_MIN_SIMILARITY: Decimal = Decimal(
    config("PATTERN_ENGINE_MIN_SIMILARITY", default="0.60")
)
# Maximum number of precomputed historical feature vectors loaded per symbol.
PATTERN_ENGINE_HISTORY_LIMIT: int = config(
    "PATTERN_ENGINE_HISTORY_LIMIT", default=500, cast=int
)
# Optional, read-only Trader Memory enrichment for historical recommendation
# accuracy. Defaults to False — accuracy is enrichment, never a hard dependency.
PATTERN_ENGINE_ACCURACY_LOOKUP_ENABLED: bool = config(
    "PATTERN_ENGINE_ACCURACY_LOOKUP_ENABLED", default=False, cast=bool
)

# ---------------------------------------------------------------------------
# Circuit breaker defaults
# ---------------------------------------------------------------------------
CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = config(
    "CIRCUIT_BREAKER_FAILURE_THRESHOLD", default=5, cast=int
)
CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = config(
    "CIRCUIT_BREAKER_RECOVERY_TIMEOUT", default=60, cast=int
)

# ---------------------------------------------------------------------------
# Redis direct URL — for use outside the Django cache framework
# ---------------------------------------------------------------------------
REDIS_URL: str = config("REDIS_URL", default="redis://redis:6379/0")
REDIS_MAX_CONNECTIONS: int = config("REDIS_MAX_CONNECTIONS", default=50, cast=int)

# ---------------------------------------------------------------------------
# EventBus — Redis Streams (AnalysisEvent transport)
# ---------------------------------------------------------------------------
EVENT_STREAM_MAXLEN: int = config("EVENT_STREAM_MAXLEN", default=10000, cast=int)
EVENT_STREAM_CONSUMER_GROUP_PREFIX: str = config(
    "EVENT_STREAM_CONSUMER_GROUP_PREFIX", default="tradevision"
)

# ---------------------------------------------------------------------------
# Market data provider
# ---------------------------------------------------------------------------
MARKET_DATA_PROVIDER: str = config("MARKET_DATA_PROVIDER", default="mock")

# ---------------------------------------------------------------------------
# M3 — Deterministic Risk Management
# ---------------------------------------------------------------------------
# Stub capital source (ADR-027): config-driven, non-production. Every read is
# logged as a WARNING and every persisted RiskDecision records
# portfolio_gateway_impl="stub". Never used to back a real order.
RISK_MANAGEMENT: dict = {
    "risk_pct": Decimal("0.01"),
    "max_position_size": 1_000_000,
    "max_exposure_cap": Decimal("1000000"),
    "daily_loss_limit": Decimal("100000"),
    "min_risk_reward": Decimal("1.0"),
    "kill_switch_active": False,
    "tradable_symbols": [],
    "max_freshness_seconds": 600,
    "market_hours_only": True,
    "available_capital": Decimal("1000000"),
    "current_exposure": Decimal("0"),
    "daily_loss": Decimal("0"),
    "instrument_max_qty": None,
    # Risk Sophistication batch: portfolio-level concentration governance.
    # Defaults are None (disabled) — a sector/correlation data source does not
    # exist yet, and the concentration check fails CLOSED on missing data, so
    # enabling these without sector data rejects every order by design.
    "max_sector_exposure_pct": None,
    "correlated_trigger_max_multiple": None,
    "sector_by_symbol": {},
    "portfolio_positions": [],
    # Risk Sophistication batch: automatic drawdown circuit breaker. Thresholds
    # are None (disabled) by default; when set, a realized daily/weekly loss
    # breaching the share of capital auto-activates the ACCOUNT kill switch.
    "max_daily_loss_pct": None,
    "max_weekly_loss_pct": None,
    "weekly_loss": Decimal("0"),
}
# Short-TTL for the kill-switch read-through cache (fail-closed on error).
RISK_KILL_SWITCH_CACHE_TTL_SECONDS: int = config(
    "RISK_KILL_SWITCH_CACHE_TTL_SECONDS", default=10, cast=int
)

# ---------------------------------------------------------------------------
# Execution-cost realism (Risk Sophistication batch)
#
# "flat" keeps the historical commission_rate + flat slippage_bps model
# untouched (the default, so no backtest numbers change). "nse" switches
# BacktestStatsService to the realistic NSE cost model — STT, brokerage,
# exchange transaction charges, GST, SEBI turnover fee, stamp duty and a
# size-dependent impact cost — parameterised by BACKTEST_NSE_COST_MODEL.
# ---------------------------------------------------------------------------
BACKTEST_COST_MODEL: str = config("BACKTEST_COST_MODEL", default="flat")
BACKTEST_NSE_COST_MODEL: dict = {
    "product": "delivery",
    "brokerage_per_order": Decimal("20"),
    "impact_base_bps": Decimal("5"),
    "impact_reference_adv": Decimal("1000000"),
    "impact_max_multiple": Decimal("5"),
}

# ---------------------------------------------------------------------------
# Calibration-drift monitoring (Risk Sophistication batch)
#
# The Celery beat evaluates each rule's live paper-trading win rate over a
# rolling window against its backtested expected win rate and flags a
# statistically significant divergence. Below CALIBRATION_DRIFT_MIN_TRADES no
# verdict is produced; CALIBRATION_DRIFT_ALPHA is the two-sided test level.
# ---------------------------------------------------------------------------
CALIBRATION_DRIFT_WINDOW_DAYS: int = config(
    "CALIBRATION_DRIFT_WINDOW_DAYS", default=30, cast=int
)
CALIBRATION_DRIFT_MIN_TRADES: int = config(
    "CALIBRATION_DRIFT_MIN_TRADES", default=30, cast=int
)
CALIBRATION_DRIFT_ALPHA: float = config(
    "CALIBRATION_DRIFT_ALPHA", default=0.05, cast=float
)

# M4 — gateway implementation feeding Risk Management's capital/exposure reads.
# "portfolio" → RealCapitalGateway / RealPortfolioStateGateway backed by
# apps.portfolio (the production source of truth, ADR-028 §2.9); "stub" →
# the M3 config-driven StubPortfolioStateGateway (guarded dev/fallback).
# The production default is the real gateway so the stub is never the
# production capital source (ADR-028 DoD #7). The factory keeps its own
# "stub" fallback for safety if the setting is ever absent.
RISK_MANAGEMENT_GATEWAY_IMPL: str = config(
    "RISK_MANAGEMENT_GATEWAY_IMPL", default="portfolio", cast=str
)
