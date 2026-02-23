# OJS Real-Time Status — Extension Specification

| Field        | Value                                      |
|-------------|---------------------------------------------|
| **Title**   | OJS Real-Time Job Status Updates            |
| **Version** | 0.1.0                                       |
| **Status**  | Experimental (Stage 0)                      |
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
- MUST implement heartbeats as specified.
- MUST handle graceful shutdown as specified (Section 5.1).

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
