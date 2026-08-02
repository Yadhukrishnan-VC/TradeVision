from __future__ import annotations

from enum import Enum


class KillSwitchScope(str, Enum):
    """Scopes a trade-safety kill switch toggle.

    ``GLOBAL`` blocks every symbol, ``ACCOUNT`` blocks the whole account,
    ``SYMBOL`` blocks a single instrument. For "is this trade blocked",
    most-specific wins: SYMBOL > ACCOUNT > GLOBAL.
    """

    GLOBAL = "GLOBAL"
    ACCOUNT = "ACCOUNT"
    SYMBOL = "SYMBOL"


class RejectionReason(str, Enum):
    """Deterministic fail-closed rejection codes emitted by Risk Management.

    Every code is an explicit, stable value — never a silent ``None``. The
    same code surfaces in ``RiskRejection.reason_code``, the persisted
    ``RiskDecisionExecution`` row, and the ``risk_management.RiskRejected``
    event payload.
    """

    STOP_EQUALS_ENTRY = "STOP_EQUALS_ENTRY"
    """stop_loss == entry_price — no risk distance to measure."""

    STOP_WRONG_SIDE = "STOP_WRONG_SIDE"
    """stop lies on the wrong side of entry for the setup's direction."""

    ZERO_RISK_DISTANCE = "ZERO_RISK_DISTANCE"
    """|entry - stop| <= 0 after rounding."""

    ZERO_CAPITAL = "ZERO_CAPITAL"
    """Available capital from the gateway is <= 0."""

    MISSING_ACCOUNT_STATE = "MISSING_ACCOUNT_STATE"
    """Gateway returned no capital/exposure data."""

    MISSING_STOP_LOSS = "MISSING_STOP_LOSS"
    """trigger_data lacks a usable stop_loss (e.g. volatility breakout fired
    without supertrend_available)."""

    MISSING_ENTRY_PRICE = "MISSING_ENTRY_PRICE"
    """trigger_data lacks a usable entry_price."""

    INSUFFICIENT_CAPITAL = "INSUFFICIENT_CAPITAL"
    """Position size floors to 0 after the available-capital constraint."""

    POSITION_SIZE_ZERO = "POSITION_SIZE_ZERO"
    """Computed position size rounds to 0 for any reason."""

    MAX_EXPOSURE_EXCEEDED = "MAX_EXPOSURE_EXCEEDED"
    """Position would breach the portfolio-level exposure cap."""

    DAILY_LOSS_LIMIT_EXCEEDED = "DAILY_LOSS_LIMIT_EXCEEDED"
    """Realized (+ unrealized, when available) daily loss >= configured max."""

    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    """Global trade-safety kill-switch is on."""

    RISK_REWARD_BELOW_MINIMUM = "RISK_REWARD_BELOW_MINIMUM"
    """Computed R:R ratio is below the configured floor."""

    STALE_DATA = "STALE_DATA"
    """Packet/session facts were not fresh at fire time."""

    MARKET_CLOSED = "MARKET_CLOSED"
    """Evaluation occurred outside NSE market hours / trading day."""

    INVALID_INSTRUMENT = "INVALID_INSTRUMENT"
    """Symbol is not in the configured tradable instrument set."""

    UNKNOWN = "UNKNOWN"
    """Unexpected failure during evaluation (fail-closed)."""
