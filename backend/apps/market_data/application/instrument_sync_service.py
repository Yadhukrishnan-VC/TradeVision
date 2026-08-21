from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

from apps.common.domain.value_objects import Symbol
from apps.market_data.domain.entities import Instrument
from apps.market_data.infrastructure.models import Instrument as InstrumentModel
from apps.market_data.infrastructure.models import Candle as CandleModel
from apps.market_data.infrastructure.repositories import InstrumentRepository
from core.exceptions import DataProviderError
from core.market_data.provider_factory import MarketDataProviderFactory
from core.utils import get_now

logger = logging.getLogger(__name__)

#: Sentinel used to free a ``(exchange, tradingsymbol)`` unique slot while a
#: synthetic-token row is being replaced by the real token. Never visible to
#: callers after the transaction commits.
_MERGE_SENTINEL_SUFFIX = "__MERGE__"


class InstrumentSyncService:
    """Synchronise the local ``Instrument`` table with the broker's master list.

    Calls ``fetch_instruments()`` on the active market data provider (a new
    method on concrete providers) and upserts every entry. Instruments that
    exist locally but are absent from the provider's response are soft-marked
    as inactive (``is_active=False``).

    Identity reconciliation (REAL-DATA-BACKFILL-2): each upstream row is
    matched by ``(exchange, tradingsymbol)`` FIRST, falling back to token-only
    matching. This is what lets an instrument that was created with a
    *synthetic* token by ``import_historical_csv`` get its token REPLACED in
    place by the real Zerodha token on sync — instead of a duplicate row being
    created (a duplicate is impossible while the ``(exchange, tradingsymbol)``
    unique constraint holds, but the merge path still handles the pre-existing
    duplicate case defensively). Candle history is preserved across the token
    replacement by migrating ``market_data_candle.instrument_id`` rows.

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
            A summary dict with ``created``, ``updated``, ``deactivated``,
            and ``merged`` counts.

        Raises:
            DataProviderError: If the provider is unavailable or returns
                an unexpected response.
        """
        provider = MarketDataProviderFactory.get_provider()
        raw_instruments = self._fetch_instrument_list(provider)

        upstream_tokens: set[int] = set()
        created = 0
        updated = 0
        merged = 0

        for raw in raw_instruments:
            token = int(raw["instrument_token"])
            upstream_tokens.add(token)

            existing = self._find_matching(raw, token)
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
                continue

            if existing.instrument_token != token:
                # The upstream token differs from the locally-held token for the
                # same (exchange, tradingsymbol). Replace it in place, migrating
                # candle history, before applying field updates.
                self._reconcile_token_in_place(existing, token)
                merged += 1

            changed = self._has_changed(existing, raw, token)
            if changed:
                self._repo.update_from_dict(token, raw)
                updated += 1

        deactivated = self._deactivate_absent(upstream_tokens)

        logger.info(
            "instrument_sync_complete",
            extra={
                "created_count": created,
                "updated": updated,
                "merged": merged,
                "deactivated": deactivated,
            },
        )
        return {
            "created": created,
            "updated": updated,
            "deactivated": deactivated,
            "merged": merged,
        }

    # ------------------------------------------------------------------
    # Identity matching & token reconciliation
    # ------------------------------------------------------------------

    def _find_matching(self, raw: dict[str, Any], token: int) -> Instrument | None:
        """Locate the local row that represents *raw*.

        Primary identity is ``(exchange, tradingsymbol)`` (the natural key the
        rest of the app uses for symbol lookups and the same key
        ``import_historical_csv`` uses when creating synthetic-token rows).
        Only when no symbol match exists do we fall back to token-only
        matching, so a provider token change on an otherwise unchanged symbol
        is still recognised.
        """
        exchange = str(raw.get("exchange", "")).upper()
        tradingsymbol = str(raw.get("tradingsymbol", "")).strip()
        if exchange and tradingsymbol:
            by_symbol = self._repo.find_by_symbol(
                Symbol(exchange=exchange, tradingsymbol=tradingsymbol)
            )
            if by_symbol is not None:
                return by_symbol
        return self._repo.find_by_token(token)

    def _reconcile_token_in_place(
        self, existing: Instrument, real_token: int
    ) -> None:
        """Replace ``existing``'s synthetic token with the real token.

        ``Candle.instrument`` is the only FK to ``Instrument``, and Postgres
        FK ``NO ACTION`` blocks a plain PK update while referencing rows exist,
        so the replacement is done as a safe create-then-migrate-then-delete
        merge inside one transaction:

        1. Move the symbol-matched row off its ``(exchange, tradingsymbol)``
           unique slot (sentinel) so the real-token row can be created.
        2. Create the real-token row (or reuse one already present).
        3. Migrate the candle history onto the real token (deduplicated).
        4. Delete the now-empty synthetic row.

        Any row already holding the real token is merged into, never created
        twice. On failure the whole operation rolls back leaving the synthetic
        row and its candles intact.
        """
        synth_token = existing.instrument_token
        exchange = existing.exchange
        tradingsymbol = existing.tradingsymbol

        with transaction.atomic():
            already = self._repo.find_by_token(real_token)

            if already is None:
                # Free the unique slot, then create the real-token row.
                InstrumentModel.objects.filter(pk=synth_token).update(
                    tradingsymbol=f"{tradingsymbol}_{_MERGE_SENTINEL_SUFFIX}_{synth_token}"
                )
                self._repo.save(Instrument(
                    instrument_token=real_token,
                    exchange=exchange,
                    tradingsymbol=tradingsymbol,
                    name=existing.name,
                    segment=existing.segment,
                    lot_size=existing.lot_size,
                    tick_size=existing.tick_size,
                    instrument_type=existing.instrument_type,
                    expiry=existing.expiry,
                    is_active=True,
                ))

            # Migrate candles onto the real token, deduplicating on
            # (instrument, timeframe, timestamp) via upsert semantics.
            self._migrate_candles(synth_token, real_token)

            # Drop the now-empty synthetic row.
            InstrumentModel.objects.filter(pk=synth_token).delete()

        logger.info(
            "instrument_token_reconciled_in_place",
            extra={
                "exchange": exchange,
                "tradingsymbol": tradingsymbol,
                "synthetic_token": synth_token,
                "real_token": real_token,
            },
        )

    def _migrate_candles(self, from_token: int, to_token: int) -> None:
        """Move ``market_data_candle`` rows from *from_token* to *to_token*.

        Uses update-or-create semantics so a candle that already exists under
        the target token for the same ``(timeframe, timestamp)`` is updated in
        place rather than violating the unique constraint.
        """
        rows = list(
            CandleModel.objects.filter(instrument_id=from_token)
            .values_list("timeframe", "timestamp", "open", "high", "low", "close", "volume")
        )
        for timeframe, timestamp, open_, high, low, close, volume in rows:
            CandleModel.objects.update_or_create(
                instrument_id=to_token,
                timeframe=timeframe,
                timestamp=timestamp,
                defaults={
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                },
            )

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

    def _has_changed(self, existing: Instrument, raw: dict[str, Any], token: int) -> bool:
        """Return ``True`` if the raw data differs meaningfully from the
        persisted entity. ``existing`` reflects the pre-merge state, so the
        current token is compared directly.
        """
        if existing.instrument_token != token:
            return True
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