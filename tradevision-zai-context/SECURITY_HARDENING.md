# Security hardening

> Workstream WS5 — analytics cross-account ownership (IDOR/BOLA), one
> production blocker in the analytics read model, plus secret-handling and
> CORS audits. Builds on WS2 (rate limiting) and WS3 (WebSocket auth).

## 1. Analytics REST IDOR/BOLA — fixed

The four analytics endpoints in `apps/dashboard/interfaces/api/analytics_risk/views.py`
accepted an arbitrary `account_id` from the URL and returned that account's
data to **any** authenticated caller:

- `GET /api/v1/dashboard/accounts/<uuid>/pnl`
- `GET /api/v1/dashboard/accounts/<uuid>/pnl/daily`
- `GET /api/v1/dashboard/accounts/<uuid>/performance`
- `GET /api/v1/dashboard/accounts/<uuid>/risk`

They performed no ownership check (trading-core REST views already keyed off
`request.user.id`, and the WebSocket consumers were fixed in WS3).

### Fix

`AccountOwnershipMixin._ensure_own_account()` now requires
`str(request.user.id) == str(account_id)` and raises `NotFound` (404) otherwise.
Because `APIKeyAuthentication` resolves a key to its **owning user**, this one
identity check covers both JWT Bearer and `Api-Key` auth uniformly. 404 (not
403) is deliberate: it does not disclose that another account exists.

### Regression tests

`apps/dashboard/tests/analytics_risk/integration/test_account_ownership.py`
drives the real `JWTAuthentication` + `APIKeyAuthentication` over HTTP:

- JWT user reads own account on all four endpoints → 200
- JWT user requests another user's account → 404 on all four
- API key (owner B, correct scopes) requests owner A's account → 404 on all four
- API key reads its owner's account → 200 on all four
- unauthenticated → 401

## 2. Analytics read-model write path was broken — fixed

All five analytics projection models
(`apps/dashboard/infrastructure/analytics_risk/models.py`) declared
`id = models.UUIDField(primary_key=True)` **without a default**. The
projectors (`PerformanceRollupProjector`, `RiskMetricProjector`, wired via
`subscribe_internal("trade_record_projected", ...)`) and the repositories use
`update_or_create`, so the first write for any account failed with
`IntegrityError: null value in column "id"`.

Fix: `default=uuid4` on the five PKs. This is a Python-side (ORM) default —
the existing `NOT NULL` DB column needs no schema change, and the app has no
migrations package (`showmigrations dashboard` = none), so no migration is
produced. This greens the two pre-existing
`TestPerformanceSnapshotRepository::test_upsert_{creates,updates}` failures.

## 3. Pre-existing analytics view unit tests — repaired

`apps/dashboard/tests/analytics_risk/unit/test_views.py` asserted views under
`@override_settings(REST_FRAMEWORK={"DEFAULT_PERMISSION_CLASSES": [AllowAny]})`
with **unauthenticated** requests. The override cannot affect views that set
explicit `permission_classes`, so DRF's `permission_denied` produced 401
(`NotAuthenticated`, because authenticators exist but none succeeded) for all
eight tests. Rewritten to force-authenticate a real viewer user with
`rest_framework.test.force_authenticate`; they now exercise the actual
permission + ownership path.

## 4. Secret handling audit — clean

- API keys: `APIKeyService.create_key` uses `secrets.token_urlsafe(32)`; only a
  hash is persisted (`key_hash`, `max_length=128`, unique); the raw key is
  returned once and never logged or stored (`apps/accounts/application/services.py`).
- No code logs passwords, tokens, raw keys, request bodies, or
  `Authorization` headers. The only secret-adjacent log line is a *warning that
  the webhook shared secret is not configured*
  (`apps/ingestion/application/services.py:81`) — no secret value is logged.

## 5. CORS audit — clean

`config/settings/base.py`: `CORS_ALLOWED_ORIGINS` reads from
`CORS_ALLOWED_ORIGINS` env (empty by default → no cross-origin access) and
`CORS_ALLOW_CREDENTIALS=False` (correct: auth is header-based, no cookies).
`config/settings/development.py` sets `CORS_ALLOW_ALL_ORIGINS=True` for local
dev only. No `Access-Control-Allow-Origin: *` in any prod profile.

## 6. Rate limiting + WebSocket hardening recap

- **WS2**: DRF throttling — `anon=120/hour`, `user=6000/hour` (env-overridable),
  `auth=15/min` on login/refresh, `api_keys=30/hour` on the API-key endpoints.
  Verified by 8 unit tests that bind a fresh `LocMemCache` to
  `SimpleRateThrottle.cache` (override_settings is ineffective for class-attrs).
- **WS3**: WebSocket consumers close 4029 for unauthenticated users and for
  `account_id != user.id`; 18 protocol-level tests.

## 7. Verification

```bash
cd backend
# dashboard suite — previously 170 passed / 12 failed, now all green:
.venv/bin/pytest apps/dashboard -q          # 189 passed
.venv/bin/pytest apps/accounts apps/common apps/health apps/portfolio_reconciliation -q  # 163 passed
```

Full-suite pre-existing failures (unrelated to this work — reproduced with
changes stashed) remain in Batch 1 and other apps: journal, recommendations,
execution, market_data, rule_engine, trader_memory, replay, audit_log. See
`DEEPSEEK_PARALLEL_IMPLEMENTATION_REPORT.md` for the inventory.

## 8. Known gaps (documented, not fixed)

- `apps/execution/infrastructure/repositories.py:188` — `F821` undefined name
  `datetime`; execution is Batch-1 owned.
- Migration drift: `recommendations` (unassigned), `rule_engine`,
  `signals_engine`, `trader_memory` (Batch 1). `apps/dashboard` has no
  migrations package at all.
- `CELERY_TASK_QUEUES` string-list breaks the AMQP router in non-eager mode.
- Dashboard `side` `CharField(max_length=4)` truncates `SHORT`.