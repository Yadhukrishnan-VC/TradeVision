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