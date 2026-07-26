from __future__ import annotations

from apps.common.domain.exceptions import DomainError, NotFoundError


class UnknownInstrumentError(NotFoundError):
    """Raised when a requested symbol does not exist in the Instrument table.

    This is a V2 domain exception (subclass of ``NotFoundError``) used by
    ``MarketDataService`` and consumed by V2 callers. It is distinct from
    the V1 ``InstrumentNotFoundError`` in ``core.exceptions``.
    """


class StaleCandleDataError(DomainError):
    """Raised when the requested candle lookback requires older data than
    what is currently persisted.

    Callers should use ``HistoricalSyncService`` to backfill the missing
    candle range and retry.
    """


class UnsupportedTimeframeError(DomainError):
    """Raised when a requested timeframe is not supported by the provider
    or aggregation service.
    """
