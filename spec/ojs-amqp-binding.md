# Open Job Spec -- Layer 3: AMQP 0-9-1 Protocol Binding

**Version:** 1.0.0-rc.1
**Date:** 2026-02-15
**Status:** Release Candidate 1

| Field        | Value                      |
|--------------|----------------------------|
| Spec Version | 1.0.0-rc.1                 |
| Date         | 2026-02-15                 |
| Status       | Release Candidate 1        |
| Layer        | 3 -- Protocol Binding      |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [AMQP Topology](#4-amqp-topology)
5. [Logical Operation Mapping](#5-logical-operation-mapping)
6. [Message Format](#6-message-format)
7. [Queue Declaration](#7-queue-declaration)
8. [Retry via Dead Letter Exchange](#8-retry-via-dead-letter-exchange)
9. [Scheduled Jobs](#9-scheduled-jobs)
10. [Error Handling](#10-error-handling)
11. [Connection Management](#11-connection-management)
12. [Observability](#12-observability)
13. [Conformance Requirements](#13-conformance-requirements)
14. [Prior Art](#14-prior-art)
15. [Examples](#15-examples)

---

## 1. Introduction

This document defines the AMQP 0-9-1 protocol binding for the Open Job Spec (OJS). It specifies how the logical operations defined in the OJS Core Specification (`ojs-core.md`, Layer 1) map to AMQP 0-9-1 primitives — exchanges, queues, bindings, and message publishing/consuming methods — when transmitted over an AMQP 0-9-1 broker such as RabbitMQ or Azure Service Bus.

AMQP 0-9-1 is an **OPTIONAL** protocol binding. The HTTP binding (defined in `ojs-http-binding.md`) remains the **REQUIRED** baseline. Implementations that support AMQP provide native message-broker semantics, durable queue-based delivery, and consumer-driven flow control without HTTP polling overhead.

### 1.1 Why AMQP

AMQP 0-9-1 is the dominant open wire protocol for enterprise messaging, with RabbitMQ alone powering millions of production deployments. Key advantages for job queue workloads:

- **Reliable delivery**: Publisher confirms and consumer acknowledgements provide at-least-once guarantees without polling.
- **Native queue semantics**: Durable queues with competing consumers and prefetch-based flow control directly match OJS queue semantics.
- **Dead lettering**: Built-in DLX routing enables retry and discard patterns without additional infrastructure.
- **Broker-mediated routing**: Exchange-based routing decouples producers from consumers.

### 1.2 Relationship to Other Specifications

| Document | Layer | Relationship |
|----------|-------|-------------|
| `ojs-core.md` | Layer 1 (Core) | Defines the job envelope, lifecycle states, and logical operations this binding maps |
| `ojs-json-format.md` | Layer 2 (Wire Format) | Defines JSON serialization used in AMQP message bodies |
| `ojs-http-binding.md` | Layer 3 (Protocol) | The REQUIRED HTTP binding; AMQP MUST maintain identical semantics |
| `ojs-grpc-binding.md` | Layer 3 (Protocol) | The optional gRPC binding; AMQP provides an alternative transport |
| `ojs-retry.md` | Extension | Defines retry policies mapped to DLX + TTL patterns in this binding |
| `ojs-dead-letter.md` | Extension | Defines dead letter semantics mapped to AMQP DLX in this binding |

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt).

All examples in this document use the following conventions:

- **Broker:** `amqp://localhost:5672`
- **Virtual host:** `/ojs`
- **Job IDs:** UUIDv7 format (e.g., `019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6`)
- **Timestamps:** ISO 8601 / RFC 3339 with UTC timezone (e.g., `2026-02-15T10:30:00.000Z`)
- **Content type:** `application/openjobspec+json`

AMQP method names follow the AMQP 0-9-1 specification notation (e.g., `Basic.Publish`, `Queue.Declare`).

---

## 3. Terminology

The following terms are used throughout this document in addition to the OJS Glossary (`ojs-glossary.md`):

| Term | Definition |
|------|-----------|
| **Exchange** | An AMQP routing entity that receives published messages and routes them to queues based on bindings and routing keys. |
| **Binding** | A rule that links an exchange to a queue, optionally filtered by a routing key or headers. |
| **Routing Key** | A string used by the exchange to determine which queue(s) receive a published message. |
| **Consumer Tag** | A unique string identifying a consumer on a channel; used to cancel consumption. |
| **Delivery Tag** | A monotonically increasing integer assigned by the broker to each delivered message on a channel; used for acknowledgement. |
| **Basic.Publish** | The AMQP method for publishing a message to an exchange with a routing key. |
| **Basic.Consume** | The AMQP method for registering a consumer on a queue, enabling push-based message delivery. |
| **Basic.Ack** | The AMQP method for positively acknowledging a delivered message. |
| **Basic.Nack** | The AMQP method for negatively acknowledging one or more delivered messages, with optional requeue. |
| **Basic.Reject** | The AMQP method for negatively acknowledging a single delivered message, with optional requeue. |
| **Prefetch** | The `Basic.Qos` prefetch count that limits the number of unacknowledged messages delivered to a consumer. |
| **Dead Letter Exchange (DLX)** | An exchange to which messages are routed when they are rejected, nacked without requeue, or expire via TTL. |
| **Message Properties** | AMQP message metadata fields including `message_id`, `type`, `content_type`, `timestamp`, `headers`, `reply_to`, and `correlation_id`. |
| **Headers Exchange** | An exchange type that routes messages based on header attributes rather than routing keys. |

---

## 4. AMQP Topology

### 4.1 Naming Conventions

All AMQP entities created by an OJS implementation MUST use the following naming conventions:

| Entity | Name Pattern | Example |
|--------|-------------|---------|
| Job queue | `ojs.queue.{queue_name}` | `ojs.queue.email` |
| Direct exchange | `ojs.exchange.direct` | `ojs.exchange.direct` |
| Dead letter exchange | `ojs.exchange.dlx` | `ojs.exchange.dlx` |
| Dead letter queue | `ojs.queue.dlx.{queue_name}` | `ojs.queue.dlx.email` |
| Retry exchange | `ojs.exchange.retry` | `ojs.exchange.retry` |
| Retry delay queue | `ojs.queue.retry.{queue_name}.{delay_ms}` | `ojs.queue.retry.email.5000` |
| Delayed message exchange | `ojs.exchange.delayed` | `ojs.exchange.delayed` |
| Control queue | `ojs.queue.control.{queue_name}` | `ojs.queue.control.email` |

Implementations MAY add a configurable prefix for multi-tenancy (e.g., `tenant1.ojs.queue.email`).

### 4.2 Exchange Topology

The AMQP binding defines the following exchange topology:

```
                    ┌──────────────────────┐
                    │  ojs.exchange.direct  │  (type: direct)
                    └──────────┬───────────┘
                               │ routing_key = queue_name
                    ┌──────────▼───────────┐
                    │  ojs.queue.{name}     │  (durable, per-queue)
                    └──────────┬───────────┘
                               │ x-dead-letter-exchange
                    ┌──────────▼───────────┐
                    │  ojs.exchange.dlx     │  (type: direct)
                    └──────────┬───────────┘
                               │ routing_key = queue_name
                    ┌──────────▼───────────┐
                    │  ojs.queue.dlx.{name} │  (durable, per-queue)
                    └──────────────────────┘
```

1. **Direct exchange** (`ojs.exchange.direct`): The primary exchange for job routing. MUST be declared as `direct`, `durable=true`. Each job queue MUST be bound with `routing_key` equal to the queue name.

2. **Dead letter exchange** (`ojs.exchange.dlx`): Receives rejected/nacked messages. MUST be declared as `direct`, `durable=true`. Each DLX queue MUST be bound with `routing_key` equal to the originating queue name.

3. **Retry exchange** (`ojs.exchange.retry`): Used for retry delay routing. See [Section 8](#8-retry-via-dead-letter-exchange).

4. **Delayed message exchange** (`ojs.exchange.delayed`): For scheduled job delivery via the `rabbitmq-delayed-message-exchange` plugin. See [Section 9](#9-scheduled-jobs).

### 4.3 Queue-to-Queue Mapping

Each OJS logical queue maps to exactly one AMQP queue:

- OJS queue `email` → AMQP queue `ojs.queue.email`
- OJS queue `default` → AMQP queue `ojs.queue.default`

This is a **direct 1:1 mapping**. Implementations MUST NOT multiplex multiple OJS queues onto a single AMQP queue.

---

## 5. Logical Operation Mapping

The following table maps every OJS logical operation to its AMQP 0-9-1 implementation:

| OJS Operation | AMQP Primitive | Routing | Details |
|---------------|----------------|---------|---------|
| **PUSH** | `Basic.Publish` | To `ojs.exchange.direct` with `routing_key` = queue name | Publisher confirms MUST be enabled; `mandatory=true` RECOMMENDED |
| **PUSH (batch)** | Multiple `Basic.Publish` | Same as PUSH, one publish per job | Implementations SHOULD pipeline publishes on a single channel |
| **FETCH** | `Basic.Consume` + `Basic.Qos` | Consumer on `ojs.queue.{name}` | `prefetch_count` = requested concurrency; `no_ack=false` |
| **ACK** | `Basic.Ack` | N/A | `delivery_tag` from the consumed message; `multiple=false` |
| **FAIL (retryable)** | `Basic.Ack` + `Basic.Publish` | Ack original, republish to `ojs.exchange.retry` with TTL | See [Section 8](#8-retry-via-dead-letter-exchange) for backoff topology |
| **FAIL (discard)** | `Basic.Nack` | `requeue=false` → routes to DLX | Message arrives in `ojs.queue.dlx.{name}` |
| **CANCEL** | `Basic.Publish` | To `ojs.exchange.direct` with `routing_key` = control queue | Publish a cancellation message to `ojs.queue.control.{name}` |
| **BEAT** | `Basic.Publish` | To `ojs.exchange.direct` with `routing_key` = control queue | Heartbeat message with job ID and worker ID |
| **INFO** | RPC via `reply_to` | Request to control queue, response to exclusive temp queue | Correlation via `correlation_id`; see Section 5.8 |

### 5.1 PUSH

To enqueue a job, the client MUST: (1) serialize the job envelope as JSON per `ojs-json-format.md`, (2) set message properties per [Section 6](#6-message-format), (3) publish to `ojs.exchange.direct` with `routing_key` = target queue name, and (4) if publisher confirms are enabled, wait for broker acknowledgement.

The client SHOULD set `mandatory=true` so that unroutable messages are returned via `Basic.Return` rather than silently discarded.

### 5.2 FETCH

Workers MUST consume jobs via `Basic.Consume` with `no_ack=false` (manual acknowledgement). The `Basic.Qos` prefetch count MUST be set before consuming. Workers MUST NOT use `Basic.Get` (polling). Example for concurrency of 5:

```
Basic.Qos(prefetch_count=5, global=false)
Basic.Consume(queue="ojs.queue.email", consumer_tag="worker-01", no_ack=false)
```

### 5.3 ACK

Upon successful job completion, the worker MUST issue `Basic.Ack` with the `delivery_tag` of the consumed message and `multiple=false`.

### 5.4 FAIL (Retryable)

When a job fails but is eligible for retry, the worker MUST: (1) `Basic.Ack` the original delivery, (2) increment the `x-ojs-attempt` header, (3) compute the retry delay per the job's retry policy, and (4) `Basic.Publish` the message to the retry exchange with the appropriate TTL.

Using `Basic.Ack` followed by republish (rather than `Basic.Nack` with `requeue=true`) is REQUIRED to prevent infinite immediate redelivery loops and to enable delay-based backoff.

### 5.5 FAIL (Discard)

When a job has exhausted its retry budget or is explicitly discarded, the worker MUST issue `Basic.Nack` with `requeue=false`. The broker routes the message to the dead letter exchange (`ojs.exchange.dlx`), which delivers it to the corresponding dead letter queue.

### 5.6 CANCEL

Job cancellation is asynchronous. The client MUST publish a cancellation message to the control queue (`ojs.queue.control.{queue_name}`) with:

- `type` property set to `ojs.control.cancel`
- Message body containing `{"job_id": "<id>"}`

Workers consuming from the control queue MUST process cancellation requests and attempt to abort the target job.

### 5.7 BEAT

Worker heartbeats extend the visibility timeout of active jobs. The worker MUST publish a heartbeat message to the control queue with:

- `type` property set to `ojs.control.heartbeat`
- Message body containing `{"job_id": "<id>", "worker_id": "<worker_id>"}`

Alternatively, implementations MAY rely on AMQP connection-level heartbeat frames for liveness detection and use the control queue only for per-job visibility extension.

### 5.8 INFO

Job information retrieval uses the AMQP RPC pattern: the client declares an exclusive, auto-delete reply queue, publishes a request to the control queue with `reply_to` and a unique `correlation_id`, the backend publishes the response to the reply queue, and the client consumes it.

---

## 6. Message Format

### 6.1 AMQP Message Properties

OJS job attributes MUST be mapped to AMQP message properties as follows:

| AMQP Property | OJS Source | Required |
|---------------|-----------|----------|
| `message_id` | Job `id` (UUIDv7) | REQUIRED |
| `type` | Job `type` (e.g., `email.send`) | REQUIRED |
| `content_type` | `application/openjobspec+json` | REQUIRED |
| `content_encoding` | `utf-8` | REQUIRED |
| `timestamp` | Job `created_at` (Unix epoch seconds) | REQUIRED |
| `delivery_mode` | `2` (persistent) | REQUIRED |
| `priority` | Job `priority` (0–9), if specified | OPTIONAL |
| `correlation_id` | Trace correlation ID, if present | OPTIONAL |
| `reply_to` | Reply queue name for RPC pattern | OPTIONAL |
| `app_id` | `ojs` | RECOMMENDED |
| `expiration` | Per-message TTL in milliseconds (for retry/scheduling) | Conditional |

### 6.2 Headers Table

OJS system attributes and metadata MUST be placed in the AMQP `headers` table:

| Header Key | Type | Description |
|-----------|------|-------------|
| `x-ojs-queue` | `string` | Originating OJS queue name |
| `x-ojs-attempt` | `int32` | Current attempt number (1-based) |
| `x-ojs-max-attempts` | `int32` | Maximum retry attempts |
| `x-ojs-created-at` | `string` | ISO 8601 creation timestamp |
| `x-ojs-enqueued-at` | `string` | ISO 8601 enqueue timestamp |
| `x-ojs-scheduled-at` | `string` | ISO 8601 scheduled execution time |
| `x-ojs-tags` | `string` | Comma-separated tag list |
| `x-ojs-trace-id` | `string` | W3C Trace Context `traceparent` value |
| `x-ojs-idempotency-key` | `string` | Idempotency key for deduplication |
| `x-ojs-error-message` | `string` | Last error message (on retry republish) |
| `x-ojs-error-code` | `string` | Last error code (on retry republish) |

### 6.3 Message Body

The message body MUST be the JSON-serialized OJS job envelope as defined in `ojs-json-format.md`. The body MUST be encoded as UTF-8.

---

## 7. Queue Declaration

### 7.1 Queue Properties

All OJS job queues MUST be declared with the following properties:

| Property | Value | Rationale |
|----------|-------|-----------|
| `durable` | `true` | Queues survive broker restart |
| `exclusive` | `false` | Multiple connections may consume |
| `auto_delete` | `false` | Queue persists when no consumers are connected |

### 7.2 Queue Arguments

Implementations MUST set the following queue arguments:

| Argument | Value | Purpose |
|----------|-------|---------|
| `x-dead-letter-exchange` | `ojs.exchange.dlx` | Route rejected messages to the dead letter exchange |
| `x-dead-letter-routing-key` | `{queue_name}` | Preserve originating queue identity in DLX |

Implementations SHOULD support the following optional arguments:

| Argument | Value | Purpose |
|----------|-------|---------|
| `x-max-length` | Configurable integer | Backpressure: limit queue depth |
| `x-max-length-bytes` | Configurable integer | Backpressure: limit queue size in bytes |
| `x-overflow` | `reject-publish` | Reject new publishes when queue is full (vs. dropping head) |
| `x-max-priority` | `10` | Enable priority queue support (0–9 maps to OJS priority) |
| `x-message-ttl` | Configurable integer (ms) | Default message TTL for the queue |
| `x-queue-type` | `quorum` or `classic` | Quorum queues RECOMMENDED for durability |

### 7.3 Declaration Strategy

Implementations MUST support two strategies: **eager declaration** (all entities at startup, RECOMMENDED for production) and **lazy declaration** (on first use, acceptable for development). Declarations MUST be idempotent. Implementations MUST handle `PRECONDITION_FAILED` errors when a queue exists with different properties.

---

## 8. Retry via Dead Letter Exchange

### 8.1 DLX + Per-Message TTL Pattern

The RECOMMENDED retry pattern uses retry delay queues with per-message TTL:

```
Worker FAIL (retryable)
    │
    │ Basic.Ack + Basic.Publish(expiration=delay_ms)
    ▼
┌────────────────────────────────┐
│  ojs.exchange.retry            │  (type: direct)
└───────────────┬────────────────┘
                │ routing_key = {queue_name}.{delay_ms}
┌───────────────▼────────────────┐
│  ojs.queue.retry.{name}.{ms}  │  (durable, x-dead-letter-exchange=ojs.exchange.direct,
└───────────────┬────────────────┘   x-dead-letter-routing-key={queue_name})
                │ TTL expires
┌───────────────▼────────────────┐
│  ojs.exchange.direct           │
└───────────────┬────────────────┘
                │ routing_key = {queue_name}
┌───────────────▼────────────────┐
│  ojs.queue.{name}              │  (message redelivered for next attempt)
└────────────────────────────────┘
```

### 8.2 Retry Delay Queue Declaration

Each unique delay value requires a dedicated queue. Implementations MUST declare retry delay queues with:

| Property / Argument | Value |
|---------------------|-------|
| `durable` | `true` |
| `exclusive` | `false` |
| `auto_delete` | `false` |
| `x-dead-letter-exchange` | `ojs.exchange.direct` |
| `x-dead-letter-routing-key` | `{queue_name}` |
| `x-message-ttl` | `{delay_ms}` |

> **Note:** AMQP 0-9-1 processes TTL in head-of-queue order. If messages with different TTL values share the same delay queue, shorter-TTL messages behind longer-TTL messages will not expire on time. Implementations MUST either use per-delay queues (one queue per unique TTL) or use the delayed message exchange plugin.

### 8.3 Attempt Tracking

On each retry, the implementation MUST: (1) increment `x-ojs-attempt`, (2) set `x-ojs-error-message` and `x-ojs-error-code` to the last failure details, and (3) preserve all other original message properties and headers.

When `x-ojs-attempt` reaches `x-ojs-max-attempts`, the implementation MUST treat the next failure as a discard (FAIL with no retry).

### 8.4 Alternative: Delayed Message Exchange Plugin

Implementations deploying the [rabbitmq-delayed-message-exchange](https://github.com/rabbitmq/rabbitmq-delayed-message-exchange) plugin MAY use a single delayed exchange instead of per-delay queues. Declare `ojs.exchange.delayed` as type `x-delayed-message` with argument `x-delayed-type=direct`. On retry, publish with header `x-delay` set to the delay in milliseconds. This avoids per-delay queue proliferation but requires a broker plugin.

---

## 9. Scheduled Jobs

### 9.1 Delayed Message Patterns

OJS scheduled jobs (jobs with a `scheduled_at` timestamp in the future) require delayed delivery. Two patterns are supported:

#### 9.1.1 TTL + DLX Chain

The same DLX + TTL pattern used for retry (Section 8) can delay initial delivery. Compute `delay_ms` = `scheduled_at` - `now()`, publish the message to a scheduling delay queue with `x-message-ttl` = `delay_ms`, and the message is dead-lettered to the target queue when the TTL expires.

**Limitations:** Maximum TTL is broker-limited (typically ~49 days). Head-of-queue ordering means messages MUST be segregated by delay value.

#### 9.1.2 Delayed Message Exchange Plugin

The `rabbitmq-delayed-message-exchange` plugin (Section 8.4) is the RECOMMENDED approach. Publish to `ojs.exchange.delayed` with header `x-delay` = `delay_ms` and `routing_key` = target queue name.

**Limitations:** Requires the plugin. Maximum delay is ~49 days. Delayed messages are stored in Mnesia, which may impact performance at scale.

### 9.2 Fallback Strategy

If neither pattern is available, the implementation MAY store scheduled jobs in an external data store and publish them to AMQP when the scheduled time arrives. This approach is outside the scope of this binding specification.

---

## 10. Error Handling

### 10.1 Channel-Level Errors

AMQP 0-9-1 channel errors close the channel but leave the connection intact. The following channel errors are relevant to OJS:

| Error Code | Condition | OJS Response |
|-----------|-----------|-------------|
| `PRECONDITION_FAILED` (406) | Queue declaration with conflicting properties | Log error; implementations SHOULD NOT attempt to redeclare with different properties |
| `NOT_FOUND` (404) | Publish to non-existent exchange or consume from non-existent queue | Return error to caller; implementations MAY auto-declare the entity |
| `ACCESS_REFUSED` (403) | Insufficient permissions | Return authorization error to caller |

Implementations MUST open a new channel after a channel-level error. Implementations SHOULD maintain a channel pool to avoid the latency of channel creation on the critical path.

### 10.2 Connection-Level Errors

Connection errors close the entire AMQP connection. Implementations MUST handle connection loss gracefully and reconnect as described in [Section 11](#11-connection-management).

### 10.3 Unroutable Messages

When `mandatory=true` is set on `Basic.Publish` and the message cannot be routed, the broker returns it via `Basic.Return`. Implementations MUST register a return listener and report unroutable messages to the caller.

### 10.4 Consumer Cancellation Notification

Brokers MAY cancel consumers (e.g., when a queue is deleted). Implementations MUST handle `Basic.Cancel` notifications by logging the event, attempting to re-register the consumer after a delay, and reporting via the observability layer.

---

## 11. Connection Management

### 11.1 Connection Pooling

Implementations SHOULD maintain a pool of AMQP connections. The RECOMMENDED pool configuration is:

| Parameter | Recommended Value | Rationale |
|-----------|------------------|-----------|
| Min connections | 1 | Maintain at least one active connection |
| Max connections | Number of CPU cores | One connection per OS thread avoids contention |
| Heartbeat interval | 60 seconds | Detect dead connections; matches most broker defaults |

### 11.2 Channel-per-Thread Model

AMQP channels MUST NOT be shared across threads. Implementations MUST use either a **channel-per-thread** model (RECOMMENDED) or a **channel pool** with proper synchronization.

### 11.3 Reconnection with Exponential Backoff

On connection loss, implementations MUST reconnect using exponential backoff:

| Attempt | Delay | Notes |
|---------|-------|-------|
| 1 | 1 second | Immediate retry |
| 2 | 2 seconds | |
| 3 | 4 seconds | |
| 4 | 8 seconds | |
| 5 | 16 seconds | |
| N | min(2^(N-1), 60) seconds | Cap at 60 seconds |

Implementations SHOULD add jitter (±25%) to avoid thundering herd reconnection after broker restart. On successful reconnection, implementations MUST re-declare all exchanges, queues, and bindings, re-register all consumers with the same prefetch settings, and emit a reconnection event via the observability layer.

---

## 12. Observability

### 12.1 AMQP-Specific Metrics

Implementations SHOULD expose the following AMQP-specific metrics:

| Metric Name | Type | Description |
|-------------|------|-------------|
| `ojs_amqp_connections_active` | Gauge | Number of active AMQP connections |
| `ojs_amqp_channels_active` | Gauge | Number of active AMQP channels |
| `ojs_amqp_messages_published_total` | Counter | Total messages published (by queue) |
| `ojs_amqp_messages_consumed_total` | Counter | Total messages consumed (by queue) |
| `ojs_amqp_messages_acked_total` | Counter | Total messages acknowledged (by queue) |
| `ojs_amqp_messages_nacked_total` | Counter | Total messages negatively acknowledged (by queue) |
| `ojs_amqp_messages_returned_total` | Counter | Total messages returned via `Basic.Return` |
| `ojs_amqp_messages_unacked` | Gauge | Current unacknowledged message count (by consumer) |
| `ojs_amqp_consumer_utilization` | Gauge | Consumer utilization ratio (0.0–1.0, by queue) |
| `ojs_amqp_publish_confirm_latency_seconds` | Histogram | Publisher confirm latency |
| `ojs_amqp_reconnections_total` | Counter | Total reconnection attempts |

### 12.2 Trace Context Propagation

Implementations MUST propagate W3C Trace Context via AMQP message headers. The publisher MUST set `x-ojs-trace-id` to the `traceparent` value. The consumer MUST extract it and create a child span linked to the parent trace. On retry republish, the original trace context MUST be preserved. Implementations MAY additionally propagate `tracestate` via an `x-ojs-trace-state` header.

---

## 13. Conformance Requirements

### 13.1 Conformance Table

Implementations that advertise AMQP binding support MUST satisfy the following requirements:

| ID | Requirement | Level | MUST / SHOULD |
|----|------------|-------|---------------|
| AMQP-001 | Declare `ojs.exchange.direct` as durable direct exchange | Core | MUST |
| AMQP-002 | Declare `ojs.exchange.dlx` as durable direct exchange | Core | MUST |
| AMQP-003 | Declare job queues with `durable=true`, `exclusive=false`, `auto_delete=false` | Core | MUST |
| AMQP-004 | Set `x-dead-letter-exchange` on all job queues | Core | MUST |
| AMQP-005 | Map PUSH to `Basic.Publish` on `ojs.exchange.direct` | Core | MUST |
| AMQP-006 | Map FETCH to `Basic.Consume` with `no_ack=false` | Core | MUST |
| AMQP-007 | Set `Basic.Qos` prefetch count before consuming | Core | MUST |
| AMQP-008 | Map ACK to `Basic.Ack` with correct `delivery_tag` | Core | MUST |
| AMQP-009 | Map FAIL (discard) to `Basic.Nack` with `requeue=false` | Core | MUST |
| AMQP-010 | Set `content_type` to `application/openjobspec+json` | Core | MUST |
| AMQP-011 | Set `delivery_mode=2` (persistent) on all job messages | Core | MUST |
| AMQP-012 | Set `message_id` to OJS job ID | Core | MUST |
| AMQP-013 | Serialize message body as JSON per `ojs-json-format.md` | Core | MUST |
| AMQP-014 | Enable publisher confirms on publish channels | Reliable | MUST |
| AMQP-015 | Set `mandatory=true` on job publishes | Reliable | SHOULD |
| AMQP-016 | Handle `Basic.Return` for unroutable messages | Reliable | MUST |
| AMQP-017 | Implement retry via DLX + TTL or delayed exchange plugin | Reliable | MUST |
| AMQP-018 | Track attempt count via `x-ojs-attempt` header | Reliable | MUST |
| AMQP-019 | Implement CANCEL via control queue publish | Reliable | MUST |
| AMQP-020 | Implement BEAT via control queue publish or connection heartbeat | Reliable | MUST |
| AMQP-021 | Implement INFO via RPC reply-to pattern | Reliable | SHOULD |
| AMQP-022 | Support scheduled jobs via delayed delivery | Scheduled | MUST |
| AMQP-023 | Propagate W3C Trace Context via message headers | Observability | MUST |
| AMQP-024 | Expose AMQP-specific metrics | Observability | SHOULD |
| AMQP-025 | Reconnect with exponential backoff on connection loss | Resilience | MUST |
| AMQP-026 | Re-declare topology after reconnection | Resilience | MUST |
| AMQP-027 | Handle consumer cancellation notifications | Resilience | MUST |
| AMQP-028 | Use channel-per-thread or channel pool model | Concurrency | MUST |
| AMQP-029 | Support `x-max-length` or `x-overflow` for backpressure | Advanced | SHOULD |
| AMQP-030 | Support `x-max-priority` for priority queues | Advanced | SHOULD |
| AMQP-031 | Follow OJS entity naming conventions | Core | MUST |
| AMQP-032 | Use quorum queues for durability | Advanced | SHOULD |

---

## 14. Prior Art

This specification draws on established patterns from the following projects and frameworks:

| Project | Relevance |
|---------|-----------|
| **[RabbitMQ Work Queues Tutorial](https://www.rabbitmq.com/tutorials/tutorial-two-python)** | Foundational competing-consumer pattern with manual acknowledgement that OJS FETCH/ACK mirrors |
| **[Celery AMQP Transport](https://docs.celeryq.dev/en/stable/internals/protocol.html)** | Celery's AMQP task protocol uses similar exchange/queue topology and header-based metadata propagation |
| **[Spring AMQP](https://spring.io/projects/spring-amqp)** | Template-based publish/consume model with declarative queue/exchange/binding configuration; retry via `RetryTemplate` and DLX |
| **[MassTransit](https://masstransit.io/)** | .NET message bus framework with convention-based exchange/queue naming, retry middleware, and saga orchestration over RabbitMQ |
| **[NServiceBus](https://particular.net/nservicebus)** | Enterprise service bus with first-class delayed retry, error queues, and audit queues over AMQP transports |

---

## 15. Examples

### 15.1 Publishing a Job (Python / pika)

```python
import pika, json, uuid
from datetime import datetime, timezone

conn = pika.BlockingConnection(pika.ConnectionParameters(host='localhost', virtual_host='/ojs'))
ch = conn.channel()
ch.confirm_delivery()

# Declare topology (idempotent)
ch.exchange_declare(exchange='ojs.exchange.direct', exchange_type='direct', durable=True)
ch.exchange_declare(exchange='ojs.exchange.dlx', exchange_type='direct', durable=True)
ch.queue_declare(queue='ojs.queue.email', durable=True, arguments={
    'x-dead-letter-exchange': 'ojs.exchange.dlx',
    'x-dead-letter-routing-key': 'email',
    'x-max-priority': 10,
})
ch.queue_bind(queue='ojs.queue.email', exchange='ojs.exchange.direct', routing_key='email')

job_id = str(uuid.uuid7())
job = {
    "id": job_id, "type": "email.send", "queue": "email",
    "args": ["user@example.com", "welcome"],
    "created_at": datetime.now(timezone.utc).isoformat(),
}

ch.basic_publish(
    exchange='ojs.exchange.direct', routing_key='email',
    body=json.dumps(job), mandatory=True,
    properties=pika.BasicProperties(
        message_id=job_id, type='email.send',
        content_type='application/openjobspec+json', content_encoding='utf-8',
        delivery_mode=2, app_id='ojs',
        timestamp=int(datetime.now(timezone.utc).timestamp()),
        headers={'x-ojs-queue': 'email', 'x-ojs-attempt': 1, 'x-ojs-max-attempts': 5},
    ),
)
conn.close()
```

### 15.2 Consuming and Acknowledging Jobs

```python
import pika, json

conn = pika.BlockingConnection(pika.ConnectionParameters(host='localhost', virtual_host='/ojs'))
ch = conn.channel()
ch.basic_qos(prefetch_count=5)

def on_message(ch, method, properties, body):
    job = json.loads(body)
    attempt = properties.headers.get('x-ojs-attempt', 1)
    try:
        process_email(job)
        ch.basic_ack(delivery_tag=method.delivery_tag)                    # ACK
    except RetryableError:
        ch.basic_ack(delivery_tag=method.delivery_tag)                    # Ack original
        max_attempts = properties.headers.get('x-ojs-max-attempts', 3)
        if attempt < max_attempts:
            delay_ms = min(1000 * (2 ** (attempt - 1)), 60000)
            retry_publish(ch, job, properties, attempt + 1, delay_ms)     # Republish with delay
        else:
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False) # DLX
    except Exception:
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)    # Discard → DLX

ch.basic_consume(queue='ojs.queue.email', on_message_callback=on_message)
ch.start_consuming()
```

### 15.3 Retry Topology Setup

```python
import pika

conn = pika.BlockingConnection(pika.ConnectionParameters(host='localhost', virtual_host='/ojs'))
ch = conn.channel()
ch.exchange_declare(exchange='ojs.exchange.retry', exchange_type='direct', durable=True)

delays_ms = [1000, 2000, 4000, 8000, 16000, 32000, 60000]
queue_name = 'email'

for delay in delays_ms:
    retry_queue = f'ojs.queue.retry.{queue_name}.{delay}'
    ch.queue_declare(queue=retry_queue, durable=True, arguments={
        'x-dead-letter-exchange': 'ojs.exchange.direct',
        'x-dead-letter-routing-key': queue_name,
        'x-message-ttl': delay,
    })
    ch.queue_bind(queue=retry_queue, exchange='ojs.exchange.retry',
                  routing_key=f'{queue_name}.{delay}')
conn.close()
```

### 15.4 Retry Publish Helper

```python
import pika, json

def retry_publish(channel, job, original_props, next_attempt, delay_ms):
    headers = dict(original_props.headers or {})
    headers['x-ojs-attempt'] = next_attempt
    channel.basic_publish(
        exchange='ojs.exchange.retry',
        routing_key=f"{headers['x-ojs-queue']}.{delay_ms}",
        body=json.dumps(job), mandatory=True,
        properties=pika.BasicProperties(
            message_id=original_props.message_id, type=original_props.type,
            content_type='application/openjobspec+json', content_encoding='utf-8',
            delivery_mode=2, app_id='ojs',
            timestamp=original_props.timestamp, headers=headers,
        ),
    )
```

---

_Open Job Spec v1.0.0-rc.1 -- AMQP 0-9-1 Protocol Binding -- February 2026_
_https://openjobspec.org_
