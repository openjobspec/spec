# Open Job Spec: Distributed Tracing

| Field        | Value                                              |
|-------------|---------------------------------------------------|
| **Title**   | OJS Distributed Tracing Specification              |
| **Version** | 0.2.0                                              |
| **Date**    | 2026-02-19                                         |
| **Status**  | Draft                                              |
| **Maturity** | Alpha                                              |
| **Tier**    | Official Extension                                 |
| **URI**     | `urn:ojs:ext:distributed-tracing`                  |
| **Requires**| OJS Core Specification (Layer 1), OJS Observability Specification |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Span Naming Conventions](#4-span-naming-conventions)
5. [Required Span Attributes](#5-required-span-attributes)
6. [Context Propagation](#6-context-propagation)
7. [Span Hierarchy](#7-span-hierarchy)
8. [Error Recording and Status Codes](#8-error-recording-and-status-codes)
9. [Baggage Propagation](#9-baggage-propagation)
10. [Metric Naming Conventions](#10-metric-naming-conventions)
11. [Conformance Requirements](#11-conformance-requirements)
12. [Examples](#12-examples)

---

## 1. Introduction

The OJS Observability specification defines the foundational conventions for traces, metrics, and logging. This companion specification extends those conventions with detailed requirements for **distributed tracing** across the full OJS request lifecycle: from SDK client through backend to worker.

The goal is to enable a single trace that spans the entire lifecycle of a job — from the moment a client enqueues it, through backend processing, to the worker completing it — even when these components run in different services, written in different languages, separated by minutes or hours.

### 1.1 Scope

This specification defines:

- Standardized span naming conventions for all OJS operations.
- Required and recommended span attributes.
- W3C Trace Context propagation rules via job metadata.
- End-to-end span hierarchy (Client → Backend → Worker).
- Error recording conventions and status code mapping.
- Baggage propagation for cross-service context.
- Metric naming conventions aligned with OpenTelemetry semantic conventions.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term                 | Definition                                                                                      |
|----------------------|-----------------------------------------------------------------------------------------------|
| trace                | A collection of causally related spans representing a single logical operation.                |
| span                 | A unit of work within a trace, with a name, start/end time, attributes, and status.            |
| span link            | A causal reference between spans that are not in a parent-child relationship.                  |
| trace context        | W3C Trace Context (`traceparent` + `tracestate`) that correlates spans across services.        |
| baggage              | W3C Baggage key-value pairs propagated alongside trace context for cross-service state.        |
| instrumentation scope| The library or package performing the instrumentation (e.g., `openjobspec.org/ojs`).           |

---

## 4. Span Naming Conventions

All OJS spans MUST follow the naming pattern `ojs.{operation}` for backend/system operations, and `{queue_name} {operation}` for client-facing operations (per OTel messaging semantic conventions).

### 4.1 Client and Worker Spans

| Operation       | Span Name Pattern               | Span Kind    | Description                          |
|----------------|---------------------------------|--------------|--------------------------------------|
| Enqueue        | `{queue} enqueue`               | `PRODUCER`   | Client enqueues a job                |
| Batch enqueue  | `{queue} enqueue_batch`         | `PRODUCER`   | Client enqueues a batch of jobs      |
| Fetch          | `{queue} fetch`                 | `CONSUMER`   | Worker fetches jobs from queue       |
| Process        | `{queue} process`               | `CONSUMER`   | Worker processes a job               |
| Ack            | `ojs.ack`                       | `CLIENT`     | Worker acknowledges completion       |
| Nack           | `ojs.nack`                      | `CLIENT`     | Worker reports failure               |
| Cancel         | `ojs.cancel`                    | `CLIENT`     | Client cancels a job                 |
| Get job        | `ojs.get_job`                   | `CLIENT`     | Client retrieves job status          |

### 4.2 Backend System Spans

Backend implementations SHOULD create spans for internal operations:

| Operation             | Span Name                     | Span Kind    | Description                        |
|-----------------------|-------------------------------|--------------|------------------------------------|
| Scheduler poll        | `ojs.scheduler.poll`          | `INTERNAL`   | Promote scheduled jobs to available |
| Cron trigger          | `ojs.cron.trigger`            | `INTERNAL`   | Evaluate and trigger cron jobs      |
| Dead worker reap      | `ojs.reaper.check`            | `INTERNAL`   | Detect and recover stalled jobs     |
| Visibility check      | `ojs.visibility.check`        | `INTERNAL`   | Process visibility timeouts         |
| Workflow advance      | `ojs.workflow.advance`        | `INTERNAL`   | Advance workflow to next step       |
| Retry evaluation      | `ojs.retry.evaluate`          | `INTERNAL`   | Evaluate retry policy               |

### 4.3 Worker Processing Spans

The `ojs.worker.process` span is a convenience alias for the `{queue} process` span, used by SDK middleware when the queue context is not yet resolved:

| Operation            | Span Name                      | Span Kind    | Description                         |
|----------------------|--------------------------------|--------------|-------------------------------------|
| Worker process       | `ojs.worker.process`           | `CONSUMER`   | SDK middleware job processing span  |

**Rationale**: The `{queue} {operation}` pattern follows OTel messaging semantic conventions, which recommend using the destination name as a prefix. The `ojs.{operation}` pattern is used for operations that are not tied to a specific queue.

---

## 5. Required Span Attributes

### 5.1 Core Attributes (REQUIRED)

These attributes MUST be present on all OJS spans:

| Attribute                    | Type   | Description                               | Example                  |
|------------------------------|--------|-------------------------------------------|--------------------------|
| `messaging.system`           | string | Always `"ojs"`.                           | `"ojs"`                  |
| `ojs.job.id`                 | string | Job identifier (UUIDv7).                  | `"019503e1-7b2a-..."`    |
| `ojs.job.type`               | string | Job type identifier.                      | `"email.send"`           |
| `ojs.job.queue`              | string | Target queue name.                        | `"email"`                |

### 5.2 Execution Attributes (RECOMMENDED)

These attributes SHOULD be present when available:

| Attribute                    | Type   | Description                               | Example                  |
|------------------------------|--------|-------------------------------------------|--------------------------|
| `ojs.job.attempt`            | int    | Current attempt number (1-indexed).       | `2`                      |
| `ojs.job.state`              | string | Job state after the operation.            | `"active"`               |
| `ojs.job.priority`           | int    | Job priority (lower is higher priority).  | `0`                      |
| `ojs.worker.id`              | string | Worker identifier.                        | `"worker-01HXYZ"`        |

### 5.3 Workflow Attributes (CONDITIONAL)

These attributes MUST be present when the job is part of a workflow:

| Attribute                    | Type   | Description                               | Example                  |
|------------------------------|--------|-------------------------------------------|--------------------------|
| `ojs.workflow.id`            | string | Workflow identifier.                      | `"wf-019503e1-..."`      |
| `ojs.workflow.type`          | string | Workflow type (`chain`, `group`, `batch`).| `"chain"`                |
| `ojs.workflow.step`          | int    | Current step in workflow (0-indexed).     | `2`                      |

### 5.4 Backend Attributes (RECOMMENDED)

| Attribute                    | Type   | Description                               | Example                  |
|------------------------------|--------|-------------------------------------------|--------------------------|
| `ojs.backend.type`           | string | Backend storage type.                     | `"redis"`                |
| `ojs.backend.version`        | string | Backend implementation version.           | `"0.2.0"`                |

Valid values for `ojs.backend.type`: `redis`, `postgres`, `nats`, `kafka`, `sqs`, `lite`, `memory`.

### 5.5 Error Attributes

On error spans, the following attributes MUST be set:

| Attribute                    | Type   | Description                               |
|------------------------------|--------|-------------------------------------------|
| `error.type`                 | string | Error type or class name.                 |
| `error.message`              | string | Human-readable error message.             |
| `ojs.job.error.attempt`      | int    | Attempt number when the error occurred.   |

---

## 6. Context Propagation

### 6.1 W3C Trace Context via Job Metadata

OJS propagates distributed trace context using W3C Trace Context headers stored in the job `meta` field. This enables end-to-end tracing even when jobs cross service, language, and time boundaries.

#### Injection (Client/Producer)

When enqueuing a job, the client SDK MUST inject the current trace context into the job `meta` field:

```json
{
  "type": "email.send",
  "args": [{"to": "user@example.com"}],
  "meta": {
    "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
    "tracestate": "ojs=p:8;r:62"
  }
}
```

| Meta Field     | W3C Header     | Description                                      |
|----------------|----------------|--------------------------------------------------|
| `traceparent`  | `traceparent`  | Trace ID, parent span ID, and trace flags.       |
| `tracestate`   | `tracestate`   | Vendor-specific trace data (OPTIONAL).            |

#### Extraction (Worker/Consumer)

When processing a job, the worker SDK MUST:

1. Extract the trace context from `meta.traceparent`.
2. Create a new span with a **span link** to the extracted context (NOT a parent-child relationship).
3. Set the span link on the process span.

**Rationale**: Span links correctly model asynchronous job processing. The enqueue and process operations may be separated by hours. A parent-child relationship would create artificially long traces that break visualization tools.

### 6.2 Backend Passthrough

OJS backends MUST preserve `meta.traceparent` and `meta.tracestate` fields without modification through the entire job lifecycle (enqueue → store → fetch → ack/nack).

### 6.3 Workflow Context Propagation

For workflow jobs (chain, group, batch), each step SHOULD carry both the original trace context and the previous step's trace context:

```json
{
  "meta": {
    "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-a1b2c3d4e5f60718-01",
    "ojs.workflow.trace_origin": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
  }
}
```

| Meta Field                    | Description                                          |
|-------------------------------|------------------------------------------------------|
| `traceparent`                 | Trace context of the immediately preceding step.     |
| `ojs.workflow.trace_origin`   | Trace context of the original workflow initiator.    |

---

## 7. Span Hierarchy

### 7.1 End-to-End Trace Flow

A complete OJS trace follows this hierarchy:

```
Service A (HTTP handler)
  └─ span: "POST /api/users" (kind: SERVER)
      └─ span: "email enqueue" (kind: PRODUCER)
          │ injects meta.traceparent
          └─ [HTTP POST to OJS backend]

OJS Backend
  └─ span: "ojs.enqueue" (kind: SERVER)
      └─ [stores job in Redis/Postgres]

          ... time passes ...

Worker B
  └─ span: "email process" (kind: CONSUMER)
      │ link → enqueue PRODUCER span (via meta.traceparent)
      ├─ span: "ojs.worker.process" (kind: INTERNAL)
      │   └─ [user handler logic]
      └─ span: "ojs.ack" (kind: CLIENT)
          └─ [HTTP POST ack to backend]
```

### 7.2 Span Relationships

| Relationship                        | Type        | Description                                    |
|-------------------------------------|-------------|------------------------------------------------|
| HTTP handler → Enqueue              | Parent-child | Enqueue is a child of the originating request. |
| Enqueue → Process                   | Span link    | Asynchronous correlation via `traceparent`.    |
| Process → User handler              | Parent-child | Handler runs within the process span.          |
| Process → Ack/Nack                  | Parent-child | Acknowledgment is part of processing.          |
| Workflow step N → step N+1          | Span link    | Steps are linked, not parent-child.            |

---

## 8. Error Recording and Status Codes

### 8.1 Span Status Mapping

| Outcome                  | Span Status Code | Description                              |
|--------------------------|------------------|------------------------------------------|
| Job completed            | `OK`             | Handler returned without error.          |
| Job failed (retryable)   | `ERROR`          | Handler returned error, will retry.      |
| Job failed (discarded)   | `ERROR`          | Max attempts exceeded, job discarded.    |
| Job cancelled            | `OK`             | Intentional cancellation is not an error.|
| Enqueue succeeded        | `OK`             | Job accepted by backend.                 |
| Enqueue failed           | `ERROR`          | Backend rejected the job.                |
| Fetch timeout            | `OK`             | No jobs available is not an error.       |

### 8.2 Error Event Recording

On failure, spans MUST record an error event using the OTel `RecordError` API (or language equivalent):

```
span.RecordError(err)
span.SetStatus(codes.Error, err.Error())
```

The error event SHOULD include:

| Event Attribute         | Type   | Description                            |
|-------------------------|--------|----------------------------------------|
| `exception.type`        | string | Error class/type name.                 |
| `exception.message`     | string | Error message.                         |
| `exception.stacktrace`  | string | Stack trace (if available).            |

### 8.3 Retry Error Accumulation

For retried jobs, each attempt SHOULD produce its own span. The final attempt's span SHOULD include the total number of prior attempts as an attribute (`ojs.job.attempt`).

---

## 9. Baggage Propagation

### 9.1 W3C Baggage

OJS implementations SHOULD support W3C Baggage propagation alongside trace context. Baggage provides a mechanism for passing application-specific key-value pairs across service boundaries without modifying the job payload.

#### Storage in Job Metadata

```json
{
  "meta": {
    "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
    "baggage": "userId=12345,tenantId=acme,environment=production"
  }
}
```

### 9.2 Reserved Baggage Keys

The following baggage keys are reserved for OJS:

| Key                     | Description                                          |
|-------------------------|------------------------------------------------------|
| `ojs.priority.override` | Runtime priority adjustment.                        |
| `ojs.trace.sample_rate` | Desired sampling rate for downstream spans.          |
| `ojs.tenant.id`         | Tenant identifier for multi-tenant deployments.     |

### 9.3 Baggage Limits

Implementations SHOULD enforce a maximum total baggage size of 8192 bytes (per W3C Baggage specification). Entries exceeding this limit SHOULD be silently dropped.

---

## 10. Metric Naming Conventions

OJS metrics MUST follow OpenTelemetry semantic conventions and use the `ojs.` prefix. This section supplements the OJS Observability specification with guidance on alignment with OTel conventions.

### 10.1 Naming Rules

- Metric names MUST use lowercase dot-separated names: `ojs.job.duration`.
- Metric names MUST NOT include the unit in the name (use the OTel unit field instead).
- Counter names SHOULD use a noun describing what is counted: `ojs.job.enqueued` (not `ojs.job.enqueue_count`).
- Histogram names SHOULD describe the measured value: `ojs.job.duration`.

### 10.2 Standard Metrics

| Metric Name               | Type      | Unit    | Attributes                 | Description                          |
|---------------------------|-----------|---------|----------------------------|--------------------------------------|
| `ojs.job.enqueued`        | Counter   | `{job}` | `queue`, `type`            | Total jobs enqueued.                 |
| `ojs.job.completed`       | Counter   | `{job}` | `queue`, `type`            | Total jobs completed successfully.   |
| `ojs.job.failed`          | Counter   | `{job}` | `queue`, `type`            | Total jobs that failed.              |
| `ojs.job.retried`         | Counter   | `{job}` | `queue`, `type`            | Total retry attempts.                |
| `ojs.job.duration`        | Histogram | `s`     | `queue`, `type`, `state`   | Job processing duration.             |
| `ojs.job.queue_time`      | Histogram | `s`     | `queue`, `type`            | Time from enqueue to first process.  |
| `ojs.queue.depth`         | Gauge     | `{job}` | `queue`, `state`           | Current jobs per queue per state.    |
| `ojs.workers.active`      | Gauge     | `{worker}` | —                       | Number of active workers.            |

### 10.3 Cardinality Rules

Metric attributes MUST have bounded cardinality:

- `queue`: Bounded by the number of configured queues (typically < 50).
- `type`: Bounded by the number of registered job types (typically < 200).
- `state`: Bounded to the 8 OJS lifecycle states.

Metric attributes MUST NOT include job IDs, job arguments, or error messages.

---

## 11. Conformance Requirements

An implementation declaring support for the distributed tracing extension MUST satisfy:

| ID           | Requirement                                                                              |
|--------------|------------------------------------------------------------------------------------------|
| DT-001       | Inject W3C `traceparent` into job `meta` on enqueue.                                     |
| DT-002       | Extract `traceparent` from job `meta` on process and create a span link.                 |
| DT-003       | Preserve `meta.traceparent` and `meta.tracestate` through the full job lifecycle.        |
| DT-004       | Use `ojs.{operation}` or `{queue} {operation}` span naming.                             |
| DT-005       | Include required span attributes (`messaging.system`, `ojs.job.id`, `ojs.job.type`, `ojs.job.queue`). |
| DT-006       | Set span status to `ERROR` and call `RecordError` on failure.                            |
| DT-007       | Set workflow attributes when job is part of a workflow.                                   |

An implementation SHOULD additionally satisfy:

| ID           | Requirement                                                                              |
|--------------|------------------------------------------------------------------------------------------|
| DT-008       | Support W3C Baggage propagation via `meta.baggage`.                                      |
| DT-009       | Create system spans for internal backend operations.                                     |
| DT-010       | Propagate workflow trace origin via `meta.ojs.workflow.trace_origin`.                    |

---

## 12. Examples

### 12.1 Go SDK — Enqueue with Trace Context

```go
import (
    "context"
    ojs "github.com/openjobspec/ojs-go-sdk"
    "github.com/openjobspec/ojs-go-backend-common/tracing"
)

func EnqueueEmail(ctx context.Context, client *ojs.Client) error {
    meta := tracing.InjectContext(ctx, nil)
    return client.Enqueue(ctx, ojs.Job{
        Type:  "email.send",
        Args:  []any{"user@example.com"},
        Queue: "email",
        Meta:  meta,
    })
}
```

### 12.2 Go SDK — Worker with Trace Extraction

```go
import (
    ojs "github.com/openjobspec/ojs-go-sdk"
    ojsotel "github.com/openjobspec/ojs-go-sdk/middleware/otel"
)

worker := ojs.NewWorker(ojs.WorkerConfig{
    URL:    "http://localhost:8080",
    Queues: []string{"email"},
})
worker.Use(ojsotel.Tracing())
worker.Register("email.send", handleEmail)
```

### 12.3 Trace Visualization

```
[Service A]                        [OJS Backend]                    [Worker B]
    │                                   │                               │
    ├─ POST /api/signup ────────────────┤                               │
    │  └─ email enqueue (PRODUCER) ─────┤                               │
    │     traceparent injected          │                               │
    │                                   ├─ ojs.enqueue (SERVER)         │
    │                                   │  └─ store job                 │
    │                                   │                               │
    │                                   │     ... time passes ...       │
    │                                   │                               │
    │                                   │                               ├─ email process (CONSUMER)
    │                                   │                               │  link → email enqueue
    │                                   │                               │  └─ user handler
    │                                   │                               │  └─ ojs.ack (CLIENT) ──┤
    │                                   │                               │                        │
```

---

## Appendix A: Changelog

| Date       | Change                        |
|------------|-------------------------------|
| 2026-02-19 | Initial draft for v0.2.0.     |
