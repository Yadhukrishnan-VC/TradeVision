"""MACRO-CONTEXT-1 — macro series taxonomy.

The four series are the fixed, vetted set for the macro context dimension.
Only these series may ever be ingested; any other FRED series would require
an explicit batch scope change.
"""

from __future__ import annotations

from enum import Enum


class MacroSeries(str, Enum):
    """The supported macro series (all FRED series IDs)."""

    DGS10 = "DGS10"  # 10-Year Treasury Constant Maturity Rate (%)
    FEDFUNDS = "FEDFUNDS"  # Effective Federal Funds Rate (%)
    CPIAUCSL = "CPIAUCSL"  # CPI for All Urban Consumers (index, NSA)
    T10Y2Y = "T10Y2Y"  # 10-Year minus 2-Year Treasury spread (pp)

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        return [(member.value, member.value) for member in cls]


SUPPORTED_SERIES: tuple[str, ...] = tuple(member.value for member in MacroSeries)
