# OJS Real-Time Status — Extension Specification

| Field        | Value                                      |
|-------------|---------------------------------------------|
| **Title**   | OJS Real-Time Job Status Updates            |
| **Version** | 0.1.0                                       |
| **Status**  | Experimental (Stage 1 — Proposal)           |
| **Maturity** | Experimental                                |
| **Date**    | 2026-02-19                                  |
| **Layer**   | 3 — Protocol Binding                        |
| **Depends On** | ojs-core.md, ojs-events.md              |

---

## Abstract

This extension defines how clients subscribe to real-time job status changes via **Server-Sent Events (SSE)** and **WebSocket** protocols. It eliminates the need for polling by pushing state-change notifications directly to connected clients.

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt).

---

## Table of Contents

1. [Introduction and Motivation](#1-introduction-and-motivation)
2. [Server-Sent Events (SSE) Binding](#2-server-sent-events-sse-binding)
3. [WebSocket Binding](#3-websocket-binding)
4. [Event Format](#4-event-format)
5. [Connection Management](#5-connection-management)
6. [Security Considerations](#6-security-considerations)
7. [Conformance Requirements](#7-conformance-requirements)
8. [Examples](#8-examples)
9. [SDK Implementation Guidelines](#9-sdk-implementation-guidelines)

---

## 1. Introduction and Motivation

Polling-based status checks create unnecessary load on the server and introduce latency between state transitions and client awareness. Real-time push notifications solve both problems by delivering events to subscribed clients the moment a job's state changes.

**Rationale:** Background job systems frequently power user-facing workflows (file uploads, report generation, payment processing). Users expect immediate feedback when their job completes or fails. Without a standardized real-time mechanism, every OJS implementation invents its own, fragmenting the ecosystem and preventing portable dashboards and monitoring tools.

This extension provides two complementary transport bindings:

- **SSE** — Simple, HTTP-based, unidirectional streaming. Ideal for browser-based dashboards and monitoring tools. Built on standard HTTP infrastructure with automatic reconnection.
- **WebSocket** — Full-duplex communication. Ideal for interactive applications that need to subscribe/unsubscribe dynamically and receive events with minimal overhead.

An implementation MAY support one or both bindings. If an implementation advertises real-time support in its manifest, it MUST support at least the SSE binding.

---

## 2. Server-Sent Events (SSE) Binding

### 2.1 Subscribe to Job Updates

```
GET /ojs/v1/jobs/{id}/events
Accept: text/event-stream
```

The server MUST respond with `Content-Type: text/event-stream` and begin streaming events for the specified job.

**Rationale:** Per-job subscriptions enable lightweight, targeted monitoring. A client tracking a single job should not receive the full event firehose.

If the job does not exist, the server MUST respond with HTTP 404 and a standard OJS error body (not an SSE stream).

If the job is in a terminal state (`completed`, `cancelled`, `discarded`), the server SHOULD send a single `job.state_changed` event reflecting the current state and then close the stream.

**Rationale:** Terminal jobs will never produce further events. Sending the current state and closing prevents clients from holding idle connections.

### 2.2 Subscribe to Queue Events

```
GET /ojs/v1/queues/{name}/events
Accept: text/event-stream
```

The server MUST respond with `Content-Type: text/event-stream` and begin streaming events for all jobs in the specified queue.

If the queue does not exist, the server MUST respond with HTTP 404.

### 2.3 SSE Protocol Requirements

The server MUST comply with the [W3C Server-Sent Events specification](https://html.spec.whatwg.org/multipage/server-sent-events.html):

- Each event MUST include an `event` field indicating the event type.
- Each event MUST include a `data` field containing the JSON-encoded event payload.
- Each event MUST include an `id` field containing a monotonically increasing event identifier.
- Events SHOULD include a `retry` field (in milliseconds) to advise the client on reconnection interval. The RECOMMENDED default is `3000`.

**Rationale:** The `id` field enables automatic reconnection via the `Last-Event-ID` header, preventing event loss during transient disconnections.

### 2.4 Heartbeat

The server MUST send a comment line (`:heartbeat`) at least every **15 seconds** when no events are pending.

**Rationale:** SSE connections traverse proxies and load balancers that may close idle connections. Regular heartbeats prevent premature termination.

### 2.5 Reconnection

When a client reconnects with a `Last-Event-ID` header, the server SHOULD replay any events that occurred after the specified ID. If the server cannot replay (e.g., events were not retained), it MUST resume from the current point without error.

**Rationale:** At-least-once delivery during reconnection is critical for reliable monitoring. However, implementations are not required to maintain unbounded event history.

---

## 3. WebSocket Binding

### 3.1 Connection Endpoint

```
WS /ojs/v1/ws
```

The server MUST accept WebSocket upgrade requests at this path. The server MUST use the `ojs.v1` WebSocket subprotocol when offered by the client.

### 3.2 Subscribe Message

After connecting, a client subscribes to event channels by sending:

```json
{
  "action": "subscribe",
  "channel": "job:{id}"
}
```

Supported channel patterns:

| Pattern         | Description                          |
|-----------------|--------------------------------------|
| `job:{id}`      | Events for a specific job            |
| `queue:{name}`  | Events for all jobs in a queue       |
| `all`           | All events (global firehose)         |

The server MUST respond with an acknowledgment:

```json
{
  "type": "subscribed",
  "channel": "job:01926f5e-..."
}
```

If the referenced job or queue does not exist, the server MUST respond with an error message:

```json
{
  "type": "error",
  "code": "not_found",
  "message": "Job not found."
}
```

### 3.3 Unsubscribe Message

```json
{
  "action": "unsubscribe",
  "channel": "job:{id}"
}
```

The server MUST respond with:

```json
{
  "type": "unsubscribed",
  "channel": "job:{id}"
}
```

### 3.4 Event Messages

The server pushes events to subscribed clients using the same payload format as SSE (Section 4):

```json
{
  "type": "event",
  "channel": "job:01926f5e-...",
  "event": "job.state_changed",
  "data": { ... },
  "id": "evt_0042",
  "timestamp": "2025-07-15T10:30:00.000Z"
}
```

### 3.5 Connection Health

The server MUST send WebSocket Ping frames at least every **30 seconds**. If a client fails to respond with a Pong within **10 seconds**, the server SHOULD close the connection.

**Rationale:** Ping/Pong ensures dead connections are detected promptly, freeing server resources.

---

## 4. Event Format

All real-time events use the following JSON structure:

### 4.1 `job.state_changed`

Emitted when a job transitions between lifecycle states.

```json
{
  "job_id": "01926f5e-7a3c-7def-8000-111111111111",
  "queue": "default",
  "type": "email.send",
  "from": "active",
  "to": "completed",
  "timestamp": "2025-07-15T10:30:00.000Z"
}
```

| Field       | Type   | Required | Description                                       |
|-------------|--------|----------|---------------------------------------------------|
| `job_id`    | string | Yes      | UUIDv7 of the job                                 |
| `queue`     | string | Yes      | Queue the job belongs to                           |
| `type`      | string | Yes      | Job type                                          |
| `from`      | string | Yes      | Previous state (one of the 8 OJS lifecycle states) |
| `to`        | string | Yes      | New state                                         |
| `timestamp` | string | Yes      | RFC 3339 timestamp of the transition               |

### 4.2 `job.progress`

Emitted when a worker reports progress on an active job.

```json
{
  "job_id": "01926f5e-7a3c-7def-8000-111111111111",
  "progress": 75,
  "message": "Processing page 3 of 4",
  "timestamp": "2025-07-15T10:29:55.000Z"
}
```

| Field       | Type    | Required | Description                            |
|-------------|---------|----------|----------------------------------------|
| `job_id`    | string  | Yes      | UUIDv7 of the job                      |
| `progress`  | integer | Yes      | Percentage complete (0–100)            |
| `message`   | string  | No       | Human-readable progress description     |
| `timestamp` | string  | Yes      | RFC 3339 timestamp                     |

### 4.3 `job.heartbeat`

Emitted when a worker sends a heartbeat for an active job. This event type is OPTIONAL; implementations MAY support it.

**Rationale:** Long-running jobs benefit from periodic heartbeat signals so that dashboards and monitoring tools can distinguish between a job that is actively processing and one that has stalled.

```json
{
  "job_id": "01926f5e-7a3c-7def-8000-111111111111",
  "worker_id": "worker-a1b2c3",
  "timestamp": "2025-07-15T10:30:10.000Z"
}
```

| Field       | Type   | Required | Description                              |
|-------------|--------|----------|------------------------------------------|
| `job_id`    | string | Yes      | UUIDv7 of the job                        |
| `worker_id` | string | Yes      | Identifier of the worker sending the heartbeat |
| `timestamp` | string | Yes      | RFC 3339 timestamp of the heartbeat      |

### 4.4 `system.events_dropped`

Emitted when the server drops events due to backpressure (see Section 5.4). This event is a system notification and is not associated with a specific job.

```json
{
  "channel": "queue:default",
  "dropped_count": 42,
  "oldest_dropped_id": "evt_0100",
  "newest_dropped_id": "evt_0141",
  "timestamp": "2025-07-15T10:31:00.000Z"
}
```

| Field               | Type    | Required | Description                                         |
|---------------------|---------|----------|-----------------------------------------------------|
| `channel`           | string  | Yes      | The channel on which events were dropped             |
| `dropped_count`     | integer | Yes      | Number of events that were dropped                   |
| `oldest_dropped_id` | string  | Yes      | Event ID of the oldest dropped event                 |
| `newest_dropped_id` | string  | Yes      | Event ID of the newest dropped event                 |
| `timestamp`         | string  | Yes      | RFC 3339 timestamp of when the drop occurred         |

### 4.5 `system.gap`

Emitted when a client reconnects and requests replay of events that are no longer available in the server's buffer. This signals the client that it has missed events and should perform a full state sync.

```json
{
  "channel": "queue:default",
  "gap_start": "2025-07-15T10:25:00.000Z",
  "gap_end": "2025-07-15T10:30:00.000Z",
  "estimated_missed_count": 150
}
```

| Field                    | Type    | Required | Description                                         |
|--------------------------|---------|----------|-----------------------------------------------------|
| `channel`                | string  | Yes      | The channel with the event gap                       |
| `gap_start`              | string  | Yes      | RFC 3339 timestamp — beginning of the gap            |
| `gap_end`                | string  | Yes      | RFC 3339 timestamp — end of the gap                  |
| `estimated_missed_count` | integer | No       | Server's best estimate of how many events were missed |

### 4.6 `server.shutdown`

Emitted when the server is performing a graceful shutdown. Clients SHOULD use this event to initiate reconnection to another server instance.

```json
{
  "reason": "deployment",
  "grace_period_ms": 5000
}
```

| Field             | Type    | Required | Description                                          |
|-------------------|---------|----------|------------------------------------------------------|
| `reason`          | string  | No       | Human-readable reason for the shutdown                |
| `grace_period_ms` | integer | Yes      | Time in milliseconds before connections are terminated |

---

## 5. Connection Management

### 5.1 Graceful Shutdown

When the server is shutting down, it MUST:

1. Stop accepting new SSE and WebSocket connections.
2. Send a `server.shutdown` event to all connected clients.
3. Close all connections within a RECOMMENDED grace period of **5 seconds**.

**Rationale:** Graceful shutdown prevents clients from hanging on dead connections and allows them to reconnect to another server instance.

### 5.2 Client Limits

The server SHOULD enforce a maximum number of concurrent real-time connections per client (identified by IP address or authentication token). The RECOMMENDED default limit is **100 connections**.

**Rationale:** Without connection limits, a single misbehaving client could exhaust server resources.

### 5.3 Event Buffering

The server MAY buffer recent events (RECOMMENDED: last 100 events per channel) to support SSE reconnection via `Last-Event-ID`.

### 5.4 Backpressure

If a client cannot consume events fast enough, the server MUST buffer events up to a configurable per-connection limit (RECOMMENDED: 1000 events per connection).

**Rationale:** Without backpressure handling, a slow consumer can cause unbounded memory growth on the server, eventually destabilizing the entire system.

If the buffer exceeds the configured limit, the server MUST drop the oldest buffered events first and MUST send a `system.events_dropped` notification (Section 4.4) indicating the count and range of dropped events.

**Rationale:** Dropping the oldest events preserves the most recent state, which is typically what clients need. Notifying the client allows it to perform a state sync and avoids silent data loss.

For **SSE** connections, the server SHOULD include a `X-OJS-Events-Dropped` header in the next SSE comment or event after events were dropped. The value MUST be the integer count of dropped events:

```
:events-dropped 42

id: evt_0200
event: system.events_dropped
data: {"channel":"queue:default","dropped_count":42,"oldest_dropped_id":"evt_0100","newest_dropped_id":"evt_0141","timestamp":"2025-07-15T10:31:00.000Z"}
```

For **WebSocket** connections, the server SHOULD send a warning message before resuming normal event delivery:

```json
{
  "type": "warning",
  "code": "events_dropped",
  "count": 42,
  "channel": "queue:default",
  "oldest_dropped_id": "evt_0100",
  "newest_dropped_id": "evt_0141"
}
```

Implementations SHOULD expose the buffer size as a server configuration parameter. The parameter name SHOULD be `realtime.buffer_size` (or equivalent in the implementation's configuration scheme).

### 5.5 Connection Failure Recovery

Transient disconnections are common in production environments — network blips, load balancer rotation, rolling deployments, and server restarts all cause brief connection interruptions. Without a replay mechanism, clients miss events and display stale state.

**Rationale:** A standardized recovery protocol ensures that clients can resume event streams without data loss after transient failures, reducing the need for expensive full-state polling after every reconnection.

#### 5.5.1 SSE Recovery

When reconnecting after a disconnection, SSE clients MUST include the `Last-Event-ID` header with the ID of the last event they successfully received.

**Rationale:** The `Last-Event-ID` header is part of the W3C SSE specification and is the standard mechanism for resumable streams. Using it ensures compatibility with existing SSE infrastructure.

The server MUST check its event buffer for events after the specified ID:

- If events are available, the server MUST replay all events after the specified ID before sending new events.
- If events are no longer available (expired from the buffer), the server MUST send a `system.gap` event (Section 4.5) indicating the time range and estimated count of missing events, then resume normal delivery from the current point.

#### 5.5.2 WebSocket Recovery

After reconnecting a WebSocket connection, clients SHOULD send a resume message:

```json
{
  "action": "resume",
  "last_event_id": "evt_0042"
}
```

The server MUST re-establish all previously active subscriptions for the connection and replay events after the specified ID, following the same rules as SSE recovery (Section 5.5.1).

**Rationale:** WebSocket connections lack a built-in replay mechanism like SSE's `Last-Event-ID`. An explicit resume action provides equivalent functionality within the OJS WebSocket protocol.

If a client sends a `resume` message with an event ID that the server does not recognize, the server MUST respond with:

```json
{
  "type": "error",
  "code": "unknown_event_id",
  "message": "Event ID not found in buffer. Perform a full state sync."
}
```

#### 5.5.3 Client Behavior on `system.gap`

Clients SHOULD handle the `system.gap` event by performing a full state sync via the REST API (e.g., `GET /ojs/v1/jobs` or `GET /ojs/v1/queues/{name}/jobs`) to reconcile any missed state transitions.

**Rationale:** When the server cannot replay missed events, the only reliable way to restore correct client state is a full re-fetch. Standardizing this expectation prevents clients from operating on stale data.

### 5.6 Event Filtering

High-throughput queues may generate thousands of events per second. Clients that only care about specific event types waste bandwidth and processing time receiving events they discard.

**Rationale:** Filtering reduces bandwidth consumption and client-side processing overhead, especially for dashboards that display only state transitions or only progress updates.

#### 5.6.1 SSE Filtering

SSE clients MAY filter events by type using the `event_types` query parameter. Multiple types are specified as a comma-separated list:

```
GET /ojs/v1/queues/default/events?event_types=job.state_changed,job.progress
Accept: text/event-stream
```

#### 5.6.2 WebSocket Filtering

WebSocket subscribe messages MAY include an `event_types` array to filter events for the subscription:

```json
{
  "action": "subscribe",
  "channel": "queue:default",
  "event_types": ["job.state_changed"]
}
```

The server MUST acknowledge the filter in the subscription confirmation:

```json
{
  "type": "subscribed",
  "channel": "queue:default",
  "event_types": ["job.state_changed"]
}
```

#### 5.6.3 Filtering Rules

When an event filter is specified, the server MUST only send events whose type matches one of the specified types for that subscription or connection.

**Rationale:** Server-side filtering is more efficient than client-side filtering because it avoids serialization, transmission, and deserialization of events the client will discard.

When no filter is specified, the server MUST send all events for the subscribed channel. This preserves backward compatibility with clients that do not use filtering.

**Rationale:** Defaulting to all events ensures that existing clients continue to work without modification when filtering support is added to a server.

Clients MAY update their filters on a WebSocket subscription by sending a new subscribe message for the same channel with updated `event_types`. The server MUST replace the previous filter.

### 5.7 Rate Limiting

In pathological scenarios (e.g., a batch of 100,000 jobs completes simultaneously), the server may need to generate a burst of events that could saturate client connections.

The server SHOULD support rate-limiting event delivery per connection. The RECOMMENDED default limit is **100 events per second** per connection.

**Rationale:** Rate limiting prevents event storms from overwhelming clients with limited processing capacity, particularly browser-based dashboards rendering DOM updates.

When rate-limited, events MUST be buffered according to the backpressure rules in Section 5.4 and delivered when the rate window allows.

The server MUST NOT silently drop events due to rate limiting. If buffered events exceed the backpressure limit (Section 5.4), the server MUST follow the backpressure drop-and-notify procedure.

**Rationale:** Silent event loss is the worst outcome for monitoring systems. By chaining rate limiting into the backpressure mechanism, the system guarantees that clients are always notified when events are lost.

The server SHOULD expose the rate limit as a configuration parameter. The parameter name SHOULD be `realtime.rate_limit_per_second` (or equivalent in the implementation's configuration scheme).

---

## 6. Security Considerations

- Real-time endpoints SHOULD be subject to the same authentication and authorization mechanisms as other OJS API endpoints.
- The server MUST NOT leak job data to unauthorized subscribers. If a client is not authorized to view a job, subscribe requests MUST be rejected with HTTP 403 (SSE) or an error message (WebSocket).
- WebSocket connections SHOULD validate the `Origin` header to prevent cross-site WebSocket hijacking.

---

## 7. Conformance Requirements

An implementation claiming conformance to this extension:

- MUST support the SSE binding (Section 2).
- MUST emit `job.state_changed` events for all lifecycle transitions.
- SHOULD support the WebSocket binding (Section 3).
- MAY support the `job.progress` event type.
- MAY support the `job.heartbeat` event type.
- MUST implement heartbeats as specified.
- MUST handle graceful shutdown as specified (Section 5.1).
- MUST implement backpressure handling as specified (Section 5.4).
- MUST implement connection failure recovery for SSE (Section 5.5.1).
- SHOULD implement connection failure recovery for WebSocket (Section 5.5.2).
- MUST send `system.gap` events when replay is not possible (Section 5.5).
- MUST send `system.events_dropped` events when events are dropped (Section 5.4).
- SHOULD support event filtering (Section 5.6).
- SHOULD support rate limiting (Section 5.7).

---

## 8. Examples

### 8.1 SSE — Monitoring a Single Job

**Request:**
```http
GET /ojs/v1/jobs/01926f5e-7a3c-7def-8000-111111111111/events HTTP/1.1
Accept: text/event-stream
```

**Response stream:**
```
retry: 3000

:heartbeat

id: evt_0001
event: job.state_changed
data: {"job_id":"01926f5e-7a3c-7def-8000-111111111111","queue":"default","type":"email.send","from":"available","to":"active","timestamp":"2025-07-15T10:30:00.000Z"}

:heartbeat

id: evt_0002
event: job.state_changed
data: {"job_id":"01926f5e-7a3c-7def-8000-111111111111","queue":"default","type":"email.send","from":"active","to":"completed","timestamp":"2025-07-15T10:30:05.000Z"}

```

### 8.2 WebSocket — Subscribe and Receive Events

**Client sends:**
```json
{"action":"subscribe","channel":"queue:default"}
```

**Server responds:**
```json
{"type":"subscribed","channel":"queue:default"}
```

**Server pushes event:**
```json
{"type":"event","channel":"queue:default","event":"job.state_changed","data":{"job_id":"01926f5e-7a3c-7def-8000-111111111111","queue":"default","type":"email.send","from":"available","to":"active","timestamp":"2025-07-15T10:30:00.000Z"},"id":"evt_0001","timestamp":"2025-07-15T10:30:00.000Z"}
```

**Client unsubscribes:**
```json
{"action":"unsubscribe","channel":"queue:default"}
```

**Server confirms:**
```json
{"type":"unsubscribed","channel":"queue:default"}
```

### 8.3 SSE — Reconnection with Event Replay

A client was connected to a queue event stream and received events up to `evt_0042`. The connection drops due to a network blip. The client reconnects with the `Last-Event-ID` header.

**Reconnection request:**
```http
GET /ojs/v1/queues/default/events HTTP/1.1
Accept: text/event-stream
Last-Event-ID: evt_0042
```

**Server replays missed events then resumes normal delivery:**
```
retry: 3000

id: evt_0043
event: job.state_changed
data: {"job_id":"01926f5e-7a3c-7def-8000-222222222222","queue":"default","type":"report.generate","from":"available","to":"active","timestamp":"2025-07-15T10:30:10.000Z"}

id: evt_0044
event: job.state_changed
data: {"job_id":"01926f5e-7a3c-7def-8000-222222222222","queue":"default","type":"report.generate","from":"active","to":"completed","timestamp":"2025-07-15T10:30:15.000Z"}

id: evt_0045
event: job.progress
data: {"job_id":"01926f5e-7a3c-7def-8000-333333333333","progress":50,"message":"Halfway done","timestamp":"2025-07-15T10:30:20.000Z"}

:heartbeat

```

If the events after `evt_0042` had expired from the server's buffer, the server would instead send a gap notification:

```
retry: 3000

id: evt_0200
event: system.gap
data: {"channel":"queue:default","gap_start":"2025-07-15T10:25:00.000Z","gap_end":"2025-07-15T10:30:00.000Z","estimated_missed_count":157}

id: evt_0201
event: job.state_changed
data: {"job_id":"01926f5e-7a3c-7def-8000-444444444444","queue":"default","type":"image.resize","from":"available","to":"active","timestamp":"2025-07-15T10:30:25.000Z"}

```

### 8.4 WebSocket — Backpressure Notification

A slow consumer on a WebSocket connection falls behind. The server's per-connection buffer (1000 events) overflows, causing the oldest events to be dropped.

**Server sends warning:**
```json
{"type":"warning","code":"events_dropped","count":42,"channel":"queue:default","oldest_dropped_id":"evt_0100","newest_dropped_id":"evt_0141"}
```

**Server sends system event:**
```json
{"type":"event","channel":"queue:default","event":"system.events_dropped","data":{"channel":"queue:default","dropped_count":42,"oldest_dropped_id":"evt_0100","newest_dropped_id":"evt_0141","timestamp":"2025-07-15T10:31:00.000Z"},"id":"evt_0142","timestamp":"2025-07-15T10:31:00.000Z"}
```

**Server resumes normal event delivery:**
```json
{"type":"event","channel":"queue:default","event":"job.state_changed","data":{"job_id":"01926f5e-7a3c-7def-8000-555555555555","queue":"default","type":"payment.process","from":"active","to":"completed","timestamp":"2025-07-15T10:31:01.000Z"},"id":"evt_0143","timestamp":"2025-07-15T10:31:01.000Z"}
```

### 8.5 WebSocket — Filtered Subscription

A dashboard client only wants to display job state transitions, not progress updates or heartbeats.

**Client subscribes with filter:**
```json
{"action":"subscribe","channel":"queue:default","event_types":["job.state_changed"]}
```

**Server acknowledges with filter confirmation:**
```json
{"type":"subscribed","channel":"queue:default","event_types":["job.state_changed"]}
```

**Server sends only matching events (progress events are suppressed):**
```json
{"type":"event","channel":"queue:default","event":"job.state_changed","data":{"job_id":"01926f5e-7a3c-7def-8000-666666666666","queue":"default","type":"email.send","from":"available","to":"active","timestamp":"2025-07-15T10:32:00.000Z"},"id":"evt_0050","timestamp":"2025-07-15T10:32:00.000Z"}
```

**Client updates filter to also include progress:**
```json
{"action":"subscribe","channel":"queue:default","event_types":["job.state_changed","job.progress"]}
```

**Server acknowledges updated filter:**
```json
{"type":"subscribed","channel":"queue:default","event_types":["job.state_changed","job.progress"]}
```

---

## 9. SDK Implementation Guidelines

This section provides normative guidance for SDK implementers adding real-time subscription support.

### 9.1 Client API Surface

An OJS SDK providing real-time support SHOULD expose the following methods:

```
client.subscribe(channel, callback)    → Subscription
client.subscribeJob(jobId, callback)   → Subscription
client.subscribeQueue(queue, callback) → Subscription
subscription.unsubscribe()             → void
```

### 9.2 Transport Selection

SDKs SHOULD default to SSE for simplicity and SHOULD support WebSocket as an opt-in transport. The transport selection SHOULD be configurable at client construction time:

```
client = OJSClient(url, { realtime: "sse" })   // default
client = OJSClient(url, { realtime: "ws" })     // opt-in
```

### 9.3 Reconnection

SDKs MUST implement automatic reconnection with exponential backoff when the real-time connection drops. The SDK SHOULD use the `Last-Event-ID` header (SSE) or replay from the last received event ID (WebSocket) to resume without data loss.

### 9.4 Event Type Mapping

SDKs SHOULD provide typed event objects rather than raw JSON. At minimum, the following event types MUST be supported:

| Event Type | Trigger |
|-----------|---------|
| `job.state_changed` | Any job state transition |
| `job.completed` | Job reaches `completed` state |
| `job.failed` | Job reaches `retryable` or `discarded` state |
| `job.progress` | Job reports progress update |
| `queue.paused` | Queue paused |
| `queue.resumed` | Queue resumed |
