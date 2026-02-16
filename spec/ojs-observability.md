# Open Job Spec: Observability and OpenTelemetry Conventions

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Observability Specification                |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-13                                     |
| **Status**  | Release Candidate                              |
| **Maturity** | Beta                                           |
| **Tier**    | Official Extension                             |
| **URI**     | `urn:ojs:ext:observability`                    |
| **Requires**| OJS Core Specification (Layer 1), OJS Events Specification |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Design Principles](#4-design-principles)
5. [Trace Context Propagation](#5-trace-context-propagation)
6. [Span Conventions](#6-span-conventions)
   - 6.1 [Enqueue Span](#61-enqueue-span)
   - 6.2 [Process Span](#62-process-span)
   - 6.3 [System Spans](#63-system-spans)
7. [Span Attributes](#7-span-attributes)
8. [Metrics](#8-metrics)
   - 8.1 [Counter Metrics](#81-counter-metrics)
   - 8.2 [Histogram Metrics](#82-histogram-metrics)
   - 8.3 [Gauge Metrics](#83-gauge-metrics)
9. [Logging Conventions](#9-logging-conventions)
10. [Health Check](#10-health-check)
11. [Conformance Requirements](#11-conformance-requirements)
12. [Prior Art](#12-prior-art)
13. [Examples](#13-examples)

---

## 1. Introduction

Observability is the ability to understand the internal state of a system by examining its external outputs: traces, metrics, and logs. For background job systems, observability is not a luxury -- it is the primary mechanism operators use to detect failures, diagnose bottlenecks, and understand system behavior.

OpenTelemetry (OTel) has emerged as the industry standard for observability instrumentation. It defines semantic conventions for messaging systems that directly apply to background job processing. By aligning OJS with OTel conventions, every OJS implementation becomes immediately visible in existing monitoring infrastructure (Datadog, Grafana, Jaeger, Honeycomb, New Relic) without custom integration work.

This specification maps OJS concepts to OpenTelemetry semantic conventions, defines standard span names and attributes, specifies required and recommended metrics, and establishes trace context propagation rules. It builds upon the OJS Events specification (ojs-events.md), which defines the lifecycle event vocabulary; this specification defines how those events are instrumented for observability.

### 1.1 Scope

This specification defines:

- How W3C Trace Context propagates through OJS jobs via the `meta` field.
- Standard span names and types for enqueue, process, and system operations.
- Standard span attributes aligned with OTel messaging semantic conventions.
- Required and recommended metrics with standardized names, types, and labels.
- Structured logging conventions for job lifecycle events.
- Health check response format.

This specification does **not** define:

- Specific OTel SDK integration details (each OJS SDK adapts to its language's OTel SDK).
- Backend-specific observability (e.g., Redis SLOWLOG analysis, Postgres query stats).
- Alerting rules or dashboard layouts.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term                   | Definition                                                                                 |
|------------------------|--------------------------------------------------------------------------------------------|
| span                   | A unit of work in a distributed trace, with a start time, duration, and metadata.          |
| trace context          | The W3C Trace Context (traceparent + tracestate) that links spans across services.         |
| semantic conventions   | Standardized attribute names and values defined by OpenTelemetry.                          |
| span link              | A reference from one span to another that is not a parent-child relationship.              |
| cardinality            | The number of unique values a metric label can take. High cardinality harms performance.   |

---

## 4. Design Principles

1. **Adopt OTel conventions, don't invent.** OpenTelemetry already defines messaging semantic conventions. OJS uses those conventions as the baseline and extends them only where job-processing-specific semantics require it.

2. **Span links, not parent-child.** The enqueue span and process span are linked via span links, not parent-child relationships. This follows the OTel messaging convention and correctly models the fact that enqueue and process are independent operations that may happen hours apart.

3. **Low cardinality by default.** Metric labels use bounded values (queue names, job types, states) to prevent cardinality explosions. Job IDs are span attributes, not metric labels.

4. **Progressive instrumentation.** Required instrumentation is minimal (3 metrics, 2 span types). Recommended instrumentation provides richer observability. This allows lightweight implementations to be conformant while sophisticated deployments get full visibility.

---

## 5. Trace Context Propagation

### 5.1 Propagation via `meta`

OJS propagates W3C Trace Context through the `meta` field on the job envelope. When an instrumented SDK enqueues a job, it MUST inject the current trace context into `meta`:

```json
{
  "type": "email.send",
  "args": [{ "to": "user@example.com" }],
  "meta": {
    "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
    "tracestate": "ojs=p:8;r:62"
  }
}
```

| Meta Field     | W3C Header       | Description                                      |
|----------------|------------------|--------------------------------------------------|
| `traceparent`  | `traceparent`    | Trace ID, parent span ID, and trace flags.       |
| `tracestate`   | `tracestate`     | Vendor-specific trace data.                       |

### 5.2 Context Extraction

When a worker processes a job, the SDK MUST extract the trace context from `meta` and create a span link to the enqueue span. The process span gets its own trace context (it is a new root or child of the worker's trace) with a link back to the enqueue span.

**Rationale**: Using span links instead of parent-child correctly models the asynchronous nature of job processing. The enqueueing service may have already completed its trace by the time the job is processed. A parent-child relationship would create artificially long traces that span hours or days, which breaks trace visualization tools.

### 5.3 Propagation Through Workflows

For workflow jobs (chain, group, batch), each step SHOULD carry both the original trace context (from the workflow initiator) and the previous step's trace context:

```json
{
  "meta": {
    "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-a1b2c3d4e5f60718-01",
    "ojs.workflow.trace_origin": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
  }
}
```

---

## 6. Span Conventions

### 6.1 Enqueue Span

Created by the SDK when a job is enqueued.

| Attribute            | Value                                           |
|----------------------|-------------------------------------------------|
| **Span name**        | `{queue_name} enqueue`                          |
| **Span kind**        | `PRODUCER`                                      |
| **Status**           | `OK` on success, `ERROR` on enqueue failure     |

Example span name: `email enqueue`, `default enqueue`

### 6.2 Process Span

Created by the worker when a job begins execution.

| Attribute            | Value                                           |
|----------------------|-------------------------------------------------|
| **Span name**        | `{queue_name} process`                          |
| **Span kind**        | `CONSUMER`                                      |
| **Status**           | `OK` on completion, `ERROR` on failure           |
| **Links**            | Span link to the enqueue span (via `traceparent` in `meta`) |

Example span name: `email process`, `default process`

### 6.3 System Spans

Backend implementations SHOULD create spans for internal operations:

| Operation             | Span Name                    | Span Kind  |
|-----------------------|------------------------------|------------|
| Schedule poll         | `ojs.scheduler poll`        | `INTERNAL` |
| Cron trigger          | `ojs.cron trigger`          | `INTERNAL` |
| Dead worker reap      | `ojs.reaper check`          | `INTERNAL` |
| Visibility timeout    | `ojs.visibility check`      | `INTERNAL` |
| Workflow step advance | `ojs.workflow advance`      | `INTERNAL` |

---

## 7. Span Attributes

All span attributes use the `ojs.` prefix for OJS-specific attributes and the `messaging.` prefix for OTel messaging convention attributes.

### 7.1 Required Attributes

These attributes MUST be present on enqueue and process spans:

| Attribute                        | Type   | Description                                    | Example                  |
|----------------------------------|--------|------------------------------------------------|--------------------------|
| `messaging.system`               | string | Always `"ojs"`.                                | `"ojs"`                  |
| `messaging.operation.type`       | string | `"publish"` for enqueue, `"process"` for worker. | `"publish"`           |
| `messaging.destination.name`     | string | Queue name.                                    | `"email"`                |
| `ojs.job.id`                     | string | Job ID (UUIDv7).                               | `"019503e1-..."`         |
| `ojs.job.type`                   | string | Job type.                                      | `"email.send"`           |

### 7.2 Recommended Attributes

These attributes SHOULD be present when available:

| Attribute                        | Type    | Description                                    | Example                  |
|----------------------------------|---------|------------------------------------------------|--------------------------|
| `ojs.job.queue`                  | string  | Queue name (same as `messaging.destination.name`). | `"email"`            |
| `ojs.job.state`                  | string  | Job state after the operation.                  | `"active"`               |
| `ojs.job.attempt`                | int     | Current attempt number (1-indexed).             | `2`                      |
| `ojs.job.priority`               | int     | Job priority.                                   | `0`                      |
| `ojs.worker.id`                  | string  | Worker ID (on process spans).                   | `"worker-01HXYZ"`        |
| `ojs.job.scheduled_at`           | string  | Scheduled execution time (RFC 3339).            | `"2026-02-13T12:00:00Z"` |
| `messaging.message.id`           | string  | Same as `ojs.job.id`.                           | `"019503e1-..."`         |
| `messaging.message.body.size`    | int     | Size of the serialized job envelope in bytes.   | `342`                    |

### 7.3 Error Attributes

On error spans:

| Attribute                        | Type   | Description                                    |
|----------------------------------|--------|------------------------------------------------|
| `error.type`                     | string | Error type/class name.                         |
| `error.message`                  | string | Human-readable error message.                  |
| `ojs.job.error.attempt`          | int    | Which attempt this error occurred on.          |

---

## 8. Metrics

All metric names use the `ojs.` prefix. Labels (attributes) follow the same naming as span attributes.

### 8.1 Counter Metrics

Implementations MUST expose these counters:

| Metric Name                      | Unit   | Labels                          | Description                                   |
|----------------------------------|--------|---------------------------------|-----------------------------------------------|
| `ojs.job.enqueued`               | jobs   | `queue`, `type`                 | Total jobs enqueued.                          |
| `ojs.job.completed`              | jobs   | `queue`, `type`                 | Total jobs that reached `completed` state.     |
| `ojs.job.failed`                 | jobs   | `queue`, `type`                 | Total jobs that reached `discarded` state.     |

Implementations SHOULD expose these counters:

| Metric Name                      | Unit   | Labels                          | Description                                   |
|----------------------------------|--------|---------------------------------|-----------------------------------------------|
| `ojs.job.retried`                | jobs   | `queue`, `type`                 | Total retry attempts.                          |
| `ojs.job.cancelled`              | jobs   | `queue`, `type`                 | Total cancellations.                           |
| `ojs.job.expired`                | jobs   | `queue`, `type`                 | Total jobs expired via TTL.                    |

### 8.2 Histogram Metrics

Implementations MUST expose these histograms:

| Metric Name                      | Unit    | Labels                          | Description                                   |
|----------------------------------|---------|---------------------------------|-----------------------------------------------|
| `ojs.job.duration`               | seconds | `queue`, `type`, `state`        | Job processing duration (active → terminal).   |
| `ojs.job.queue_time`             | seconds | `queue`, `type`                 | Time from enqueue to first execution start.    |

Implementations SHOULD expose:

| Metric Name                      | Unit    | Labels                          | Description                                   |
|----------------------------------|---------|---------------------------------|-----------------------------------------------|
| `ojs.job.enqueue_duration`       | seconds | `queue`                         | Time to complete enqueue operation.            |

Recommended histogram bucket boundaries for `ojs.job.duration`: `[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300]`

Recommended histogram bucket boundaries for `ojs.job.queue_time`: `[0.01, 0.05, 0.1, 0.5, 1, 5, 10, 30, 60, 300, 600, 1800, 3600]`

### 8.3 Gauge Metrics

Implementations MUST expose these gauges:

| Metric Name                      | Unit   | Labels                          | Description                                   |
|----------------------------------|--------|---------------------------------|-----------------------------------------------|
| `ojs.queue.depth`                | jobs   | `queue`, `state`                | Current number of jobs per queue per state.    |

Implementations SHOULD expose:

| Metric Name                      | Unit    | Labels                          | Description                                   |
|----------------------------------|---------|---------------------------------|-----------------------------------------------|
| `ojs.workers.active`             | workers | --                              | Number of active (running) workers.            |
| `ojs.workers.busy`               | jobs    | `queue`                         | Number of currently executing jobs.            |

### 8.4 Cardinality Guidelines

Metric labels MUST have bounded cardinality:

- `queue`: Bounded by the number of queues (typically < 50).
- `type`: Bounded by the number of registered job types (typically < 200).
- `state`: Bounded to the 8 OJS states.

Metric labels MUST NOT include:

- Job IDs (unbounded).
- Job arguments (unbounded, potentially sensitive).
- Error messages (unbounded; use `error.type` which is bounded).
- Tenant IDs without explicit opt-in (can be high cardinality; see ojs-multi-tenancy.md).

**Rationale**: Prometheus, Datadog, and other metrics backends degrade with high-cardinality labels. A metric with a job-ID label creates a new time series per job, exhausting storage within hours in a high-throughput system.

---

## 9. Logging Conventions

### 9.1 Structured Log Format

OJS backends and SDKs SHOULD emit structured logs (JSON) for job lifecycle events. Each log entry SHOULD include:

| Field            | Type   | Description                                    |
|------------------|--------|------------------------------------------------|
| `timestamp`      | string | RFC 3339 timestamp.                            |
| `level`          | string | Log level: `debug`, `info`, `warn`, `error`.  |
| `message`        | string | Human-readable message.                        |
| `ojs.job.id`     | string | Job ID.                                        |
| `ojs.job.type`   | string | Job type.                                      |
| `ojs.job.queue`  | string | Queue name.                                    |
| `ojs.job.state`  | string | Job state after the event.                     |
| `trace_id`       | string | Trace ID (from traceparent), if available.     |
| `span_id`        | string | Span ID, if available.                         |

### 9.2 Standard Log Events

| Event                    | Level  | Message Template                                              |
|--------------------------|--------|---------------------------------------------------------------|
| Job enqueued             | info   | `"job enqueued"` with type, queue, id                         |
| Job started              | info   | `"job started"` with type, queue, id, attempt                 |
| Job completed            | info   | `"job completed"` with type, queue, id, duration              |
| Job failed               | warn   | `"job failed"` with type, queue, id, attempt, error           |
| Job retrying             | info   | `"job retrying"` with type, queue, id, attempt, next_at       |
| Job discarded            | error  | `"job discarded"` with type, queue, id, attempt, error        |
| Worker started           | info   | `"worker started"` with worker_id, queues, concurrency        |
| Worker stopping          | info   | `"worker stopping"` with worker_id, reason                    |

---

## 10. Health Check

### 10.1 Health Endpoint

The OJS health endpoint (`GET /ojs/v1/health`) SHOULD return structured health information:

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime_seconds": 86400,
  "backend": {
    "type": "redis",
    "status": "connected",
    "latency_ms": 2
  },
  "queues": {
    "active": 5,
    "paused": 1
  },
  "workers": {
    "connected": 12,
    "stale": 0
  }
}
```

| Status      | HTTP Code | Meaning                                        |
|-------------|-----------|------------------------------------------------|
| `healthy`   | 200       | Backend is connected, system is operational.   |
| `degraded`  | 200       | System is operational but experiencing issues.  |
| `unhealthy` | 503       | Backend is disconnected or system is down.      |

---

## 11. Conformance Requirements

An implementation declaring support for the observability extension MUST support:

| ID           | Requirement                                                                    |
|--------------|--------------------------------------------------------------------------------|
| OBS-001      | Trace context propagation via `meta.traceparent`.                              |
| OBS-002      | Enqueue span with `PRODUCER` kind and required attributes.                     |
| OBS-003      | Process span with `CONSUMER` kind, span link, and required attributes.         |
| OBS-004      | Counter metrics: `ojs.job.enqueued`, `ojs.job.completed`, `ojs.job.failed`.   |
| OBS-005      | Histogram metrics: `ojs.job.duration`, `ojs.job.queue_time`.                  |
| OBS-006      | Gauge metric: `ojs.queue.depth`.                                               |

---

## 12. Prior Art

| Standard/System    | Approach                                                                                |
|--------------------|-----------------------------------------------------------------------------------------|
| **OTel Messaging** | Semantic conventions for `publish`, `receive`, `process`, `settle` span types. Span links between producer and consumer. |
| **Temporal**       | Built-in OTel integration with activity and workflow spans. Trace context propagated through workflow headers. |
| **Sidekiq**        | Custom middleware for metrics (process time, queue latency). Third-party OTel integration via `opentelemetry-instrumentation-sidekiq`. |
| **Celery**         | `opentelemetry-instrumentation-celery` provides automatic span creation for task send/receive/execute. |
| **BullMQ**         | No built-in OTel. Community packages for Prometheus metrics via `bull-prom`.            |

OJS goes further than any individual system by standardizing metric names, span names, and trace propagation at the specification level rather than leaving it to per-SDK instrumentation packages.

---

## 13. Examples

### 13.1 Trace Propagation Flow

```
Service A (HTTP request)
  └─ span: "POST /api/signup" (kind: SERVER)
      └─ span: "email enqueue" (kind: PRODUCER)
          │ sets meta.traceparent = "00-{traceId}-{spanId}-01"
          └─ [enqueue via HTTP to OJS backend]

          ... time passes ...

Worker B
  └─ span: "email process" (kind: CONSUMER)
      │ links to: enqueue span via meta.traceparent
      └─ span: "smtp.send" (kind: CLIENT)
          └─ [sends email via SMTP]
```

### 13.2 Prometheus Metrics Example

```prometheus
# HELP ojs_job_enqueued_total Total jobs enqueued
# TYPE ojs_job_enqueued_total counter
ojs_job_enqueued_total{queue="email",type="email.send"} 15234
ojs_job_enqueued_total{queue="default",type="report.generate"} 892

# HELP ojs_job_duration_seconds Job processing duration
# TYPE ojs_job_duration_seconds histogram
ojs_job_duration_seconds_bucket{queue="email",type="email.send",state="completed",le="0.1"} 12891
ojs_job_duration_seconds_bucket{queue="email",type="email.send",state="completed",le="0.5"} 14987
ojs_job_duration_seconds_bucket{queue="email",type="email.send",state="completed",le="1"} 15200
ojs_job_duration_seconds_sum{queue="email",type="email.send",state="completed"} 1523.45
ojs_job_duration_seconds_count{queue="email",type="email.send",state="completed"} 15234

# HELP ojs_queue_depth Current jobs per queue per state
# TYPE ojs_queue_depth gauge
ojs_queue_depth{queue="email",state="available"} 42
ojs_queue_depth{queue="email",state="active"} 8
ojs_queue_depth{queue="email",state="scheduled"} 15
```

### 13.3 Structured Log Output

```json
{"timestamp":"2026-02-13T12:00:00.123Z","level":"info","message":"job enqueued","ojs.job.id":"019503e1-7b2a-7000-8000-000000000001","ojs.job.type":"email.send","ojs.job.queue":"email","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736"}
{"timestamp":"2026-02-13T12:00:00.456Z","level":"info","message":"job started","ojs.job.id":"019503e1-7b2a-7000-8000-000000000001","ojs.job.type":"email.send","ojs.job.queue":"email","ojs.job.attempt":1,"ojs.worker.id":"worker-01HXYZ","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736"}
{"timestamp":"2026-02-13T12:00:01.234Z","level":"info","message":"job completed","ojs.job.id":"019503e1-7b2a-7000-8000-000000000001","ojs.job.type":"email.send","ojs.job.queue":"email","ojs.job.duration_ms":778,"trace_id":"4bf92f3577b34da6a3ce929d0e0e4736"}
```

---

## Appendix A: Changelog

| Date       | Change                        |
|------------|-------------------------------|
| 2026-02-13 | Initial release candidate.    |
