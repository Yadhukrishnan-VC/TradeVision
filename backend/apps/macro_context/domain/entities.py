"""MACRO-CONTEXT-1 — pure domain entities.

``ProvenancedObservation`` is the unit of point-in-time data: it pairs a
value with the exact moment it became public (``published_at``). Nothing in
this module touches Django ORM models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class ProvenancedObservation:
    """A single macro value plus its provenance (vintage) metadata.

    - ``observed_at``: the period the value describes (FRED ``date``).
    - ``published_at``: the moment this specific value became public
      (FRED ``realtime_start``) — the point-in-time cut-off key.
    - ``value``: ``None`` means the value was known to be missing at
      publish time (FRED ``"."``), never ``Decimal("0")``.

    A series has one row per (observed_at, published_at) pair — each FRED
    revision is a separate vintage row, never an UPDATE.
    """

    provider: str
    series_id: str
    observed_at: date
    published_at: datetime
    value: Decimal | None


@dataclass(frozen=True)
class MacroContext:
    """A point-in-time snapshot of the supported macro series.

    Built by ``MacroContextBuilder.build(as_of=...)``: every value is what
    was known at ``as_of``. ``series_count`` is the number of series with a
    known (non-``None``) value at that moment.
    """

    as_of: datetime
    dgs10: Decimal | None = None
    fedfunds: Decimal | None = None
    cpiaucsl: Decimal | None = None
    t10y2y: Decimal | None = None
    series_count: int = 0
