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
    DASHBOARD_READ_HOME = "dashboard:read:home"
    DASHBOARD_READ_PORTFOLIO = "dashboard:read:portfolio"
    DASHBOARD_READ_POSITIONS = "dashboard:read:positions"
    DASHBOARD_READ_ORDERS = "dashboard:read:orders"
    DASHBOARD_READ_TRADE_HISTORY = "dashboard:read:trade_history"
    DASHBOARD_READ_PNL_ANALYTICS = "dashboard:read:pnl_analytics"
    DASHBOARD_READ_PERFORMANCE_METRICS = "dashboard:read:performance_metrics"
    DASHBOARD_READ_RISK = "dashboard:read:risk"
