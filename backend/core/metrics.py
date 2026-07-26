"""
TradeVision AI — Prometheus metrics registry.

All metrics are defined as module-level constants so they are registered
once on first import. Importing this module multiple times is safe because
Python's module cache returns the same object.

Metric naming follows the Prometheus convention:
    tradevision_<subsystem>_<name>_<unit>

Access metrics in application code::

    from core.metrics import TICKS_INGESTED_TOTAL
    TICKS_INGESTED_TOTAL.labels(symbol="RELIANCE", interval="1min").inc()
"""

from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Market data ingestion
# ---------------------------------------------------------------------------

TICKS_INGESTED_TOTAL = Counter(
    "tradevision_ticks_ingested_total",
    "Total number of market data ticks ingested and stored",
    ["symbol", "interval"],
)

DATA_FEED_STALENESS_SECONDS = Gauge(
    "tradevision_data_feed_staleness_seconds",
    "Age in seconds of the latest tick for a symbol and source",
    ["symbol", "source"],
)

INGESTION_ERRORS_TOTAL = Counter(
    "tradevision_ingestion_errors_total",
    "Total number of errors during market data ingestion",
    ["symbol", "source", "error_type"],
)

# ---------------------------------------------------------------------------
# Rule engine
# ---------------------------------------------------------------------------

RULE_EVALUATIONS_TOTAL = Counter(
    "tradevision_rule_evaluations_total",
    "Total number of rule engine evaluations",
    ["rule_id", "outcome"],  # outcome: fired | no_fire | skipped_stale | error
)

RULE_FIRES_TOTAL = Counter(
    "tradevision_rule_fires_total",
    "Total number of times each rule has fired",
    ["rule_id", "symbol"],
)

# ---------------------------------------------------------------------------
# Market Intelligence Engine
# ---------------------------------------------------------------------------

INTELLIGENCE_PACKET_QUALITY = Histogram(
    "tradevision_intelligence_packet_quality",
    "Distribution of IntelligencePacket quality scores (0.0–1.0)",
    ["symbol"],
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

INTELLIGENCE_ASSEMBLY_DURATION_SECONDS = Histogram(
    "tradevision_intelligence_assembly_duration_seconds",
    "Time taken to assemble an IntelligencePacket",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

# ---------------------------------------------------------------------------
# AI orchestration
# ---------------------------------------------------------------------------

AI_CALLS_TOTAL = Counter(
    "tradevision_ai_calls_total",
    "Total number of AI provider API calls",
    ["provider", "event_type", "outcome"],  # outcome: success | validation_error | provider_error
)

AI_CALL_DURATION_SECONDS = Histogram(
    "tradevision_ai_call_duration_seconds",
    "AI provider call latency in seconds",
    ["provider"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

AI_COST_USD_TOTAL = Counter(
    "tradevision_ai_cost_usd_total",
    "Estimated cumulative AI provider cost in USD",
    ["provider"],
)

AI_CONFIDENCE_SCORES = Histogram(
    "tradevision_ai_confidence_scores",
    "Distribution of AI recommendation confidence scores",
    ["event_type"],
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

AI_SUPPRESSED_TOTAL = Counter(
    "tradevision_ai_suppressed_total",
    "Recommendations suppressed due to low confidence or budget exhaustion",
    ["reason"],  # reason: low_confidence | budget_exhausted | dedup_window
)

# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

RECOMMENDATIONS_CREATED_TOTAL = Counter(
    "tradevision_recommendations_created_total",
    "Total number of recommendations created",
    ["direction", "event_type"],  # direction: BUY | SELL | WATCH | AVOID
)

RECOMMENDATIONS_DELIVERED_TOTAL = Counter(
    "tradevision_recommendations_delivered_total",
    "Total number of recommendations delivered to at least one user",
    ["direction"],
)

# ---------------------------------------------------------------------------
# Celery task execution
# ---------------------------------------------------------------------------

CELERY_TASK_DURATION_SECONDS = Histogram(
    "tradevision_celery_task_duration_seconds",
    "Celery task execution time in seconds",
    ["task_name", "queue", "status"],  # status: success | failure | retry
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 30.0, 120.0),
)

CELERY_TASK_ERRORS_TOTAL = Counter(
    "tradevision_celery_task_errors_total",
    "Total number of Celery task failures",
    ["task_name", "queue", "exception_type"],
)

# ---------------------------------------------------------------------------
# Circuit breaker state
# ---------------------------------------------------------------------------

CIRCUIT_BREAKER_STATE = Gauge(
    "tradevision_circuit_breaker_state",
    "Current state of a circuit breaker (0=CLOSED, 1=OPEN, 2=HALF_OPEN)",
    ["service"],
)

CIRCUIT_BREAKER_TRIPS_TOTAL = Counter(
    "tradevision_circuit_breaker_trips_total",
    "Total number of times a circuit breaker has opened",
    ["service"],
)

# ---------------------------------------------------------------------------
# EventBus — Redis Streams
# ---------------------------------------------------------------------------

EVENT_STREAM_LENGTH = Gauge(
    "tradevision_event_stream_length",
    "Current number of entries in each EventBus stream",
    ["stream"],
)

EVENT_STREAM_PENDING_TOTAL = Gauge(
    "tradevision_event_stream_pending_total",
    "Number of pending (unacknowledged) messages in each consumer group",
    ["stream", "group"],
)

EVENT_PUBLISHED_TOTAL = Counter(
    "tradevision_event_published_total",
    "Total number of events published through the EventBus",
    ["stream", "event_type"],
)

EVENT_CONSUMED_TOTAL = Counter(
    "tradevision_event_consumed_total",
    "Total number of events consumed and acknowledged through the EventBus",
    ["stream", "group"],
)
