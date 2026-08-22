"""PORTFOLIO-RECONCILE-1 — Celery tasks.

Three tasks:

- ``reconcile_account_positions`` / ``reconcile_account_orders`` run one
  reconciliation pass for a single account (position / order side
  respectively).
- ``reconcile_all_accounts`` is the Beat-scheduled fan-out: it enumerates
  the accounts in ``apps.accounts`` and dispatches the two single-account
  tasks per account.

Retry/timeout policy is copied verbatim from the --- now deprecated ---
``apps.dashboard.tasks.trading_core_tasks.reconcile_*`` tasks this batch
supersedes: same ``maintenance`` queue, ``autoretry_for`` set and
``countdown``/``max_retries`` shape. The soft/time limits are higher
because a real pass compares and (on drift) repairs rows, which the old
count-only tasks never did.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    queue="maintenance",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    soft_time_limit=180,
    time_limit=240,
)
def reconcile_account_positions(account_id: str) -> dict[str, Any]:
    """Run one position reconciliation pass for ``account_id``.

    Args:
        account_id: The account (UUID as a string) whose open positions
            are compared against their ``PositionSnapshot`` rows.

    Returns:
        The per-classification outcome of the run (see
        ``ReconciliationResult.as_dict()``). Drift is repaired in place
        and recorded; an exception is retried by Celery up to 3 times.
    """
    from apps.portfolio_reconciliation.application.position_reconciliation_service import (
        get_position_reconciliation_service,
    )

    result = get_position_reconciliation_service().reconcile(
        uuid.UUID(account_id)
    )
    outcome = result.as_dict()
    logger.info(
        "portfolio_reconciliation_position_task_complete",
        extra=outcome,
    )
    return outcome


@shared_task(
    queue="maintenance",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    soft_time_limit=180,
    time_limit=240,
)
def reconcile_account_orders(account_id: str) -> dict[str, Any]:
    """Run one order reconciliation pass for ``account_id``.

    Args:
        account_id: The account (UUID as a string) whose orders are
            compared against their ``OrderSnapshot`` rows.

    Returns:
        The per-classification outcome of the run.
    """
    from apps.portfolio_reconciliation.application.order_reconciliation_service import (
        get_order_reconciliation_service,
    )

    result = get_order_reconciliation_service().reconcile(
        uuid.UUID(account_id)
    )
    outcome = result.as_dict()
    logger.info(
        "portfolio_reconciliation_order_task_complete",
        extra=outcome,
    )
    return outcome


@shared_task(queue="maintenance")
def reconcile_all_accounts() -> None:
    """Fan out reconciliation to every account (Beat, every 5 minutes).

    Enumerates ``apps.accounts.Account`` rows (the anchor entity for the
    write-model ``account_id`` fields this batch compares) and dispatches
    one position + one order pass per account. The two sub-tasks carry
    their own retry policy; a per-account failure never blocks the other
    accounts.
    """
    from apps.accounts.infrastructure.models import Account

    account_ids = list(Account.objects.values_list("id", flat=True))
    if not account_ids:
        logger.info("portfolio_reconciliation_no_accounts_to_reconcile")
        return

    logger.info(
        "portfolio_reconciliation_fanout_start",
        extra={"account_count": len(account_ids)},
    )
    for account_id in account_ids:
        account_id_str = str(account_id)
        reconcile_account_positions.delay(account_id_str)  # type: ignore[attr-defined]
        reconcile_account_orders.delay(account_id_str)  # type: ignore[attr-defined]
    logger.info(
        "portfolio_reconciliation_fanout_dispatched",
        extra={"account_count": len(account_ids)},
    )

@shared_task(
    queue="maintenance",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    soft_time_limit=120,
    time_limit=180,
)
def reconcile_rule_expectations(window_hours: int = 24) -> dict[str, Any]:
    """LIVE-PAPER-DRESS-REHEARSAL-1 — decision-chain reconciliation (daily).

    Compares what the rule pipeline *expected* to happen against what the
    execution write model *actually* produced over the trailing window, per
    account:

        RuleFired  ->  RiskApproved  ->  ExecutionRequest  ->  Order(FILLED)  ->  Fill

    The chain must be monotonically non-increasing; every inversion is a
    real integrity gap (e.g. approvals that never became orders, filled
    orders without fills). This is deliberately read-only flagging — unlike
    PORTFOLIO-RECONCILE-1 there is no auto-repair, because the write model
    is the source of truth here and a mismatch means an investigation, not
    a mutation.
    """
    from datetime import timedelta

    from django.utils import timezone as dj_tz

    from apps.accounts.infrastructure.models import Account
    from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order
    from apps.risk_management.infrastructure.models import RiskDecisionExecution

    window_start = dj_tz.now() - timedelta(hours=window_hours)

    # The decision write model records one row per evaluated rule firing
    # (APPROVED / REJECTED), so "fired" == all rows and "approved" ==
    # status=APPROVED — the true upstream expectation counts.
    fired_by_account: dict[str, int] = {}
    approved_by_account: dict[str, int] = {}
    for row in (
        RiskDecisionExecution.objects.filter(created_at__gte=window_start)
        .values_list("account_id", "status")
        .iterator()
    ):
        account_key, status = str(row[0]), str(row[1]).upper()
        fired_by_account[account_key] = fired_by_account.get(account_key, 0) + 1
        if status == "APPROVED":
            approved_by_account[account_key] = approved_by_account.get(account_key, 0) + 1

    def _count_by_account(queryset) -> dict[str, int]:
        counts: dict[str, int] = {}
        for account_id in queryset.iterator():
            key = str(account_id)
            counts[key] = counts.get(key, 0) + 1
        return counts

    requests_by_account = _count_by_account(
        ExecutionRequest.objects.filter(created_at__gte=window_start).values_list("account_id")
    )
    orders_by_account = _count_by_account(
        Order.objects.filter(created_at__gte=window_start).values_list("account_id")
    )
    fills_by_account = _count_by_account(
        Fill.objects.filter(created_at__gte=window_start).values_list("order__account_id")
    )

    known_accounts = set(Account.objects.values_list("id", flat=True)) | set(
        fired_by_account
    ) | set(requests_by_account) | set(orders_by_account) | set(fills_by_account)

    report: dict[str, Any] = {"window_hours": window_hours, "accounts": {}, "mismatches": []}
    for account_key in sorted(known_accounts):
        fired = fired_by_account.get(account_key, 0)
        approved = approved_by_account.get(account_key, 0)
        requests_n = requests_by_account.get(account_key, 0)
        orders_n = orders_by_account.get(account_key, 0)
        fills_n = fills_by_account.get(account_key, 0)
        report["accounts"][account_key] = {
            "rule_fired": fired,
            "risk_approved": approved,
            "execution_requests": requests_n,
            "orders": orders_n,
            "fills": fills_n,
        }
        # Monotonicity checks (each stage may legitimately drop — risk
        # rejections, unfilled limits — but never grow relative to upstream,
        # and every approval must surface as exactly one request/order).
        checks = [
            ("approved_gt_fired", approved > fired),
            ("requests_gt_approved", requests_n > approved),
            ("orders_ne_requests", orders_n != requests_n),
            ("fills_gt_orders", fills_n > orders_n),
        ]
        for name, violated in checks:
            if violated:
                mismatch = {"account_id": account_key, "check": name}
                report["mismatches"].append(mismatch)
                logger.error(
                    "rule_expectation_mismatch",
                    extra={"account_id": account_key, "check": name, **report["accounts"][account_key]},
                )

    logger.info(
        "reconcile_rule_expectations_completed",
        extra={"accounts": len(report["accounts"]), "mismatches": len(report["mismatches"])},
    )
    return report
