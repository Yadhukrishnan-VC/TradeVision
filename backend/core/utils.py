"""
TradeVision AI — Shared utility functions.

All datetime helpers return timezone-aware objects. Never use datetime.now()
or date.today() in application code — use the functions in this module.
"""

import uuid
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from django.utils import timezone

_IST = ZoneInfo("Asia/Kolkata")
_UTC = ZoneInfo("UTC")

# ---------------------------------------------------------------------------
# Datetime helpers — always timezone-aware
# ---------------------------------------------------------------------------


def get_now() -> datetime:
    """
    Return the current datetime in UTC (timezone-aware).

    Prefer this over ``django.utils.timezone.now()`` for explicit clarity
    that the result is UTC, not the display timezone.
    """
    return timezone.now()


def get_ist_now() -> datetime:
    """
    Return the current datetime in IST (Asia/Kolkata), timezone-aware.

    Use for market-hours calculations and user-facing display values.
    Never use for database storage — store UTC, display IST.
    """
    return datetime.now(tz=_IST)


def to_ist(dt: datetime) -> datetime:
    """
    Convert any timezone-aware datetime to IST.

    Args:
        dt: A timezone-aware datetime (UTC or otherwise).

    Returns:
        The same moment expressed in IST.

    Raises:
        ValueError: If ``dt`` is naive (missing tzinfo).
    """
    if dt.tzinfo is None:
        raise ValueError(f"Cannot convert naive datetime to IST: {dt!r}")
    return dt.astimezone(_IST)


def to_utc(dt: datetime) -> datetime:
    """
    Convert any timezone-aware datetime to UTC.

    Args:
        dt: A timezone-aware datetime.

    Returns:
        The same moment expressed in UTC.

    Raises:
        ValueError: If ``dt`` is naive.
    """
    if dt.tzinfo is None:
        raise ValueError(f"Cannot convert naive datetime to UTC: {dt!r}")
    return dt.astimezone(_UTC)


# ---------------------------------------------------------------------------
# Identity helpers
# ---------------------------------------------------------------------------


def generate_uuid() -> uuid.UUID:
    """Generate a new random UUID4."""
    return uuid.uuid4()


def generate_correlation_id() -> str:
    """
    Generate a correlation ID string for request and task tracing.

    The ID is a UUID4 formatted as a hyphenated string, suitable for use
    as a log field or HTTP response header.
    """
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Financial formatting helpers
# ---------------------------------------------------------------------------


def format_inr(amount: Decimal, *, show_symbol: bool = True) -> str:
    """
    Format a Decimal value as Indian Rupees with two decimal places.

    Args:
        amount: The monetary amount to format.
        show_symbol: When True, prepends the ₹ symbol.

    Returns:
        Formatted string, e.g. ``"₹1,23,456.78"`` or ``"1,23,456.78"``.
    """
    rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    # Indian number formatting: last three digits, then groups of two
    integer_part, _, decimal_part = f"{rounded:,.2f}".partition(".")
    digits = integer_part.replace(",", "").replace("-", "")
    negative = rounded < 0

    if len(digits) > 3:
        last_three = digits[-3:]
        rest = digits[:-3]
        groups = []
        while rest:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        formatted_int = ",".join(groups) + "," + last_three
    else:
        formatted_int = digits

    result = f"{'-' if negative else ''}{formatted_int}.{decimal_part}"
    return f"₹{result}" if show_symbol else result


def format_percentage(value: Decimal, *, decimal_places: int = 2) -> str:
    """
    Format a Decimal as a percentage string with sign.

    Args:
        value: The percentage value (e.g. ``Decimal("2.34")`` for 2.34%).
        decimal_places: Number of decimal places to display.

    Returns:
        Formatted string, e.g. ``"+2.34%"`` or ``"-1.50%"``.
    """
    quantizer = Decimal(10) ** -decimal_places
    rounded = value.quantize(quantizer, rounding=ROUND_HALF_UP)
    sign = "+" if rounded >= 0 else ""
    return f"{sign}{rounded}%"
