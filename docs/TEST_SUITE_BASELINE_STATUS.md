# Test Suite Baseline Status

Recorded: 2026-08-22 · HEAD at capture: `361e856` (REAL-DATA-BACKFILL-4) · branch `trading-core`

Purpose: a real, diffable baseline for the pytest suite in this dev environment,
so future batches compare against recorded numbers instead of verbal claims.

## How to reproduce

```bash
docker exec infra-backend-1 bash -c "cd /app && python -m pytest --tb=no -q"
```

## Totals

```
============ 7 failed, 880 passed, 1 warning, 1013 errors in 27.11s ============
```

## Error categorization (the 1013 ERRORs)

Grouped by exception type via a per-report plugin (`pytest_runtest_logreport`),
not hand-counted:

| Count | Exception | Verdict |
|------:|-----------|---------|
| 1013 | `psycopg2.OperationalError` / `django.db.utils.OperationalError`: `connection to server at "pgbouncer" ..., port 6432 failed: FATAL: no such database: test_tradevision_dev_db` | **100% environment/infra config — 0% code-related** |

Every single one of the 1013 errors is the same root cause: Django's test
runner creates/connects to `test_tradevision_dev_db` **through pgbouncer**
(port 6432), which cannot create or route that database
(`FATAL: no such database`). The tests never reach application code; they fail
during DB setup. Fix (when desired): point `config/settings/testing.py` at the
`postgres` host/port directly, or pre-create the test database outside
pgbouncer. None of these errors indicate product-code problems.

## Failure categorization (the 7 FAILEDs) — named explicitly, none folded away

| Count | Test(s) | Exact cause line |
|------:|---------|------------------|
| 3 | `apps/recommendations/tests/unit/test_recommendation_aggregate.py::TestRecommendationAggregate::{test_accepted,test_rejected,test_expired}_cannot_transition` | `apps/recommendations/domain/entities.py:68: IllegalTransition: Cannot transition from ACCEPTED to ACCEPTED` (and analogous for REJECTED/EXPIRED) — domain now raises where the test expects a no-op/self-transition path |
| 2 | `apps/rule_engine/tests/unit/test_event_handlers.py::TestRegisterHandlers::{test_subscribed_handler_invoked_when_event_published, test_handler_not_invoked_for_unsubscribed_event_type}` | `unittest/mock.py:662: AttributeError: __name__` — handler registration reads `handler.__name__` on an object the test supplies as a plain Mock/lambda without one |
| 1 | `apps/market_data/tests/unit/test_candle_aggregation.py::TestCandleAggregationService::test_empty_bars_raises` | `test_candle_aggregation.py:109: Failed: DID NOT RAISE <class 'ValueError'>` — service no longer raises on empty bars (or test expectation is stale) |
| 1 | `apps/rule_engine/tests/unit/test_domain_rules.py::TestVolumeSpikeRule::test_trigger_data_contains_volume_info` | `test_domain_rules.py:217: AssertionError: assert '5' == '5.0'` — trigger_data volume serialized as int-string vs float-string |

All 7 are genuine code-vs-test divergences in modules untouched by the
REAL-DATA-BACKFILL batches (recommendations domain, rule_engine event
registration/domain rules, market_data aggregation). They are tracked here so
they are neither ignored nor misattributed.

## Provenance / history

- Batch REAL-DATA-BACKFILL-4 verified via `git stash` A/B run:
  with and without its changes the suite reported identical totals
  (at that time `9 failed, 877 passed, 1013 errors`) — no regressions introduced.
- Of those 9 earlier failures, 2 were `TestCalculateDistribution` assertions
  broken by commit `9569824` adding the `mean` key without running the suite;
  fixed + extended in batch 4 (now 7 failed, 880 passed).
- flake8 is not installed in the backend container; `ruff 0.7.4`,
  `mypy 1.13.0`, `black 24.10.0` are available. mypy currently cannot start
  (`Source file found twice under different module names`, config issue).
