# WebSocket production hardening

> Workstream WS3 — WebSocket consumer tests + a cross-user data-exposure fix.

## Scope

The real-time surface lives under `ws/dashboard/*`:

| Consumer | Path | Auth | Group key |
| --- | --- | --- | --- |
| `DashboardHomeConsumer` | `/ws/dashboard/home/` | required | `dashboard.home.{user.id}` |
| `DashboardPortfolioConsumer` | `/ws/dashboard/portfolio/` | required | `dashboard.portfolio.{user.id}` |
| `DashboardPositionsConsumer` | `/ws/dashboard/positions/live/` | required | `dashboard.positions.{user.id}` |
| `DashboardOrdersConsumer` | `/ws/dashboard/orders/` | required | `dashboard.orders.{user.id}` |
| `PnLConsumer` | `/ws/dashboard/accounts/{account_id}/pnl/` | **fixed in WS3** | `pnl_{account_id}` |
| `RiskConsumer` | `/ws/dashboard/accounts/{account_id}/risk/` | **fixed in WS3** | `risk_{account_id}` |

## Security fix (WS3)

The two analytics-risk consumers (`apps/dashboard/interfaces/websocket/analytics_risk/consumers.py`)
accepted **any** `account_id` in the URL with no authentication and no
ownership check — a cross-user data exposure (IDOR/BOLA). They now:

1. Reject unauthenticated connections (missing or anonymous `scope["user"]`)
   with close code `4029` — the same code the trading-core consumers already used.
2. Reject connections whose `account_id` differs from the authenticated
   user's id (`str(account_id) != str(user.id)`) with close code `4029`.

This mirrors the REST contract: every dashboard read-model row is keyed by
`account_id == user.id` (see API-WIRING-CLOSURE-1 live verification), and the
frontend fetches analytics for the account id in the URL route, which is the
user's own id. The change is therefore strictly narrowing: legit self-access
is unchanged, cross-account access is now refused.

## Test harness

`channels.testing.WebsocketCommunicator` imports `daphne`, which is not a
project dependency, so WS3 ships a minimal in-process ASGI harness in
`apps/dashboard/tests/websocket/conftest.py` (`WSClient`) that speaks the ASGI
`websocket` protocol surface exactly the way a real server would:

- `websocket.connect` → consumer `connect()`
- `websocket.receive` (text) → consumer `receive_json()`
- `websocket.disconnect` → consumer `disconnect()`

Channel-layer events are delivered through the real `InMemoryChannelLayer`
(`config.settings.testing`), so `group_send` takes the same code path a
production Redis channel layer does.

## Coverage

`apps/dashboard/tests/websocket/` (18 tests):

- **Authentication** — every consumer rejects missing/anonymous users (close 4029).
- **Account ownership (IDOR)** — PnL/Risk reject a foreign `account_id`
  (close 4029) and accept the owner's own id.
- **Live delivery** — `home_summary_updated`, `portfolio_composition_updated`,
  `position_snapshot_updated`, `order_status_changed`, `pnl_update`,
  `risk_update` all reach the subscribed client.
- **Bulk snapshot** — positions consumer emits `position.snapshot_bulk` on connect.
- **Isolation** — user B never receives user A's group messages.
- **Disconnect** — the channel is discarded from its group on disconnect.
- **Client frames** — arbitrary JSON frames are ignored without crashing
  (trading-core no-op) or answered (`{"status": "ok", ...}` for analytics).

## Run

```bash
cd backend
# env as per CI.md / local test run
.venv/bin/pytest apps/dashboard/tests/websocket -q
```

## Remaining notes

- The WebSocket layer authenticates via Django **sessions**
  (`AuthMiddlewareStack` in `config/asgi.py`), not JWT. JWT/API-key auth is
  currently REST-only. If bearer-token WebSocket auth is required later, it
  must be added to the ASGI stack — out of scope here.
- There is no heartbeat/ping in the consumers. Long-lived idle connections
  rely on the deployment's proxy (Daphne/nginx) timeouts; a `ping` frame is a
  candidate follow-up.
- The frontend does not yet consume any WebSocket (all live data is REST);
  the WS surface is exercised only by tests until the UI wiring lands.