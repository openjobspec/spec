# OJS Events: Standard Event Vocabulary

**Open Job Spec v1.0.0-rc.1**

| Field       | Value                  |
|-------------|------------------------|
| Version     | 1.0.0-rc.1             |
| Status      | Release Candidate      |
| Date        | 2025-06-01             |
| Layer       | Core (Layer 1)         |
| Depends On  | ojs-core.md            |

---

## Abstract

This document defines the standard lifecycle events that every OJS-conforming implementation MUST emit. Events provide the observability foundation for monitoring, alerting, debugging, auditing, and driving reactive logic (such as webhook delivery or workflow orchestration) in background job systems.

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt).

---

## Table of Contents

1. [Introduction and Motivation](#1-introduction-and-motivation)
2. [Event Envelope Specification](#2-event-envelope-specification)
3. [Event Type Catalog](#3-event-type-catalog)
4. [Event Data Schemas](#4-event-data-schemas)
5. [Conformance Requirements](#5-conformance-requirements)
6. [Subscription and Filtering](#6-subscription-and-filtering)
7. [Metrics Specification](#7-metrics-specification)
8. [Distributed Tracing](#8-distributed-tracing)
9. [Event Delivery Guarantees](#9-event-delivery-guarantees)
10. [Complete Examples](#10-complete-examples)
11. [Prior Art](#11-prior-art)

---

## 1. Introduction and Motivation

Observable-by-default is a core OJS design principle. Every conforming implementation MUST emit lifecycle events so that operators, dashboards, and downstream systems can react to state changes without polling.

**Rationale for MUST:** Without mandatory event emission, there is no portable way for monitoring tools, dashboards, or orchestration logic to observe job lifecycle transitions. Making events optional would fragment the ecosystem -- an OJS dashboard that works with one backend would fail silently against another. The cost of emitting events is marginal compared to job execution time, and the observability benefit is foundational.

Events serve four purposes:

1. **Operational visibility.** Operators monitor job throughput, failure rates, and queue depth in real time.
2. **Debugging.** When a job fails, the event trail provides the context needed to diagnose the root cause across language and service boundaries.
3. **Reactive logic.** Downstream systems subscribe to events to trigger webhooks, update UIs, drive workflow orchestration, or feed analytics pipelines.
4. **Auditing.** Regulated environments require an immutable record of every state transition a job undergoes.

The transport mechanism for delivering events is **implementation-defined**. Conforming implementations MAY use any combination of: in-process callbacks, webhooks, an event bus (Redis Streams, Kafka, NATS), HTTP streaming (Server-Sent Events), WebSocket, or gRPC server-streaming. The event envelope format and type vocabulary defined here are transport-agnostic.

---

## 2. Event Envelope Specification

### 2.1 Envelope Format

Every OJS event MUST be represented as a JSON object conforming to the envelope schema defined in this section. The envelope design is inspired by the [CloudEvents v1.0 specification](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md), adapted for background job semantics.

**Rationale for MUST (CloudEvents-inspired envelope):** A standardized envelope ensures that event consumers -- dashboards, alerting systems, webhook handlers, log aggregators -- can parse events from any OJS implementation without per-backend adaptation. The CloudEvents alignment enables interoperability with the broader event-driven ecosystem (Knative, Azure Event Grid, AWS EventBridge) and avoids inventing a new envelope format where a proven one exists.

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-b68c-7def-8000-aabbccddeeff",
  "type": "job.completed",
  "source": "ojs://my-service/workers/worker-1",
  "time": "2025-06-01T10:30:02.789Z",
  "subject": "job_019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "data": {
    "job_type": "email.send",
    "queue": "email",
    "duration_ms": 1333,
    "attempt": 1,
    "result": { "message_id": "msg_abc123" }
  }
}
```

### 2.2 Envelope Fields

#### Required Context Attributes

Every event MUST include the following context attributes.

**Rationale for MUST:** These fields constitute the minimum viable envelope. Without them, an event consumer cannot determine what happened (`type`), which spec produced it (`specversion`), where it came from (`source`), when it occurred (`time`), or how to deduplicate it (`id`).

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `specversion` | string | The OJS events specification version. | MUST be `"1.0"`. |
| `id` | string | Globally unique event identifier. | MUST be unique within the scope of `source`. Implementations SHOULD use UUIDv7 for time-sortability. The `evt_` prefix is RECOMMENDED for human readability. |
| `type` | string | The event type from the catalog defined in [Section 3](#3-event-type-catalog). | MUST be a value from the OJS event type catalog. Dot-namespaced (e.g., `job.completed`). |
| `source` | string (URI) | Identifies the context in which the event was produced. | MUST be a valid URI. The RECOMMENDED format is `ojs://{service}/{component}/{instance}` (e.g., `ojs://my-service/workers/worker-1`, `ojs://my-service/scheduler`). |
| `time` | string (RFC 3339) | Timestamp of when the event was emitted. | MUST be an ISO 8601 / RFC 3339 timestamp with timezone. UTC with `Z` suffix is RECOMMENDED. |

#### Optional Context Attributes

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `subject` | string | The subject of the event, typically the job ID. | SHOULD be the job ID for job events, the queue name for queue events, the worker ID for worker events, the workflow ID for workflow events, or the cron job name for cron events. |
| `datacontenttype` | string | Content type of the `data` field. | Defaults to `application/json`. Implementations MUST NOT use non-JSON content types for OJS events. |

#### Data Attribute

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `data` | object | Event-specific payload. | MUST conform to the schema for the given `type` as defined in [Section 4](#4-event-data-schemas). |

**Rationale for MUST (data schema conformance):** If event data is unstructured or inconsistent across implementations, consumers cannot reliably extract fields like `duration_ms` or `error`. Mandating per-type schemas ensures that a dashboard built against one OJS backend will correctly parse events from any other.

### 2.3 Event ID Generation

Event IDs MUST be unique within the scope of a given `source`.

**Rationale for MUST:** Duplicate event IDs break deduplication logic in consumers that use at-least-once delivery. UUIDv7 provides uniqueness guarantees without coordination, and its time-ordered prefix enables efficient indexing and range queries over event logs.

Implementations SHOULD use UUIDv7 (RFC 9562) with the `evt_` prefix. Example: `evt_019539a4-b68c-7def-8000-aabbccddeeff`.

### 2.4 Source URI Format

The `source` field MUST be a valid URI. The RECOMMENDED format is:

```
ojs://{service-name}/{component}/{instance-id}
```

Components:

| Segment | Description | Examples |
|---------|-------------|----------|
| `{service-name}` | The logical service or application name. | `my-service`, `billing-api` |
| `{component}` | The OJS component type. | `workers`, `scheduler`, `cron`, `api` |
| `{instance-id}` | The specific instance identifier. | `worker-1`, `scheduler-0`, `pod-abc123` |

Examples:

- `ojs://billing-api/workers/worker-1` -- A worker process in the billing-api service.
- `ojs://billing-api/scheduler` -- The scheduler component (for `job.scheduled` events).
- `ojs://billing-api/cron` -- The cron scheduler (for `cron.triggered` events).
- `ojs://billing-api/api` -- The API server (for `job.enqueued` events initiated via HTTP).

---

## 3. Event Type Catalog

Events are organized into six categories. Each event type uses a dot-namespaced format: `{category}.{action}`.

### 3.1 Job Events (Core)

These events correspond to the core job lifecycle defined in `ojs-core.md`. All conformance levels MUST emit these events.

**Rationale for MUST:** These five events map directly to the fundamental job state transitions. Without them, there is no way to observe whether jobs are being processed, how long they take, or whether they succeed or fail. They are the minimum viable observability surface.

| Event Type | Emitted When | Data Fields |
|------------|-------------|-------------|
| `job.enqueued` | Job enters the `available` state (enqueued into a queue). | `job_type`, `queue` |
| `job.started` | A worker begins executing the job (transitions to `active`). | `job_type`, `queue`, `worker_id`, `attempt` |
| `job.completed` | The handler succeeds (transitions to `completed`). | `job_type`, `queue`, `duration_ms`, `attempt`, `result` |
| `job.failed` | The handler fails on a given attempt (transitions to `retryable` or `discarded`). | `job_type`, `queue`, `attempt`, `error` |
| `job.discarded` | Job moved to the dead letter queue (all retries exhausted, transitions to `discarded`). | `job_type`, `queue`, `total_attempts`, `last_error` |

### 3.2 Job Events (Extended)

Extended job events provide deeper lifecycle visibility. These events are RECOMMENDED for Level 1+ implementations and MUST be emitted when the corresponding feature is supported.

**Rationale for conditional MUST:** If an implementation supports retries but does not emit `job.retrying`, consumers cannot distinguish between a job that will be retried and one that has been permanently discarded. The rule is: if you support the feature, you MUST emit the corresponding event.

| Event Type | Emitted When | Minimum Level | Data Fields |
|------------|-------------|---------------|-------------|
| `job.retrying` | Job is scheduled for retry after a failed attempt (transitions to `retryable`). | 1 | `job_type`, `queue`, `attempt`, `max_attempts`, `next_retry_at`, `error` |
| `job.cancelled` | Job is cancelled before or during execution (transitions to `cancelled`). | 1 | `job_type`, `queue`, `cancelled_by`, `reason` |
| `job.heartbeat` | Worker extends the job's visibility timeout. | 1 | `job_type`, `queue`, `worker_id`, `attempt`, `visible_until` |
| `job.scheduled` | Job is scheduled for future execution (enters or remains in `scheduled` state). | 2 | `job_type`, `queue`, `scheduled_at` |
| `job.expired` | Job expired because its TTL elapsed before execution could begin. | 2 | `job_type`, `queue`, `created_at`, `expired_at`, `ttl_ms` |
| `job.progress` | Job reports incremental progress during execution. | 3 | `job_type`, `queue`, `worker_id`, `attempt`, `progress_percent`, `progress_message` |

### 3.3 Queue Events

Queue events track administrative actions on queues. Implementations that support queue pause/resume (Level 4) MUST emit these events.

**Rationale for MUST:** Pausing and resuming queues are operational actions with significant impact (workers stop receiving jobs). Without events, there is no audit trail for who paused a queue and when, making incident response harder.

| Event Type | Emitted When | Minimum Level | Data Fields |
|------------|-------------|---------------|-------------|
| `queue.paused` | A queue is paused (workers stop fetching from it). | 4 | `queue`, `paused_by` |
| `queue.resumed` | A previously paused queue is resumed. | 4 | `queue`, `resumed_by` |

### 3.4 Worker Events

Worker events track the worker lifecycle. Implementations SHOULD emit these events.

**Rationale for SHOULD (not MUST):** In embedded/in-process deployments (e.g., `ojs-memory` in a test suite), worker lifecycle events may not be meaningful. Making them SHOULD ensures that production deployments emit them while not burdening minimal implementations.

| Event Type | Emitted When | Data Fields |
|------------|-------------|-------------|
| `worker.started` | A worker process starts and begins polling for jobs. | `worker_id`, `queues`, `concurrency` |
| `worker.stopped` | A worker process completes graceful shutdown. | `worker_id`, `reason`, `jobs_completed`, `uptime_ms` |
| `worker.quiet` | A worker enters quiet mode (stops fetching new jobs, finishes active ones). | `worker_id`, `active_jobs` |
| `worker.heartbeat` | A worker sends a periodic heartbeat to indicate liveness. | `worker_id`, `active_jobs`, `queues`, `memory_mb`, `cpu_percent` |

### 3.5 Workflow Events

Workflow events track the lifecycle of composite workflows (chains, groups, batches). Implementations that support workflows (Level 3) MUST emit these events.

**Rationale for MUST:** Workflows span multiple jobs and may run for minutes or hours. Without workflow-level events, operators can only observe individual job events and must manually correlate them to understand whether a multi-step pipeline succeeded or failed.

| Event Type | Emitted When | Minimum Level | Data Fields |
|------------|-------------|---------------|-------------|
| `workflow.started` | The first step of a workflow begins execution. | 3 | `workflow_id`, `workflow_name`, `total_steps` |
| `workflow.step_completed` | An individual step within a workflow completes. | 3 | `workflow_id`, `workflow_name`, `step_id`, `step_type`, `duration_ms`, `steps_remaining` |
| `workflow.completed` | All steps in a workflow have completed successfully. | 3 | `workflow_id`, `workflow_name`, `total_steps`, `duration_ms` |
| `workflow.failed` | A workflow failed because a step failed with no retries remaining and no fallback defined. | 3 | `workflow_id`, `workflow_name`, `failed_step_id`, `failed_step_type`, `error` |

### 3.6 Cron Events

Cron events track periodic/recurring job scheduling. Implementations that support cron jobs (Level 2) MUST emit these events.

**Rationale for MUST:** Cron jobs run on a schedule, often unattended. Without events, there is no way to confirm that a cron job actually fired, or to detect when it was skipped due to overlap prevention. Silent cron failures are a common source of production incidents.

| Event Type | Emitted When | Minimum Level | Data Fields |
|------------|-------------|---------------|-------------|
| `cron.triggered` | A cron schedule fires and a job is enqueued. | 2 | `cron_name`, `cron_expr`, `job_type`, `job_id`, `scheduled_at` |
| `cron.skipped` | A cron schedule fires but the job is not enqueued because the previous instance is still running (overlap prevention). | 2 | `cron_name`, `cron_expr`, `job_type`, `reason`, `existing_job_id` |

---

## 4. Event Data Schemas

This section defines the `data` object schema for each event type. All fields marked as **Required** MUST be present in the `data` object. Fields marked as **Optional** MAY be omitted.

**Rationale for MUST (required fields):** Without guaranteed field presence, consumers must defensively handle missing fields for every event, defeating the purpose of a typed event vocabulary.

### 4.1 Job Event Data Schemas

#### `job.enqueued`

Emitted when a job transitions to the `available` state.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `job_type` | string | Yes | The dot-namespaced job type (e.g., `email.send`). |
| `queue` | string | Yes | The queue the job was enqueued into. |
| `priority` | integer | No | Job priority, if set. |
| `scheduled_at` | string (RFC 3339) | No | If the job was enqueued with a delay, the time it will become available. |
| `unique_key` | string | No | The computed uniqueness key, if unique job semantics apply. |

```json
{
  "job_type": "email.send",
  "queue": "email",
  "priority": 0
}
```

#### `job.started`

Emitted when a worker begins executing a job.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `job_type` | string | Yes | The dot-namespaced job type. |
| `queue` | string | Yes | The queue the job was fetched from. |
| `worker_id` | string | Yes | Identifier of the worker that claimed the job. |
| `attempt` | integer | Yes | The current attempt number (1-indexed). |

```json
{
  "job_type": "email.send",
  "queue": "email",
  "worker_id": "worker-1",
  "attempt": 1
}
```

#### `job.completed`

Emitted when a handler returns successfully.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `job_type` | string | Yes | The dot-namespaced job type. |
| `queue` | string | Yes | The queue the job was processed from. |
| `duration_ms` | integer | Yes | Wall-clock execution time in milliseconds. |
| `attempt` | integer | Yes | The attempt number that succeeded (1-indexed). |
| `result` | object or null | No | The return value from the handler, if any. |

```json
{
  "job_type": "email.send",
  "queue": "email",
  "duration_ms": 1333,
  "attempt": 1,
  "result": { "message_id": "msg_abc123" }
}
```

#### `job.failed`

Emitted when a handler fails on a given attempt. This event is emitted per-attempt, regardless of whether the job will be retried or discarded.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `job_type` | string | Yes | The dot-namespaced job type. |
| `queue` | string | Yes | The queue the job was processed from. |
| `attempt` | integer | Yes | The attempt number that failed (1-indexed). |
| `error` | object | Yes | Structured error information. |
| `error.code` | string | Yes | Machine-readable error code (see `ojs-core.md` Section 10). |
| `error.message` | string | Yes | Human-readable error description. |
| `error.retryable` | boolean | Yes | Whether the error is retryable. |
| `error.stack_trace` | string | No | Stack trace or backtrace, if available. |
| `duration_ms` | integer | No | Execution time before failure, in milliseconds. |

```json
{
  "job_type": "email.send",
  "queue": "email",
  "attempt": 1,
  "error": {
    "code": "handler_error",
    "message": "SMTP connection refused: connect ECONNREFUSED 10.0.0.5:587",
    "retryable": true,
    "stack_trace": "Error: SMTP connection refused\n    at SMTPClient.connect (smtp.js:42)\n    at sendEmail (handler.js:15)"
  },
  "duration_ms": 245
}
```

#### `job.discarded`

Emitted when a job has exhausted all retry attempts and is moved to the dead letter queue.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `job_type` | string | Yes | The dot-namespaced job type. |
| `queue` | string | Yes | The queue the job was processed from. |
| `total_attempts` | integer | Yes | Total number of attempts made (including the final failure). |
| `last_error` | object | Yes | The error from the final attempt. |
| `last_error.code` | string | Yes | Machine-readable error code. |
| `last_error.message` | string | Yes | Human-readable error description. |

```json
{
  "job_type": "email.send",
  "queue": "email",
  "total_attempts": 5,
  "last_error": {
    "code": "handler_error",
    "message": "SMTP connection refused: connect ECONNREFUSED 10.0.0.5:587"
  }
}
```

#### `job.retrying`

Emitted when a failed job is scheduled for retry.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `job_type` | string | Yes | The dot-namespaced job type. |
| `queue` | string | Yes | The queue the job belongs to. |
| `attempt` | integer | Yes | The attempt number that just failed (1-indexed). |
| `max_attempts` | integer | Yes | The maximum number of attempts configured. |
| `next_retry_at` | string (RFC 3339) | Yes | When the next retry will be attempted. |
| `error` | object | Yes | The error from the failed attempt. |
| `error.code` | string | Yes | Machine-readable error code. |
| `error.message` | string | Yes | Human-readable error description. |

```json
{
  "job_type": "email.send",
  "queue": "email",
  "attempt": 2,
  "max_attempts": 5,
  "next_retry_at": "2025-06-01T10:32:04.000Z",
  "error": {
    "code": "handler_error",
    "message": "SMTP connection refused"
  }
}
```

#### `job.cancelled`

Emitted when a job is cancelled.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `job_type` | string | Yes | The dot-namespaced job type. |
| `queue` | string | Yes | The queue the job belongs to. |
| `cancelled_by` | string | No | Identifier of the actor that cancelled the job (user, API key, system). |
| `reason` | string | No | Human-readable reason for cancellation. |

```json
{
  "job_type": "report.generate",
  "queue": "reports",
  "cancelled_by": "user:admin@example.com",
  "reason": "Superseded by updated report request"
}
```

#### `job.heartbeat`

Emitted when a worker extends the visibility timeout for a long-running job.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `job_type` | string | Yes | The dot-namespaced job type. |
| `queue` | string | Yes | The queue the job belongs to. |
| `worker_id` | string | Yes | Identifier of the worker holding the job. |
| `attempt` | integer | Yes | The current attempt number. |
| `visible_until` | string (RFC 3339) | Yes | The new visibility timeout deadline. |

```json
{
  "job_type": "video.transcode",
  "queue": "media",
  "worker_id": "worker-3",
  "attempt": 1,
  "visible_until": "2025-06-01T10:35:00.000Z"
}
```

#### `job.scheduled`

Emitted when a job is accepted for future execution.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `job_type` | string | Yes | The dot-namespaced job type. |
| `queue` | string | Yes | The target queue. |
| `scheduled_at` | string (RFC 3339) | Yes | When the job will become available for execution. |

```json
{
  "job_type": "report.generate",
  "queue": "reports",
  "scheduled_at": "2025-06-02T09:00:00.000Z"
}
```

#### `job.expired`

Emitted when a job's TTL elapses before execution begins.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `job_type` | string | Yes | The dot-namespaced job type. |
| `queue` | string | Yes | The queue the job was in. |
| `created_at` | string (RFC 3339) | Yes | When the job was originally created. |
| `expired_at` | string (RFC 3339) | Yes | When the expiration was detected. |
| `ttl_ms` | integer | Yes | The TTL that was configured, in milliseconds. |

```json
{
  "job_type": "notification.push",
  "queue": "notifications",
  "created_at": "2025-06-01T10:00:00.000Z",
  "expired_at": "2025-06-01T10:05:00.123Z",
  "ttl_ms": 300000
}
```

#### `job.progress`

Emitted when a running job reports incremental progress.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `job_type` | string | Yes | The dot-namespaced job type. |
| `queue` | string | Yes | The queue the job belongs to. |
| `worker_id` | string | Yes | Identifier of the worker executing the job. |
| `attempt` | integer | Yes | The current attempt number. |
| `progress_percent` | number | Yes | Progress as a percentage (0-100). |
| `progress_message` | string | No | Optional human-readable progress description. |

```json
{
  "job_type": "data.import",
  "queue": "etl",
  "worker_id": "worker-2",
  "attempt": 1,
  "progress_percent": 65.5,
  "progress_message": "Processed 6,550 of 10,000 rows"
}
```

### 4.2 Queue Event Data Schemas

#### `queue.paused`

Emitted when a queue is paused.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `queue` | string | Yes | The name of the paused queue. |
| `paused_by` | string | No | Identifier of the actor that paused the queue. |

```json
{
  "queue": "email",
  "paused_by": "user:ops@example.com"
}
```

#### `queue.resumed`

Emitted when a queue is resumed.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `queue` | string | Yes | The name of the resumed queue. |
| `resumed_by` | string | No | Identifier of the actor that resumed the queue. |

```json
{
  "queue": "email",
  "resumed_by": "user:ops@example.com"
}
```

### 4.3 Worker Event Data Schemas

#### `worker.started`

Emitted when a worker process starts.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `worker_id` | string | Yes | Unique identifier for the worker. |
| `queues` | string[] | Yes | List of queues the worker is polling. |
| `concurrency` | integer | Yes | Maximum number of concurrent jobs this worker will process. |

```json
{
  "worker_id": "worker-1",
  "queues": ["default", "email", "reports"],
  "concurrency": 10
}
```

#### `worker.stopped`

Emitted when a worker process completes shutdown.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `worker_id` | string | Yes | Unique identifier for the worker. |
| `reason` | string | Yes | Reason for stopping. One of: `shutdown`, `signal`, `error`. |
| `jobs_completed` | integer | No | Total number of jobs completed during this worker's lifetime. |
| `uptime_ms` | integer | No | How long the worker was running, in milliseconds. |

```json
{
  "worker_id": "worker-1",
  "reason": "signal",
  "jobs_completed": 12847,
  "uptime_ms": 86400000
}
```

#### `worker.quiet`

Emitted when a worker enters quiet mode (stops fetching, finishes active jobs).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `worker_id` | string | Yes | Unique identifier for the worker. |
| `active_jobs` | integer | Yes | Number of jobs currently in-flight on this worker. |

```json
{
  "worker_id": "worker-1",
  "active_jobs": 3
}
```

#### `worker.heartbeat`

Emitted periodically to indicate worker liveness.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `worker_id` | string | Yes | Unique identifier for the worker. |
| `active_jobs` | integer | Yes | Number of jobs currently in-flight. |
| `queues` | string[] | Yes | Queues being polled. |
| `memory_mb` | number | No | Current memory usage in megabytes. |
| `cpu_percent` | number | No | Current CPU usage as a percentage. |

```json
{
  "worker_id": "worker-1",
  "active_jobs": 7,
  "queues": ["default", "email"],
  "memory_mb": 256.4,
  "cpu_percent": 12.3
}
```

### 4.4 Workflow Event Data Schemas

#### `workflow.started`

Emitted when the first step of a workflow begins execution.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `workflow_id` | string | Yes | Unique identifier for the workflow. |
| `workflow_name` | string | Yes | Human-readable name of the workflow. |
| `total_steps` | integer | Yes | Total number of steps in the workflow. |

```json
{
  "workflow_id": "wf_019539a4-b68c-7def-8000-ffeeddccbbaa",
  "workflow_name": "etl-pipeline",
  "total_steps": 4
}
```

#### `workflow.step_completed`

Emitted when an individual workflow step completes.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `workflow_id` | string | Yes | Unique identifier for the workflow. |
| `workflow_name` | string | Yes | Human-readable name of the workflow. |
| `step_id` | string | Yes | Identifier of the completed step. |
| `step_type` | string | Yes | The job type of the completed step. |
| `duration_ms` | integer | Yes | Execution time of the step in milliseconds. |
| `steps_remaining` | integer | Yes | Number of steps not yet completed. |

```json
{
  "workflow_id": "wf_019539a4-b68c-7def-8000-ffeeddccbbaa",
  "workflow_name": "etl-pipeline",
  "step_id": "extract",
  "step_type": "data.fetch",
  "duration_ms": 2450,
  "steps_remaining": 3
}
```

#### `workflow.completed`

Emitted when all steps in a workflow have completed successfully.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `workflow_id` | string | Yes | Unique identifier for the workflow. |
| `workflow_name` | string | Yes | Human-readable name of the workflow. |
| `total_steps` | integer | Yes | Total number of steps that were executed. |
| `duration_ms` | integer | Yes | Total wall-clock time of the workflow in milliseconds. |

```json
{
  "workflow_id": "wf_019539a4-b68c-7def-8000-ffeeddccbbaa",
  "workflow_name": "etl-pipeline",
  "total_steps": 4,
  "duration_ms": 15230
}
```

#### `workflow.failed`

Emitted when a workflow fails because a step exhausted retries and no fallback is defined.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `workflow_id` | string | Yes | Unique identifier for the workflow. |
| `workflow_name` | string | Yes | Human-readable name of the workflow. |
| `failed_step_id` | string | Yes | Identifier of the step that caused the failure. |
| `failed_step_type` | string | Yes | Job type of the step that caused the failure. |
| `error` | object | Yes | Error information from the failed step. |
| `error.code` | string | Yes | Machine-readable error code. |
| `error.message` | string | Yes | Human-readable error description. |

```json
{
  "workflow_id": "wf_019539a4-b68c-7def-8000-ffeeddccbbaa",
  "workflow_name": "etl-pipeline",
  "failed_step_id": "transform",
  "failed_step_type": "data.transform",
  "error": {
    "code": "handler_error",
    "message": "Out of memory: input dataset exceeds 4GB limit"
  }
}
```

### 4.5 Cron Event Data Schemas

#### `cron.triggered`

Emitted when a cron schedule fires and a new job is enqueued.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cron_name` | string | Yes | The registered name of the cron job. |
| `cron_expr` | string | Yes | The cron expression that fired. |
| `job_type` | string | Yes | The job type that was enqueued. |
| `job_id` | string | Yes | The ID of the newly enqueued job. |
| `scheduled_at` | string (RFC 3339) | Yes | The nominal fire time for this cron tick. |

```json
{
  "cron_name": "daily-report",
  "cron_expr": "0 9 * * *",
  "job_type": "report.generate",
  "job_id": "job_019539a4-b68c-7def-8000-99887766aabb",
  "scheduled_at": "2025-06-02T09:00:00.000Z"
}
```

#### `cron.skipped`

Emitted when a cron schedule fires but the job is not enqueued due to overlap prevention.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cron_name` | string | Yes | The registered name of the cron job. |
| `cron_expr` | string | Yes | The cron expression that fired. |
| `job_type` | string | Yes | The job type that would have been enqueued. |
| `reason` | string | Yes | Why the job was skipped (e.g., `"overlap_prevention"`, `"queue_paused"`). |
| `existing_job_id` | string | No | The ID of the still-running job that caused the skip. |

```json
{
  "cron_name": "daily-report",
  "cron_expr": "0 9 * * *",
  "job_type": "report.generate",
  "reason": "overlap_prevention",
  "existing_job_id": "job_019539a4-b68c-7def-8000-112233445566"
}
```

---

## 5. Conformance Requirements

### 5.1 Event Emission by Conformance Level

The following table summarizes which events MUST, SHOULD, or MAY be emitted at each conformance level. A Level N implementation MUST satisfy all requirements from levels 0 through N.

**Rationale for the MUST/SHOULD/MAY tiering:** Core job events are MUST because they represent the minimum viable observability contract. Extended events are MUST-when-supported because omitting them when the feature exists creates an inconsistent observability surface. Worker events are SHOULD because some deployment models (in-process, serverless) do not have a meaningful worker lifecycle.

#### Level 0 -- Core

| Event Type | Requirement | Rationale |
|------------|-------------|-----------|
| `job.enqueued` | MUST | Producers need confirmation that jobs entered the queue. |
| `job.started` | MUST | Operators need to know when processing begins. |
| `job.completed` | MUST | The fundamental success signal. |
| `job.failed` | MUST | The fundamental failure signal. |
| `job.discarded` | MUST | Operators MUST know when jobs reach a terminal failure state. |
| `worker.started` | SHOULD | Useful for monitoring but not meaningful in all deployment models. |
| `worker.stopped` | SHOULD | Useful for monitoring but not meaningful in all deployment models. |
| `worker.heartbeat` | SHOULD | Useful for liveness detection. |

#### Level 1 -- Reliable

All Level 0 requirements, plus:

| Event Type | Requirement | Rationale |
|------------|-------------|-----------|
| `job.retrying` | MUST | Operators need to distinguish retry from permanent failure. |
| `job.cancelled` | MUST | Cancellation must be observable for audit and debugging. |
| `job.heartbeat` | MUST | Visibility timeout extensions must be trackable. |
| `worker.quiet` | SHOULD | Useful for graceful shutdown monitoring. |

#### Level 2 -- Scheduled

All Level 1 requirements, plus:

| Event Type | Requirement | Rationale |
|------------|-------------|-----------|
| `job.scheduled` | MUST | Operators need to confirm that delayed jobs are accepted. |
| `job.expired` | MUST | Expired jobs must not silently disappear. |
| `cron.triggered` | MUST | Cron job execution must be verifiable. |
| `cron.skipped` | MUST | Skipped cron runs must be visible for debugging silent failures. |

#### Level 3 -- Orchestration

All Level 2 requirements, plus:

| Event Type | Requirement | Rationale |
|------------|-------------|-----------|
| `workflow.started` | MUST | Multi-step pipeline execution must be observable at the workflow level. |
| `workflow.step_completed` | MUST | Individual step progress within a workflow must be trackable. |
| `workflow.completed` | MUST | Overall workflow success must be signaled. |
| `workflow.failed` | MUST | Overall workflow failure must be signaled. |
| `job.progress` | SHOULD | Progress reporting is useful but not always implemented by handlers. |

#### Level 4 -- Advanced

All Level 3 requirements, plus:

| Event Type | Requirement | Rationale |
|------------|-------------|-----------|
| `queue.paused` | MUST | Queue administrative actions must be auditable. |
| `queue.resumed` | MUST | Queue administrative actions must be auditable. |

### 5.2 Conformance Validation

A conformance test suite for events MUST verify:

1. **Emission completeness.** All MUST events for the declared conformance level are emitted at the correct lifecycle points.
2. **Envelope validity.** Every emitted event conforms to the envelope schema defined in [Section 2](#2-event-envelope-specification).
3. **Data schema validity.** The `data` field of every emitted event conforms to the schema for its `type` as defined in [Section 4](#4-event-data-schemas).
4. **Temporal ordering.** Events for a single job MUST be emitted in lifecycle order (e.g., `job.enqueued` before `job.started` before `job.completed`).
5. **Idempotent identifiers.** No two events from the same `source` share the same `id`.

**Rationale for MUST (temporal ordering):** Out-of-order events break causal reasoning. A consumer that receives `job.completed` before `job.started` cannot compute execution duration. Implementations MUST emit events in lifecycle order within a single job's timeline, though events across different jobs MAY be interleaved.

---

## 6. Subscription and Filtering

The transport for event delivery is implementation-defined. This section defines the semantics that any subscription mechanism SHOULD support to enable interoperable consumers.

### 6.1 Filter Model

Implementations that support event subscription SHOULD accept filters on the following dimensions:

| Dimension | Type | Description | Example |
|-----------|------|-------------|---------|
| `event_types` | string[] | Restrict to specific event types. Supports prefix matching with `*`. | `["job.completed", "job.failed"]` or `["job.*"]` |
| `queues` | string[] | Restrict to events from specific queues. | `["email", "reports"]` |
| `job_types` | string[] | Restrict to events for specific job types. | `["email.send"]` |
| `sources` | string[] | Restrict to events from specific sources. | `["ojs://billing-api/*"]` |

Filters are combined with AND semantics: an event must match all specified dimensions to be delivered.

### 6.2 WebSocket Subscription

Implementations that support WebSocket event streaming SHOULD accept subscription messages conforming to this format.

Connect: `ws://{host}/ojs/v1/ws`

Subscribe message:

```json
{
  "action": "subscribe",
  "channel": "events",
  "filter": {
    "event_types": ["job.completed", "job.failed"],
    "queues": ["email"]
  }
}
```

Subscription acknowledgment:

```json
{
  "action": "subscribed",
  "channel": "events",
  "subscription_id": "sub_019539a4-b68c-7def-8000-001122334455"
}
```

Unsubscribe message:

```json
{
  "action": "unsubscribe",
  "subscription_id": "sub_019539a4-b68c-7def-8000-001122334455"
}
```

After subscription, the server pushes events as individual JSON messages matching the envelope format from [Section 2](#2-event-envelope-specification).

### 6.3 gRPC Subscription

Implementations that support gRPC event streaming SHOULD provide a `StreamEvents` RPC.

```protobuf
message StreamEventsRequest {
  repeated string event_types = 1;    // e.g., ["job.completed", "job.failed"]
  repeated string queues = 2;         // e.g., ["email"]
  repeated string job_types = 3;      // e.g., ["email.send"]
}

rpc StreamEvents(StreamEventsRequest) returns (stream Event);
```

The server sends `Event` messages on the stream as they occur, filtered by the request parameters.

### 6.4 HTTP Polling (Optional)

Implementations MAY provide an HTTP polling endpoint for environments where streaming is not feasible.

```
GET /ojs/v1/events?after={event_id}&types=job.completed,job.failed&queues=email&limit=100
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `after` | string | Return events after this event ID (cursor-based pagination). |
| `types` | string (comma-separated) | Filter by event types. |
| `queues` | string (comma-separated) | Filter by queue names. |
| `job_types` | string (comma-separated) | Filter by job types. |
| `limit` | integer | Maximum number of events to return (default: 100, max: 1000). |

Response:

```json
{
  "events": [
    { "specversion": "1.0", "id": "evt_...", "type": "job.completed", "..." : "..." }
  ],
  "cursor": "evt_019539a4-b68c-7def-8000-ffeeddccbb00",
  "has_more": true
}
```

### 6.5 Webhooks

Implementations MAY support webhook delivery. Webhook configuration is implementation-defined, but the payload delivered to webhook endpoints MUST conform to the event envelope format from [Section 2](#2-event-envelope-specification).

**Rationale for MUST (envelope conformance on webhooks):** Webhook consumers should be able to reuse the same event parsing logic regardless of whether events arrive via WebSocket, gRPC stream, or webhook POST. Using a different format for webhooks would require consumers to implement multiple parsers.

Implementations that support webhooks SHOULD:

- Deliver events via HTTP POST to the configured URL.
- Set `Content-Type: application/json`.
- Include an `X-OJS-Signature` header for payload verification (HMAC-SHA256 of the body using a shared secret).
- Retry delivery on 5xx responses with exponential backoff.
- Respect a configurable timeout (default: 30 seconds).

---

## 7. Metrics Specification

### 7.1 OpenTelemetry Metrics

Implementations SHOULD expose metrics via [OpenTelemetry](https://opentelemetry.io/). The metric names, types, and labels defined here constitute the standard OJS metrics vocabulary.

**Rationale for SHOULD (not MUST):** Metrics infrastructure varies widely across deployments. Some implementations may expose Prometheus endpoints, others StatsD, others CloudWatch. Mandating OpenTelemetry specifically would be overly prescriptive. However, the metric names and semantics defined here MUST be used when metrics are exposed, to ensure dashboard and alerting portability.

### 7.2 Metric Definitions

#### Counters

Counters track cumulative totals and MUST only increase (except on process restart).

| Metric Name | Unit | Labels | Description |
|-------------|------|--------|-------------|
| `ojs.jobs.enqueued` | `{job}` | `job_type`, `queue` | Total number of jobs enqueued. |
| `ojs.jobs.completed` | `{job}` | `job_type`, `queue` | Total number of jobs that completed successfully. |
| `ojs.jobs.failed` | `{job}` | `job_type`, `queue` | Total number of jobs that reached terminal failure (discarded). |

#### Histograms

Histograms track the distribution of values.

| Metric Name | Unit | Labels | Description |
|-------------|------|--------|-------------|
| `ojs.jobs.duration_ms` | `ms` | `job_type`, `queue` | Execution wall-clock time per job. Recorded on `job.completed` and `job.failed`. |
| `ojs.jobs.wait_ms` | `ms` | `job_type`, `queue` | Time from `enqueued_at` to `started_at`. Recorded on `job.started`. |

Implementations SHOULD use the following default histogram bucket boundaries for `ojs.jobs.duration_ms`:

```
[5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000, 300000]
```

And for `ojs.jobs.wait_ms`:

```
[10, 50, 100, 500, 1000, 5000, 10000, 30000, 60000, 300000, 600000]
```

#### Gauges

Gauges track current values that can increase or decrease.

| Metric Name | Unit | Labels | Description |
|-------------|------|--------|-------------|
| `ojs.queue.depth` | `{job}` | `queue` | Current number of jobs in `available` state per queue. |
| `ojs.queue.active` | `{job}` | `queue` | Current number of jobs in `active` state per queue. |
| `ojs.dead_letter.depth` | `{job}` | `queue` | Current number of jobs in the dead letter queue (per source queue). |

### 7.3 Label Conventions

| Label | Type | Description |
|-------|------|-------------|
| `job_type` | string | The dot-namespaced job type (e.g., `email.send`). |
| `queue` | string | The queue name (e.g., `email`, `default`). |

Implementations MUST NOT use high-cardinality values (such as job IDs) as metric labels. Job IDs MUST be conveyed through events and traces, not metrics.

**Rationale for MUST NOT:** High-cardinality metric labels cause memory exhaustion and performance degradation in metrics backends (Prometheus, Datadog, etc.). A queue processing millions of unique job IDs would generate millions of time series, which is unsustainable.

### 7.4 Metric-to-Event Relationship

Every metric increment corresponds to an event emission. The relationship is:

| Metric | Incremented When | Corresponding Event |
|--------|-----------------|---------------------|
| `ojs.jobs.enqueued` | Job enqueued | `job.enqueued` |
| `ojs.jobs.completed` | Job completed | `job.completed` |
| `ojs.jobs.failed` | Job discarded | `job.discarded` |
| `ojs.jobs.duration_ms` | Job completed or failed | `job.completed`, `job.failed` |
| `ojs.jobs.wait_ms` | Job started | `job.started` |

---

## 8. Distributed Tracing

### 8.1 W3C Trace Context Propagation

Jobs SHOULD propagate [W3C Trace Context](https://www.w3.org/TR/trace-context/) to enable end-to-end distributed tracing across services and job boundaries.

When a job is enqueued with a `trace_id` in its `meta` field, implementations MUST include the `trace_id` in all events emitted for that job.

**Rationale for MUST:** If a job carries trace context but events do not include it, the trace is broken at the job boundary. This defeats the purpose of distributed tracing, making it impossible to correlate a job's execution with the request that initiated it.

### 8.2 Trace Context in Job Envelope

Trace context is carried in the job's `meta` field:

```json
{
  "id": "job_019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "type": "email.send",
  "args": ["user@example.com", "welcome"],
  "meta": {
    "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
    "tracestate": "congo=t61rcWkgMzE",
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
  }
}
```

The `trace_id` field in `meta` is a convenience extraction of the trace ID from the W3C `traceparent` header. Both fields SHOULD be set; if only one is present, implementations MUST honor whichever is available.

### 8.3 Trace Context in Events

When a job has trace context, every event for that job MUST include the `trace_id` in the `data` field:

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-b68c-7def-8000-aabbccddeeff",
  "type": "job.completed",
  "source": "ojs://my-service/workers/worker-1",
  "time": "2025-06-01T10:30:02.789Z",
  "subject": "job_019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "data": {
    "job_type": "email.send",
    "queue": "email",
    "duration_ms": 1333,
    "attempt": 1,
    "result": { "message_id": "msg_abc123" },
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
  }
}
```

### 8.4 Span Creation

Implementations SHOULD create OpenTelemetry spans for the following operations:

| Operation | Span Name | Span Kind |
|-----------|-----------|-----------|
| Enqueue a job | `ojs.enqueue {job_type}` | PRODUCER |
| Execute a job | `ojs.execute {job_type}` | CONSUMER |
| Workflow execution | `ojs.workflow {workflow_name}` | INTERNAL |

The enqueue span SHOULD be the parent of the execute span, connected via the `traceparent` propagated through the job's `meta` field. This creates a causal link between the producer and consumer in the trace timeline.

---

## 9. Event Delivery Guarantees

### 9.1 Delivery Semantics

OJS defines two delivery guarantee levels for events. Implementations MUST declare which level they provide.

**Rationale for MUST (declaration):** Consumers need to know whether they can rely on receiving every event or whether they must tolerate gaps. An implementation that claims at-least-once but silently drops events under load creates unreliable downstream systems.

#### At-Least-Once (SHOULD)

Implementations SHOULD provide at-least-once event delivery.

**Rationale for SHOULD:** At-least-once delivery ensures that no lifecycle transition is silently lost. This is critical for audit logs, billing systems, and workflow orchestration that depend on event completeness. The cost is that consumers must handle duplicate events, which is a well-understood engineering pattern (idempotent consumers via event ID deduplication).

At-least-once delivery means:

- Every event is delivered to every active subscriber at least once.
- Events MAY be delivered more than once (duplicates are possible).
- Consumers MUST be prepared to handle duplicate events (idempotent processing using `id`).
- Events are persisted before delivery acknowledgment.

#### Best-Effort (MAY)

Implementations MAY provide best-effort event delivery as a lower-cost alternative.

Best-effort delivery means:

- Events are emitted on a best-effort basis.
- Events MAY be lost under high load, during network partitions, or during process restarts.
- No delivery acknowledgment or retry is required.
- This level is acceptable for metrics collection, logging, and non-critical monitoring.

### 9.2 Ordering

Events for a single job MUST be delivered in lifecycle order to a given subscriber.

**Rationale for MUST:** Out-of-order events break state reconstruction. A consumer building a job timeline from events must receive `job.enqueued` before `job.started` before `job.completed` to correctly compute metrics like wait time and execution duration.

Events across different jobs MAY be delivered in any order. Global ordering across all jobs is not required and would impose unacceptable performance costs on high-throughput systems.

### 9.3 Event Retention

Implementations that persist events SHOULD support configurable retention:

| Configuration | Default | Description |
|---------------|---------|-------------|
| `events.retention_period` | `168h` (7 days) | How long events are retained before pruning. |
| `events.max_count` | `1000000` | Maximum number of events retained (oldest pruned first). |

---

## 10. Complete Examples

This section provides end-to-end event sequences for common job lifecycle scenarios.

### 10.1 Successful Job Execution

A job is enqueued, picked up by a worker, and completes successfully.

**Event 1: `job.enqueued`**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-b68c-7def-8000-000000000001",
  "type": "job.enqueued",
  "source": "ojs://billing-api/api",
  "time": "2025-06-01T10:30:00.123Z",
  "subject": "job_019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "data": {
    "job_type": "email.send",
    "queue": "email",
    "priority": 0
  }
}
```

**Event 2: `job.started`**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-b68c-7def-8000-000000000002",
  "type": "job.started",
  "source": "ojs://billing-api/workers/worker-1",
  "time": "2025-06-01T10:30:01.456Z",
  "subject": "job_019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "data": {
    "job_type": "email.send",
    "queue": "email",
    "worker_id": "worker-1",
    "attempt": 1
  }
}
```

**Event 3: `job.completed`**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-b68c-7def-8000-000000000003",
  "type": "job.completed",
  "source": "ojs://billing-api/workers/worker-1",
  "time": "2025-06-01T10:30:02.789Z",
  "subject": "job_019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "data": {
    "job_type": "email.send",
    "queue": "email",
    "duration_ms": 1333,
    "attempt": 1,
    "result": { "message_id": "msg_abc123" }
  }
}
```

### 10.2 Job Failure with Retry and Eventual Discard

A job fails twice, is retried, then exhausts retries and is discarded to the dead letter queue.

**Event 1: `job.enqueued`**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-c000-7def-8000-000000000001",
  "type": "job.enqueued",
  "source": "ojs://order-service/api",
  "time": "2025-06-01T11:00:00.000Z",
  "subject": "job_019539a4-c000-7def-8000-aaaaaaaaaaaa",
  "data": {
    "job_type": "payment.charge",
    "queue": "payments"
  }
}
```

**Event 2: `job.started` (attempt 1)**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-c000-7def-8000-000000000002",
  "type": "job.started",
  "source": "ojs://order-service/workers/worker-2",
  "time": "2025-06-01T11:00:00.500Z",
  "subject": "job_019539a4-c000-7def-8000-aaaaaaaaaaaa",
  "data": {
    "job_type": "payment.charge",
    "queue": "payments",
    "worker_id": "worker-2",
    "attempt": 1
  }
}
```

**Event 3: `job.failed` (attempt 1)**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-c000-7def-8000-000000000003",
  "type": "job.failed",
  "source": "ojs://order-service/workers/worker-2",
  "time": "2025-06-01T11:00:01.200Z",
  "subject": "job_019539a4-c000-7def-8000-aaaaaaaaaaaa",
  "data": {
    "job_type": "payment.charge",
    "queue": "payments",
    "attempt": 1,
    "error": {
      "code": "handler_error",
      "message": "Payment gateway timeout: 10.0.1.50:443",
      "retryable": true
    },
    "duration_ms": 700
  }
}
```

**Event 4: `job.retrying` (scheduling retry for attempt 2)**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-c000-7def-8000-000000000004",
  "type": "job.retrying",
  "source": "ojs://order-service/workers/worker-2",
  "time": "2025-06-01T11:00:01.210Z",
  "subject": "job_019539a4-c000-7def-8000-aaaaaaaaaaaa",
  "data": {
    "job_type": "payment.charge",
    "queue": "payments",
    "attempt": 1,
    "max_attempts": 3,
    "next_retry_at": "2025-06-01T11:00:03.210Z",
    "error": {
      "code": "handler_error",
      "message": "Payment gateway timeout: 10.0.1.50:443"
    }
  }
}
```

**Event 5: `job.started` (attempt 2)**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-c000-7def-8000-000000000005",
  "type": "job.started",
  "source": "ojs://order-service/workers/worker-3",
  "time": "2025-06-01T11:00:03.300Z",
  "subject": "job_019539a4-c000-7def-8000-aaaaaaaaaaaa",
  "data": {
    "job_type": "payment.charge",
    "queue": "payments",
    "worker_id": "worker-3",
    "attempt": 2
  }
}
```

**Event 6: `job.failed` (attempt 2)**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-c000-7def-8000-000000000006",
  "type": "job.failed",
  "source": "ojs://order-service/workers/worker-3",
  "time": "2025-06-01T11:00:04.100Z",
  "subject": "job_019539a4-c000-7def-8000-aaaaaaaaaaaa",
  "data": {
    "job_type": "payment.charge",
    "queue": "payments",
    "attempt": 2,
    "error": {
      "code": "handler_error",
      "message": "Payment gateway timeout: 10.0.1.50:443",
      "retryable": true
    },
    "duration_ms": 800
  }
}
```

**Event 7: `job.retrying` (scheduling retry for attempt 3)**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-c000-7def-8000-000000000007",
  "type": "job.retrying",
  "source": "ojs://order-service/workers/worker-3",
  "time": "2025-06-01T11:00:04.110Z",
  "subject": "job_019539a4-c000-7def-8000-aaaaaaaaaaaa",
  "data": {
    "job_type": "payment.charge",
    "queue": "payments",
    "attempt": 2,
    "max_attempts": 3,
    "next_retry_at": "2025-06-01T11:00:08.110Z",
    "error": {
      "code": "handler_error",
      "message": "Payment gateway timeout: 10.0.1.50:443"
    }
  }
}
```

**Event 8: `job.started` (attempt 3)**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-c000-7def-8000-000000000008",
  "type": "job.started",
  "source": "ojs://order-service/workers/worker-1",
  "time": "2025-06-01T11:00:08.200Z",
  "subject": "job_019539a4-c000-7def-8000-aaaaaaaaaaaa",
  "data": {
    "job_type": "payment.charge",
    "queue": "payments",
    "worker_id": "worker-1",
    "attempt": 3
  }
}
```

**Event 9: `job.failed` (attempt 3, final)**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-c000-7def-8000-000000000009",
  "type": "job.failed",
  "source": "ojs://order-service/workers/worker-1",
  "time": "2025-06-01T11:00:09.000Z",
  "subject": "job_019539a4-c000-7def-8000-aaaaaaaaaaaa",
  "data": {
    "job_type": "payment.charge",
    "queue": "payments",
    "attempt": 3,
    "error": {
      "code": "handler_error",
      "message": "Payment gateway timeout: 10.0.1.50:443",
      "retryable": true
    },
    "duration_ms": 800
  }
}
```

**Event 10: `job.discarded` (moved to dead letter queue)**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-c000-7def-8000-000000000010",
  "type": "job.discarded",
  "source": "ojs://order-service/workers/worker-1",
  "time": "2025-06-01T11:00:09.010Z",
  "subject": "job_019539a4-c000-7def-8000-aaaaaaaaaaaa",
  "data": {
    "job_type": "payment.charge",
    "queue": "payments",
    "total_attempts": 3,
    "last_error": {
      "code": "handler_error",
      "message": "Payment gateway timeout: 10.0.1.50:443"
    }
  }
}
```

### 10.3 Scheduled Job with Cancellation

A job is scheduled for future execution, then cancelled before it runs.

**Event 1: `job.scheduled`**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-d000-7def-8000-000000000001",
  "type": "job.scheduled",
  "source": "ojs://marketing-api/api",
  "time": "2025-06-01T12:00:00.000Z",
  "subject": "job_019539a4-d000-7def-8000-bbbbbbbbbbbb",
  "data": {
    "job_type": "campaign.launch",
    "queue": "marketing",
    "scheduled_at": "2025-06-02T09:00:00.000Z"
  }
}
```

**Event 2: `job.cancelled`**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-d000-7def-8000-000000000002",
  "type": "job.cancelled",
  "source": "ojs://marketing-api/api",
  "time": "2025-06-01T14:30:00.000Z",
  "subject": "job_019539a4-d000-7def-8000-bbbbbbbbbbbb",
  "data": {
    "job_type": "campaign.launch",
    "queue": "marketing",
    "cancelled_by": "user:marketing-lead@example.com",
    "reason": "Campaign budget was not approved"
  }
}
```

### 10.4 Cron Job with Overlap Skip

A cron job fires, then fires again while the first instance is still running.

**Event 1: `cron.triggered` (first fire)**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-e000-7def-8000-000000000001",
  "type": "cron.triggered",
  "source": "ojs://analytics-service/cron",
  "time": "2025-06-01T09:00:00.100Z",
  "subject": "daily-report",
  "data": {
    "cron_name": "daily-report",
    "cron_expr": "0 9 * * *",
    "job_type": "report.generate",
    "job_id": "job_019539a4-e000-7def-8000-cccccccccccc",
    "scheduled_at": "2025-06-01T09:00:00.000Z"
  }
}
```

**Event 2: `cron.skipped` (second fire, overlapping)**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-e100-7def-8000-000000000001",
  "type": "cron.skipped",
  "source": "ojs://analytics-service/cron",
  "time": "2025-06-02T09:00:00.100Z",
  "subject": "daily-report",
  "data": {
    "cron_name": "daily-report",
    "cron_expr": "0 9 * * *",
    "job_type": "report.generate",
    "reason": "overlap_prevention",
    "existing_job_id": "job_019539a4-e000-7def-8000-cccccccccccc"
  }
}
```

### 10.5 Workflow Execution

A multi-step ETL pipeline workflow executes to completion.

**Event 1: `workflow.started`**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-f000-7def-8000-000000000001",
  "type": "workflow.started",
  "source": "ojs://data-platform/api",
  "time": "2025-06-01T15:00:00.000Z",
  "subject": "wf_019539a4-f000-7def-8000-dddddddddddd",
  "data": {
    "workflow_id": "wf_019539a4-f000-7def-8000-dddddddddddd",
    "workflow_name": "etl-pipeline",
    "total_steps": 3
  }
}
```

**Event 2: `workflow.step_completed` (step 1: extract)**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-f000-7def-8000-000000000002",
  "type": "workflow.step_completed",
  "source": "ojs://data-platform/workers/worker-1",
  "time": "2025-06-01T15:00:05.000Z",
  "subject": "wf_019539a4-f000-7def-8000-dddddddddddd",
  "data": {
    "workflow_id": "wf_019539a4-f000-7def-8000-dddddddddddd",
    "workflow_name": "etl-pipeline",
    "step_id": "extract",
    "step_type": "data.fetch",
    "duration_ms": 4800,
    "steps_remaining": 2
  }
}
```

**Event 3: `workflow.step_completed` (step 2: transform)**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-f000-7def-8000-000000000003",
  "type": "workflow.step_completed",
  "source": "ojs://data-platform/workers/worker-2",
  "time": "2025-06-01T15:00:12.000Z",
  "subject": "wf_019539a4-f000-7def-8000-dddddddddddd",
  "data": {
    "workflow_id": "wf_019539a4-f000-7def-8000-dddddddddddd",
    "workflow_name": "etl-pipeline",
    "step_id": "transform",
    "step_type": "data.transform",
    "duration_ms": 6500,
    "steps_remaining": 1
  }
}
```

**Event 4: `workflow.step_completed` (step 3: load)**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-f000-7def-8000-000000000004",
  "type": "workflow.step_completed",
  "source": "ojs://data-platform/workers/worker-1",
  "time": "2025-06-01T15:00:15.000Z",
  "subject": "wf_019539a4-f000-7def-8000-dddddddddddd",
  "data": {
    "workflow_id": "wf_019539a4-f000-7def-8000-dddddddddddd",
    "workflow_name": "etl-pipeline",
    "step_id": "load",
    "step_type": "data.load",
    "duration_ms": 2800,
    "steps_remaining": 0
  }
}
```

**Event 5: `workflow.completed`**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-f000-7def-8000-000000000005",
  "type": "workflow.completed",
  "source": "ojs://data-platform/api",
  "time": "2025-06-01T15:00:15.010Z",
  "subject": "wf_019539a4-f000-7def-8000-dddddddddddd",
  "data": {
    "workflow_id": "wf_019539a4-f000-7def-8000-dddddddddddd",
    "workflow_name": "etl-pipeline",
    "total_steps": 3,
    "duration_ms": 15010
  }
}
```

### 10.6 Worker Lifecycle

A worker starts, processes jobs, enters quiet mode, and stops.

**Event 1: `worker.started`**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-a000-7def-8000-000000000001",
  "type": "worker.started",
  "source": "ojs://billing-api/workers/worker-1",
  "time": "2025-06-01T08:00:00.000Z",
  "subject": "worker-1",
  "data": {
    "worker_id": "worker-1",
    "queues": ["default", "email", "reports"],
    "concurrency": 10
  }
}
```

**Event 2: `worker.heartbeat`**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-a000-7def-8000-000000000002",
  "type": "worker.heartbeat",
  "source": "ojs://billing-api/workers/worker-1",
  "time": "2025-06-01T08:00:30.000Z",
  "subject": "worker-1",
  "data": {
    "worker_id": "worker-1",
    "active_jobs": 7,
    "queues": ["default", "email", "reports"],
    "memory_mb": 256.4,
    "cpu_percent": 12.3
  }
}
```

**Event 3: `worker.quiet`**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-a000-7def-8000-000000000003",
  "type": "worker.quiet",
  "source": "ojs://billing-api/workers/worker-1",
  "time": "2025-06-01T18:00:00.000Z",
  "subject": "worker-1",
  "data": {
    "worker_id": "worker-1",
    "active_jobs": 3
  }
}
```

**Event 4: `worker.stopped`**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-a000-7def-8000-000000000004",
  "type": "worker.stopped",
  "source": "ojs://billing-api/workers/worker-1",
  "time": "2025-06-01T18:00:05.000Z",
  "subject": "worker-1",
  "data": {
    "worker_id": "worker-1",
    "reason": "signal",
    "jobs_completed": 12847,
    "uptime_ms": 36005000
  }
}
```

### 10.7 Queue Pause and Resume

An operator pauses a queue during an incident and resumes it afterward.

**Event 1: `queue.paused`**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-b000-7def-8000-000000000001",
  "type": "queue.paused",
  "source": "ojs://billing-api/api",
  "time": "2025-06-01T16:00:00.000Z",
  "subject": "email",
  "data": {
    "queue": "email",
    "paused_by": "user:oncall@example.com"
  }
}
```

**Event 2: `queue.resumed`**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-b000-7def-8000-000000000002",
  "type": "queue.resumed",
  "source": "ojs://billing-api/api",
  "time": "2025-06-01T16:45:00.000Z",
  "subject": "email",
  "data": {
    "queue": "email",
    "resumed_by": "user:oncall@example.com"
  }
}
```

### 10.8 Job with Distributed Trace Context

A job enqueued with W3C Trace Context, showing trace propagation through events.

**Event 1: `job.enqueued` (with trace context)**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-g000-7def-8000-000000000001",
  "type": "job.enqueued",
  "source": "ojs://checkout-service/api",
  "time": "2025-06-01T20:00:00.000Z",
  "subject": "job_019539a4-g000-7def-8000-eeeeeeeeeeee",
  "data": {
    "job_type": "order.process",
    "queue": "orders",
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
  }
}
```

**Event 2: `job.completed` (with trace context)**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-g000-7def-8000-000000000002",
  "type": "job.completed",
  "source": "ojs://checkout-service/workers/worker-5",
  "time": "2025-06-01T20:00:02.500Z",
  "subject": "job_019539a4-g000-7def-8000-eeeeeeeeeeee",
  "data": {
    "job_type": "order.process",
    "queue": "orders",
    "duration_ms": 2300,
    "attempt": 1,
    "result": { "order_id": "ord_12345", "status": "confirmed" },
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
  }
}
```

### 10.9 Job Expiration (TTL Exceeded)

A time-sensitive job expires before a worker picks it up.

**Event 1: `job.enqueued`**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-h000-7def-8000-000000000001",
  "type": "job.enqueued",
  "source": "ojs://notification-service/api",
  "time": "2025-06-01T10:00:00.000Z",
  "subject": "job_019539a4-h000-7def-8000-ffffffffffff",
  "data": {
    "job_type": "notification.push",
    "queue": "notifications"
  }
}
```

**Event 2: `job.expired`**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-h000-7def-8000-000000000002",
  "type": "job.expired",
  "source": "ojs://notification-service/scheduler",
  "time": "2025-06-01T10:05:00.123Z",
  "subject": "job_019539a4-h000-7def-8000-ffffffffffff",
  "data": {
    "job_type": "notification.push",
    "queue": "notifications",
    "created_at": "2025-06-01T10:00:00.000Z",
    "expired_at": "2025-06-01T10:05:00.123Z",
    "ttl_ms": 300000
  }
}
```

### 10.10 Job Progress Reporting

A long-running data import job reports incremental progress.

**Event 1: `job.started`**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-i000-7def-8000-000000000001",
  "type": "job.started",
  "source": "ojs://data-service/workers/worker-4",
  "time": "2025-06-01T14:00:00.000Z",
  "subject": "job_019539a4-i000-7def-8000-111111111111",
  "data": {
    "job_type": "data.import",
    "queue": "etl",
    "worker_id": "worker-4",
    "attempt": 1
  }
}
```

**Event 2: `job.progress` (25%)**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-i000-7def-8000-000000000002",
  "type": "job.progress",
  "source": "ojs://data-service/workers/worker-4",
  "time": "2025-06-01T14:01:00.000Z",
  "subject": "job_019539a4-i000-7def-8000-111111111111",
  "data": {
    "job_type": "data.import",
    "queue": "etl",
    "worker_id": "worker-4",
    "attempt": 1,
    "progress_percent": 25.0,
    "progress_message": "Processed 2,500 of 10,000 records"
  }
}
```

**Event 3: `job.progress` (75%)**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-i000-7def-8000-000000000003",
  "type": "job.progress",
  "source": "ojs://data-service/workers/worker-4",
  "time": "2025-06-01T14:03:00.000Z",
  "subject": "job_019539a4-i000-7def-8000-111111111111",
  "data": {
    "job_type": "data.import",
    "queue": "etl",
    "worker_id": "worker-4",
    "attempt": 1,
    "progress_percent": 75.0,
    "progress_message": "Processed 7,500 of 10,000 records"
  }
}
```

**Event 4: `job.completed`**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-i000-7def-8000-000000000004",
  "type": "job.completed",
  "source": "ojs://data-service/workers/worker-4",
  "time": "2025-06-01T14:04:00.000Z",
  "subject": "job_019539a4-i000-7def-8000-111111111111",
  "data": {
    "job_type": "data.import",
    "queue": "etl",
    "duration_ms": 240000,
    "attempt": 1,
    "result": { "records_imported": 10000, "errors": 0 }
  }
}
```

---

## 11. Prior Art

The OJS event vocabulary draws from established systems and standards. This section documents the specific influences and how OJS adapts them.

### 11.1 CloudEvents

[CloudEvents v1.0](https://github.com/cloudevents/spec) provides the structural template for the OJS event envelope. The context attributes (`specversion`, `id`, `type`, `source`, `time`, `subject`) are directly adopted from CloudEvents. OJS narrows the CloudEvents model by mandating JSON as the `datacontenttype` and defining a fixed vocabulary of event types, whereas CloudEvents is type-agnostic.

### 11.2 BullMQ

[BullMQ](https://docs.bullmq.io/) pioneered the use of Redis Streams for job lifecycle events. BullMQ emits events including `completed`, `failed`, `progress`, `stalled`, `active`, `waiting`, `delayed`, and `drained`. The OJS event catalog is a superset of BullMQ's event vocabulary, extended with explicit retry, workflow, cron, and worker lifecycle events. BullMQ's stream-based architecture -- where events are published to a Redis Stream and consumers read from configurable positions -- directly influenced OJS's at-least-once delivery model and cursor-based HTTP polling design.

### 11.3 Sidekiq / Faktory

[Sidekiq](https://sidekiq.org/) and [Faktory](https://github.com/contribsys/faktory) define the worker heartbeat protocol (`BEAT` command with server-initiated state changes: `quiet`, `terminate`) that informs the `worker.quiet` and `worker.stopped` events. Faktory's structured error format (`{errtype, message, backtrace}`) directly influenced the `error` object schema in `job.failed` and `job.retrying` events.

### 11.4 Oban

[Oban](https://hexdocs.pm/oban/) (Elixir) provides the most granular job state model among existing systems, with eight states including `retryable`, `cancelled`, and `discarded`. OJS adopts Oban's state naming conventions. Oban's telemetry events (via Erlang's `:telemetry` library) -- emitted as `[:oban, :job, :start]`, `[:oban, :job, :stop]`, `[:oban, :job, :exception]` -- demonstrate the value of structured lifecycle events for metrics and monitoring.

### 11.5 OpenTelemetry

[OpenTelemetry](https://opentelemetry.io/) provides the metrics naming conventions and semantic conventions used in [Section 7](#7-metrics-specification). The `ojs.` metric prefix follows OpenTelemetry's namespace convention. The histogram bucket boundaries are aligned with OpenTelemetry's default latency buckets. The W3C Trace Context propagation defined in [Section 8](#8-distributed-tracing) is the OpenTelemetry standard for distributed trace correlation.

### 11.6 Temporal

[Temporal](https://temporal.io/) influenced the workflow event model. Temporal emits granular workflow events (`WorkflowExecutionStarted`, `WorkflowExecutionCompleted`, `ActivityTaskStarted`, `ActivityTaskCompleted`) that enable full workflow replay and observability. OJS simplifies this model for the background job context, mapping Temporal's activities to OJS workflow steps.

---

*OJS Events Specification v1.0.0-rc.1 -- Release Candidate -- June 2025*
*Part of the Open Job Spec: https://openjobspec.org*
