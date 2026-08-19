# Remediation Batch — Environment & Runtime

Batch of three environment/runtime remediations: (1) Django version drift in
the local virtualenv, (2) migration drift in four apps, (3) AI prompt templates
failing to load because of a reserved `LogRecord` attribute used in a logging
`extra` dict. All three are resolved; a codebase-wide audit for the same
reserved-key mistake surfaced two more live instances that were fixed under the
same issue.

---

## Issue 1 — Django version drift in the local virtualenv

### Root cause

`backend/requirements/base.txt` pins `django>=5.0,<5.1`, but the local
`backend/.venv` had **Django 6.0.7** installed. The drift was caused by a prior
ad-hoc install that pulled in Django 6.x, and was silently preserved because
the venv is gitignored and never rebuilt from the declared requirements.

Canonical dev requirements are `backend/requirements/dev.txt` (referenced by
`.github/workflows/ci.yml`). `requirements/development.txt` (exact pins, used
by `Dockerfile.dev`) also exists and agrees on the Django 5.0.x line.

### Fix

Rebuilt `backend/.venv` from scratch:

```bash
cd backend
rm -rf .venv                     # old venv backed up to /tmp (later cleaned)
/usr/bin/virtualenv --python=/usr/bin/python3.12 .venv
.venv/bin/pip install -r requirements/dev.txt
```

(System `python3.12` has no `ensurepip`, so `virtualenv` is used to bootstrap.)

Then installed the runtime dependencies required by the code but missing from
**every** requirements file (see findings), pinned to the versions the old venv
had:

```bash
.venv/bin/pip install \
    python-decouple==3.8 \
    structlog==24.4.0 \
    channels==4.3.2 \
    channels-redis==4.3.0 \
    django-prometheus==2.4.0 \
    Jinja2==3.1.6
```

`django-prometheus==2.4.0` is deliberately used: **2.5.0 requires
`Django!=5.0.*,<6.1,>=4.2`**, i.e. it would force Django off the pinned 5.0.x
line back onto 6.x. 2.4.0 has no Django constraint.

### Before / after

| | Before (old venv) | After (rebuilt venv) |
|---|---|---|
| Python | 3.12 | 3.12 |
| Django | **6.0.7** | **5.0.14** (`>=5.0,<5.1` ✓) |
| structlog | 24.4.0 | 24.4.0 |
| channels | 4.3.2 | 4.3.2 |
| channels-redis | 4.3.0 | 4.3.0 |
| django-prometheus | – | 2.4.0 |
| python-decouple | – | 3.8 |
| Jinja2 | – | 3.1.6 |
| requests | (undeclared) | 2.34.2 (restored for parity, see findings) |
| ruff | — | 0.16.3 (in-pin `>=0.6,<1`) |
| `pip check` | — | clean |
| `manage.py check` | OK | OK (no issues, 0 silenced) |

`pip check` after rebuild:

```
No broken requirements found.
```

---

## Issue 2 — Migration drift in four apps

`python manage.py makemigrations --check --dry-run` exited `1` with pending
changes in `recommendations`, `rule_engine`, `signals_engine`, and
`trader_memory`.

### Root cause

The drift persisted after the Issue-1 venv rebuild (exit 1 on both Django 6.0.7
and 5.0.14), so it is **not** version-caused — it is genuine pre-existing drift:

1. **`help_text` drift.** `backend/core/models.py` adds `help_text` to the
   five BaseModel fields (`id`, `created_at`, `updated_at`, `is_deleted`,
   `deleted_at`). These apps' `0001` migrations were generated before the
   `help_text` was added, so Django wants to emit `AlterField`s for them.
2. **Index-name drift.** The models declare `Meta.indexes` **without** explicit
   `name=`, so Django derives a name that differs from the explicit name baked
   into the `0001` migrations (e.g. `signals_engine_signal_sym_created` →
   `signals_eng_instrum_d7df11_idx`), producing `RenameIndex` operations.

### Migration set

Four migrations were generated with Django 5.0.14 and hand-inspected:

| App | Migration | SQL emitted |
|---|---|---|
| recommendations | `0005_rename_recommendat_symbol_ea83d2_idx_recommendat_symbol_9d6ca0_idx_and_more.py` | 1 × `ALTER INDEX … RENAME` + no-op field alters |
| rule_engine | `0004_alter_ruleconfig_created_at_and_more.py` | no-op field alters only |
| signals_engine | `0002_rename_signals_engine_signal_sym_created_signals_eng_instrum_d7df11_idx_and_more.py` | 2 × `ALTER INDEX … RENAME` |
| trader_memory | `0002_rename_trader_memo_recomme_6eb1be_idx_trader_memo_recomme_3b3392_idx_and_more.py` | 1 × `ALTER INDEX … RENAME` + no-op field alters |

`python manage.py sqlmigrate <app> <migration>` confirmed every `AlterField`
renders as `(no-op)` (zero SQL) and the only real statements are four
`ALTER INDEX … RENAME TO …` metadata renames. **All four migrations are
non-destructive** — no data is touched, no table rewritten.

### Applied

```text
Applying recommendations.0005_… … OK
Applying rule_engine.0004_… OK
Applying signals_engine.0002_… OK
Applying trader_memory.0002_… OK
```

Final check:

```text
$ python manage.py makemigrations --check --dry-run
exit code 0 — "No changes detected"
```

> Note: `manage.py migrate` accepts only **one** app label per invocation.
> `migrate recommendations rule_engine signals_engine trader_memory` fails with
> `unrecognized arguments`; run per-app.

---

## Issue 3 — AI prompt templates silently failing to load

### Root cause

`backend/apps/ai_engine/prompt_manager/service.py`, `_load_templates()`, logged
the success path with a **reserved** `LogRecord` attribute name:

```python
logger.info(
    "prompt_template_loaded",
    extra={
        "event_type": event_type,
        "filename": filename,      # 'filename' is reserved by LogRecord
        "version": version,
    },
)
```

`Logger.makeRecord` raises `KeyError: "Attempt to overwrite 'filename' in
LogRecord"` on every iteration. The broad `except Exception` swallowed it and
reported `prompt_template_load_failed` for **all 11 event types** — and because
the exception fired *before* `_ensure_persisted_version(...)`, template-version
persistence never ran either.

### Fix

Renamed the key to `template_filename` (the value is unchanged). Audit of every
`extra={...}` in the codebase (`apps/`, `core/`, `config/`) for reserved
`LogRecord` attributes found **two more live instances of the same bug**, fixed
under this issue:

| File | Reserved key | Renamed to |
|---|---|---|
| `apps/ai_engine/prompt_manager/service.py:54` | `filename` | `template_filename` |
| `apps/market_data/application/instrument_sync_service.py:80` | `created` | `created_count` |
| `core/exceptions.py:194` | `message` | `error_message` |

The `created` instance would crash the instrument-sync completion log at the
end of every sync; the `message` instance would crash the DRF exception handler
on every API error response.

### Before / after (boot log, development settings, INFO level enabled)

Before (all 11 event types fail; note the doubling is two log handlers):

```text
prompt_template_load_failed   ×22   error: "Attempt to overwrite 'filename' in LogRecord"
prompt_template_loaded        ×0
```

After:

```text
prompt_template_load_failed   ×0
prompt_template_loaded        ×22   (11 event types × 2 handlers)
```

### Regression test

`backend/apps/ai_engine/tests/test_prompt_manager_regression.py` — three tests:

1. all 11 `TEMPLATE_NAMES` entries have a loaded template at boot;
2. with INFO logging enabled on the module logger, no
   `prompt_template_load_failed` is recorded and `prompt_template_loaded` is;
3. with `PROMPT_VERSIONING_PERSISTENCE_ENABLED=True`, all 11 versions are
   persisted (proves the success path — including persistence — actually runs).

> Reproduction note: `Logger.log()` returns early when the level is disabled,
> so the reserved-key `KeyError` only fires when INFO is enabled. The tests
> enable INFO via caplog; otherwise the old bug is masked by the WARNING
> default (as it is under `config.settings.testing`, which uses a NullHandler).

Verified the tests fail on the old code (2 failed with the `filename` bug
reintroduced) and pass with the fix (3 passed).

---

## Verification (raw output)

```text
$ python manage.py check
System check identified no issues (0 silenced).

$ python manage.py makemigrations --check --dry-run
exit code 0 — "No changes detected"

$ pip check
No broken requirements found.

$ pytest -q
====== 34 failed, 1745 passed, 3 warnings, 15 errors in 116.06s ======
```

Full-suite comparison vs. the pre-existing baseline:

| | Baseline (pre-batch) | After remediation |
|---|---|---|
| passed | 1725 | **1745** (+17 Batch 2 +3 regression) |
| failed | 34 | 34 (all pre-existing, unchanged) |
| errors | 15 | 15 (all pre-existing, unchanged) |

Targeted suites: `apps/ai_engine` → 69 passed; market_data instrument-sync →
6 passed. The 7 market_data failures and 2 market_data collection errors are
pre-existing (see findings).

---

## Anything else discovered (findings — not fixed)

1. **Runtime dependencies undeclared in requirements files.** `python-decouple`
   (settings), `structlog` (core/logging.py), `channels` / `channels-redis`
   (INSTALLED_APPS + ASGI), `django-prometheus` (middleware + urls), `Jinja2`
   (prompt manager), and `requests` (5 provider/scan modules) are all imported
   by code but appear in **no** requirements file. The rebuilt venv had to
   install them manually. `requests` is the most dangerous: it was present
   (undeclared) in the old venv, so a clean CI/dev install of the declared
   requirements will break `zerodha_provider`, `chartink_scan_fetcher`,
   `fred_provider`, and `marketaux_provider` imports.
2. **`django-prometheus==2.5.0` excludes Django 5.0.x** (`Django!=5.0.*,<6.1`).
   Pin 2.4.0 (or bump the Django line) if it is ever upgraded.
3. **`apps/recommendations/migrations/0004_rename_recommendat_symbol_ea83d2_idx_recommendat_symbol_9d6ca0_idx_and_more.py`
   lies.** Generated by Django 6.0.7, its filename promises an index rename plus
   field alterations, but the file contains only two `AddField`s; the rename and
   alters were silently dropped. The new `0005` performs what 0004's name claims.
4. **`opencv-python-headless`** (~500MB) was installed in the old venv but is
   imported nowhere — a stray package that inflated the old venv.
5. **`psql` is not installed** on this machine; PostgreSQL inspection had to go
   through `manage.py shell` / `django.db.connection`.
6. **`pytest-asyncio` / `pytest-xdist`** are listed in
   `requirements/development.txt` but not in `requirements/dev.txt` and are not
   installed; the suite runs fine without them, so the discrepancy is harmless.
7. **Pre-existing suite failures/errors unchanged** (34 failed / 15 errors):
   journal, recommendations, execution, market_data, rule_engine,
   trader_memory, replay, audit_log. Known items: `apps/execution/infrastructure/repositories.py:188`
   `F821 datetime`; `CELERY_TASK_QUEUES` as a string list breaks the AMQP
   router; dashboard `side` `CharField(4)` truncates `SHORT`; dashboard has no
   migrations package; `strategy_registry` has no tests.
