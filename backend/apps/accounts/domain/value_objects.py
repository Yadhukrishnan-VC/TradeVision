from __future__ import annotations

import enum


class Role(enum.Enum):
    """User roles for authorization within the TradeVision system."""

    OWNER = "owner"
    STAFF = "staff"
    VIEWER = "viewer"


class Scope(enum.Enum):
    """Capability scopes that can be granted to an API key.

    Scopes correspond 1:1 to staff-only or owner-only endpoints across
    the system. This list is append-only — new scopes are added by
    later batches but never removed or redefined here.
    """

    READ_MARKET_DATA = "read:market_data"
    READ_PORTFOLIO = "read:portfolio"
    READ_JOURNAL = "read:journal"
    MANAGE_RISK_POLICY = "manage:risk_policy"
    MANAGE_EXECUTION = "manage:execution"
    MANAGE_BROKER_SESSION = "manage:broker_session"
