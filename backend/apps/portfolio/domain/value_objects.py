from __future__ import annotations

from enum import Enum


class Side(str, Enum):
    """Direction of an open position.

    ``LONG`` gains when price rises, ``SHORT`` gains when price falls.
    The sign convention used by every P&L formula in ADR-028:
    ``direction_sign = +1 for LONG, -1 for SHORT``.
    """

    LONG = "LONG"
    SHORT = "SHORT"


def direction_sign(side: Side) -> int:
    """Return the multiplicative sign used by the ADR-028 P&L formulas."""
    return 1 if side is Side.LONG else -1


def opposite_side(side: Side) -> Side:
    """Return the opposing :class:`Side`."""
    return Side.SHORT if side is Side.LONG else Side.LONG


class CapitalAdjustmentReason(str, Enum):
    """Stable reason codes attached to ``portfolio.AccountCapitalChanged``.

    Append-only — never removed or redefined. The ledger field mutated by a
    given adjustment is implied by the reason (cash for DEPOSIT/WITHDRAWAL,
    margin_used for MARGIN_RESERVED/MARGIN_RELEASED, cash + realized_pnl_today
    for REALIZED_PNL).
    """

    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    MARGIN_RESERVED = "MARGIN_RESERVED"
    MARGIN_RELEASED = "MARGIN_RELEASED"
    REALIZED_PNL = "REALIZED_PNL"
