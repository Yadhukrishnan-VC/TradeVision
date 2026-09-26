# Rollback / Incident Procedure — Live Broker Execution

**Status:** defined. This document exists to satisfy ADR-030 §5.3 gate item 4
(execution.E007): a written incident/rollback procedure for live-execution
misbehaviour must exist before `BROKER_ENVIRONMENT=live` is reachable.

**Full runbook:** the detailed, sanctioned runbook for Phase 2 incidents lives
at `docs/PHASE2_ROLLBACK_RUNBOOK.md`. This page is the short-form summary that
the startup gate points at; the runbook is the operative document a human
follows during an incident.

---

## One-paragraph summary

If the live adapter misbehaves in any way (duplicate/wrong orders, unexpected
positions, retry storm, unreconcilable numbers): **halt first, investigate
second.** Block all order flow with the global kill switch, freeze broker-side
and app-side evidence, reconcile against broker truth, fix the root cause, and
only re-enter after a clean sandbox re-run and explicit owner approval.

## Quick actions (in order)

1. **Halt — management command (works even if the API is down):**
   ```bash
   docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml \
       exec backend python manage.py kill_switch --activate --scope GLOBAL \
       --reason "live adapter incident: <one-line symptom>"
   ```
   Verify: `manage.py kill_switch --status`. Every order attempt is now
   rejected with `KILL_SWITCH_ACTIVE` (proven end-to-end by
   `backend/apps/risk_management/tests/integration/test_kill_switch_halt_e2e.py`).
2. **Halt — API path (if the API surface is healthy):**
   `POST /api/v1/risk-management/kill-switch/activate/`
   `{"scope": "GLOBAL", "reason": "live adapter incident"}` with a
   `manage:risk_policy` API key.
3. **Belt-and-braces:** `docker compose ... stop celery-worker-execution
   celery-beat`, and/or set `EXECUTION_ENGINE_ENABLED=False` + restart.
4. **Freeze evidence** (§2 of the runbook): dump Kite orders/positions/trades,
   app order/decision/audit rows, and the running `BROKER_/ZERODHA_/RISK_` env.
5. **Reconcile** (§3 of the runbook) against broker truth using the existing
   reconciliation machinery; never hand-edit position/capital rows.
6. **Fix the root cause**, re-run sandbox smoke test green
   (`scripts/kite_sandbox_smoke_test.py`), confirm risk caps unchanged.
7. **Re-enter** only after the project owner explicitly approves resumption:
   ```bash
   ... exec backend python manage.py kill_switch --deactivate --scope GLOBAL \
       --reason "incident <id> closed, owner approved"
   ```

## Golden rules

- Halt before diagnosing; every extra minute is real-capital exposure.
- Freeze evidence before touching state.
- Never "correct" books to match the broker manually — record drift, fix cause,
  let reconciliation repair run.
- The kill switch blocks *new* orders at the risk gate; stopping workers also
  silences in-flight retries.
- Any real-money discrepancy unexplained within the hour: keep GLOBAL ON,
  escalate to the project owner.

## Related

- `docs/PHASE2_ROLLBACK_RUNBOOK.md` — full incident runbook (triage table,
  evidence freeze scripts, reconciliation, re-entry checklist, audit trail,
  escalation).
- `docs/PHASE2_GATE_STATUS.md` — current ADR-030 gate status.
- `docs/adr/ADR-030-live-broker-execution-phase-1.md` — the gate conditions
  (§5), including this written-procedure requirement.