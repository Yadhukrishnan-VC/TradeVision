# Empty-module assessment

> Workstream WS8 — classification of near-empty / skeleton application modules.
> Documentation only; no code changed.

## Classification summary

| Module | Code (non-test, non-migration) | In INSTALLED_APPS | Wired | Tests | Verdict |
|---|---|---|---|---|---|
| `announcements` | 0 lines | no | no | none | **NOT REQUIRED** (empty scaffold) |
| `global_markets` | 0 lines | no | no | none | **NOT REQUIRED** (empty scaffold) |
| `market_breadth` | 0 lines | no | no | none | **NOT REQUIRED** (empty scaffold) |
| `notifications` | 0 lines | no | no (queue-name string only) | none | **NOT REQUIRED** (empty scaffold) |
| `options_chain` | 0 lines | no | no | none | **NOT REQUIRED** (empty scaffold) |
| `risk_analysis` | 0 lines | no | no | none | **NOT REQUIRED** (empty scaffold) |
| `strategy_registry` | 196 lines | yes | yes | **zero** | **DEFERRED** — implemented, untested |
| `replay` | 104 lines | yes | yes | 1 failing of several | **DEFERRED** — pre-existing test failure |

## Empty scaffolds (announcements, global_markets, market_breadth, notifications, options_chain, risk_analysis)

Every Python file is an empty placeholder (`urls.py`, `views.py`, `models.py`,
`services.py`, `serializers.py`, `repository.py`, `tasks.py`, `admin.py`,
`consumers.py`, `apps.py`, plus empty `tests/` stubs). None of these apps are
in `INSTALLED_APPS`, none appear in `config/urls.py`, and none produce
tables. `notifications` appears in `CELERY_TASK_QUEUES` only as a queue-name
string (intended routing, harmless — queue names are just labels).

**Verdict: NOT REQUIRED for this batch.** They are un-wired scaffolding for
future features, not production risk. Recommendation: delete them in a
clean-up batch, or implement them deliberately behind a feature gate. Their
presence does not affect CI, tests, or the running system.

## strategy_registry — DEFERRED

In `INSTALLED_APPS` and genuinely wired:
- `tasks.match_packet` registered as `tradevision.strategy_registry.match_packet`
  routed to the `ai_reasoning` queue
- `consumers.register_consumers()` subscribes to `PRICE_MOVEMENT` events
- `StrategyMatcher.match()` (services.py) + a real `TradingStrategy` model
  (admin, consumers)

The task's deserialization target (`EnrichedIntelligencePacket`) exists in
`core.events.event_types`. The logic is coherent, but the module has **zero
tests**. Because it only becomes active when `PRICE_MOVEMENT` packets are
emitted through the event bus (a later-stage dependency), it is not a blocker
for this batch — flagged for the report as a wired-but-untested module.

## replay — DEFERRED

In `INSTALLED_APPS`, with `replay_service.py` (73 lines), event handlers, and
tests. One pre-existing failure:
`test_replay_by_correlation_id` → `duplicate key value violates unique
constraint "eventbus_storedevent_pkey"`. This is a test-isolation defect of
the same class as the watchlist committed-transaction issue (stored events
leaked into the reused test DB), not a replay-logic regression. Flagged for
the report; not fixed here (touching `eventbus` store behavior is out of
scope and Batch-adjacent).

## Bottom line

No empty module blocks production readiness. The two thin modules with real
code (strategy_registry, replay) are functional-but-flagged and do not gate
the GO/NO-GO for the workstreams delivered in this batch.