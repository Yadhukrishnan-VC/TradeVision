#!/usr/bin/env python3
"""Scoped wipe of edge-validation replay artifacts (audit trail for REAL-DATA-BACKFILL-3).

Reproduces, reviewable and re-runnable, the database cleanup performed on
2026-08-21 after the 47-symbol edge-validation screening pass deleted
~1.3M replay rows while leaving the one-time candle asset untouched.

What it deletes (scoped, never table-wide):
  1. Account-scoped rows: every Account created on/after ``--accounts-since``
     (default covers all EdgeValidation*/WalkForward */Backtest * runs).
     Fills -> Orders -> ExecutionRequests, Positions, PositionFillExecutions,
     AccountCapitalStates, BacktestRuns, dashboard order/position snapshots,
     journal entries, then the Accounts themselves.
  2. Replay-only tables by ``--ephemeral-since``: rule executions, risk
     decisions, pattern analysis runs, audit-log entries, pipeline heartbeats,
     AI confidence evaluations, recommendations (+ explanations), trader memory.
  3. Event/log tables by ``--events-since``: dashboard/journal event logs and
     the event-bus store.
  4. Replay-created pine outputs.
  5. TASnapshot dedup: keeps exactly ONE row per
     (symbol, second-truncated snapshot_timestamp) — the clean baseline — and
     deletes the per-run duplicates that repeated historical ingestion creates.

What it NEVER touches (hard exclusions):
    market_data_candle, market_data_instrument, market_data_syncrun,
    accounts_user, auth_*, django_*, celery/beat schedules, token tables.

Usage (inside the backend container):
    # dry run — prints matched counts only (default):
    python scripts/db_wipe_validation_data.py
    # execute:
    python scripts/db_wipe_validation_data.py --execute

All deletes run in ONE transaction; any failure rolls everything back.
"""
from __future__ import annotations

import argparse
import os
import sys

# Works both from the repo root (sibling backend/) and inside the backend
# container (cwd=/app).
for _candidate in (
    "/app",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"),
):
    if os.path.isdir(_candidate) and _candidate not in sys.path:
        sys.path.insert(0, _candidate)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
os.environ["LOG_LEVEL"] = "ERROR"

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402

# Defaults reproduce the boundaries used for the 2026-08-21 wipe. Override via
# CLI flags when cleaning a different validation window.
DEFAULT_ACCOUNTS_SINCE = "2026-08-19 15:00:00+00:00"  # earliest validation account
DEFAULT_EPHEMERAL_SINCE = "2026-08-19 14:00:00+00:00"
DEFAULT_EVENTS_SINCE = "2026-08-19 14:00:00+00:00"

EXPECTED_CANDLES = 35813  # sanity floor: the one-time yfinance asset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete (default: dry run, counts only).",
    )
    parser.add_argument("--accounts-since", default=DEFAULT_ACCOUNTS_SINCE)
    parser.add_argument("--ephemeral-since", default=DEFAULT_EPHEMERAL_SINCE)
    parser.add_argument("--events-since", default=DEFAULT_EVENTS_SINCE)
    args = parser.parse_args()

    cur = connection.cursor()

    def count(sql: str, params=None) -> int:
        cur.execute(sql, params or [])
        return int(cur.fetchone()[0])

    def step(label: str, table: str, where: str, params=None) -> None:
        n = count(f'SELECT count(*) FROM "{table}" WHERE {where}', params)
        print(f"  {label}: {n} rows matched")
        if args.execute:
            cur.execute(f'DELETE FROM "{table}" WHERE {where}', params)
            print(f"    -> deleted {cur.rowcount}")

    mode = "EXECUTE" if args.execute else "DRY RUN"
    print(f"mode={mode}")
    print(f"thresholds accounts>={args.accounts_since} ephemeral>={args.ephemeral_since} events>={args.events_since}")

    print("\n[0] SANITY — Candle table must stay intact")
    n_candles = count('SELECT count(*) FROM "market_data_candle"')
    print(f"  market_data_candle total: {n_candles}  (expected {EXPECTED_CANDLES})")
    if n_candles < EXPECTED_CANDLES:
        print("  ABORT: candle count below expected baseline — refusing to run.")
        return 1

    print("\n[1] Account-scoped deletes")
    cur.execute(
        "SELECT id FROM accounts_account "
        "WHERE created_at >= %s OR name LIKE 'EdgeValidation%%' "
        "OR name LIKE 'WalkForward %%' OR name LIKE 'Backtest %%'",
        [args.accounts_since],
    )
    acct_ids = [r[0] for r in cur.fetchall()]
    print(f"  validation-window accounts found: {len(acct_ids)}")
    if acct_ids:
        cur.execute(
            'SELECT id FROM execution_order WHERE "account_id" = ANY(%s::uuid[])',
            [acct_ids],
        )
        order_ids = [r[0] for r in cur.fetchall()]
        if order_ids:
            step("execution_fill", "execution_fill", '"order_id" = ANY(%s::uuid[])', [order_ids])
        step("execution_order", "execution_order", '"account_id" = ANY(%s::uuid[])', [acct_ids])
        step("execution_executionrequest", "execution_executionrequest", '"account_id" = ANY(%s::uuid[])', [acct_ids])
        step("portfolio_position", "portfolio_position", '"account_id" = ANY(%s::uuid[])', [acct_ids])
        step("portfolio_positionfillexecution", "portfolio_positionfillexecution", '"account_id" = ANY(%s::uuid[])', [acct_ids])
        step("portfolio_accountcapitalstate", "portfolio_accountcapitalstate", '"account_id" = ANY(%s::uuid[])', [acct_ids])
        step("backtesting_backtestrun", "backtesting_backtestrun", '"account_id" = ANY(%s::uuid[])', [acct_ids])
        step("dashboard_positionsnapshot", "dashboard_positionsnapshot", '"account_id" = ANY(%s::uuid[])', [acct_ids])
        step("dashboard_ordersnapshot", "dashboard_ordersnapshot", '"account_id" = ANY(%s::uuid[])', [acct_ids])
        step("journal_journalentry", "journal_journalentry", '"account_id" = ANY(%s::uuid[])', [acct_ids])
        step("accounts_account", "accounts_account", "id = ANY(%s::uuid[])", [acct_ids])

    print("\n[2] Replay-only tables (created_at >= ephemeral threshold)")
    for table in [
        "rule_engine_ruleexecution",
        "risk_management_riskdecisionexecution",
        "pattern_engine_patternanalysisrun",
        "audit_log_auditlogentry",
        "pipeline_health_stageheartbeat",
        "ai_engine_confidenceevaluation",
        "recommendations_recommendation",
        "recommendations_recommendationexplanation",
        "trader_memory_memoryentry",
    ]:
        step(table, table, "created_at >= %s", [args.ephemeral_since])

    print("\n[3] Event/log tables")
    step("dashboard_eventlog", "dashboard_eventlog", "applied_at >= %s", [args.events_since])
    step("journal_eventlog", "journal_eventlog", "applied_at >= %s", [args.events_since])
    step("eventbus_storedevent", "eventbus_storedevent", "occurred_at >= %s", [args.events_since])

    print("\n[4] intelligence_pineoutput (replay-created)")
    step("intelligence_pineoutput", "intelligence_pineoutput", "ingested_at >= %s", [args.ephemeral_since])

    print("\n[5] TASnapshot dedup — keep one row per (symbol, second-truncated ts)")
    keep_sql = (
        "SELECT id FROM ("
        "SELECT DISTINCT ON (symbol, date_trunc('second', snapshot_timestamp)) id "
        "FROM technical_analysis_snapshot "
        "ORDER BY symbol, date_trunc('second', snapshot_timestamp), id"
        ") keep"
    )
    n_dup = count(f"SELECT count(*) FROM technical_analysis_snapshot WHERE id NOT IN ({keep_sql})")
    print(f"  technical_analysis_snapshot duplicates to delete: {n_dup}")
    if args.execute:
        cur.execute(f"DELETE FROM technical_analysis_snapshot WHERE id NOT IN ({keep_sql})")
        print(f"    -> deleted {cur.rowcount}")

    print("\n[6] POST-CHECK")
    for table, floor in [
        ("market_data_candle", EXPECTED_CANDLES),
        ("technical_analysis_snapshot", EXPECTED_CANDLES),
        ("accounts_account", None),
        ("execution_order", None),
        ("backtesting_backtestrun", None),
        ("eventbus_storedevent", None),
    ]:
        n = count(f"SELECT count(*) FROM {table}")
        marker = ""
        if floor is not None and n != floor:
            marker = f"  (!! expected {floor})"
        print(f"  {table}: {n}{marker}")

    if args.execute:
        connection.commit()
        print("\nCOMMITTED.")
    else:
        connection.rollback()
        print("\nDRY RUN — rolled back.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
