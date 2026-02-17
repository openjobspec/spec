# RFC-0005: Standardized Event System

- **Stage**: 0 (Strawman)
- **Champion**: TBD
- **Created**: 2025-07-25
- **Last Updated**: 2025-07-25
- **Target Spec Version**: 0.3.0

## Summary

This RFC proposes standardizing a real-time event delivery system across all OJS backends using Server-Sent Events (SSE) and WebSocket transports. It defines event types, subscription patterns, delivery guarantees, filtering capabilities, and the wire format for event streams, enabling operators and applications to observe job lifecycle changes in real time.

## Motivation

The existing `ojs-events.md` specification defines a rich event vocabulary (job lifecycle events, queue events, worker events) and a CloudEvents-inspired envelope format. However, it does not mandate a specific delivery mechanism. Today:

1. **Backend divergence**: The Postgres backend uses `LISTEN/NOTIFY` for real-time notifications, while the Redis backend uses Pub/Sub. Each backend exposes events through different APIs with different semantics, making it impossible to build a backend-agnostic event consumer.

2. **No standard subscription model**: The gRPC binding defines `StreamEvents` for event delivery, but there is no equivalent for HTTP-based clients. Browser-based admin UIs and monitoring dashboards cannot consume events without a backend-specific WebSocket or polling implementation.

3. **Missing delivery guarantees**: The spec defines event types but not delivery semantics. Can events be lost during network interruptions? Is replay supported? Operators need to know whether they can rely on the event stream for alerting and audit logging.

4. **No filtering standard**: Different consumers need different events. An admin dashboard cares about `queue.paused` and `worker.stopped`, while a workflow engine cares about `job.completed` and `job.failed`. Without standardized server-side filtering, every consumer receives all events and must filter client-side.

The v0.3 roadmap targets ecosystem expansion. A standardized event system is foundational for building admin UIs, monitoring integrations, webhook bridges, and third-party tooling that works across all OJS backends.

### Use Cases

1. **Admin dashboard**: A web-based admin UI subscribes to all events via SSE and renders a real-time job processing timeline.

2. **Alerting pipeline**: A monitoring system subscribes to `job.discarded` and `worker.stopped` events via WebSocket and triggers PagerDuty alerts.

3. **Workflow orchestration**: A workflow engine subscribes to `job.completed` and `job.failed` events with a filter on `workflow_id` to track workflow step completion.

4. **Audit logging**: A compliance system subscribes to all events with replay from a specific timestamp to reconstruct a complete audit trail after a consumer restart.

## Prior Art

### Sidekiq (Ruby)

Sidekiq provides lifecycle hooks (`sidekiq_retries_exhausted`, `after_perform`) but no real-time event stream. The Sidekiq Web UI polls the Redis backend for dashboard updates. Third-party tools like `sidekiq-statsd` instrument events by wrapping middleware.

**Lesson**: Polling-based dashboards have poor latency and waste resources. A push-based event stream is necessary for real-time UIs.

### BullMQ (TypeScript)

BullMQ uses Node.js `EventEmitter` for local events and Redis Pub/Sub for distributed events. Events include `completed`, `failed`, `progress`, `stalled`. The BullBoard dashboard subscribes to these events for real-time updates. There is no event replay or guaranteed delivery.

**Lesson**: Redis Pub/Sub is fire-and-forget with no replay. OJS needs a delivery tier above raw pub/sub for reliability.

### Temporal (Go/TypeScript)

Temporal provides a visibility store that supports queries over workflow execution history. Events are persisted and queryable via SQL-like syntax. The Temporal Web UI uses long-polling against the visibility store. Temporal also supports streaming via gRPC server streaming.

**Lesson**: Persisting events for queryability enables powerful debugging. OJS should define an optional event persistence tier.

### CloudEvents (Specification)

CloudEvents defines a vendor-neutral event envelope with standardized attributes (`specversion`, `id`, `type`, `source`, `time`, `subject`). OJS events already align with CloudEvents. Protocol bindings exist for HTTP (webhooks), AMQP, Kafka, and NATS.

**Lesson**: Aligning with CloudEvents enables interoperability with the broader event-driven ecosystem. OJS events should be valid CloudEvents.

## Detailed Design

### 1. Transport Bindings

#### Server-Sent Events (SSE)

SSE is the RECOMMENDED transport for HTTP-based event consumers. *Rationale: SSE is natively supported by browsers, requires no additional dependencies, and provides automatic reconnection.*

**Endpoint**: `GET /v1/events/stream`

**Request Headers**:
```
Accept: text/event-stream
Last-Event-ID: 01912e4a-7b3c-7def-8a12-abcdef123456  (optional, for replay)
```

**Query Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `types` | string (comma-separated) | Event type filter (e.g., `job.completed,job.failed`) |
| `queues` | string (comma-separated) | Queue name filter |
| `job_types` | string (comma-separated) | Job type filter |
| `since` | string (RFC 3339) | Replay events from this timestamp |

**Response** (200 OK, `Content-Type: text/event-stream`):

```
id: 01912e4a-7b3c-7def-8a12-abcdef123456
event: job.enqueued
data: {"specversion":"1.0","id":"01912e4a-7b3c-7def-8a12-abcdef123456","type":"job.enqueued","source":"/ojs/backend/redis","time":"2026-03-15T10:30:00.123Z","subject":"01912e4a-1234-7def-8a12-abcdef123456","data":{"job_id":"01912e4a-1234-7def-8a12-abcdef123456","type":"email.send","queue":"email","state":"available"}}

id: 01912e4a-8c4d-7ef0-9b23-bcdef1234567
event: job.started
data: {"specversion":"1.0","id":"01912e4a-8c4d-7ef0-9b23-bcdef1234567","type":"job.started","source":"/ojs/backend/redis","time":"2026-03-15T10:30:01.456Z","subject":"01912e4a-1234-7def-8a12-abcdef123456","data":{"job_id":"01912e4a-1234-7def-8a12-abcdef123456","type":"email.send","queue":"email","state":"active","attempt":1,"worker_id":"worker-001"}}

```

#### WebSocket

WebSocket is an OPTIONAL transport for bidirectional event communication. *Rationale: WebSocket enables client-initiated subscription changes without reconnecting.*

**Endpoint**: `GET /v1/events/ws` (upgrade to WebSocket)

**Subscribe message** (client → server):

```json
{
  "action": "subscribe",
  "subscription_id": "sub-001",
  "filters": {
    "types": ["job.completed", "job.failed"],
    "queues": ["email", "notifications"],
    "job_types": ["email.send"]
  }
}
```

**Unsubscribe message** (client → server):

```json
{
  "action": "unsubscribe",
  "subscription_id": "sub-001"
}
```

**Event message** (server → client):

```json
{
  "subscription_id": "sub-001",
  "event": {
    "specversion": "1.0",
    "id": "01912e4a-7b3c-7def-8a12-abcdef123456",
    "type": "job.completed",
    "source": "/ojs/backend/redis",
    "time": "2026-03-15T10:30:05.789Z",
    "subject": "01912e4a-1234-7def-8a12-abcdef123456",
    "data": {
      "job_id": "01912e4a-1234-7def-8a12-abcdef123456",
      "type": "email.send",
      "queue": "email",
      "state": "completed",
      "attempt": 1,
      "duration_ms": 143
    }
  }
}
```

#### gRPC (Existing)

The existing `StreamEvents` RPC in the gRPC binding already provides event streaming. This RFC does not modify the gRPC transport but ensures the event envelope format is consistent across all three transports.

### 2. Event Envelope

All events MUST use the CloudEvents v1.0 envelope format as defined in `ojs-events.md`, with the following required attributes:

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `specversion` | string | MUST | Always `"1.0"` |
| `id` | string (UUIDv7) | MUST | Unique event identifier |
| `type` | string | MUST | Event type (e.g., `job.enqueued`) |
| `source` | string (URI) | MUST | Event source (e.g., `/ojs/backend/redis`) |
| `time` | string (RFC 3339) | MUST | Event timestamp in UTC |
| `subject` | string | MUST | Subject identifier (typically job ID) |
| `data` | object | MUST | Event-specific payload |

### 3. Event Type Catalog

The following events MUST be emitted by all backends. Events are grouped by maturity level:

#### Core Events (Level 0)

| Event Type | Trigger | `data` Fields |
|------------|---------|---------------|
| `job.enqueued` | Job enters `available` state | `job_id`, `type`, `queue`, `state` |
| `job.started` | Worker begins execution | `job_id`, `type`, `queue`, `state`, `attempt`, `worker_id` |
| `job.completed` | Handler succeeds | `job_id`, `type`, `queue`, `state`, `attempt`, `duration_ms` |
| `job.failed` | Handler fails (per attempt) | `job_id`, `type`, `queue`, `state`, `attempt`, `error` |
| `job.discarded` | All retries exhausted | `job_id`, `type`, `queue`, `state`, `attempt`, `error` |

#### Extended Events (Level 1+)

| Event Type | Level | Trigger | `data` Fields |
|------------|-------|---------|---------------|
| `job.retrying` | 1 | Scheduled for retry | `job_id`, `type`, `queue`, `next_attempt_at`, `attempt` |
| `job.cancelled` | 1 | Job cancelled | `job_id`, `type`, `queue`, `cancelled_by` |
| `job.scheduled` | 2 | Future execution scheduled | `job_id`, `type`, `queue`, `scheduled_at` |
| `job.expired` | 2 | TTL elapsed | `job_id`, `type`, `queue`, `expired_at` |
| `queue.paused` | 4 | Queue paused | `queue`, `paused_by` |
| `queue.resumed` | 4 | Queue resumed | `queue`, `resumed_by` |
| `worker.started` | 3 | Worker process starts | `worker_id`, `queues`, `concurrency` |
| `worker.stopped` | 3 | Worker process stops | `worker_id`, `reason` |
| `worker.heartbeat` | 3 | Worker heartbeat | `worker_id`, `active_jobs`, `uptime_ms` |

### 4. Subscription Filtering

Server-side filtering reduces bandwidth and client processing overhead. Backends MUST support the following filter dimensions:

| Dimension | SSE Parameter | WebSocket Field | Description |
|-----------|---------------|-----------------|-------------|
| Event type | `types` | `filters.types` | Match event type prefix (e.g., `job.*` matches all job events) |
| Queue | `queues` | `filters.queues` | Match queue name exactly |
| Job type | `job_types` | `filters.job_types` | Match job type exactly |

Wildcard patterns use `*` as a suffix-only glob. *Rationale: Prefix matching covers the common case (subscribe to all `job.*` events) without the complexity of full glob/regex support.*

### 5. Delivery Guarantees

OJS defines two delivery tiers:

#### Tier 1: Best-Effort (MUST)

All backends MUST support best-effort event delivery:

- Events are delivered to connected clients in real time
- Events MAY be lost if the client is disconnected at the time of emission
- No event persistence or replay
- Suitable for dashboards and monitoring where occasional missed events are acceptable

#### Tier 2: At-Least-Once (SHOULD)

Backends SHOULD support at-least-once delivery:

- Events are persisted for a configurable retention period (default: 1 hour)
- Clients can replay events from a specific event ID (`Last-Event-ID` in SSE) or timestamp (`since` parameter)
- Duplicate events MAY be delivered during reconnection
- Consumers MUST be idempotent or deduplicate by event `id`
- Suitable for workflow orchestration, alerting, and audit logging

#### Event Ordering

Events MUST be delivered in causal order per job. *Rationale: A `job.completed` event delivered before the corresponding `job.started` event would break consumer logic.* Events across different jobs MAY be delivered out of order.

### 6. Backend Requirements

| Requirement | Redis Backend | Postgres Backend | MUST/SHOULD |
|-------------|---------------|------------------|-------------|
| SSE endpoint | Pub/Sub → SSE bridge | LISTEN/NOTIFY → SSE bridge | MUST |
| WebSocket endpoint | Pub/Sub → WS bridge | LISTEN/NOTIFY → WS bridge | MAY |
| Event persistence | Redis Streams (XADD/XREAD) | Events table with BRIN index | SHOULD |
| Replay from ID | XREAD with ID | SELECT WHERE id > $1 | SHOULD |
| Replay from timestamp | XRANGE with timestamp | SELECT WHERE time >= $1 | SHOULD |
| Server-side filtering | Pub/Sub channel per type | WHERE clause | MUST |

### 7. SDK Integration

Each SDK SHOULD provide an event subscription client:

```go
// Go SDK
eventStream, err := client.SubscribeEvents(ctx, ojs.EventFilter{
    Types:  []string{"job.completed", "job.failed"},
    Queues: []string{"email"},
})
for event := range eventStream.Events() {
    fmt.Printf("Event: %s for job %s\n", event.Type, event.Subject)
}
```

```typescript
// TypeScript SDK
const stream = client.subscribeEvents({
  types: ["job.completed", "job.failed"],
  queues: ["email"],
});
for await (const event of stream) {
  console.log(`Event: ${event.type} for job ${event.subject}`);
}
```

```python
# Python SDK
async for event in client.subscribe_events(
    types=["job.completed", "job.failed"],
    queues=["email"],
):
    print(f"Event: {event.type} for job {event.subject}")
```

## Examples

### SSE Subscription with Filtering

```bash
# Subscribe to job completion events for the email queue
curl -N -H "Accept: text/event-stream" \
  "http://localhost:8080/v1/events/stream?types=job.completed,job.failed&queues=email"
```

### SSE Replay After Reconnection

```bash
# Resume from the last received event
curl -N -H "Accept: text/event-stream" \
  -H "Last-Event-ID: 01912e4a-7b3c-7def-8a12-abcdef123456" \
  "http://localhost:8080/v1/events/stream?types=job.*"
```

### Complete Event Stream for a Job Lifecycle

```
id: evt-001
event: job.enqueued
data: {"specversion":"1.0","id":"evt-001","type":"job.enqueued","source":"/ojs/backend/redis","time":"2026-03-15T10:30:00.000Z","subject":"job-123","data":{"job_id":"job-123","type":"email.send","queue":"email","state":"available"}}

id: evt-002
event: job.started
data: {"specversion":"1.0","id":"evt-002","type":"job.started","source":"/ojs/backend/redis","time":"2026-03-15T10:30:01.000Z","subject":"job-123","data":{"job_id":"job-123","type":"email.send","queue":"email","state":"active","attempt":1,"worker_id":"worker-001"}}

id: evt-003
event: job.completed
data: {"specversion":"1.0","id":"evt-003","type":"job.completed","source":"/ojs/backend/redis","time":"2026-03-15T10:30:01.150Z","subject":"job-123","data":{"job_id":"job-123","type":"email.send","queue":"email","state":"completed","attempt":1,"duration_ms":143}}

```

## Conformance Impact

The standardized event system is an OPTIONAL extension. Backends that implement it MUST pass the event-specific conformance tests.

New requirements introduced:

- **MUST**: Backends that expose an event stream MUST use the CloudEvents v1.0 envelope format. *Rationale: CloudEvents is the established standard for event envelopes, enabling interoperability with event-driven infrastructure.*
- **MUST**: Backends MUST support SSE as the baseline HTTP event transport. *Rationale: SSE is universally supported by HTTP clients and browsers without additional dependencies.*
- **MUST**: Events MUST be delivered in causal order per job. *Rationale: Out-of-order lifecycle events (e.g., completed before started) would corrupt consumer state.*
- **SHOULD**: Backends SHOULD support at-least-once delivery with event replay. *Rationale: Best-effort delivery is insufficient for alerting and audit logging use cases.*
- **MAY**: Backends MAY support WebSocket as an additional transport. *Rationale: WebSocket enables bidirectional communication for subscription management.*

## Backward Compatibility

This proposal is fully backward compatible. It introduces new HTTP endpoints (`/v1/events/stream`, `/v1/events/ws`) without modifying existing endpoints. Backends that do not implement the event system continue to function as before. SDKs that add event subscription methods do not break existing client code.

## Implementation Requirements

Per the OJS RFC process, proposals at Stage 2+ MUST include working prototypes in at least two languages:

- [ ] Go: SSE endpoint in `ojs-backend-redis` and `ojs-backend-postgres`
- [ ] TypeScript: Event subscription client in `ojs-js-sdk/src/events/`

## Alternatives Considered

### Webhooks Only

Relying exclusively on webhooks (outbound HTTP POST) for event delivery was considered. This was rejected because:

- Webhooks require the consumer to expose a public HTTP endpoint, which is not always feasible
- Webhook delivery has higher latency than streaming (TCP connection establishment per event)
- Webhooks are better suited for inter-service communication; SSE/WebSocket are better for real-time UIs

### WebSocket Only

Using WebSocket as the sole transport was considered. This was rejected because:

- WebSocket requires library support in all clients (not natively available in `curl` or browsers' `EventSource`)
- SSE provides automatic reconnection and `Last-Event-ID` replay natively
- WebSocket adds complexity (framing, ping/pong, close handshake) that is unnecessary for server-to-client push

### Kafka/NATS as Event Bus

Using a message broker (Kafka, NATS) as the event transport was considered. This was rejected because:

- It introduces an additional infrastructure dependency for all deployments
- The event system should be self-contained within the OJS backend
- Operators who want to bridge events to Kafka/NATS can consume from the SSE/WebSocket endpoint and forward events

## Open Questions

1. **Event retention**: What should the default and maximum retention period for persisted events? The Postgres backend can store events efficiently, but Redis Streams have memory implications.

2. **Backpressure**: How should the SSE/WebSocket endpoint handle slow consumers? Options: drop events, buffer with a size limit, or close the connection after a threshold.

3. **Authentication**: Should event streams require the same authentication as the job API, or is a separate event-scoped token appropriate?

4. **Cross-backend events**: In a federated deployment, should events from remote regions be forwarded to local event streams?

5. **Event schema evolution**: How should new event fields be added without breaking existing consumers? Proposed: new fields are always additive; consumers MUST ignore unknown fields.
