# Open Job Spec: Structured Logging

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Structured Logging Specification           |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-15                                     |
| **Status**  | Release Candidate                              |
| **Maturity** | Beta                                           |
| **Tier**    | Official Extension                             |
| **URI**     | `urn:ojs:ext:logging`                          |
| **Requires**| OJS Core Specification (Layer 1)               |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Design Principles](#4-design-principles)
5. [Log Format](#5-log-format)
   - 5.1 [Log Record Structure](#51-log-record-structure)
   - 5.2 [Required Fields](#52-required-fields)
   - 5.3 [Contextual Fields](#53-contextual-fields)
   - 5.4 [Severity Levels](#54-severity-levels)
6. [Log Categories](#6-log-categories)
   - 6.1 [Lifecycle Logs](#61-lifecycle-logs)
   - 6.2 [Worker Logs](#62-worker-logs)
   - 6.3 [Error Logs](#63-error-logs)
   - 6.4 [Performance Logs](#64-performance-logs)
7. [Correlation](#7-correlation)
   - 7.1 [Job Correlation](#71-job-correlation)
   - 7.2 [Distributed Tracing Integration](#72-distributed-tracing-integration)
   - 7.3 [Request Correlation](#73-request-correlation)
8. [Sampling and Volume Control](#8-sampling-and-volume-control)
9. [Sensitive Data Handling](#9-sensitive-data-handling)
10. [Interaction with Other Extensions](#10-interaction-with-other-extensions)
    - 10.1 [Observability](#101-observability)
    - 10.2 [Events](#102-events)
    - 10.3 [Middleware](#103-middleware)
11. [Conformance Requirements](#11-conformance-requirements)
12. [Prior Art](#12-prior-art)
13. [Examples](#13-examples)

---

## 1. Introduction

The OJS Observability specification (ojs-observability.md) defines distributed tracing and metrics conventions. The OJS Events specification (ojs-events.md) defines lifecycle events. However, neither addresses structured logging — the detailed, human-and-machine-readable records emitted during job processing that are essential for debugging, auditing, and operational insight.

Logging is the most fundamental observability signal. When a job fails in production, the first action is almost always "check the logs." Without standardized log formats, correlating logs across producers, brokers, and workers — especially across language boundaries — requires custom parsing for each implementation. A Go backend's logs look nothing like a Python worker's logs, making cross-service debugging painful.

This specification defines a structured logging format for OJS implementations that enables consistent log aggregation, correlation, and querying across any language and any backend.

### 1.1 Scope

This specification defines:

- A structured JSON log format with required and contextual fields.
- Severity levels aligned with OpenTelemetry and syslog conventions.
- Log categories for lifecycle, worker, error, and performance events.
- Correlation patterns linking logs to jobs, traces, and requests.
- Sampling and volume control guidelines.
- Sensitive data handling requirements.

This specification does **not** define:

- Log transport (stdout, files, syslog, log aggregation services) — these are deployment concerns.
- Log storage or retention — these are operational policies.
- Application-level logging within job handlers — handlers may log however they wish; this specification covers OJS infrastructure logging.

### 1.2 Companion Specifications

| Document | Layer | Description |
|----------|-------|-------------|
| **ojs-core.md** | 1 -- Core | Job envelope, lifecycle, metadata |
| **ojs-observability.md** | Extension | Distributed tracing, metrics, OpenTelemetry conventions |
| **ojs-events.md** | Core | Lifecycle events, event envelope |
| **ojs-middleware.md** | Core | Middleware chains, interceptor model |
| **ojs-security.md** | Extension | Sensitive data, PII handling |

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term | Definition |
|------|------------|
| **Log Record** | A single structured log entry emitted by an OJS component. |
| **Structured Logging** | Logging in a machine-parseable format (JSON) with typed, named fields rather than free-form text. |
| **Severity Level** | A numeric/string indicator of the log record's importance, from TRACE to FATAL. |
| **Log Category** | A classification of log records by their purpose (lifecycle, worker, error, performance). |
| **Correlation ID** | A unique identifier that links related log records across components and services. |
| **Sampling** | Selectively emitting a subset of log records to control volume while maintaining observability. |

---

## 4. Design Principles

1. **Structured over unstructured.** All OJS infrastructure logs MUST be structured JSON. Free-form text messages are embedded within a structured envelope, never emitted as bare strings. Structured logs enable indexing, querying, and automated analysis.

2. **Correlated by default.** Every log record emitted during job processing MUST include the job ID. This enables a single query to retrieve all logs for a given job, across all components that touched it.

3. **OpenTelemetry-aligned.** Severity levels, attribute naming, and trace context follow OpenTelemetry Logs Data Model conventions. This ensures compatibility with the broader observability ecosystem without inventing OJS-specific conventions.

4. **Proportional to value.** Not every internal operation warrants a log record. This specification defines what MUST be logged (errors, state transitions) and what SHOULD be logged (performance data) while leaving routine internal operations to implementation discretion.

---

## 5. Log Format

### 5.1 Log Record Structure

Every OJS log record MUST be a JSON object with the following structure:

```json
{
  "timestamp": "2026-02-15T22:00:00.123Z",
  "severity": "INFO",
  "severity_number": 9,
  "message": "Job completed successfully",
  "category": "lifecycle",
  "component": "worker",
  "ojs": {
    "job_id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
    "job_type": "email.send",
    "queue": "email",
    "attempt": 1,
    "state": "completed"
  },
  "trace": {
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "span_id": "00f067aa0ba902b7"
  },
  "attributes": {}
}
```

### 5.2 Required Fields

Every OJS log record MUST include:

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string (ISO 8601) | When the log record was created. MUST include millisecond precision. |
| `severity` | string | Human-readable severity level. |
| `severity_number` | integer | Numeric severity per OpenTelemetry convention. |
| `message` | string | Human-readable description of the event. |
| `component` | string | The OJS component that emitted the log (`"server"`, `"worker"`, `"client"`). |

### 5.3 Contextual Fields

When available, the following fields SHOULD be included:

| Field | Type | Description |
|-------|------|-------------|
| `category` | string | Log category: `"lifecycle"`, `"worker"`, `"error"`, `"performance"`. |
| `ojs.job_id` | string | Job ID being processed. |
| `ojs.job_type` | string | Job type. |
| `ojs.queue` | string | Queue name. |
| `ojs.attempt` | integer | Current attempt number. |
| `ojs.state` | string | Current or target job state. |
| `ojs.worker_id` | string | Worker identifier. |
| `ojs.workflow_id` | string | Workflow identifier (if applicable). |
| `trace.trace_id` | string | W3C Trace Context trace ID. |
| `trace.span_id` | string | W3C Trace Context span ID. |
| `attributes` | object | Additional key-value pairs specific to the log record. |

### 5.4 Severity Levels

OJS severity levels align with the [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/):

| Severity | Number | OTel Equivalent | Usage |
|----------|--------|-----------------|-------|
| `TRACE` | 1 | TRACE | Detailed debugging. Internal state dumps, serialization details. |
| `DEBUG` | 5 | DEBUG | Diagnostic information. Job fetch attempts, heartbeat sends. |
| `INFO` | 9 | INFO | Normal operations. Job enqueued, completed, state transitions. |
| `WARN` | 13 | WARN | Recoverable issues. Retry triggered, approaching rate limit. |
| `ERROR` | 17 | ERROR | Failed operations. Job failed, timeout, handler exception. |
| `FATAL` | 21 | FATAL | Unrecoverable errors. Worker crash, broker connection lost. |

Implementations MUST support at least INFO, WARN, and ERROR levels. Implementations SHOULD support all six levels.

---

## 6. Log Categories

### 6.1 Lifecycle Logs

Lifecycle logs record job state transitions. Implementations MUST emit lifecycle logs for all state transitions.

| Event | Severity | Message Template |
|-------|----------|-----------------|
| Job enqueued | INFO | `"Job enqueued"` |
| Job fetched | DEBUG | `"Job fetched by worker"` |
| Job completed | INFO | `"Job completed successfully"` |
| Job failed | WARN | `"Job failed, will retry"` (if retryable) |
| Job discarded | ERROR | `"Job discarded after {attempt} attempts"` |
| Job cancelled | INFO | `"Job cancelled"` |
| Job timeout | ERROR | `"Job execution timed out after {elapsed}s"` |
| Job stalled | ERROR | `"Job stalled, no heartbeat for {elapsed}s"` |

### 6.2 Worker Logs

Worker logs record worker lifecycle events.

| Event | Severity | Message Template |
|-------|----------|-----------------|
| Worker started | INFO | `"Worker started with {concurrency} goroutines"` |
| Worker registered | INFO | `"Worker registered: {worker_id}"` |
| Worker heartbeat | DEBUG | `"Worker heartbeat sent"` |
| Worker draining | INFO | `"Worker draining, {active} jobs in progress"` |
| Worker stopped | INFO | `"Worker stopped gracefully"` |
| Worker error | ERROR | `"Worker encountered error: {message}"` |

### 6.3 Error Logs

Error logs provide detailed failure context. Implementations MUST emit error logs when a job handler raises an exception or when a system error occurs.

```json
{
  "timestamp": "2026-02-15T22:00:00.123Z",
  "severity": "ERROR",
  "severity_number": 17,
  "message": "Job handler raised exception",
  "category": "error",
  "component": "worker",
  "ojs": {
    "job_id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
    "job_type": "payment.process",
    "queue": "payments",
    "attempt": 2,
    "state": "retryable"
  },
  "error": {
    "type": "PaymentGatewayError",
    "message": "Connection refused to payment gateway",
    "backtrace": "at PaymentHandler.process(PaymentHandler.java:42)\n..."
  },
  "attributes": {
    "next_retry_at": "2026-02-15T22:05:00Z",
    "retry_delay_seconds": 300
  }
}
```

### 6.4 Performance Logs

Performance logs capture timing data for job execution. Implementations SHOULD emit performance logs for completed jobs.

```json
{
  "timestamp": "2026-02-15T22:00:01.456Z",
  "severity": "INFO",
  "severity_number": 9,
  "message": "Job execution completed",
  "category": "performance",
  "component": "worker",
  "ojs": {
    "job_id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
    "job_type": "email.send",
    "queue": "email",
    "attempt": 1,
    "state": "completed"
  },
  "attributes": {
    "duration_ms": 1234,
    "queue_wait_ms": 567,
    "total_elapsed_ms": 1801
  }
}
```

---

## 7. Correlation

### 7.1 Job Correlation

The `ojs.job_id` field provides the primary correlation key. All log records related to a specific job — from enqueue through completion — MUST include this field. This enables a single query like `ojs.job_id = "019539a4-..."` to retrieve the complete processing history.

For workflows, the `ojs.workflow_id` provides a secondary correlation key that links all jobs within a workflow.

### 7.2 Distributed Tracing Integration

When distributed tracing is active (ojs-observability.md), log records SHOULD include `trace.trace_id` and `trace.span_id`. This enables log-to-trace correlation in observability platforms that support both signals (e.g., Grafana, Datadog, Honeycomb).

The trace context SHOULD be propagated from the producer's enqueue call through the worker's execution, ensuring that logs emitted by the job handler are correlated with the originating request's trace.

### 7.3 Request Correlation

When a job is enqueued as part of an HTTP request, the `ojs.correlation_id` field (from `meta.correlation_id` in the job envelope) links job logs back to the originating request. This is especially valuable for debugging user-facing operations that trigger background processing.

---

## 8. Sampling and Volume Control

High-throughput OJS deployments may process millions of jobs per hour. Logging every lifecycle transition at INFO level can generate overwhelming log volume. This section provides guidelines for managing log volume without sacrificing observability.

### 8.1 Sampling Strategies

Implementations SHOULD support configurable log sampling:

| Strategy | Description |
|----------|-------------|
| **Rate-based** | Emit 1 in N log records for a given category. |
| **Error-biased** | Always log errors; sample success logs. |
| **Tail-based** | Log all records for jobs that fail; sample records for jobs that succeed. |

### 8.2 Minimum Logging

Regardless of sampling configuration:

- Error logs (severity ≥ ERROR) MUST NOT be sampled. All errors MUST be logged.
- State transitions to terminal states (`completed`, `discarded`, `cancelled`) SHOULD always be logged.
- Worker startup and shutdown MUST always be logged.

### 8.3 Volume Estimation

For capacity planning, implementations SHOULD document the expected log volume per job:

| Sampling | Log Records per Job | Records at 10K jobs/min |
|----------|-------------------|------------------------|
| Full | 4-6 | 40K-60K/min |
| Error-biased | 1-2 (success) / 4-6 (failure) | 10K-20K/min |
| Errors only | 0 (success) / 2-3 (failure) | 0-3K/min |

---

## 9. Sensitive Data Handling

Job arguments (`args`) and results (`result`) may contain personally identifiable information (PII), credentials, or other sensitive data. Log records MUST NOT include raw job arguments or results by default.

### 9.1 Redaction Rules

- The `args` field MUST NOT appear in log records unless explicitly opted in.
- The `result` field MUST NOT appear in log records unless explicitly opted in.
- The `error.backtrace` field MAY be truncated in production to limit exposure of internal code paths.
- The `meta` field SHOULD be logged, excluding keys that match known PII patterns (`password`, `token`, `secret`, `authorization`).

### 9.2 Opt-In Verbose Logging

Implementations MAY provide a configuration option to include `args` and `result` in log records for debugging purposes. This option MUST default to disabled and SHOULD emit a warning when enabled in production environments.

---

## 10. Interaction with Other Extensions

### 10.1 Observability

Structured logging complements the observability extension:

- **Traces** provide request-scoped causality chains.
- **Metrics** provide aggregated quantitative signals.
- **Logs** provide detailed, human-readable records of individual events.

Together, the three signals form the "three pillars of observability." This specification covers the logs pillar; ojs-observability.md covers traces and metrics.

### 10.2 Events

OJS events (ojs-events.md) and log records serve different purposes:

- **Events** are machine-to-machine signals designed for reactive logic (webhooks, workflow orchestration, dashboard updates).
- **Logs** are human-and-machine-readable records designed for debugging and auditing.

An implementation MAY emit both an event and a log record for the same state transition. They are not redundant — they serve different consumers.

### 10.3 Middleware

Logging middleware is a natural use of the OJS middleware chain. Implementations SHOULD provide a built-in logging middleware that wraps job handler execution and emits lifecycle and performance logs.

The logging middleware SHOULD be the outermost middleware in the chain (first to execute, last to complete) to capture the full execution duration including other middleware processing time.

---

## 11. Conformance Requirements

### 11.1 Required

| Capability | Requirement |
|------------|-------------|
| Structured JSON format | Implementations MUST emit logs as structured JSON. |
| Required fields | Implementations MUST include `timestamp`, `severity`, `severity_number`, `message`, `component`. |
| Job correlation | Implementations MUST include `ojs.job_id` in all job-related logs. |
| Error logging | Implementations MUST log all job failures with error details. |
| PII redaction | Implementations MUST NOT include `args` or `result` in logs by default. |

### 11.2 Recommended

| Capability | Requirement |
|------------|-------------|
| All severity levels | Implementations SHOULD support TRACE through FATAL. |
| Lifecycle logs | Implementations SHOULD log all state transitions. |
| Performance logs | Implementations SHOULD emit timing data for completed jobs. |
| Trace correlation | Implementations SHOULD include `trace.trace_id` and `trace.span_id`. |
| Configurable sampling | Implementations SHOULD support log sampling for volume control. |
| Logging middleware | Implementations SHOULD provide built-in logging middleware. |

### 11.3 Optional

| Capability | Requirement |
|------------|-------------|
| Verbose mode | Implementations MAY support opt-in `args`/`result` logging. |
| Custom log attributes | Implementations MAY allow handlers to inject custom attributes into log records. |
| Log level per queue | Implementations MAY support different log levels per queue. |

---

## 12. Prior Art

| System | Logging Approach |
|--------|-----------------|
| **OpenTelemetry** | Logs Data Model with severity levels, resource attributes, and trace correlation. OJS severity levels directly align with OTel. |
| **Sidekiq** | Logs job lifecycle to `Sidekiq.logger` (Ruby Logger). JSON logging available via `Sidekiq::Logger::Formatters::JSON`. |
| **BullMQ** | No built-in structured logging. Relies on application-level logging. |
| **Celery** | Uses Python's `logging` module with task-aware log records. `celery.utils.log.get_task_logger()` provides task context. |
| **Temporal** | Structured logging via `workflow.GetLogger()` and `activity.GetLogger()`. Context automatically includes workflow/run IDs. |
| **Faktory** | Server logs in logfmt format. Workers log via language runtime. |
| **Datadog** | Structured JSON logging with `dd.trace_id` and `dd.span_id` for log-trace correlation. Influenced OJS trace field naming. |

---

## 13. Examples

### 13.1 Complete Job Lifecycle (Log Sequence)

```json
{"timestamp":"2026-02-15T22:00:00.001Z","severity":"INFO","severity_number":9,"message":"Job enqueued","category":"lifecycle","component":"server","ojs":{"job_id":"019539a4-b68c-7def-8000-1a2b3c4d5e6f","job_type":"email.send","queue":"email","state":"available"}}
{"timestamp":"2026-02-15T22:00:00.123Z","severity":"DEBUG","severity_number":5,"message":"Job fetched by worker","category":"lifecycle","component":"server","ojs":{"job_id":"019539a4-b68c-7def-8000-1a2b3c4d5e6f","job_type":"email.send","queue":"email","attempt":1,"state":"active","worker_id":"worker-1"}}
{"timestamp":"2026-02-15T22:00:01.456Z","severity":"INFO","severity_number":9,"message":"Job completed successfully","category":"lifecycle","component":"worker","ojs":{"job_id":"019539a4-b68c-7def-8000-1a2b3c4d5e6f","job_type":"email.send","queue":"email","attempt":1,"state":"completed"},"attributes":{"duration_ms":1333}}
```

### 13.2 Failed Job with Retry

```json
{"timestamp":"2026-02-15T22:00:05.000Z","severity":"ERROR","severity_number":17,"message":"Job handler raised exception","category":"error","component":"worker","ojs":{"job_id":"019539a4-b68c-7def-8000-2b3c4d5e6f7a","job_type":"payment.process","queue":"payments","attempt":1,"state":"retryable"},"error":{"type":"ConnectionError","message":"Connection refused"},"attributes":{"next_retry_at":"2026-02-15T22:00:15Z"}}
{"timestamp":"2026-02-15T22:00:05.001Z","severity":"WARN","severity_number":13,"message":"Job failed, will retry","category":"lifecycle","component":"server","ojs":{"job_id":"019539a4-b68c-7def-8000-2b3c4d5e6f7a","job_type":"payment.process","queue":"payments","attempt":1,"state":"retryable"},"attributes":{"retry_delay_seconds":10,"remaining_attempts":2}}
```

### 13.3 Worker Lifecycle

```json
{"timestamp":"2026-02-15T22:00:00.000Z","severity":"INFO","severity_number":9,"message":"Worker started with 10 goroutines","category":"worker","component":"worker","ojs":{"worker_id":"worker-1"},"attributes":{"concurrency":10,"queues":["default","email","payments"]}}
{"timestamp":"2026-02-15T23:00:00.000Z","severity":"INFO","severity_number":9,"message":"Worker draining, 3 jobs in progress","category":"worker","component":"worker","ojs":{"worker_id":"worker-1"},"attributes":{"active_jobs":3,"signal":"SIGTERM"}}
{"timestamp":"2026-02-15T23:00:05.000Z","severity":"INFO","severity_number":9,"message":"Worker stopped gracefully","category":"worker","component":"worker","ojs":{"worker_id":"worker-1"},"attributes":{"total_processed":15234,"uptime_seconds":3600}}
```

---

## Appendix A: Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0-rc.1 | 2026-02-15 | Initial release candidate. |
