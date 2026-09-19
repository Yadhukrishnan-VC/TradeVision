# TradeVision — Local Live Paper Automation Batch Prompt
**Batch:** LOCAL-LIVE-PAPER-AUTOMATION-1  
**Audited state:** `trading-core` branch, HEAD `e1d0392` ("RULE-GATE-EDGE-RECONCILE-1")  
**Generated:** 2026-09-19  
**Governance:** BROKER_ENVIRONMENT=sandbox maintained throughout. No BROKER_ENVIRONMENT=live changes. No ADR-030 Phase 2 implementation. No live order execution. Phase 2 gate requires separate owner sign-off per `docs/PHASE2_GATE_STATUS.md`.

---

## 1. Audit context (verified against the repo tree)

**What's real and wired end-to-end (paper mode):**
- Django/Celery event-driven monolith: TA ingestion → `IntelligencePacket` → rule engine → risk management (9-check fail-closed pipeline, hard caps, kill switch) → `PaperBroker`. Real integration tests, not stubs.
- `ZerodhaTickerAdapter` and `ZerodhaBroker` are real implementations — tick parsing, reconnect backoff, idempotent order placement via correlation-id tags, Kite status mapping.
- Risk gate machinery for going live (ADR-030 §5) is unusually rigorous: hard position/loss caps, dual-path kill switch, rollback runbook, Django startup check (`execution.E001`) that refuses to boot with `BROKER_ENVIRONMENT=live`.
- React/Vite dashboard (~35 pages) exists despite `PROJECT_STATE.md` marking Phase 8 "NOT STARTED".

**What's deliberately switched off, by design:**
- `ZerodhaBroker` **hard-refuses** `BROKER_ENVIRONMENT=live` (`LIVE_UNREACHABLE_PHASE_1` / `LIVE_UNREACHABLE_NO_ALGO_REGISTRATION`). Intentional per ADR-030 — Phase 2 not implemented.
- Execution engine feature-flagged off by default (`EXECUTION_ENGINE_ENABLED`, default False) — even in paper mode, no order placed unless explicitly turned on.
- `rule_engine_ruleconfig` has **zero rows** in the audited state. The fail-closed gate (ADR-029 §4) means no rule can fire live regardless of what any backtest concluded, because a validated GO verdict was never published from the edge-validation report into the actual `RuleConfig` table.
- Edge validation itself is `PENDING real data` — the one statistically significant result found so far (`breakout_v1` in `RANGING`, p=0.001) came from a screening run across 47 NIFTY50 symbols, not from years of backfilled history, and hasn't been walk-forward/OOS-validated.
- **No in-app Zerodha login flow.** The repo does not implement the `request_token → generate_session` OAuth handshake. `ZERODHA_ACCESS_TOKEN` must be obtained manually, once, and expires **every day** (Kite Connect access tokens are valid until the next day's login-window reset, not 24h rolling).
- Two test-suite baselines in `docs/` (197 failed / 1719 passed vs 34 failed / 1745 passed) were never diffed under identical service conditions — divergence caused by service availability mismatch (Docker has Postgres/Redis/TimescaleDB; local venv doesn't).

**Net assessment:** the *scaffolding* for live/auto-execution is more mature than most solo trading projects get — the risk gates, kill switches, and idempotency are the parts people usually skip, and you didn't skip them. But the specific thing you're asking for right now — "run locally against a live market session with Zerodha connection and auto order execution" — is currently blocked by **five concrete, known gaps**, not by architecture problems.

---

## 2. Gaps standing between here and your stated vision

1. **No daily Zerodha login flow.** Needs a `request_token → access_token` exchange endpoint/command, because Kite Connect requires a fresh human-in-the-loop login every trading day (Zerodha platform constraint, not a TradeVision limitation).
2. **`EXECUTION_ENGINE_ENABLED` and `rule_engine_ruleconfig` are both effectively off.** Nothing will fire even in paper mode until the rule-gate reconciliation fix (already scoped in `docs/RULE_GATE_EDGE_RECONCILE_1.md`) is applied, and the flag is turned on.
3. **`BROKER_ENVIRONMENT=live` is architecturally blocked (ADR-030 Phase 2 not built)**, and additionally gated behind an `ALGO_REGISTRATION_ID` not yet set. This is the big one: going from paper to real orders means implementing Phase 2 of your own ADR, which requires the owner's separate, explicit, written sign-off per `docs/PHASE2_GATE_STATUS.md`.
4. **No validated trading edge yet.** Every regime/rule pair is either `NO-GO` or `INSUFFICIENT-DATA` against real data except one screening result that hasn't cleared walk-forward validation. Auto-executing real orders off an unvalidated edge is a different risk category.
5. **Two unreconciled test baselines** and a stale `PROJECT_STATE.md` (dashboard marked "NOT STARTED" when ~35 pages exist) — not blockers to running locally, but worth cleaning up before status docs are trustworthy for a go/no-go call.

---

## 3. Legal/regulatory note (not advice, just flagging what your repo already flags)

Your `tradevision.md` memory notes personal-use SEBI registration was assessed as "almost certainly not required," but `ZerodhaBroker` itself gates live execution behind `ALGO_REGISTRATION_ID` per India's evolving algo-trading rules for retail API-based execution. Worth a five-minute check of current SEBI/exchange circulars on algo tagging for retail API orders before flipping the live switch — rules here have been actively changing through 2025–2026. I'm not a lawyer and this isn't legal advice; just don't skip it.

---

## 4. Development prompt — hand this to whichever engineer/AI does the implementation batch

Copy everything below the line into your next DeepSeek/implementation batch.

```
BATCH: LOCAL-LIVE-PAPER-AUTOMATION-1

Context: TradeVision, branch trading-core, HEAD e1d0392. Owner wants to run the full stack locally against real Zerodha market data, with the existing rule engine → risk → execution pipeline automatically evaluating and (initially, in paper mode only) placing simulated orders through a live market session. Broker-live real-money execution is explicitly OUT OF SCOPE for this batch — do not touch ZerodhaBroker._validate_environment's refusal of BROKER_ENVIRONMENT=live, do not implement ADR-030 Phase 2, and do not remove execution.E001. That step requires the owner's separate, explicit, written sign-off per docs/PHASE2_GATE_STATUS.md — it is not part of this batch under any framing.

Objective: Local dev stack running live Zerodha tick data through the existing pipeline end-to-end in paper broker mode, with real (not mock) market data driving rule evaluation and simulated order placement, verifiably and reproducibly.

Deliverables, in order:

1. Zerodha daily login flow (the actual missing piece).
   - Add a management command or a thin authenticated internal endpoint that performs the Kite Connect request_token → generate_session exchange: print/open the Kite login URL (https://kite.trade/connect/login?api_key=...), accept the redirected request_token, call generate_session, and persist the resulting access_token — do not hardcode it in .env by hand each morning.
   - Store the token somewhere the running stack picks it up without a restart (Redis key, or a DB-backed settings row) since it changes daily and the stack shouldn't need docker compose restart every trading morning.
   - Add a startup/health check that surfaces "Zerodha session expired, re-login required" clearly (dashboard banner or a /api/v1/health/zerodha endpoint) rather than failing silently mid-session.
   - Test: a fixture-based test proving the exchange call shape, plus a manual runbook step in the deliverable doc for the one part that can't be automated (Zerodha's own login page requiring your 2FA).

2. Rule-gate reconciliation fix — apply what docs/RULE_GATE_EDGE_RECONCILE_1.md already scoped.
   - Implement the Phase-1 data migration it specifies: publish the Aug-22 edge-validation GO verdict (breakout_v1 / RANGING) into RuleConfig.validated_regimes, set enabled=True for that rule only.
   - Re-run manage.py rule_gate_report --verbose and paste real output proving breakout_v1 now shows ENABLED=yes under RANGING and every other rule still correctly shows NO_CONFIG/disabled (fail-closed for everything unvalidated).
   - Add the regression test the reconcile doc specifies (future GO-without-publish should never silently pass the gate again).

3. Turn the pipeline on for paper mode, end to end, with real ticks.
   - Set MARKET_DATA_PROVIDER=zerodha_ticker, BROKER_ADAPTER=paper, BROKER_ENVIRONMENT=sandbox, EXECUTION_ENGINE_ENABLED=True in a documented local .env profile (infra/.env.live-paper.example or similar — don't touch the safe-default .env.example).
   - Subscribe the ticker to a small, explicit watchlist (start with the ≤5 symbols already covered by the validated breakout_v1/RANGING regime — don't wire up all 47 screened symbols yet).
   - Prove the full chain fires during a real market session: tick → candle → TASnapshot → IntelligencePacket → rule evaluation → (if breakout_v1/RANGING fires) risk approval → paper order placement → Position/Order visible in the dashboard. Capture real log/DB output, not a description of what "would" happen — your project's own governance standard (see RULE_GATE_EDGE_RECONCILE_1.md's format) requires pasted command output, not assertions.
   - Explicitly confirm in the deliverable that BROKER_ADAPTER=paper throughout — no code path in this batch should be capable of reaching ZerodhaBroker.place_order.

4. Reconcile the two stale test baselines.
   - Run the full suite once with Docker-provided Postgres/Redis/TimescaleDB and once against the same services from a local venv (per the reconcile doc's own recommended next step), diff the two failure lists line-by-line, and update docs/TEST_SUITE_BASELINE_STATUS.md / docs/LIVE_READINESS_BLOCKERS.md into one current, trustworthy baseline.

5. Fix PROJECT_STATE.md drift.
   - The "Phase 8 — Frontend Dashboard: NOT STARTED" row is factually wrong given ~35 implemented pages in frontend/src/pages/. Update the Development Status table to reflect actual repo state before it's relied on for a go/no-go decision again.

Explicitly NOT in scope for this batch (flag and stop if asked to do these without separate owner approval):
- Anything that sets or reads ALGO_REGISTRATION_ID for the purpose of enabling live orders.
- Anything that weakens, removes, or bypasses execution.E001, ZerodhaBroker's LIVE_UNREACHABLE_* refusals, or the kill-switch paths.
- Expanding the live watchlist beyond the one validated rule/regime pair without a corresponding edge-validation run backing the new symbols/rules.

Acceptance criteria: owner can run docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d locally during NSE market hours, complete a one-time daily Zerodha login, watch real ticks flow into the dashboard, and see at least one real paper trade get placed, risk-checked, and logged from a live signal on breakout_v1/RANGING — with every step backed by pasted command/log output in the batch deliverable doc, in the same proof-of-execution format as your existing docs/ files.

---

## 5. Suggested order of operations on your end

1. Hand the prompt above to your implementation AI/engineer as the next batch.
2. Once paper mode is verifiably running live, watch it for a real observation period (your own PHASE2_GATE_STATUS.md condition #5) before thinking about Phase 2 at all.
3. Only then decide, deliberately and separately, whether to pursue the ADR-030 Phase 2 live unlock — that's a decision with real money and regulatory weight attached, and it's correctly gated behind your own sign-off, not a batch deliverable.