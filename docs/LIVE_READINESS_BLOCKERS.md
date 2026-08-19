# Live/Paper Trading Readiness Blockers

Batch that removes the remaining blockers between the simulated/dev environment
and running the pipeline against live or paper broker data. Four additive
changes — no broker execution is introduced (ADR-030 owner-gated, Phase 2/3 out
of scope):

1. Runtime dependencies restored in the remediation batch were **declared
   nowhere in requirements**; a fresh rebuild would have silently lost them.
2. Historical data could only be backfilled via Celery tasks — no operator CLI.
3. Nothing stopped a live environment pointing at a `*test*` database (or a dev
   environment pointing at a non-`test`/`dev` database).
4. The ADR-029 §4 fail-closed rule gate returns verdicts silently (INFO log
   only) — no visibility into *why* rules are not firing.

---

## Task 1 — Requirements now declare the restored runtime dependencies

### Before

`backend/requirements/base.txt` did not list seven runtime dependencies that the
code imports. They were only present in the local venv because the remediation
batch hand-installed them:

- `django-prometheus==2.4.0`
- `python-decouple==3.8`
- `structlog==24.4.0`
- `channels==4.3.2`
- `channels-redis==4.3.0`
- `Jinja2==3.1.6`
- `requests` (imported by `zerodha`/`chartink`/`fred`/`marketaux` providers)

A fresh environment built strictly from the requirements files would have
started, then failed at runtime with `ModuleNotFoundError`.

### After

`backend/requirements/base.txt` now declares all seven with exact pins and a
comment documenting the constraints:

```
# Live/paper trading runtime deps (declared post-remediation; see
# docs/LIVE_READINESS_BLOCKERS.md). django-prometheus must stay <2.5.0
# (2.5+ requires Django!=5.0.*,<6.1 — excludes the pinned 5.0.x line).
django-prometheus==2.4.0
python-decouple==3.8
structlog==24.4.0
channels==4.3.2
channels-redis==4.3.0
Jinja2==3.1.6
requests==2.34.2
```

### Proof — fresh rebuild from requirements only, zero manual installs

```bash
cd backend
rm -rf .venv
/usr/bin/virtualenv --python=/usr/bin/python3.12 .venv   # system python3.12 has no ensurepip
.venv/bin/pip install -r requirements/dev.txt            # no other installs
```

```text
$ .venv/bin/pip check
No broken requirements found.

$ POSTGRES_DB=tradevision_test .venv/bin/python manage.py check
System check identified no issues (0 silenced).
```

All seven deps resolve to the pinned versions and `manage.py check` passes with
**no manual intervention**. The rebuild also resolved transitive deps to newer
allowed versions (celery 5.6.3, django-celery-beat 2.9.0, django-celery-results
2.6.0, Faker 40.36.0, django-stubs 5.2.9); the full test suite is unchanged.

---

## Task 2 — `manage.py backfill_historical` operator CLI

### Before

Historical candles could only be backfilled by dispatching the
`historical_sync_service` Celery tasks (or Python calls into the service). An
operator onboarding a sandbox/paper broker had no CLI to prime the data store.

### After

`backend/apps/market_data/management/commands/backfill_historical.py` wraps
`HistoricalSyncService.backfill` unchanged:

```
--provider   mock|paper|zerodha (default: settings.MARKET_DATA_PROVIDER)
--symbols    NSE:RELIANCE[,NSE:INFY] (or bare RELIANCE -> default exchange)
--tokens     comma-separated instrument tokens (alternative to --symbols)
--timeframe  1m|1D|... (default 1min)
--from/--to  explicit range, or --days N trailing window (exactly one required)
--dry-run    fetch + report counts without persisting
```

Per-instrument progress and a final summary; exit 1 if any instrument failed
(failures never abort the batch — per-instrument isolation).

### Proof — dry-run (paper provider, no persistence)

```text
$ manage.py backfill_historical --provider=paper --symbols=RELIANCE,INFY --timeframe=1D --days=2 --dry-run
provider=paper timeframe=1D range=2026-08-17T08:52Z -> 2026-08-19T08:52Z mode=dry-run instruments=2
  [NSE:RELIANCE] OK dry-run, 2 bars would be persisted
  [NSE:INFY]     OK dry-run, 2 bars would be persisted
---
done: instruments=2 failures=0 candles_persisted=0 bars_dry_run=4
```

### Proof — real run (persists through `HistoricalSyncService`)

```text
$ manage.py backfill_historical --provider=paper --symbols=NSE:RELIANCE --timeframe=1D --from=2026-08-14T00:00:00Z --to=2026-08-19T00:00:00Z
  [NSE:RELIANCE] OK, 10 candles persisted
---
done: instruments=2 failures=0 candles_persisted=10 bars_dry_run=0
```

---

## Task 3 — Fail-loud environment ↔ database separation system check

### Before

Settings point at a database purely by what the operator exported. A `prod`
settings module pointed at `tradevision_test`, or a dev settings module pointed
at `tradevision_db`, started up silently — the wrong-database mistake only
surfaced later as confusing test/live data mix.

### After

`backend/config/checks.py` registers `config` system checks, wired into startup
via `apps/common/apps.py` `CommonConfig.ready()`:

- `config.E001` — settings module contains `prod`/`staging` AND the default DB
  name carries a `test` marker → **ERROR**.
- `config.E002` — settings module contains `dev`/`test` AND the default DB name
  carries neither `test` nor `dev` marker → **ERROR**.

Markers use word-boundary matching (`_name_has_marker`), so `dev` does not match
the `dev` inside `tradevision`. The pytest harness settings
(`config.settings.testing` / `config.settings.test`) are exempt (the runner owns
its `test_*` databases).

### Proof — both directions

```text
$ POSTGRES_DB=tradevision_test manage.py check                       # dev settings
System check identified no issues (0 silenced).                       # OK: test DB

$ POSTGRES_DB=tradevision_db manage.py check                          # dev settings
config.E002: ERROR ... settings module is dev, but default DB name 'tradevision_db'
carries no 'test' or 'dev' marker — refusing to start.

$ POSTGRES_DB=tradevision_test DJANGO_SETTINGS_MODULE=config.settings.staging manage.py check
config.E001: ERROR ... settings module is live, but default DB name 'tradevision_test'
carries a 'test' marker — refusing to start.

$ POSTGRES_DB=tradevision_live DJANGO_SETTINGS_MODULE=config.settings.staging manage.py check
System check identified no issues (0 silenced).                       # OK: live DB
```

`config.E001`/`config.E002` abort startup (`ERROR`, not `WARNING`).

---

## Task 4 — Rule-gate GO status is now observable (`rule_gate_report`)

### Before

`RuleEvaluationService._filter_by_gate` (ADR-029 §4) silently returns `[]` when
a rule lacks config, is disabled, has no regime, or is not GO-validated — the
reasons are logged at INFO only. During paper/live onboarding, nothing makes it
visible why zero rules are firing.

### After

`backend/apps/rule_engine/management/commands/rule_gate_report.py` prints, per
registered rule × reported regime, the exact gate verdict
(`GO` / `NO_GO` / `INSUFFICIENT_DATA` / `NOT_VALIDATED` / `DISABLED` / `NO_CONFIG`),
mirroring `_filter_by_gate` reasons. `--regime` filters to one regime; `--verbose`
prints the stored verdict payload.

### Proof — sandbox database (seeded configs)

```text
$ manage.py rule_gate_report
ADR-029 §4 fail-closed gate — per-rule regime GO status
gate pass = RuleConfig exists + enabled + validated_regimes[regime].status == GO

RULE                         EVENT                ENABLED  BULLISH       BEARISH      RANGING      VOLATILE     BREAKOUT     BREAKDOWN
--------------------------------------------------------------------------------------------------------------------------------------------
price_movement_v1            price_movement       yes      GO            NOT_VALIDATED NO_GO        NOT_VALIDATED NOT_VALIDATED NOT_VALIDATED
volume_spike_v1              volume_spike         yes      NOT_VALIDATED NOT_VALIDATED NOT_VALIDATED NOT_VALIDATED NOT_VALIDATED NOT_VALIDATED
breakout_v1                  breakout             yes      INSUFFICIENT_DATA NOT_VALIDATED NOT_VALIDATED NOT_VALIDATED NOT_VALIDATED NOT_VALIDATED
long_momentum_v1             breakout             no       NO_CONFIG     NO_CONFIG    NO_CONFIG    NO_CONFIG    NO_CONFIG    NO_CONFIG
short_sell_v1                breakdown            no       DISABLED      DISABLED     DISABLED     DISABLED     DISABLED     DISABLED
volatility_breakout_v1       breakout             no       NO_CONFIG     NO_CONFIG    NO_CONFIG    NO_CONFIG    NO_CONFIG    NO_CONFIG
high_beta_breakout_v1        breakout             no       NO_CONFIG     NO_CONFIG    NO_CONFIG    NO_CONFIG    NO_CONFIG    NO_CONFIG
short_breakdown_v1           breakdown            no       NO_CONFIG     NO_CONFIG    NO_CONFIG    NO_CONFIG    NO_CONFIG    NO_CONFIG

rules fireable in at least one reported regime: 1/8
note: backtest-created configs are always disabled (ADR-029 §3); a GO verdict alone never flips a rule live.
```

---

## Regression tests

- `config/tests/test_env_db_separation_check.py` — E001/E002 in both directions,
  pass cases, `dev`-substring-in-`tradevision` guard, test-harness exemption.
- `apps/market_data/tests/unit/test_backfill_historical_command.py` — dry-run
  persists nothing, real run persists via service, unknown-symbol failure output,
  `--from`/`--days` exclusivity.
- `apps/rule_engine/tests/unit/test_rule_gate_report_command.py` — NO_CONFIG,
  GO / NOT_VALIDATED / DISABLED, INSUFFICIENT_DATA rows and fireable counts.

Result: 16 new tests, all green. Full suite on the rebuilt venv remains
**34 failed / 1745 passed / 15 errors** — identical to the pre-batch baseline
(zero regressions; the failures are pre-existing and unrelated).

---

## Consequences / findings

- **Dev convention change:** `manage.py` runs now require a DB whose name
  contains a `test`/`dev` token (e.g. `POSTGRES_DB=tradevision_test`).
  `backend/.env` already uses `tradevision_test` — no change needed there.
- **`docker-compose` default trips E002:** `infra/docker-compose.yml` defaults
  `POSTGRES_DB=tradevision_db`, which now fails the check under dev settings.
  Compose operators must set `POSTGRES_DB=tradevision_dev_db` (or similar) when
  running with dev settings — documented here so it is not a surprise.
- **CI unaffected:** `.github/workflows/ci.yml` runs the check with
  `config.settings.testing` (exempt) and `POSTGRES_DB=tradevision_db`.
- **No schema changes** were required for Tasks 2–4; `makemigrations --check`
  is clean.
