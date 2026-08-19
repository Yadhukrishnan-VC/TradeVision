from __future__ import annotations

import logging
from typing import Any

from apps.market_data.domain.entities import Instrument
from apps.market_data.infrastructure.models import Instrument as InstrumentModel
from apps.market_data.infrastructure.repositories import InstrumentRepository
from core.exceptions import DataProviderError
from core.market_data.provider_factory import MarketDataProviderFactory
from core.utils import get_now

logger = logging.getLogger(__name__)


class InstrumentSyncService:
    """Synchronise the local ``Instrument`` table with the broker's master list.

    Calls ``fetch_instruments()`` on the active market data provider (a new
    method on concrete providers) and upserts every entry. Instruments that
    exist locally but are absent from the provider's response are soft-marked
    as inactive (``is_active=False``).

    Construct via ``get_instrument_sync_service()`` rather than directly.
    """

    def __init__(
        self,
        repository: InstrumentRepository | None = None,
    ) -> None:
        self._repo = repository or InstrumentRepository()

    def sync(self) -> dict[str, int]:
        """Run a full instrument master synchronisation.

        Returns:
            A summary dict with ``created``, ``updated``, and
            ``deactivated`` counts.

        Raises:
            DataProviderError: If the provider is unavailable or returns
                an unexpected response.
        """
        provider = MarketDataProviderFactory.get_provider()
        raw_instruments = self._fetch_instrument_list(provider)

        upstream_tokens: set[int] = set()
        created = 0
        updated = 0

        for raw in raw_instruments:
            token = raw["instrument_token"]
            upstream_tokens.add(token)

            existing = self._repo.find_by_token(token)
            if existing is None:
                self._repo.save(Instrument(
                    instrument_token=token,
                    exchange=raw.get("exchange", ""),
                    tradingsymbol=raw.get("tradingsymbol", ""),
                    name=raw.get("name", ""),
                    segment=raw.get("segment", ""),
                    lot_size=int(raw.get("lot_size", 1)),
                    tick_size=raw.get("tick_size", 1),
                    instrument_type=raw.get("instrument_type", ""),
                    expiry=raw.get("expiry"),
                    is_active=True,
                ))
                created += 1
            else:
                changed = self._has_changed(existing, raw)
                if changed:
                    self._repo.update_from_dict(token, raw)
                    updated += 1

        deactivated = self._deactivate_absent(upstream_tokens)

        logger.info(
            "instrument_sync_complete",
            extra={
                "created_count": created,
                "updated": updated,
                "deactivated": deactivated,
            },
        )
        return {"created": created, "updated": updated, "deactivated": deactivated}

    def _fetch_instrument_list(self, provider: Any) -> list[dict[str, Any]]:
        """Retrieve the instrument master from the provider.

        Uses ``fetch_instruments()`` if available on the concrete provider,
        otherwise falls back to a best-effort empty list.
        """
        fetcher = getattr(provider, "fetch_instruments", None)
        if fetcher is not None:
            return fetcher()
        logger.warning(
            "instrument_sync_provider_no_fetch_instruments",
            extra={"provider": getattr(provider, "provider_name", "unknown")},
        )
        return []

    def _has_changed(self, existing: Instrument, raw: dict[str, Any]) -> bool:
        """Return ``True`` if the raw data differs meaningfully from the
        persisted entity.
        """
        fields = ["tradingsymbol", "name", "segment", "lot_size", "tick_size", "instrument_type"]
        for field in fields:
            raw_val = raw.get(field)
            existing_val = getattr(existing, field, None)
            if str(raw_val) != str(existing_val) if raw_val is not None else existing_val is not None:
                return True
        return False

    def _deactivate_absent(self, active_tokens: set[int]) -> int:
        """Set ``is_active=False`` for instruments not in *active_tokens*."""
        return self._repo.deactivate_missing(active_tokens)


_service_instance: InstrumentSyncService | None = None


def get_instrument_sync_service() -> InstrumentSyncService:
    """Return a process-wide ``InstrumentSyncService`` singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = InstrumentSyncService()
    return _service_instance


def reset_instrument_sync_service() -> None:
    """Reset the singleton (primarily for testing)."""
    global _service_instance
    _service_instance = None
