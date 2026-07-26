# ADR-013: Event Bus Transport — Redis Streams vs. Redis Pub/Sub

**Status:** Approved
**Date:** 2026-07-26
**Author:** Architecture Authority
**Product:** TradeVision AI

## Context

The EventBus (`core/events/event_bus.py`) is responsible for reliable delivery of `AnalysisEvent` messages from the Rule Engine to the AI orchestration pipeline. Phase 0 implemented it using Redis Pub/Sub, which provides at-most-once delivery semantics — a message published with zero subscribers connected is permanently lost, silently.

As the system matures toward Tier 1 (Market Data ingestion, real AnalysisEvent publication), losing events due to subscriber availability gaps is unacceptable for a system whose recommendations may drive financial decisions. We need a transport that guarantees at-least-once delivery with consumer group semantics.

## Decision

**Adopt Redis Streams for `AnalysisEvent` publication and consumption.** Retain Redis Pub/Sub exclusively for the notifications / WebSocket fan-out path (Django Channels), which has genuinely weaker delivery requirements.

### Why not Pub/Sub

| Concern | Pub/Sub | Streams |
|---|---|---|
| Message persistence | None — lost if no subscriber is connected | Persisted until explicitly acknowledged or trimmed |
| Consumer groups | Not supported — fan-out only | Native `XREADGROUP` — exactly-once-per-group processing |
| Replay capability | Impossible | A new consumer group can read from any point in the stream |
| Dead-letter support | Must be hand-rolled entirely | `XCLAIM` / `XAUTOCLAIM` provide retry primitives |
| Suitability for AnalysisEvent | **Not appropriate** — losing an event is safe for fire-and-forget notifications but not for analysis pipeline triggers | **Correct fit** — at-least-once, consumer groups, replay for debugging |

### Why Pub/Sub is retained for notifications

The Django Channels WebSocket layer (notifications, user alerts) is a broadcast pattern: publish once and deliver to all currently-connected subscribers. If no one is connected, losing the message is acceptable because the backing data persists in PostgreSQL. Pub/Sub's lower overhead and zero persistence cost make it the right choice for that path.

## Consequences

1. **EventBus API change**: `publish_analysis_event` now returns a stream entry ID (`str`) instead of a subscriber count (`int`). `subscribe_analysis_events` now requires `consumer_group` and `consumer_name` parameters. A new `ack_event` method is added for explicit acknowledgment.
2. **Backward compatibility**: Since no production consumers exist yet (Phase 0 has no active Rule Engine publishing events), this is a clean cutover with zero data migration cost.
3. **Operational responsibility**: Streams retain data until trimmed. `MAXLEN ~ N` approximate trimming is applied on every `XADD` call, bounded by `settings.EVENT_STREAM_MAXLEN`. This value must be revisited once Tier 1's real volume is understood.
4. **Redis resource usage**: Slightly higher memory and CPU overhead compared to Pub/Sub, but negligible at the expected volume (AnalysisEvents fire only when a rule matches, not on every tick — ticks stay in TimescaleDB).
5. **Notifications path unaffected**: The `channels` layer continues to use Redis Pub/Sub and is not touched by this change.

## Implementation Notes

- One Redis stream per event type (`analysis_event:{event_type}`), matching the existing `EventChannel` naming convention.
- Single consumer group per logical consumer role (e.g., `tradevision:rule-engine-workers`), composed of `settings.EVENT_STREAM_CONSUMER_GROUP_PREFIX` and a role suffix.
- Consumer group creation is idempotent (`XGROUP CREATE ... MKSTREAM`, ignoring `BUSYGROUP` errors on subsequent starts).
- Every consumer MUST call `ack_event` after successfully processing a message, or the message will be redelivered after the consumer group's idle timeout.
- `MAXLEN` approximate trimming (`~ N`) on every `XADD` call via `settings.EVENT_STREAM_MAXLEN` (default 10000).
