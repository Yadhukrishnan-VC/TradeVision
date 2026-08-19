# ADR-030: Live Broker Execution — Phase 1 (sandbox adapter only)

**Status:** Proposed
**Date:** 2026-08-17
**Deciders:** Trading Core team (user + architect); the project owner gates Phase 2
**Depends on:** ADR-002 (event-driven architecture), EXEC-1 milestones
(`apps/execution` `BrokerAdapter` protocol), `apps/risk_management` gate
(kill switch, sizing, exposure limits)

## Context

`apps/execution` ships a single broker adapter, `PaperBroker`, and its
`application/ports.py` `BrokerAdapter` protocol explicitly documents that *"a
future live broker adapter implements only the protocol methods"*. Every prior
audit of this repo has insisted live trading stay out of reach: research →
broker execution must be a separate, phased project phase with hard limits
before any real capital moves.

This ADR is Phase 1 of a three-phase rollout:

- **Phase 1 (this batch):** a real broker **sandbox** adapter only. Zero real
  capital at risk. Goal: prove the adapter works against the real broker's API
  shape.
- **Phase 2 (future batch, NOT started):** limited real capital, hard-capped.
  Requires the explicit gate in §5 below.
- **Phase 3 (future batch, NOT started):** full production execution, only
  after Phase 2 has run clean for a defined observation period.

## Decision

### 1. Broker: Zerodha Kite Connect (sandbox mode)

The repo already targets Zerodha: `MARKET_DATA_PROVIDER=zerodha` is supported,
`ZERODHA_API_KEY` / `ZERODHA_ACCESS_TOKEN` already exist in settings and
`.env.example`, and `README.md` documents optional Zerodha integration. Zerodha
is therefore the decided broker; no new third-party dependency at the app level.

**Sandbox availability (verified 2026-08-17):** Kite Connect v3 provides an
official sandbox at `sandbox.kite.trade` with a shared demo app (`api_key`
`sandboxdemo`, `api_secret` `sandboxdemo-secret`) that is explicitly *"safe to
keep in plain text: not tied to a real account or real money"*. Older support
FAQ pages ("no sandbox") predate the v3 sandbox and are stale. Sandbox facts
the adapter relies on:

- Routes are served under an `/oms` prefix (except the instruments dumps).
- **Only `LIMIT` orders** are accepted; `MARKET` is rejected.
- GTT orders and margin calculations are not supported in the sandbox.
- Rate limits follow production (so the adapter is rate-limit-shaped by the
  same behaviour it will see live).

### 2. Adapter contract: exactly `BrokerAdapter`, nothing more

`ZerodhaBroker` implements only `place_order` / `cancel_order` /
`get_order_status` and the session plumbing required to call them. It does not
auto-size, split orders, or add any capability the paper broker lacks —
matching the paper broker's behaviour is the point of Phase 1. The execution
engine already supports non-simulated adapters
(`execution_engine.py:195-196`, single full fill at reference price) and
handles `BrokerRejection` through the existing error path, so **no frozen
component is modified**.

### 3. Settings-driven selection and hard sandbox guard

- `BROKER_ADAPTER=paper|zerodha` (default `paper`) selects the adapter through
  the factory in `apps/execution/infrastructure/brokers/__init__.py`
  (`get_broker_adapter()`), mirroring the `MarketDataProviderFactory` pattern.
  `apps/execution/infrastructure/tasks.py:process_order` now builds its engine
  via that factory (default behaviour unchanged: paper).
- `BROKER_ENVIRONMENT=sandbox|live` (default `sandbox`). A Django system check
  (`apps/execution/checks.py`, `execution.E001/E002`, registered from
  `execution.apps.ready()`) **fails startup** — never falls back silently —
  for `live` (the Phase-2 unlock does not exist yet) and for any unknown value.
  The adapter also refuses `live` at construction
  (`LIVE_UNREACHABLE_PHASE_1`) as defense-in-depth. `live` is therefore
  entirely unreachable in this batch.
- In sandbox mode the adapter falls back to the shared demo app
  (`sandboxdemo` / `sandboxdemo-secret`, `sandbox.kite.trade`) when
  `ZERODHA_API_KEY`/`ZERODHA_API_SECRET` are empty, and applies the `/oms`
  route patch. An operator can supply a real sandbox `access_token` (or a
  single-use `request_token` that the adapter exchanges via
  `generate_session`) to exercise the sandbox with a personal login.

### 4. Order mapping and idempotency

- Internal orders map to Kite `LIMIT` orders at `order.price` (the sandbox and
  the Kite API reject `MARKET`; the engine's internal type stays unchanged).
  `product` comes from `ZERODHA_PRODUCT` (default `MIS`, matching the sandbox
  docs). `BUY`/`SELL` derive from `Side.LONG`/`SHORT`.
- Symbols without an exchange prefix are assumed `NSE` (the paper broker's
  default market); `NSE:RELIANCE`-style symbols are split into
  exchange/tradingsymbol.
- **Idempotent placement.** `order.correlation_id` is sent as the Kite order
  `tag`. `place_order` first scans recent orders for a matching tag: a retried
  placement (e.g. after a network timeout mid-request) reuses the existing
  broker order instead of placing a second one. If the duplicate check itself
  fails (network), the placement is **not** attempted — the error propagates so
  the retry re-checks first. This guarantees a retry cannot produce two
  broker-side orders, and is covered by an explicit test.
- **Rejections use the existing error shape.** Kite `InputException` /
  `OrderException` / `DataException` surface as `BrokerRejection` (as the paper
  broker does); network/token/permission errors propagate for caller retry. No
  new exception type.

### 5. Phase 2 gate — written now, implemented later

Before Phase 2 (real capital) may start, ALL of the following must hold. This
batch implements none of them as code; it records the boundary so it is
explicit:

1. **Explicit written sign-off from the project owner** for Phase 2 — not
   inferred from "tests pass".
2. **Hard-capped maximum order size and maximum daily loss**, configured and
   enforced by `apps/risk_management` (which already has the machinery; Phase
   2's job is setting real numbers, not building new machinery).
3. **A tested, verified-working kill switch** reachable from both the API and
   an out-of-band path (e.g. a management command) so trading can be halted
   even if the API surface is unreachable.
4. **A defined rollback/incident procedure** for misbehaviour of the live
   adapter.
5. **A minimum observation period on sandbox** before any real-capital order
   is placed.

Only when all five are satisfied may `BROKER_ENVIRONMENT=live` be made
reachable — which also requires removing the Phase-1 startup check
(`execution.E001`) by design, not by accident.

### 6. Phase 3

Full production execution after Phase 2 has run clean for a defined
observation period. Removes remaining sandbox-only mappings (e.g. the LIMIT
translation) if the production account tier supports more order types, and
enables real credentials.

## Non-goals (this batch)

- Real capital, production credentials, Phase 2/3 implementation.
- Any change to `apps/execution/application/execution_engine.py`,
  `execution_request_service.py`, or any file under `apps/risk_management/`.
- Any change to risk limits or the kill switch.
- Removing or bypassing any paper-only execution path (the paper default is
  preserved).

## Consequences

- `BROKER_ENVIRONMENT=live` is unreachable in this batch; setting it fails
  Django startup. Sandbox-only credentials are the only reachable mode.
- A config change (`BROKER_ADAPTER=zerodha` + sandbox `access_token`), not a
  code change, is what a sandbox smoke test requires.
- The `kiteconnect` package is an **optional runtime dependency** for the
  zerodha adapter only (lazy-imported, matching the existing market-data
  adapter); it is not added to `requirements/`. Tests inject an in-memory
  client, so CI needs no `kiteconnect` and makes **no live calls**.

## References

- `kite.trade/docs/connect/v3/sandbox/` (sandbox credentials, `/oms` patch,
  LIMIT-only orders)
- `apps/execution/application/ports.py` (`BrokerAdapter` protocol)
- `apps/execution/infrastructure/brokers/paper_broker.py` (reference adapter)
- `core/market_data/provider_factory.py` (settings-driven factory precedent)
