from __future__ import annotations

from decimal import Decimal

from django.db import models

from core.models import BaseModel

MONEY_DECIMAL_KWARGS = {
    "max_digits": 20,
    "decimal_places": 8,
}

MONEY_QUANT = Decimal("0.00000001")


def quantize_money(value: Decimal) -> Decimal:
    """Round a money value to the 8-decimal-precision field convention.

    ``Decimal`` arithmetic on two 8-dp values (e.g. ``quantity *
    avg_entry_price``) yields 16 dp, which would fail the field's
    ``decimal_places=8`` validation on ``full_clean()``. Call at every
    persistence boundary so stored values always honour the convention.
    """
    return value.quantize(MONEY_QUANT)


class AccountCapitalState(BaseModel):
    """Authoritative capital ledger for one account (ADR-028 §2.2).

    A one-to-one, purely additive extension of ``apps.accounts.Account`` —
    ``Account`` itself is never modified. Every field is a ``Decimal`` with
    the dashboard-precision convention ``max_digits=20, decimal_places=8``.

    Invariants maintained by :class:`CapitalService` / the query service:
        equity           = cash + unrealized_pnl_today
        available_capital = cash - margin_used
    """

    account = models.OneToOneField(
        "accounts.Account",
        on_delete=models.CASCADE,
        related_name="capital_state",
    )
    cash = models.DecimalField(default=0, **MONEY_DECIMAL_KWARGS)
    margin_used = models.DecimalField(default=0, **MONEY_DECIMAL_KWARGS)
    equity = models.DecimalField(default=0, **MONEY_DECIMAL_KWARGS)
    available_capital = models.DecimalField(default=0, **MONEY_DECIMAL_KWARGS)
    realized_pnl_today = models.DecimalField(default=0, **MONEY_DECIMAL_KWARGS)
    unrealized_pnl_today = models.DecimalField(default=0, **MONEY_DECIMAL_KWARGS)

    class Meta:
        db_table = "portfolio_accountcapitalstate"
        verbose_name = "Account Capital State"
        verbose_name_plural = "Account Capital States"

    def __str__(self) -> str:
        return f"AccountCapitalState({self.account_id}, cash={self.cash})"


class Position(BaseModel):
    """Portfolio's write-model for an open position (ADR-028 §2.4).

    One row per **open** position per ``(account_id, symbol)``. Closing a
    position removes the row, so a plain unique constraint on the pair is
    the "unique while open" guarantee.

    This is deliberately distinct from dashboard's read-model
    ``PositionSnapshot`` (same CQRS split used repo-wide).
    """

    account_id = models.UUIDField(db_index=True)
    symbol = models.CharField(max_length=50, db_index=True)
    side = models.CharField(max_length=10)  # LONG / SHORT
    quantity = models.DecimalField(**MONEY_DECIMAL_KWARGS)
    avg_entry_price = models.DecimalField(**MONEY_DECIMAL_KWARGS)
    opened_at = models.DateTimeField()

    class Meta:
        db_table = "portfolio_position"
        verbose_name = "Position"
        verbose_name_plural = "Positions"
        constraints = [
            models.UniqueConstraint(
                fields=["account_id", "symbol"],
                name="uq_portfolio_position_account_symbol",
            ),
        ]
        indexes = [
            models.Index(fields=["account_id", "opened_at"], name="idx_port_pos_account_opened"),
        ]

    def __str__(self) -> str:
        return f"Position({self.account_id}, {self.symbol}, {self.side})"


class PositionFillExecution(BaseModel):
    """Idempotency record for a single applied fill (ADR-028 §2.11).

    ``source_fill_id`` is the natural key duplicate delivery is keyed on
    (supplied by a future broker-sync adapter, or generated for manual
    reconciliation). The unique constraint on it mirrors the
    ``(analysis_event_id, rule_id)`` guard used by ``RuleExecution`` and
    ``RiskDecisionExecution``.
    """

    source_fill_id = models.UUIDField(unique=True)
    account_id = models.UUIDField(db_index=True)
    symbol = models.CharField(max_length=50)
    side = models.CharField(max_length=10)  # LONG / SHORT
    quantity = models.DecimalField(**MONEY_DECIMAL_KWARGS)
    price = models.DecimalField(**MONEY_DECIMAL_KWARGS)
    applied_at = models.DateTimeField()

    class Meta:
        db_table = "portfolio_positionfillexecution"
        verbose_name = "Position Fill Execution"
        verbose_name_plural = "Position Fill Executions"
        indexes = [
            models.Index(fields=["account_id", "symbol"], name="idx_port_fill_account_symbol"),
        ]

    def __str__(self) -> str:
        return f"PositionFillExecution({self.source_fill_id})"
