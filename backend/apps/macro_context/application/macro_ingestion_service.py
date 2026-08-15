"""MACRO-CONTEXT-1 — macro ingestion service.

Fetches the full point-in-time vintage history of every supported series
from the configured provider and persists it append-only. Re-runs are
idempotent: the (provider, series_id, observed_at, published_at) uniqueness
constraint makes a repeated fetch a no-op for already-stored vintages.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

from apps.macro_context.application.ports import (
    MacroDataProvider,
    MacroObservationRepository,
)
from apps.macro_context.domain.value_objects import SUPPORTED_SERIES
from core.config import config
from core.metrics import (
    MACRO_INGESTION_ERRORS_TOTAL,
    MACRO_INGESTION_OBSERVATIONS_TOTAL,
    MACRO_PROVIDER_LATENCY_SECONDS,
)

logger = logging.getLogger(__name__)

# FRED's realtime_end sentinel for "all vintages ever".
_REALTIME_END_SENTINEL = date(9999, 12, 31)


class MacroIngestionService:
    """Orchestrate provider fetch -> append-only persistence per series."""

    def __init__(
        self,
        provider: MacroDataProvider,
        repository: MacroObservationRepository,
        *,
        realtime_start: date,
        realtime_end: date = _REALTIME_END_SENTINEL,
    ) -> None:
        self._provider = provider
        self._repository = repository
        self._realtime_start = realtime_start
        self._realtime_end = realtime_end

    def run(self) -> dict[str, Any]:
        """Ingest every supported series. Returns a per-series summary.

        A failure on one series is isolated (logged + counted) so one bad
        provider response never blocks the other series.
        """
        summary: dict[str, Any] = {"fetched": 0, "inserted": 0, "errors": []}
        for series_id in SUPPORTED_SERIES:
            outcome = self._ingest_series(series_id)
            summary["fetched"] += outcome["fetched"]
            summary["inserted"] += outcome["inserted"]
            if outcome["error"] is not None:
                summary["errors"].append(
                    {"series_id": series_id, "error": outcome["error"]}
                )

        logger.info(
            "macro_ingestion_run_complete",
            extra={
                "provider": self._provider.provider_name,
                "fetched": summary["fetched"],
                "inserted": summary["inserted"],
                "errors": len(summary["errors"]),
            },
        )
        return summary

    def _ingest_series(self, series_id: str) -> dict[str, Any]:
        started = time.monotonic()
        try:
            observations = self._provider.fetch_observations(
                series_id,
                realtime_start=self._realtime_start,
                realtime_end=self._realtime_end,
            )
            inserted = self._repository.upsert_many(observations)
            latency = round(time.monotonic() - started, 4)
            MACRO_PROVIDER_LATENCY_SECONDS.labels(series_id=series_id).observe(latency)
            MACRO_INGESTION_OBSERVATIONS_TOTAL.labels(series_id=series_id).inc(
                inserted
            )
            return {"fetched": len(observations), "inserted": inserted, "error": None}
        except Exception as exc:
            error_type = type(exc).__name__
            MACRO_INGESTION_ERRORS_TOTAL.labels(
                series_id=series_id,
                error_type=error_type,
            ).inc()
            logger.exception(
                "macro_ingestion_series_failed",
                extra={"series_id": series_id, "error_type": error_type},
            )
            return {
                "fetched": 0,
                "inserted": 0,
                "error": f"{error_type}: {exc}",
            }


def get_ingestion_service() -> MacroIngestionService:
    """Return the default service wired to the FRED provider and ORM store."""
    from apps.macro_context.infrastructure.providers.fred_provider import (
        FredMacroProvider,
    )
    from apps.macro_context.infrastructure.repositories import (
        MacroObservationRepository,
    )

    return MacroIngestionService(
        provider=FredMacroProvider(),
        repository=MacroObservationRepository(),
        realtime_start=config.macro_backfill_start,
    )
