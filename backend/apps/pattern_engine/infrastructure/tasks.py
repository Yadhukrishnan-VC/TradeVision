from __future__ import annotations

import logging
import uuid
from typing import Any

from celery import shared_task

from apps.pattern_engine.infrastructure.feature_vector_builder import (
    build_historical_feature_vector,
    compute_outcome,
)
from core.tasks.base import DEFAULT_MAX_RETRIES, DEFAULT_RETRY_DELAY, BaseTask

logger = logging.getLogger(__name__)


@shared_task(
    name="tradevision.pattern_engine.run_pattern_analysis",
    queue="analytics",
    bind=True,
    base=BaseTask,
    max_retries=DEFAULT_MAX_RETRIES,
    default_retry_delay=DEFAULT_RETRY_DELAY,
)
def run_pattern_analysis(
    self,
    symbol: str,
    packet_data: dict,
    as_of: str = "",
    correlation_id: str = "",
    causation_id: str = "",
) -> dict[str, Any]:
    """Rehydrate the packet, run deterministic similarity analysis, publish."""
    from apps.pattern_engine.application.pattern_analysis_service import (
        PatternAnalysisService,
    )
    from apps.pattern_engine.infrastructure.event_publisher import (
        publish_pattern_analysis_completed,
    )
    from apps.pattern_engine.infrastructure.packet_codec import deserialize_packet
    from apps.pattern_engine.infrastructure.repositories import (
        HistoricalFeatureVectorRepository,
        PatternAnalysisRunRepository,
    )

    try:
        packet = deserialize_packet(packet_data)
    except Exception as exc:
        logger.exception(
            "pe_packet_deserialize_failed",
            extra={"symbol": symbol, "error": str(exc)},
        )
        return {"status": "failed", "symbol": symbol, "stage": "deserialize"}

    service = PatternAnalysisService(
        vector_repository=HistoricalFeatureVectorRepository(),
        run_repository=PatternAnalysisRunRepository(),
    )

    try:
        result = service.analyze(
            packet,
            correlation_id=uuid.UUID(correlation_id)
            if correlation_id
            else uuid.uuid4(),
        )
    except Exception as exc:
        logger.exception(
            "pe_analysis_failed",
            extra={"symbol": symbol, "error": str(exc)},
        )
        raise

    publish_pattern_analysis_completed(
        result,
        correlation_id=uuid.UUID(correlation_id) if correlation_id else result.id,
        causation_id=uuid.UUID(causation_id) if causation_id else None,
    )
    return {
        "status": "completed",
        "symbol": symbol,
        "run_id": str(result.id),
        "match_count": len(result.matched_patterns),
    }


@shared_task(
    name="tradevision.pattern_engine.precompute_historical_vectors",
    queue="analytics",
    bind=True,
    base=BaseTask,
    max_retries=DEFAULT_MAX_RETRIES,
    default_retry_delay=DEFAULT_RETRY_DELAY,
)
def precompute_historical_vectors(
    self,
    symbols: list[str] | None = None,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Nightly precompute of historical feature vectors (ADR-007 §5.3).

    Vectors are computed from 1D candles plus any matching Technical Analysis
    snapshots, keyed by ``(symbol, as_of)`` and upserted idempotently.
    ``symbols`` defaults to all active NSE instruments in ``market_data``.
    """
    from apps.market_data.infrastructure.repositories import (
        CandleRepository,
        InstrumentRepository,
    )
    from apps.pattern_engine.infrastructure.repositories import (
        HistoricalFeatureVectorRepository,
    )
    from apps.technical_analysis.infrastructure.repositories import TASnapshotRepository

    repo = HistoricalFeatureVectorRepository()
    instrument_repo = InstrumentRepository()
    candle_repo = CandleRepository()
    ta_repo = TASnapshotRepository()

    if not symbols:
        symbols = _active_symbols(instrument_repo)

    processed = 0
    for symbol in symbols:
        try:
            processed += _precompute_symbol(
                repo=repo,
                symbol=symbol,
                candle_repo=candle_repo,
                ta_repo=ta_repo,
                instrument_repo=instrument_repo,
            )
        except Exception:
            logger.exception(
                "pe_precompute_symbol_failed",
                extra={"symbol": symbol},
            )
    return {
        "status": "completed",
        "symbols_processed": len(symbols),
        "vectors_processed": processed,
    }


def _active_symbols(instrument_repo) -> list[str]:
    try:
        from apps.market_data.infrastructure.models import Instrument

        qs = Instrument.objects.filter(is_active=True).values_list(
            "tradingsymbol", flat=True
        )
        return [str(s) for s in qs]
    except Exception:
        logger.exception("pe_active_symbols_failed")
        return []


def _precompute_symbol(
    *,
    repo,
    symbol: str,
    candle_repo,
    ta_repo,
    instrument_repo,
    max_sessions: int = 120,
) -> int:
    from datetime import timedelta, timezone

    from apps.common.domain.value_objects import Symbol
    from core.utils import get_now

    instrument = instrument_repo.find_by_symbol(
        Symbol(exchange="NSE", tradingsymbol=symbol.upper())
    )
    if instrument is None:
        return 0

    now = get_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    candles = candle_repo.find_range(
        instrument.instrument_token,
        "1D",
        now - timedelta(days=365),
        now + timedelta(days=1),
    )
    if len(candles) < 2:
        return 0

    # Skip the most recent session (no outcome yet).
    compute_sessions = candles[:-1]

    count = 0
    for session in compute_sessions[-max_sessions:]:
        vector = build_historical_feature_vector(
            symbol=symbol,
            as_of=session.timestamp,
            candle_repo=candle_repo,
            ta_repo=ta_repo,
            instrument_repo=instrument_repo,
        )
        if vector is None:
            continue
        outcome_pct, window_hours = compute_outcome(
            symbol=symbol,
            as_of=session.timestamp,
            candle_repo=candle_repo,
            instrument_repo=instrument_repo,
        )
        repo.save_vector(
            vector=vector,
            outcome_price_change_pct=outcome_pct,
            outcome_window_hours=window_hours,
        )
        count += 1
    return count


__all__ = ["precompute_historical_vectors", "run_pattern_analysis"]
