# Open Job Spec: Backpressure Specification

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Backpressure Specification                 |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-13                                     |
| **Status**  | Release Candidate                              |
| **Maturity** | Experimental                                   |
| **Tier**    | Official Extension                             |
| **URI**     | `urn:ojs:ext:backpressure`                     |
| **Requires**| OJS Core Specification (Layer 1)               |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [The Problem](#4-the-problem)
5. [Backpressure Strategies](#5-backpressure-strategies)
   - 5.1 [Reject](#51-reject)
   - 5.2 [Block](#52-block)
   - 5.3 [Drop Oldest](#53-drop-oldest)
6. [Queue Bounds Configuration](#6-queue-bounds-configuration)
7. [HTTP Binding](#7-http-binding)
8. [Producer-Side Backpressure](#8-producer-side-backpressure)
9. [Interaction with Other Extensions](#9-interaction-with-other-extensions)
10. [Observability](#10-observability)
11. [Conformance Requirements](#11-conformance-requirements)
12. [Prior Art](#12-prior-art)
13. [Examples](#13-examples)

---

## 1. Introduction

Unbounded queues are the most common failure mode in distributed systems. As one distributed systems researcher noted: "The most common failure for correctly handling backpressure: an unbounded queue will just continue to accept input from producers. The queue pretends everything is fine while the system burns behind it."

Without backpressure, a spike in enqueue rate -- from a webhook storm, a bulk import, or a runaway producer -- fills the queue beyond what consumers can process. Memory grows, latency increases, and eventually the entire system fails. Worse, the failure is not graceful: it manifests as OOM kills, Redis evictions, or database disk exhaustion.

The rate-limiting extension (ojs-rate-limiting.md) addresses execution-side throttling: controlling how fast jobs are processed. This specification addresses the complementary concern: **enqueue-side backpressure** -- controlling how fast jobs enter the system.

### 1.1 Scope

This specification defines:

- Three backpressure strategies (reject, block, drop-oldest) and their semantics.
- Queue bound configuration (max depth, max size in bytes).
- HTTP response codes and headers for backpressure signaling.
- Producer-side backpressure handling guidance for SDKs.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term                  | Definition                                                                                     |
|-----------------------|------------------------------------------------------------------------------------------------|
| backpressure          | A mechanism that slows or stops producers when the system cannot keep up with the input rate.  |
| bounded queue         | A queue with a configured maximum number of jobs or maximum total size.                        |
| queue depth           | The number of non-terminal jobs in a queue (available + scheduled + retryable).                |
| queue bound           | The configured limit on queue depth or size.                                                   |
| headroom              | The percentage of queue capacity below the bound at which warning signals begin.               |

---

## 4. The Problem

Consider a system processing 1,000 jobs/minute with a burst of 100,000 jobs enqueued in 1 minute:

| Without Backpressure | With Backpressure |
|---------------------|-------------------|
| All 100,000 jobs accepted | Jobs accepted up to bound (e.g., 50,000) |
| Queue grows to 100,000 | Queue stays at ≤50,000 |
| Memory usage spikes | Memory stays bounded |
| Processing latency: 100+ minutes | Producer gets 429, can retry or alert user |
| Recovery takes hours | Recovery is immediate when burst subsides |
| Cascading failure risk | Failure is contained |

The three fundamental approaches to backpressure, in order of preference:

1. **Control the producer** (reject/block): Best. No data loss, clear feedback.
2. **Buffer** (bounded queue): Dangerous if unbounded. Safe when bounded.
3. **Drop** (oldest or newest): Acceptable for non-critical data. Lossy.

---

## 5. Backpressure Strategies

### 5.1 Reject

**Default strategy.** When the queue bound is reached, the backend rejects the enqueue request immediately with an HTTP 429 response.

**Semantics**:
- The job is NOT stored.
- The producer receives an immediate error response.
- The response includes `Retry-After` header with a recommended delay.
- The producer can retry, alert the user, or buffer locally.

This is the RECOMMENDED strategy for most use cases.

**Rationale**: Rejection puts the producer in control. The producer can decide how to handle the situation: retry with backoff, fail the user request with a meaningful error, or enqueue to a fallback system. No data is silently lost.

### 5.2 Block

When the queue bound is reached, the backend holds the enqueue request open until space becomes available or a timeout expires.

**Semantics**:
- The HTTP connection remains open.
- When a job completes and frees capacity, the blocked job is accepted.
- If the timeout expires before space is available, the backend responds with 429.
- The timeout is controlled by the `OJS-Block-Timeout` request header (default: 0, meaning reject immediately).

```http
POST /ojs/v1/jobs HTTP/1.1
Content-Type: application/openjobspec+json
OJS-Block-Timeout: 30

{ "type": "report.generate", "args": [{}] }
```

**Rationale**: Blocking is useful for synchronous producers that prefer to wait rather than implement retry logic. However, it ties up an HTTP connection and can cascade to the producer's upstream (the user waits for a loading spinner). Use with caution.

### 5.3 Drop Oldest

When the queue bound is reached, the backend accepts the new job and discards the oldest `available` job in the queue.

**Semantics**:
- The new job is accepted normally.
- The oldest `available` (not `active`, not `scheduled`) job is moved to `discarded` state.
- A `backpressure.dropped` event is emitted for the dropped job.

**When to use**: Only for queues where job freshness matters more than completeness. Examples: real-time notification queues, cache warmup jobs, metrics aggregation jobs.

Implementations MUST NOT enable drop-oldest by default. It MUST be explicitly configured per queue.

**Rationale**: Drop-oldest is a lossy strategy that should never surprise a developer. Requiring explicit configuration prevents accidental data loss.

---

## 6. Queue Bounds Configuration

### 6.1 Bound Types

Queue bounds can be configured in two dimensions:

| Bound Type      | Field               | Description                                              |
|-----------------|---------------------|----------------------------------------------------------|
| Depth bound     | `max_depth`         | Maximum number of non-terminal jobs in the queue.        |
| Size bound      | `max_size_bytes`    | Maximum total serialized size of jobs in the queue.      |

Either or both may be configured. When both are set, the first bound reached triggers backpressure.

### 6.2 Configuration Format

Queue bounds are configured via the Admin API (see ojs-admin-api.md):

```http
PUT /ojs/v1/admin/queues/{name}/config
Content-Type: application/json

{
  "backpressure": {
    "max_depth": 50000,
    "max_size_bytes": 536870912,
    "strategy": "reject",
    "warning_threshold": 0.8
  }
}
```

| Field                | Type    | Required | Default    | Description                                              |
|----------------------|---------|----------|------------|----------------------------------------------------------|
| `max_depth`          | integer | No       | unbounded  | Maximum non-terminal jobs. `0` means unbounded.          |
| `max_size_bytes`     | integer | No       | unbounded  | Maximum total size in bytes. `0` means unbounded.        |
| `strategy`           | string  | No       | `"reject"` | One of: `"reject"`, `"block"`, `"drop_oldest"`.          |
| `warning_threshold`  | number  | No       | `0.8`      | Fraction (0.0-1.0) at which `backpressure.warning` events fire. |

### 6.3 Default: Unbounded

When no bounds are configured, queues are unbounded (matching the behavior of OJS without this extension). This preserves backward compatibility.

Implementations SHOULD log a warning at startup for queues without bounds configured, because unbounded queues are a known operational risk.

---

## 7. HTTP Binding

### 7.1 Rejection Response

When the backend rejects an enqueue due to backpressure:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 5
X-OJS-Queue-Depth: 50000
X-OJS-Queue-Bound: 50000

{
  "error": {
    "code": "QUEUE_FULL",
    "message": "Queue 'default' has reached its depth bound (50000)",
    "queue": "default",
    "depth": 50000,
    "bound": 50000,
    "strategy": "reject"
  }
}
```

### 7.2 Response Headers

| Header              | Type    | Description                                               |
|---------------------|---------|-----------------------------------------------------------|
| `Retry-After`       | integer | Recommended seconds to wait before retrying.              |
| `X-OJS-Queue-Depth` | integer | Current queue depth.                                      |
| `X-OJS-Queue-Bound` | integer | Configured queue bound.                                   |

### 7.3 Warning Headers

When the queue depth exceeds the warning threshold but has not reached the bound, the backend SHOULD include warning headers on successful enqueue responses:

```http
HTTP/1.1 201 Created
X-OJS-Queue-Depth: 42000
X-OJS-Queue-Bound: 50000
X-OJS-Queue-Pressure: 0.84
```

The `X-OJS-Queue-Pressure` header is a float between 0.0 and 1.0 representing current depth / bound.

---

## 8. Producer-Side Backpressure

### 8.1 SDK Retry Behavior

SDKs SHOULD implement automatic retry with exponential backoff when receiving a 429 response:

1. Wait for `Retry-After` seconds (or 1 second if header is absent).
2. Retry the enqueue.
3. If still rejected, double the delay (up to a configurable maximum).
4. After a configurable number of retries, surface the error to the caller.

### 8.2 Circuit Breaker Pattern

SDKs MAY implement a circuit breaker that temporarily stops sending enqueue requests after repeated 429 responses. The circuit breaker:

- **Opens** after N consecutive 429 responses (default: 5).
- **Half-opens** after a cooldown period (default: 10 seconds).
- **Closes** after a successful enqueue.

### 8.3 Local Buffering

For producers that cannot tolerate enqueue failures, SDKs MAY provide an optional local buffer:

- Jobs that fail to enqueue due to backpressure are stored locally (in-memory or on disk).
- A background thread retries buffered jobs with exponential backoff.
- The buffer has its own bound to prevent local resource exhaustion.

SDKs that implement local buffering MUST clearly document the durability guarantees (in-memory buffers lose data on process crash).

---

## 9. Interaction with Other Extensions

### 9.1 Rate Limiting

Rate limiting (ojs-rate-limiting.md) and backpressure are complementary:

- **Rate limiting** controls how fast jobs are **executed**.
- **Backpressure** controls how fast jobs are **enqueued**.

Both may be active simultaneously. A queue with both a rate limit and a depth bound ensures that neither the producer nor the consumer can overwhelm the system.

### 9.2 Multi-Tenancy

When multi-tenancy is enabled (ojs-multi-tenancy.md), backpressure bounds MAY be configured per-tenant:

```json
{
  "tenant_id": "acme-corp",
  "limits": {
    "max_queue_depth": 50000
  }
}
```

Per-tenant bounds prevent one tenant's burst from triggering backpressure for other tenants in shared-queue deployments.

### 9.3 Batch Enqueue

When a batch enqueue request (`POST /ojs/v1/jobs/batch`) would exceed the queue bound:

- **Reject strategy**: The entire batch is rejected. No partial acceptance.
- **Block strategy**: The request blocks until space for the full batch is available.
- **Drop-oldest strategy**: Oldest jobs are dropped to make room for the full batch.

**Rationale**: Partial batch acceptance creates a complex failure mode where the producer must track which jobs succeeded and which didn't. Rejecting the entire batch is simpler and easier to retry.

---

## 10. Observability

### 10.1 Events

| Event Type                  | Trigger                                              | Data Fields                     |
|-----------------------------|------------------------------------------------------|---------------------------------|
| `backpressure.warning`      | Queue depth crosses warning threshold.               | `queue`, `depth`, `bound`       |
| `backpressure.rejected`     | An enqueue was rejected due to backpressure.         | `queue`, `depth`, `bound`, `job_type` |
| `backpressure.dropped`      | A job was dropped by drop-oldest strategy.           | `queue`, `job_id`, `job_type`   |
| `backpressure.cleared`      | Queue depth dropped below warning threshold.         | `queue`, `depth`, `bound`       |

### 10.2 Metrics

| Metric Name                         | Type    | Labels    | Description                                  |
|-------------------------------------|---------|-----------|----------------------------------------------|
| `ojs.backpressure.rejected_total`   | Counter | `queue`   | Total enqueue rejections due to backpressure.|
| `ojs.backpressure.dropped_total`    | Counter | `queue`   | Total jobs dropped by drop-oldest.            |
| `ojs.backpressure.pressure`         | Gauge   | `queue`   | Current depth / bound ratio (0.0 - 1.0).    |

---

## 11. Conformance Requirements

An implementation declaring support for the backpressure extension MUST support:

| ID           | Requirement                                                                    |
|--------------|--------------------------------------------------------------------------------|
| BP-001       | Depth-based queue bounds (`max_depth`).                                        |
| BP-002       | Reject strategy: return 429 with `Retry-After` when bound is exceeded.        |
| BP-003       | Queue bound configuration via Admin API.                                       |
| BP-004       | `backpressure.rejected` event emission.                                        |
| BP-005       | `X-OJS-Queue-Depth` and `X-OJS-Queue-Bound` response headers on 429.          |

Recommended:

| ID           | Requirement                                                                    |
|--------------|--------------------------------------------------------------------------------|
| BP-R001      | Size-based queue bounds (`max_size_bytes`).                                    |
| BP-R002      | Block strategy with `OJS-Block-Timeout` header.                               |
| BP-R003      | Drop-oldest strategy.                                                          |
| BP-R004      | Warning headers on successful enqueue when above warning threshold.            |
| BP-R005      | `ojs.backpressure.pressure` gauge metric.                                      |

---

## 12. Prior Art

| System            | Backpressure Approach                                                                   |
|-------------------|-----------------------------------------------------------------------------------------|
| **Kafka**         | Broker returns `QUOTA_VIOLATION` when producer exceeds rate. Client-side backoff.       |
| **RabbitMQ**      | Flow control: blocks publishers when memory or disk alarm triggers.                     |
| **BullMQ**        | No built-in backpressure. Queue grows until Redis OOM.                                  |
| **Sidekiq**       | No built-in backpressure. Relies on Redis `maxmemory-policy`.                           |
| **Temporal**      | Namespace-level rate limiting on enqueue. Rejects with `RESOURCE_EXHAUSTED`.            |
| **Inngest**       | Account-level concurrency limits. Queues are bounded by plan tier.                      |
| **AWS SQS**       | 120,000 message limit per standard queue. Returns error when exceeded.                  |

Most job systems rely on the backing store's limits (Redis `maxmemory`, Postgres disk) as implicit backpressure. This is dangerous because the failure mode is a system-wide crash rather than a controlled rejection. OJS makes backpressure explicit and configurable.

---

## 12.1 Relationship to Rate Limiting

Backpressure (this specification) controls enqueue behavior when queues are full or overwhelmed. Rate limiting ([ojs-rate-limiting.md](./ojs-rate-limiting.md)) controls dequeue and execution rate. The two are complementary: backpressure prevents producer overload by bounding queue depth, while rate limiting prevents consumer overload by throttling execution throughput. Implementations SHOULD support both to provide end-to-end flow control.

---

## 13. Examples

### 13.1 Configuring a Bounded Queue

```bash
curl -X PUT http://localhost:8080/ojs/v1/admin/queues/email/config \
  -H "Content-Type: application/json" \
  -d '{
    "backpressure": {
      "max_depth": 100000,
      "strategy": "reject",
      "warning_threshold": 0.8
    }
  }'
```

### 13.2 Producer Handling 429

```typescript
async function enqueueWithBackpressure(type: string, args: any[]) {
  for (let attempt = 0; attempt < 5; attempt++) {
    const response = await fetch('http://localhost:8080/ojs/v1/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/openjobspec+json' },
      body: JSON.stringify({ type, args }),
    });

    if (response.status === 201) return response.json();

    if (response.status === 429) {
      const retryAfter = parseInt(response.headers.get('Retry-After') || '1');
      await sleep(retryAfter * 1000 * (attempt + 1)); // Exponential backoff
      continue;
    }

    throw new Error(`Enqueue failed: ${response.status}`);
  }

  throw new Error('Enqueue failed after 5 attempts (queue full)');
}
```

### 13.3 Real-Time Notification Queue with Drop-Oldest

```bash
# Configure drop-oldest for non-critical notifications
curl -X PUT http://localhost:8080/ojs/v1/admin/queues/notifications/config \
  -H "Content-Type: application/json" \
  -d '{
    "backpressure": {
      "max_depth": 10000,
      "strategy": "drop_oldest"
    }
  }'
```

---

## Appendix A: Changelog

| Date       | Change                        |
|------------|-------------------------------|
| 2026-02-13 | Initial release candidate.    |
