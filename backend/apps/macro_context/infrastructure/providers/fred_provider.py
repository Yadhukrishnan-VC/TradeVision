"""MACRO-CONTEXT-1 — FRED / ALFRED macro data provider.

Fetches the full point-in-time (vintage) history of a FRED series via the
official ``fred/series/observations`` endpoint.

Vintage mechanics (verified against the FRED API reference):

- Every observation row is ``{realtime_start, realtime_end, date, value}``.
- ``date`` is the period the value describes (``observed_at``).
- ``realtime_start`` is the moment that specific value became public
  (``published_at``) — the point-in-time cut-off key.
- Querying with a far-past ``realtime_start`` returns every revision of
  every period: the complete ALFRED vintage matrix.
- ``value`` is a *string*; ``"."`` means the value was known-missing at
  publish time. It is mapped to ``None`` — never ``Decimal("0")``.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

from apps.macro_context.domain.entities import ProvenancedObservation
from apps.macro_context.domain.exceptions import MacroProviderError
from core.config import config

logger = logging.getLogger(__name__)

_FRED_API_BASE = "https://api.stlouisfed.org/fred"
_OBSERVATIONS_ENDPOINT = "/series/observations"
_MISSING_SENTINEL = "."


class FredMacroProvider:
    """Fetch FRED/ALFRED observations with full vintage provenance."""

    provider_name = "fred"

    def fetch_observations(
        self,
        series_id: str,
        *,
        realtime_start: date,
        realtime_end: date,
    ) -> list[ProvenancedObservation]:
        api_key = config.fred_api_key
        if not api_key:
            raise MacroProviderError(
                "FRED_API_KEY is not configured; cannot fetch macro series."
            )

        started = time.monotonic()
        url = f"{_FRED_API_BASE}{_OBSERVATIONS_ENDPOINT}"
        params = {
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "realtime_start": realtime_start.isoformat(),
            "realtime_end": realtime_end.isoformat(),
            "sort_order": "asc",
        }
        try:
            response = requests.get(
                url,
                params=params,
                timeout=config.fred_request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise MacroProviderError(
                f"FRED request failed for {series_id}: {exc}"
            ) from exc
        except ValueError as exc:
            raise MacroProviderError(
                f"FRED returned non-JSON response for {series_id}: {exc}"
            ) from exc

        observations = payload.get("observations", [])
        parsed = self._parse_observations(series_id, observations)
        logger.info(
            "fred_observations_fetched",
            extra={
                "series_id": series_id,
                "count": len(parsed),
                "latency_ms": round((time.monotonic() - started) * 1000, 2),
            },
        )
        return parsed

    def health_check(self) -> dict[str, Any]:
        """Report provider liveness; requires a configured API key."""
        if not config.fred_api_key:
            return {
                "status": "degraded",
                "provider": self.provider_name,
                "latency_ms": 0.0,
                "note": "FRED_API_KEY not configured.",
            }
        return {
            "status": "healthy",
            "provider": self.provider_name,
            "latency_ms": 0.0,
            "note": "FRED API key configured.",
        }

    @staticmethod
    def _parse_observations(
        series_id: str,
        observations: list[dict[str, Any]],
    ) -> list[ProvenancedObservation]:
        parsed: list[ProvenancedObservation] = []
        for row in observations:
            published_on = row.get("realtime_start") or row.get("realtime_end")
            try:
                observed_at = date.fromisoformat(row["date"])
                published_at = _as_utc_midnight(published_on)
                value = _parse_value(row.get("value"))
            except (KeyError, ValueError, InvalidOperation, TypeError) as exc:
                raise MacroProviderError(
                    f"Malformed FRED observation for {series_id}: {row!r}"
                ) from exc
            parsed.append(
                ProvenancedObservation(
                    provider="fred",
                    series_id=series_id,
                    observed_at=observed_at,
                    published_at=published_at,
                    value=value,
                )
            )
        return parsed


def _as_utc_midnight(iso_date: str | None) -> datetime:
    if iso_date is None:
        raise ValueError("observation missing realtime date")
    return datetime.combine(
        date.fromisoformat(iso_date),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )


def _parse_value(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if text == _MISSING_SENTINEL or text == "":
        return None
    return Decimal(text)
