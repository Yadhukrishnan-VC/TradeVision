from __future__ import annotations

from core.exceptions import TradeVisionError


class PatternEngineError(TradeVisionError):
    """Base error for the Pattern Engine (Batch AI-5).

    Raised only for freshness/validation failures. The Pattern Engine never
    raises for missing optional data — it returns a result with empty matches
    (same discipline as ``IntelligenceService.build_packet()``).
    """


class InsufficientHistoryError(PatternEngineError):
    """Raised when the requested operation requires more historical data
    than is available (e.g. the nightly precompute has no candles to work
    with). Callers should degrade gracefully."""


class PatternAnalysisError(PatternEngineError):
    """Raised when a pattern analysis run fails at the persistence or
    publication stage after successful computation."""
