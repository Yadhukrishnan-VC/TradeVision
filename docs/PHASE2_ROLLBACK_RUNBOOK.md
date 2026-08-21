# Phase 2 Rollback / Incident Runbook — Live Broker Execution (ADR-030 §5.4)

**Scope:** what a human does when the live broker adapter (`BROKER_ADAPTER=zerodha`,
`BROKER_ENVIRONMENT=live`) misbehaves after the Phase 2 unlock. This runbook is
one of the five ADR-030 §5 gate conditions; it is written *before* Phase 2
starts and must be rehearsed on sandbox before any real-capital order.

**Status:** procedure defined; `live` remains unreachable (execution.E001) until
the owner signs off all five gate conditions — see
`docs/PHASE2_GATE_STATUS.md`.

---

## 0. Triage keywords

| Symptom | Go to |
| --- | --- |
| Orders duplicating, wrong quantity/symbol, unexpected fills | §1 Halt, then §3 Reconcile |
| Adapter raising repeatedly / retry storm | §1 Halt, then §2 Freeze evidence |
| Positions in broker that we did not expect | §1 Halt, then §3 Reconcile |
| Kill switch won't activate via API | §1.2 out-of-band path |
| Money/position numbers disagree with broker | §3 Reconcile, then §4 Report |

## 1. Halt trading first, investigate second

Every minute the adapter runs while misbehaving is real-capital exposure.
Halt **before** diagnosing.

### 1.1 Preferred path — management command (works even if the API is down)

```bash
# Block ALL order flow globally (RuleFired → risk evaluation rejects every order):
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml \
    exec backend python manage.py kill_switch --activate --scope GLOBAL \
    --reason "live adapter incident: <one-line symptom>"

# Or block one symbol only:
... exec backend python manage.py kill_switch --activate --scope SYMBOL \
    --symbol RELIANCE --reason "bad fills on RELIANCE"
```

Verify it took effect:

```bash
... exec backend python manage.py kill_switch --status
```

While any covering scope is active, the risk check chain rejects every
subsequent order attempt with `KILL_SWITCH_ACTIVE` — proven end-to-end by
`backend/apps/risk_management/tests/integration/test_kill_switch_halt_e2e.py`.

### 1.2 API path (when the API surface itself is healthy)

```
POST /api/v1/risk-management/kill-switch/activate/
Authorization: Api-Key <key with manage:risk_policy scope>
{"scope": "GLOBAL", "reason": "live adapter incident"}
```

### 1.3 Belt-and-braces: stop the workers

The kill switch blocks *new* orders at the risk gate. If you also want zero
broker traffic of any kind (in-flight retries included):

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml stop celery-worker-execution celery-beat
```

Set `EXECUTION_ENGINE_ENABLED=False` in `.env` and restart the stack to keep
workers up but inert to approvals:

```bash
docker compose ... restart backend celery-worker-default
```

## 2. Freeze the evidence

Do this before touching state, so the post-mortem works from facts:

```bash
# 1. Broker-side truth: dump orders + positions from Kite (sandbox or live).
#    Use the same credentials the adapter used (ZERODHA_ACCESS_TOKEN).
python - <<'PY'
from kiteconnect import KiteConnect
k = KiteConnect(api_key="...", root="https://api.kite.trade")  # sandbox: https://sandbox.kite.trade + /oms patch
k.set_access_token("...")
import json
print(json.dumps({"orders": k.orders(), "positions": k.positions(), "trades": k.trades()}, indent=2, default=str))
PY

# 2. Our side: order lifecycle + decisions + audit log (see §5 for locations).
docker compose ... exec backend python manage.py shell -c "
from apps.execution.infrastructure.models import Order, Fill
from apps.risk_management.infrastructure.models import RiskDecisionExecution
from apps.audit_log.infrastructure.models import AuditLogEntry
import json
print(json.dumps({
  'orders': list(Order.objects.values()),
  'fills': list(Fill.objects.values()),
  'risk_decisions': list(RiskDecisionExecution.objects.order_by('-created_at').values()[:200]),
  'audit_tail': list(AuditLogEntry.objects.order_by('-created_at').values()[:200]),
}, indent=2, default=str))"

# 3. Snapshot the running config (prove which env was live):
docker compose ... exec backend env | grep -E 'BROKER_|ZERODHA_|RISK_' > incident_env.txt
```

## 3. Reconcile positions against the broker

Compare broker truth (§2 step 1) against our portfolio read model, using the
existing reconciliation machinery rather than hand-editing rows:

```bash
# One pass per account (positions + orders):
docker compose ... exec backend python manage.py shell -c "
from django.contrib.auth import get_user_model
from apps.accounts.infrastructure.models import Account
from apps.portfolio_reconciliation.infrastructure.tasks import (
    reconcile_account_positions, reconcile_account_orders)
for a in Account.objects.all():
    print('positions:', reconcile_account_positions(str(a.id)))
    print('orders:', reconcile_account_orders(str(a.id)))"
```

- Every mismatch is classified and persisted as a `DriftRecord` (append-only)
  by `PositionReconciliationService` / `OrderReconciliationService`; safe
  repairs are applied row-by-row, everything else stays flagged for review.
- **Manual correction rule:** never `UPDATE` position/capital rows by hand to
  "match" the broker during an incident. Record the drift, fix the *cause*,
  let the reconciliation repair pass run, and re-run it until clean.
- If the broker shows open positions we did not intend: flatten them on the
  **broker side first** (Kite terminal/API), then re-run reconciliation so our
  books converge to broker truth. Document each flatten in the incident log.

## 4. Post-incident re-entry checklist

All boxes checked, in order, before deactivating the kill switch:

1. Root cause identified and fixed (code or config), fix deployed.
2. Reconciliation clean: zero unexplained `DriftRecord`s vs broker.
3. Sandbox smoke test re-run green against the same adapter build
   (`scripts/kite_sandbox_smoke_test.py`, evidence appended to
   `docs/PHASE1_SANDBOX_SMOKE_TEST.md`).
4. Risk caps still configured as signed off (`RISK_MAX_POSITION_SIZE`,
   `RISK_DAILY_LOSS_LIMIT`) — no silent loosening during the incident.
5. Owner explicitly approves resumption (this is a human decision, not a
   test result).

Then:

```bash
docker compose ... exec backend python manage.py kill_switch --deactivate \
    --scope GLOBAL --reason "incident <id> closed, owner approved"
```

## 5. Audit trail locations

| What | Where |
| --- | --- |
| Every kill-switch toggle (who/when/why) | `audit_log.AuditLogEntry`, `action='risk_management.KillSwitchActivated'/'KillSwitchDeactivated'`; raw state rows in `risk_management.KillSwitchState` |
| Every order attempt decision (approved/rejected + reason code) | `risk_management.RiskDecisionExecution` (+ published `risk_management.RiskApproved`/`RiskRejected` events on the event stream) |
| Order lifecycle (CREATED → … → terminal) | `execution.Order`, `execution.ExecutionRequest`, fills in `execution.Fill` |
| Position/order drift found during reconciliation | `portfolio_reconciliation` drift records (append-only) |
| Event transport history | Redis Streams (`EVENT_STREAM_MAXLEN`) — correlation_id threads RuleFired → decision → order → broker ref |

## 6. Escalation

- Any real-money discrepancy you cannot explain within the hour: keep the
  GLOBAL kill switch ON and escalate to the project owner.
- Suspected credential compromise: rotate Zerodha credentials, invalidate the
  access token (`DELETE /session/token`), keep the halt on.
