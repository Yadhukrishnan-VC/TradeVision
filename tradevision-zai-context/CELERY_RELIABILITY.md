# Celery task reliability

> Workstream WS4 — task reliability tests + one real task bug fix.

## Bug fixed

`apps/dashboard/tasks/trading_core_tasks.py` annotated `Count("id")` on
`PositionSnapshot` and `OrderSnapshot`, but those models use UUID primary keys
named `position_id` / `order_id` — there is no `id` field. The queries raised
`FieldError`, so `reconcile_open_positions` and `reconcile_orders` always
failed. Fixed to `Count("position_id")` / `Count("order_id")`.

This greens the two long-standing pre-existing failures
`TestReconcileTasks::test_reconcile_open_positions` and
`TestReconcileTasks::test_reconcile_orders`.

## Retry/timeout policy (verified, unchanged)

All dashboard maintenance tasks and the portfolio-reconciliation single-account
tasks declare:

- `autoretry_for=(Exception,)`
- `retry_kwargs={"max_retries": 3, "countdown": 60}`
- soft/time limits (`120/180` for dashboard; `180/240` for reconciliation)

The Beat fan-out task `reconcile_all_accounts` deliberately has **no**
auto-retry: a partial fan-out must not redispatch the whole batch. Each
per-account subtask carries its own retry policy, so one account's failure
never blocks the others.

## Invariants now tested

`apps/portfolio_reconciliation/tests/integration/test_task_reliability.py` and
`apps/dashboard/tests/trading_core/unit/test_task_reliability.py`:

1. **Retry does not duplicate financial mutation** — running a
   reconciliation pass twice (simulating a retry) converges to the same
   state and never grows the read model (exact `PositionSnapshot` count,
   drift-record count stable across runs).
2. **Retry policy contract** — `autoretry_for == (Exception,)`,
   `max_retries == 3`, soft/hard limits present on every maintenance and
   reconciliation task; fan-out task has no auto-retry and no tight limits.
3. **Failure handling** — `generate_trade_history_export` marks its
   `ExportJob` `failed` on error and re-raises; a subsequent (retried) run
   converges to `completed` with exactly **one** job row (no duplicate jobs).
4. **Fan-out correctness** — `reconcile_all_accounts` enumerates the whole
   current account table exactly once per side (positions + orders).

## Test-suite hygiene finding

`apps/watchlist/tests/unit/test_services.py` uses
`pytest.mark.django_db(transaction=True)` on two tests, which **commits**
their "Primary" accounts into the reused test DB (`--reuse-db`). Because those
rows persist across test runs, any test that enumerates the `Account` table
sees committed leftovers. The fan-out test was written to be robust to this
(exact-set vs. the current table) rather than depending on an empty DB. This
is pre-existing behaviour, not introduced here; converting those tests to
transactional-safe assertions is a candidate follow-up.

## Run

```bash
cd backend
# env as per CI.md / local test run
.venv/bin/pytest apps/dashboard/tests/trading_core apps/portfolio_reconciliation -q
```