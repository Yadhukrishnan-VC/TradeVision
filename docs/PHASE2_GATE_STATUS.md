# Phase 2 Gate Status (ADR-030 §5)

**Verdict: NOT CLEARED.** `BROKER_ENVIRONMENT=live` remains unreachable and
must stay so until the project owner ticks every box below in person.
This page is the at-a-glance tracker; each row links to its evidence.

| # | ADR-030 §5 condition | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Explicit written sign-off from the project owner for Phase 2 | ☐ **OPEN** | Owner sign-off happens outside any batch, by decision. Nothing in this repo may infer it from green tests. |
| 2 | Hard-capped max order size & max daily loss, configured and enforced by `apps/risk_management` | ☑ **DONE** | Caps are env-configurable (`RISK_MAX_POSITION_SIZE`, `RISK_MAX_EXPOSURE_CAP`, `RISK_DAILY_LOSS_LIMIT` → `backend/config/settings/base.py`, documented in `.env.example`) and enforced pre-trade by the real chain: approved orders clamped to ≤ cap; daily-loss breach rejects with `DAILY_LOSS_LIMIT_EXCEEDED`. Proof: `backend/apps/risk_management/tests/integration/test_hard_caps_enforcement.py` |
| 3 | Tested, verified-working kill switch reachable via API **and** an out-of-band path | ☑ **DONE** | API path (`POST /api/v1/risk-management/kill-switch/activate/`) and out-of-band path (`manage.py kill_switch --activate --scope GLOBAL`) both proven end-to-end to halt the next order attempt (`RiskRejected` / `KILL_SWITCH_ACTIVE`), plus deactivate-restores-flow and per-symbol scope: `backend/apps/risk_management/tests/integration/test_kill_switch_halt_e2e.py`. Command: `backend/apps/risk_management/management/commands/kill_switch.py` |
| 4 | Defined rollback / incident procedure for live-adapter misbehaviour | ☑ **DONE** | `docs/PHASE2_ROLLBACK_RUNBOOK.md` — halt-first triage, both kill-switch paths, evidence freeze, broker reconciliation steps, audit-trail locations, re-entry checklist. Not yet *rehearsed* on a credentialed environment — rehearse before §1 sign-off. |
| 5 | Minimum observation period on sandbox before any real-capital order | ☐ **OPEN** | Cannot start: the authenticated sandbox smoke test is **PENDING** — no usable sandbox-user session exists and the owner will run the real-API smoke test separately with their own Kite Connect app. Probe evidence + exact procedure + pending checklist: `docs/PHASE1_SANDBOX_SMOKE_TEST.md`. The observation clock only starts after that run is green. |

## Guard that must not weaken while the gate is open

- [x] **`execution.E001` still fails startup on `BROKER_ENVIRONMENT=live`.**
      Proven against Django's real system-check machinery (`manage.py check`
      raises `SystemCheckError` carrying E001 even when
      `ALGO_REGISTRATION_ID` is set; registration alone satisfies only E003),
      plus a registration-integrity test if the check itself is ever dropped:
      `backend/apps/execution/tests/integration/test_live_startup_guard.py`.
- [x] Adapter-level defense-in-depth intact: `ZerodhaBroker` refuses `live`
      at construction (`LIVE_UNREACHABLE_PHASE_1`,
      `test_zerodha_broker.py::TestSessionAndSandbox`).
- [x] Default stays safe: `BROKER_ADAPTER=paper`, `BROKER_ENVIRONMENT=sandbox`.

## Batch summary (what landed)

**Part A — Phase 1 proof:** real-endpoint probes recorded in
`docs/PHASE1_SANDBOX_SMOKE_TEST.md` §1 (reachability, `/oms` routing,
auth-failure envelope, instruments dump). Authenticated order flow +
idempotency: PENDING owner run; adapter behaviour meanwhile pinned by
fixture tests using the live-captured shapes
(`test_zerodha_broker_fixture.py::TestZerodhaSandboxFixtureLiveShapes`).
Runnable procedure: `scripts/kite_sandbox_smoke_test.py`.

**Part B — gate machinery:** configurable hard caps (§5.2), dual-path
kill-switch integration proof + management command (§5.3), rollback runbook
(§5.4), startup-guard regression tests. No change to execution_engine core
logic, risk-limit values, or the paper default.

## To clear the gate

1. Owner runs the credentialed smoke test (procedure in
   `docs/PHASE1_SANDBOX_SMOKE_TEST.md` §2) and appends results to §3.
2. Observation period elapses clean on sandbox/paper.
3. Runbook rehearsed once (tabletop or sandbox).
4. Owner signs off §1 in writing; only then remove `execution.E001` **by
   design** in the Phase 2 unlock batch.
