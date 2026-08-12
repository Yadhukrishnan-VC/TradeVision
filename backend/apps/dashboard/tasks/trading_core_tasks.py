from __future__ import annotations

import csv
import io
import logging
import uuid
import warnings
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from celery import shared_task
from django.db.models import Count, Max, Min
from django.utils import timezone

from apps.dashboard.infrastructure.common.event_log import EventLog
from apps.dashboard.infrastructure.trading_core.cache import DashboardHomeCache, LatestPriceCache
from apps.dashboard.infrastructure.trading_core.models import (
    DashboardHomeSummary,
    ExportJob,
    Holding,
    OrderSnapshot,
    PositionSnapshot,
    TradeRecord,
)
from apps.dashboard.infrastructure.trading_core.repositories import ExportJobRepository

logger = logging.getLogger(__name__)


@shared_task(
    queue="maintenance",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    soft_time_limit=120,
    time_limit=180,
)
def reconcile_positions_snapshot_deprecated(account_id: str) -> dict[str, Any]:
    """DEPRECATED — use ``apps.portfolio_reconciliation`` (PORTFOLIO-RECONCILE-1).

    The real reconciliation is performed by
    ``apps.portfolio_reconciliation.infrastructure.tasks.reconcile_account_positions``,
    which compares the dashboard read model against the portfolio write
    model and repairs drift. This task only counts its own snapshot
    table and reports "completed" regardless of drift — kept as a
    backward-compatible shim for the beat/caller that reference the old
    name.
    """
    warnings.warn(
        "reconcile_positions_snapshot is deprecated; use "
        "apps.portfolio_reconciliation.infrastructure.tasks.",
        DeprecationWarning,
        stacklevel=2,
    )
    logger.warning(
        "deprecated_reconcile_positions_snapshot_called",
        extra={"account_id": account_id},
    )
    open_count = PositionSnapshot.objects.filter(
        account_id=account_id, is_open=True
    ).count()
    return {
        "account_id": account_id,
        "open_positions_count": open_count,
        "status": "completed",
    }


@shared_task(
    queue="maintenance",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    soft_time_limit=120,
    time_limit=180,
)
def reconcile_open_positions(account_id: str) -> dict[str, Any]:
    logger.info("Reconciling open positions", extra={"account_id": account_id})
    open_positions = PositionSnapshot.objects.filter(account_id=account_id, is_open=True)
    symbol_count = open_positions.values("symbol").annotate(count=Count("id"))
    return {
        "account_id": account_id,
        "symbols": list(symbol_count),
        "status": "completed",
    }


@shared_task(
    queue="maintenance",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    soft_time_limit=120,
    time_limit=180,
)
def reconcile_holdings(account_id: str) -> dict[str, Any]:
    logger.info("Reconciling holdings", extra={"account_id": account_id})
    holding_count = Holding.objects.filter(account_id=account_id).count()
    return {
        "account_id": account_id,
        "holding_count": holding_count,
        "status": "completed",
    }


@shared_task(
    queue="maintenance",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    soft_time_limit=120,
    time_limit=180,
)
def reconcile_orders_deprecated(account_id: str) -> dict[str, Any]:
    """DEPRECATED — use ``apps.portfolio_reconciliation`` (PORTFOLIO-RECONCILE-1).

    See ``reconcile_positions_snapshot_deprecated`` — the real
    read-model reconciliation now lives in
    ``apps.portfolio_reconciliation.infrastructure.tasks.reconcile_account_orders``.
    """
    warnings.warn(
        "reconcile_orders is deprecated; use "
        "apps.portfolio_reconciliation.infrastructure.tasks.",
        DeprecationWarning,
        stacklevel=2,
    )
    logger.warning(
        "deprecated_reconcile_orders_called",
        extra={"account_id": account_id},
    )
    order_count = OrderSnapshot.objects.filter(account_id=account_id).count()
    status_counts = OrderSnapshot.objects.filter(account_id=account_id).values(
        "status"
    ).annotate(count=Count("id"))
    return {
        "account_id": account_id,
        "order_count": order_count,
        "status_breakdown": {s["status"]: s["count"] for s in status_counts},
        "status": "completed",
    }


@shared_task(
    queue="maintenance",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    soft_time_limit=120,
    time_limit=180,
)
def rebuild_dashboard_home_summary(account_id: str) -> dict[str, Any]:
    logger.info("Rebuilding dashboard home summary", extra={"account_id": account_id})
    open_positions_count = PositionSnapshot.objects.filter(
        account_id=account_id, is_open=True
    ).count()
    open_orders_count = OrderSnapshot.objects.filter(
        account_id=account_id, status__in=["pending", "partially_filled"]
    ).count()
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_trades = TradeRecord.objects.filter(
        account_id=account_id, closed_at__gte=today_start
    )
    today_realized_pnl = (
        today_trades.aggregate(total=Sum("realized_pnl"))["total"] or Decimal("0")
    )

    summary, created = DashboardHomeSummary.objects.get_or_create(pk=account_id)
    summary.open_positions_count = open_positions_count
    summary.open_orders_count = open_orders_count
    summary.today_realized_pnl = today_realized_pnl
    summary.projection_updated_at = timezone.now()
    summary.save()

    cache = DashboardHomeCache()
    cache.delete_summary(uuid.UUID(account_id))

    return {
        "account_id": account_id,
        "open_positions_count": open_positions_count,
        "open_orders_count": open_orders_count,
        "status": "completed",
    }


@shared_task(
    queue="maintenance",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 30},
    soft_time_limit=300,
    time_limit=600,
)
def generate_trade_history_export(
    export_id: str, account_id: str, filters: dict[str, Any], format: str
) -> dict[str, Any]:
    logger.info(
        "Generating trade history export",
        extra={"export_id": export_id, "account_id": account_id, "format": format},
    )

    repo = ExportJobRepository()
    try:
        qs = TradeRecord.objects.filter(account_id=account_id)
        if filters:
            if filters.get("symbol"):
                qs = qs.filter(symbol=filters["symbol"])
            if filters.get("side"):
                qs = qs.filter(side=filters["side"])
            if filters.get("date_from"):
                qs = qs.filter(closed_at__gte=filters["date_from"])
            if filters.get("date_to"):
                qs = qs.filter(closed_at__lte=filters["date_to"])
            if filters.get("min_pnl"):
                qs = qs.filter(realized_pnl__gte=Decimal(str(filters["min_pnl"])))
            if filters.get("max_pnl"):
                qs = qs.filter(realized_pnl__lte=Decimal(str(filters["max_pnl"])))

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "trade_id", "symbol", "side", "entry_price", "exit_price",
            "quantity", "realized_pnl", "realized_pnl_pct",
            "opened_at", "closed_at", "holding_period_seconds",
        ])
        for trade in qs.iterator():
            writer.writerow([
                trade.trade_id,
                trade.symbol,
                trade.side,
                str(trade.entry_price),
                str(trade.exit_price),
                str(trade.quantity),
                str(trade.realized_pnl),
                str(trade.realized_pnl_pct),
                trade.opened_at.isoformat(),
                trade.closed_at.isoformat(),
                trade.holding_period_seconds,
            ])

        output.seek(0)
        content = output.getvalue()

        file_url = f"/media/exports/{export_id}.csv"
        repo.update(
            uuid.UUID(export_id),
            status="completed",
            file_url=file_url,
            completed_at=timezone.now(),
        )

        logger.info(
            "Export completed",
            extra={"export_id": export_id, "rows": qs.count()},
        )

        return {
            "export_id": export_id,
            "status": "completed",
            "rows": qs.count(),
        }

    except Exception as exc:
        repo.update(
            uuid.UUID(export_id),
            status="failed",
            error_message=str(exc),
            completed_at=timezone.now(),
        )
        logger.exception(
            "Export failed",
            extra={"export_id": export_id, "account_id": account_id},
        )
        raise


from django.db.models import Sum


# ---------------------------------------------------------------------------
# Backward-compatible aliases (PORTFOLIO-RECONCILE-1 deprecation)
#
# ``reconcile_positions_snapshot`` and ``reconcile_orders`` were renamed to
# ``reconcile_positions_snapshot_deprecated`` / ``reconcile_orders_deprecated``
# in favour of the real reconciliation engine in
# ``apps.portfolio_reconciliation``. The old names remain importable so
# existing callers/tests resolve; they emit ``DeprecationWarning`` when
# invoked. Celery registers the tasks under the ``_deprecated`` names.
# ---------------------------------------------------------------------------

reconcile_positions_snapshot = reconcile_positions_snapshot_deprecated
reconcile_orders = reconcile_orders_deprecated
