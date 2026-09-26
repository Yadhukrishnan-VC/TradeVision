from __future__ import annotations

import logging
import subprocess
import sys

from celery import shared_task

from core.events.event_types import EnrichedIntelligencePacket

logger = logging.getLogger(__name__)


@shared_task(
    name="tradevision.strategy_registry.match_packet",
    queue="ai_reasoning",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def match_packet(self, packet_data: dict) -> dict | None:
    from apps.strategy_registry.services import StrategyMatcher

    matcher = StrategyMatcher()
    try:
        packet = _deserialize_packet(packet_data)
    except Exception:
        logger.exception("failed_to_deserialize_intelligence_packet")
        return None

    if packet is None:
        return None

    strategy = matcher.match(packet)
    if strategy is None:
        logger.info(
            "packet_dropped_no_strategy_match",
            extra={"symbol": getattr(packet, "symbol", "unknown")},
        )
        return None

    return {
        "strategy_id": str(strategy.id),
        "strategy_name": strategy.name,
        "preferred_provider": strategy.preferred_provider,
        "confidence_threshold": float(strategy.confidence_threshold),
        "risk_threshold": float(strategy.risk_threshold),
        "packet_data": packet_data,
    }


def _deserialize_packet(data: dict) -> EnrichedIntelligencePacket | None:
    if not data:
        return None
    try:
        packet_dict = data.get("packet", data)
        from core.events.event_types import IntelligencePacket

        intel_packet = IntelligencePacket(**packet_dict)
        enriched = EnrichedIntelligencePacket(packet=intel_packet)
        return enriched
    except Exception:
        logger.exception("packet_deserialization_failed")
        return None


@shared_task(
    name="tradevision.strategy_registry.run_watchlist_per_symbol_backtests",
    queue="analytics",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=2,
    default_retry_delay=300,
    soft_time_limit=7200,
    time_limit=7500,
)
def run_watchlist_per_symbol_backtests(self, days: int = 730) -> dict:
    """Nightly per-symbol strategy backtests for every watchlist stock.

    Runs the ``per_symbol_backtests`` management command as a *separate
    process* on purpose: that command forces ``CELERY_TASK_ALWAYS_EAGER`` and
    ``BACKTEST_NO_REDIS_MIRROR`` for the duration of the run, which must never
    leak into a worker process (it would make every other task on that worker
    run eagerly). Existing runs resume from their snapshot cursors, so after
    the first full backfill each nightly tick is incremental; new watchlist
    symbols get their 6 strategy combos created automatically.
    """
    cmd = [sys.executable, "manage.py", "per_symbol_backtests", "--days", str(days)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=7000)
    except subprocess.TimeoutExpired:
        logger.warning("watchlist_backtests_timed_out", extra={"days": days})
        raise self.retry(exc=TimeoutError("per_symbol_backtests exceeded 7000s"))

    logger.info(
        "watchlist_backtests_done",
        extra={"days": days, "returncode": proc.returncode},
    )
    if proc.returncode != 0:
        logger.error(
            "watchlist_backtests_failed",
            extra={"days": days, "stderr_tail": proc.stderr[-2000:]},
        )
        return {"status": "ERROR", "returncode": proc.returncode}

    return {"status": "OK", "days": days, "returncode": 0}
