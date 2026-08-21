# Phase 1 Sandbox Smoke Test — Evidence (ADR-030)

**Status: PARTIALLY VERIFIED — order-flow steps PENDING a credentialed run.**
**Date of probe:** 2026-08-21
**Endpoint under test:** `https://sandbox.kite.trade` (Kite Connect v3 shared demo app, `api_key=sandboxdemo`)
**Adapter:** `apps/execution/infrastructure/brokers/zerodha_broker.py` (`ZerodhaBroker`)

## Why this is not just unit tests

The adapter's CI tests inject an in-memory Kite client double (per ADR-030's
"CI makes no live calls" constraint). This page records what has been
verified against the **real** endpoint so far, and exactly how to finish the
verification once credentials are available.

## 1. Verified against the real endpoint (2026-08-21, no user session required)

These probes were made from this environment with `curl` / `requests`,
using only the public demo app id — no tokens, no secrets:

| # | Probe | Request | Observed response | What it proves |
| --- | --- | --- | --- | --- |
| 1 | Endpoint reachability | `GET https://sandbox.kite.trade/` | HTTP 200 | Host exists and serves traffic; not a mock |
| 2 | Login flow present | `GET /connect/login?api_key=sandboxdemo` | HTTP 302 → `.../connect/login?api_key=sandboxdemo&sess_id=…` → HTTP 200 (Kite login SPA) | The documented login → `request_token` redirect flow is really there |
| 3 | `/oms` route prefix on order routes | `GET https://sandbox.kite.trade/oms/orders`, headers `X-Kite-Version: 3`, `Authorization: token sandboxdemo:<dummy>` | HTTP 403, body `{"status":"error","message":"Incorrect \`api_key\` or \`access_token\`.","data":null,"error_type":"TokenException"}` | Order routes are served under `/oms` exactly as the adapter patches them; auth failures surface as Kite's standard error envelope (`TokenException`) which the adapter lets propagate as retryable — never as an order rejection |
| 4 | Public instruments dump (the `/oms`-exempt route) | `GET https://sandbox.kite.trade/instruments/NSE` | HTTP 200, 590949 bytes, 10,093 CSV rows (`instrument_token,exchange_token,tradingsymbol,…`) | Route-patch passthrough set matches reality; response shape is genuine Kite |

Captured envelope (verbatim, also pinned in
`backend/apps/execution/tests/integration/fixtures/zerodha_sandbox_order_flow.json`
under `observed_live`):

```json
{"status":"error","message":"Incorrect `api_key` or `access_token`.","data":null,"error_type":"TokenException"}
```

Fixture-backed integration tests pin this behaviour without live calls:
`test_zerodha_broker_fixture.py::TestZerodhaSandboxFixtureLiveShapes`
(envelope shape, `TokenException` propagates and blocks placement,
idempotent replay places exactly one broker order).

## 2. PENDING — authenticated order lifecycle (needs a real session)

The following steps could not be executed because no usable *user session*
exists in this environment:

- [ ] **PENDING: place a LIMIT order** via `ZerodhaBroker.place_order` against the real endpoint.
- [ ] **PENDING: fetch its status** via `get_order_status` (expect OPEN/PENDING for a resting price).
- [ ] **PENDING: cancel it** via `cancel_order` (expect CANCELLED).
- [ ] **PENDING: idempotent placement proof (ADR-030 §4)** — retry `place_order`
      with the same `correlation_id` tag and confirm exactly one broker-side
      order carries that tag.

### Why pending

Minting an access token requires an interactive browser login with a
*sandbox user* account (login → redirect with single-use `request_token` →
`generate_session()`). The project owner has no sandbox-user provisioning
and — importantly for the record — reports that Zerodha does not provide an
official sandbox to them; per owner instruction, **live credentials must not
be used or requested for this test**. The authenticated smoke run will be
performed separately by the owner using their own Kite Connect app when the
environment is ready.

> Note for ADR-030 reviewers: §1 records the sandbox as available (verified
> 2026-08-17). This probe confirmed the endpoint itself behaves as
> documented, but the demo-user login could not be obtained, so the ADR's
> availability claim should be treated as unconfirmed until the credentialed
> run completes. Gate condition §5.5 (observation period) stays open either way.

### How to run it when ready

`scripts/kite_sandbox_smoke_test.py` drives the REAL adapter end-to-end and
records every HTTP request/response pair to a JSON evidence file:

```bash
# 1. Log in at:  https://<kite-host>/connect/login?api_key=<your api_key>
# 2. Copy request_token from the redirect URL.
cd backend && .venv/bin/python ../scripts/kite_sandbox_smoke_test.py \
    --request-token <TOKEN> --output /tmp/opencode/kite_sandbox_smoke_evidence.json
# (or pass --access-token <TOKEN> directly)
```

The script asserts, in one run: session exchange, LIMIT placement, idempotent
retry (same tag ⇒ same order ref, one order with that tag), status read,
cancel, final CANCELLED status. Append its output to §3 below and tick the
§2 boxes.

## 3. Credentialed run results

*(empty — to be filled by the owner's separate smoke run)*

## Related evidence

- Unit tests (in-memory double): `backend/apps/execution/tests/unit/test_zerodha_broker.py`
- Fixture-shape integration tests incl. live-captured error envelope:
  `backend/apps/execution/tests/integration/test_zerodha_broker_fixture.py`
- Startup guard still blocking `live`: `backend/apps/execution/tests/integration/test_live_startup_guard.py`
