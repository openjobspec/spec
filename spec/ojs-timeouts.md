# Open Job Spec: Job Timeouts

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Job Timeouts Specification                 |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-15                                     |
| **Status**  | Release Candidate                              |
| **Tier**    | Official Extension                             |
| **URI**     | `urn:ojs:ext:timeouts`                         |
| **Requires**| OJS Core Specification (Layer 1)               |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Design Principles](#4-design-principles)
5. [Timeout Model](#5-timeout-model)
   - 5.1 [Execution Timeout](#51-execution-timeout)
   - 5.2 [Total Timeout](#52-total-timeout)
   - 5.3 [Enqueue TTL](#53-enqueue-ttl)
   - 5.4 [Grace Period](#54-grace-period)
   - 5.5 [Heartbeat Timeout](#55-heartbeat-timeout)
6. [Timeout Fields](#6-timeout-fields)
7. [Timeout Detection and Enforcement](#7-timeout-detection-and-enforcement)
   - 7.1 [Server-Side Enforcement](#71-server-side-enforcement)
   - 7.2 [Worker-Side Enforcement](#72-worker-side-enforcement)
   - 7.3 [Heartbeat-Based Detection](#73-heartbeat-based-detection)
8. [Timeout Actions](#8-timeout-actions)
9. [Interaction with Other Extensions](#9-interaction-with-other-extensions)
   - 9.1 [Retry Policy](#91-retry-policy)
   - 9.2 [Workflows](#92-workflows)
   - 9.3 [Progress](#93-progress)
   - 9.4 [Graceful Shutdown](#94-graceful-shutdown)
10. [HTTP Binding](#10-http-binding)
11. [Observability](#11-observability)
12. [Conformance Requirements](#12-conformance-requirements)
13. [Prior Art](#13-prior-art)
14. [Examples](#14-examples)

---

## 1. Introduction

Every production job processing system must answer the question: "What happens when a job runs too long?" Without explicit timeout semantics, a stuck or deadlocked job can hold a worker slot indefinitely, reducing system throughput and eventually causing cascading failures. The OJS core specification defines a basic `timeout` integer field (seconds) for maximum execution time. This extension formalizes the full timeout model with richer semantics: per-attempt vs. total wall-clock limits, enqueue TTL, grace periods for cleanup, and heartbeat-based liveness detection.

Timeout handling is nuanced because different failure modes require different responses. A job that exceeds its execution timeout within a single attempt should be retried; a job that exceeds its total wall-clock budget across all attempts should be discarded. A job that was enqueued but never started before its TTL expired should be dropped without wasting a worker slot. This specification provides the vocabulary and semantics for all of these cases.

### 1.1 Scope

This specification defines:

- A multi-layered timeout model distinguishing execution, total, and enqueue timeouts.
- Grace period semantics for orderly cleanup before forceful termination.
- Heartbeat-based liveness detection for long-running jobs.
- Timeout actions that control behavior when a timeout fires.
- Interaction semantics with retry, workflows, progress, and graceful shutdown.

This specification does **not** define:

- OS-level process signal handling (SIGTERM, SIGKILL) — these are implementation-specific.
- Network-level timeouts (TCP keepalive, HTTP request timeouts) — these belong to protocol bindings.
- Idle detection within a job (the job handler is responsible for its own internal timeout logic for sub-operations).

### 1.2 Companion Specifications

| Document | Layer | Description |
|----------|-------|-------------|
| **ojs-core.md** | 1 -- Core | Job envelope, lifecycle, `timeout` attribute, visibility timeout |
| **ojs-retry.md** | Core | Retry policy, `max_attempts`, backoff, dead-letter |
| **ojs-progress.md** | Extension | Progress reporting, checkpoint resumption |
| **ojs-graceful-shutdown.md** | Extension | Drain semantics, container integration |
| **ojs-worker-protocol.md** | Core | Worker heartbeat protocol, BEAT operation |

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term | Definition |
|------|------------|
| **Execution Timeout** | Maximum wall-clock time allowed for a single attempt of a job. |
| **Total Timeout** | Maximum wall-clock time allowed from first enqueue to final completion, across all attempts. |
| **Enqueue TTL** | Maximum time a job may remain in a non-active state before it is discarded without execution. |
| **Grace Period** | Time window between a soft timeout signal and forceful termination, allowing cleanup. |
| **Heartbeat Timeout** | Maximum interval between consecutive heartbeats before a job is considered stalled. |
| **Visibility Timeout** | Duration during which a fetched job is reserved for a worker (defined in OJS Core). |
| **Stalled Job** | A job whose worker has stopped sending heartbeats within the expected interval. |

---

## 4. Design Principles

1. **Layered timeouts prevent different failure modes.** A single `timeout` value cannot distinguish between "this attempt is stuck" and "this job has been retrying for days." Separate execution, total, and enqueue timeouts each address a distinct failure class.

2. **Graceful before forceful.** Workers SHOULD receive a soft timeout signal before forceful termination. This allows database connections to be released, partial results to be checkpointed, and cleanup logic to execute.

3. **Server is the authority.** Timeout enforcement MUST NOT rely solely on worker cooperation. A crashed or malicious worker will never self-report a timeout. Server-side enforcement through heartbeat monitoring and visibility timeout expiry is the backstop.

4. **Sensible defaults over mandatory configuration.** Every timeout has a reasonable default. Producers who do not set timeouts still get protection against runaway jobs.

---

## 5. Timeout Model

OJS defines five distinct timeout mechanisms, each addressing a different failure mode:

```
                                    total_timeout
    ├──────────────────────────────────────────────────────────────┤
    │                                                              │
    │  enqueue_ttl          execution_timeout       execution_timeout
    │  ├──────────┤        ├──────────────────┤    ├──────────────────┤
    │  │ waiting  │        │   attempt 1      │    │   attempt 2      │
    │  │ in queue │        │   (active)       │    │   (active)       │
    ├──┼──────────┼────────┼──────────────────┼────┼──────────────────┼──┤
  enqueue     fetched   failed/retry       fetched                done
```

### 5.1 Execution Timeout

The execution timeout limits the wall-clock duration of a single job attempt. When exceeded, the current attempt is terminated and the job transitions to the `retryable` state (if retries remain) or `discarded` state (if exhausted).

Implementations MUST enforce the execution timeout. The enforcement mechanism is implementation-defined but MUST NOT rely solely on worker self-reporting.

**Rationale:** Execution timeouts catch individual stuck attempts — a deadlocked database query, an unresponsive external service, or an infinite loop. Without per-attempt limits, a single bad attempt would consume a worker slot until the process is manually killed.

**Default:** Implementations MUST define a default execution timeout. The RECOMMENDED default is 1800 seconds (30 minutes).

### 5.2 Total Timeout

The total timeout limits the wall-clock duration from the job's `created_at` timestamp to final completion. This clock runs continuously across all retry attempts, wait times, and backoff delays. When exceeded, the job transitions directly to the `discarded` state regardless of remaining retry attempts.

Implementations SHOULD support total timeout. When supported, the total timeout MUST take precedence over the retry policy's `max_attempts`.

**Rationale:** Total timeout prevents zombie jobs that retry indefinitely with long backoff intervals. A job with exponential backoff and 25 retries could theoretically run for weeks. Total timeout provides an absolute upper bound on job lifetime.

**Default:** When not specified, there is no total timeout (job lifetime is bounded only by `max_attempts`).

### 5.3 Enqueue TTL

The enqueue TTL limits how long a job may remain in a non-active state (i.e., `scheduled`, `available`, or `pending`) before being discarded. This is measured from the job's `created_at` timestamp. If the job has not transitioned to `active` before the TTL expires, it MUST transition to `discarded` with error type `"enqueue_ttl_expired"`.

Implementations SHOULD support enqueue TTL.

**Rationale:** Enqueue TTL prevents stale work. A time-sensitive job (e.g., "send password reset email") that sits in a queue for 24 hours is no longer useful. Rather than wasting a worker slot executing it, the system should discard it before execution begins.

**Default:** When not specified, there is no enqueue TTL (jobs wait indefinitely for a worker).

### 5.4 Grace Period

The grace period defines a time window between the soft timeout signal and forceful termination. During the grace period, the worker SHOULD:

1. Stop accepting new work within the handler.
2. Checkpoint progress (if the progress extension is supported).
3. Release external resources (database connections, file handles).
4. Return a partial result or error.

Implementations that support grace periods MUST deliver a cancellation signal to the job handler at the start of the grace period. The mechanism for delivering this signal is language-specific (e.g., context cancellation in Go, `AbortSignal` in JavaScript, `CancellationToken` in C#, `asyncio.Task.cancel()` in Python).

If the handler does not complete within the grace period, the implementation MUST forcefully terminate the attempt and transition the job to the appropriate state.

**Rationale:** Graceful degradation is preferable to abrupt termination. A job processing a batch of items can checkpoint which items were completed, enabling the retry to resume from the last checkpoint rather than reprocessing everything.

**Default:** The RECOMMENDED default grace period is 30 seconds.

### 5.5 Heartbeat Timeout

The heartbeat timeout defines the maximum allowed interval between consecutive BEAT operations from a worker processing a job. If no heartbeat is received within this interval, the server MUST consider the job stalled.

When a job is detected as stalled, the server MUST:

1. Transition the job from `active` to `retryable` (if retries remain) or `discarded` (if exhausted).
2. Emit a `job.stalled` event (see [Section 11](#11-observability)).
3. Make the job available for re-processing by another worker.

**Rationale:** Heartbeat timeout catches worker crashes and network partitions that the execution timeout alone cannot detect. A worker that crashes mid-execution will never report a timeout; heartbeat monitoring ensures the server detects the failure.

**Default:** Implementations MUST define a default heartbeat timeout. The RECOMMENDED default is 60 seconds. The heartbeat timeout SHOULD be at least 4× the heartbeat interval to tolerate transient network delays.

---

## 6. Timeout Fields

The following fields extend the job envelope defined in the OJS Core Specification:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `timeout` | integer (seconds) | 1800 | Maximum execution time for a single attempt. Defined in OJS Core; semantics extended here. |
| `total_timeout` | integer (seconds) | none | Maximum wall-clock time from `created_at` to completion, across all attempts. |
| `enqueue_ttl` | integer (seconds) | none | Maximum time in non-active state before discard. |
| `grace_period` | integer (seconds) | 30 | Time between soft timeout signal and forceful termination. |
| `heartbeat_timeout` | integer (seconds) | 60 | Maximum interval between consecutive heartbeats. |

**Validation rules:**

- `timeout` MUST be a positive integer greater than 0.
- `total_timeout`, when specified, MUST be greater than or equal to `timeout`.
- `grace_period` MUST be a non-negative integer. A value of 0 means no grace period (immediate termination).
- `heartbeat_timeout` MUST be a positive integer greater than 0.
- `enqueue_ttl` MUST be a positive integer greater than 0.

**Rationale for seconds (not ISO 8601 durations):** Timeouts are operational parameters that benefit from simple arithmetic comparison. Seconds are unambiguous, require no parsing, and align with the core `timeout` field. ISO 8601 durations are used in the retry extension for backoff intervals where human readability of values like `"PT5M"` is more important than computational simplicity.

---

## 7. Timeout Detection and Enforcement

### 7.1 Server-Side Enforcement

The server MUST enforce execution timeouts independently of worker behavior. The primary mechanism is visibility timeout expiry: when a worker fetches a job, the server starts a visibility timer. If the worker does not ACK or FAIL the job within `timeout + grace_period` seconds, the server reclaims the job.

Implementations MUST:

- Track the `started_at` timestamp when a job transitions to `active`.
- Periodically scan for jobs where `now() - started_at > timeout + grace_period`.
- Transition expired jobs to `retryable` or `discarded` based on the retry policy.
- Set the error type to `"timeout"` on timeout-induced failures.

**Rationale:** Server-side enforcement is the only reliable mechanism. Workers may crash, hang, lose network connectivity, or be killed by an OOM killer. The server cannot depend on worker cooperation for timeout enforcement.

### 7.2 Worker-Side Enforcement

Workers SHOULD also enforce execution timeouts locally to enable graceful degradation. Worker-side enforcement provides the grace period mechanism:

1. Worker starts a timer when beginning job execution.
2. At `timeout` seconds, the worker delivers a cancellation signal to the handler.
3. The handler has `grace_period` seconds to clean up.
4. At `timeout + grace_period` seconds, the worker forcefully terminates the handler and reports FAIL with error type `"timeout"`.

Worker-side enforcement is RECOMMENDED but not sufficient on its own. The server MUST NOT rely on worker-side timeout reports as the sole enforcement mechanism.

### 7.3 Heartbeat-Based Detection

For long-running jobs, heartbeat-based detection provides faster stall detection than visibility timeout expiry alone.

The heartbeat timeout clock resets each time the server receives a BEAT for the job. If the worker also reports progress (via the progress extension), a progress update SHOULD reset the heartbeat clock.

Implementations MUST:

- Track the last heartbeat timestamp for each active job.
- Periodically scan for active jobs where `now() - last_heartbeat > heartbeat_timeout`.
- Transition stalled jobs to `retryable` or `discarded`.
- Distinguish heartbeat timeout from execution timeout in the error type (`"stalled"` vs. `"timeout"`).

---

## 8. Timeout Actions

When a timeout fires, the implementation determines the job's next state based on the retry policy:

| Condition | Next State | Error Type |
|-----------|------------|------------|
| Execution timeout, retries remaining | `retryable` | `"timeout"` |
| Execution timeout, retries exhausted | `discarded` | `"timeout"` |
| Total timeout exceeded | `discarded` | `"total_timeout"` |
| Enqueue TTL expired | `discarded` | `"enqueue_ttl_expired"` |
| Heartbeat timeout, retries remaining | `retryable` | `"stalled"` |
| Heartbeat timeout, retries exhausted | `discarded` | `"stalled"` |

The error object stored on the job MUST include:

```json
{
  "type": "timeout",
  "message": "Job execution exceeded timeout of 300 seconds",
  "timeout_kind": "execution",
  "limit_seconds": 300,
  "elapsed_seconds": 305
}
```

The `timeout_kind` field MUST be one of: `"execution"`, `"total"`, `"enqueue_ttl"`, or `"stalled"`.

---

## 9. Interaction with Other Extensions

### 9.1 Retry Policy

When a job times out with retries remaining, the retry policy determines the backoff delay before the next attempt. The `timeout` error type is retryable by default unless explicitly listed in the retry policy's `non_retryable_errors` array.

If `total_timeout` is set, the retry evaluator MUST check whether the next attempt would exceed the total timeout. If `created_at + total_timeout < now() + backoff_delay + timeout`, the job SHOULD transition directly to `discarded` rather than scheduling a retry that cannot complete.

### 9.2 Workflows

In a workflow chain, an individual step's timeout is independent of the workflow's overall timeline. If a step times out and is discarded, the chain MUST halt and the workflow MUST transition to a failed state.

Implementations MAY support a `workflow_timeout` field on the workflow envelope to limit the total duration of the entire workflow, independent of individual step timeouts.

### 9.3 Progress

Progress updates (via the progress extension) SHOULD reset the heartbeat timeout clock. This prevents long-running jobs that are actively reporting progress from being incorrectly classified as stalled.

Checkpoint data saved during the grace period MUST be available to the next retry attempt via `last_checkpoint`, enabling resumption from the point of timeout.

### 9.4 Graceful Shutdown

When a worker receives a shutdown signal (SIGTERM), jobs that are within their execution timeout SHOULD be allowed to complete up to the shutdown's drain timeout. If the drain timeout expires before the job completes, the worker MUST FAIL the job with error type `"shutdown"` (not `"timeout"`).

The shutdown drain timeout and the job's grace period are independent. The shorter of the two wins.

---

## 10. HTTP Binding

Timeout fields are included in the job envelope and transmitted as part of the JSON body. No additional HTTP headers are defined for timeouts.

### 10.1 Enqueue with Timeouts

```http
POST /ojs/v1/jobs HTTP/1.1
Content-Type: application/openjobspec+json

{
  "type": "video.transcode",
  "queue": "media",
  "args": ["video_001", "1080p"],
  "timeout": 3600,
  "total_timeout": 86400,
  "enqueue_ttl": 7200,
  "grace_period": 60
}
```

### 10.2 Timeout Error in Job Response

```http
GET /ojs/v1/jobs/019539a4-b68c-7def-8000-1a2b3c4d5e6f HTTP/1.1

{
  "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "type": "video.transcode",
  "state": "retryable",
  "attempt": 2,
  "error": {
    "type": "timeout",
    "message": "Job execution exceeded timeout of 3600 seconds",
    "timeout_kind": "execution",
    "limit_seconds": 3600,
    "elapsed_seconds": 3602
  }
}
```

---

## 11. Observability

### 11.1 Events

Implementations MUST emit the following events when timeout-related state transitions occur:

| Event Type | Trigger |
|------------|---------|
| `job.timeout` | Job execution timeout fired. |
| `job.stalled` | Heartbeat timeout detected a stalled job. |
| `job.ttl_expired` | Enqueue TTL expired before job was fetched. |
| `job.total_timeout` | Total timeout exceeded across all attempts. |

Event data MUST include:

```json
{
  "job_id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "job_type": "video.transcode",
  "queue": "media",
  "timeout_kind": "execution",
  "limit_seconds": 3600,
  "elapsed_seconds": 3602,
  "attempt": 2
}
```

### 11.2 Metrics

Implementations SHOULD expose the following metrics:

| Metric | Type | Description |
|--------|------|-------------|
| `ojs.job.timeout.count` | Counter | Number of jobs timed out, labeled by `timeout_kind`, `queue`, `job_type`. |
| `ojs.job.execution.duration` | Histogram | Execution duration in seconds, labeled by `queue`, `job_type`, `outcome` (completed, timeout, stalled). |
| `ojs.job.heartbeat.age` | Gauge | Time since last heartbeat for active jobs. |
| `ojs.job.enqueue.wait_time` | Histogram | Time spent in queue before first execution, labeled by `queue`. |

---

## 12. Conformance Requirements

### 12.1 Required

| Capability | Requirement |
|------------|-------------|
| Execution timeout enforcement | Implementations MUST enforce execution timeouts server-side. |
| Timeout error type | Implementations MUST set error type to `"timeout"` on execution timeout. |
| Heartbeat timeout | Implementations MUST detect stalled jobs via heartbeat monitoring. |
| Timeout events | Implementations MUST emit `job.timeout` and `job.stalled` events. |

### 12.2 Recommended

| Capability | Requirement |
|------------|-------------|
| Total timeout | Implementations SHOULD support `total_timeout`. |
| Enqueue TTL | Implementations SHOULD support `enqueue_ttl`. |
| Grace period | Implementations SHOULD support `grace_period` for orderly cleanup. |
| Worker-side enforcement | Workers SHOULD enforce timeouts locally with cancellation signals. |
| Timeout metrics | Implementations SHOULD expose timeout-related metrics. |

### 12.3 Optional

| Capability | Requirement |
|------------|-------------|
| Workflow timeout | Implementations MAY support `workflow_timeout` on workflow envelopes. |
| Dynamic timeout adjustment | Implementations MAY allow timeout values to be modified for pending jobs. |

---

## 13. Prior Art

| System | Timeout Model |
|--------|---------------|
| **Sidekiq** | No built-in execution timeout; relies on `Timeout.timeout` (Ruby stdlib) which is notoriously unsafe. Sidekiq Enterprise adds `timeout_retry_count`. |
| **BullMQ** | `timeout` option (ms) for per-attempt timeout. Stalled job detection via lock renewal. No total timeout. |
| **Celery** | `time_limit` (hard kill via SIGKILL) and `soft_time_limit` (raises `SoftTimeLimitExceeded`). Two-phase model inspired OJS grace period. |
| **Faktory** | `reserve_for` (visibility timeout). No execution timeout; relies on worker heartbeat and reserve expiry. |
| **Temporal** | Rich timeout model: `StartToCloseTimeout` (per-attempt), `ScheduleToCloseTimeout` (total), `ScheduleToStartTimeout` (enqueue TTL), `HeartbeatTimeout`. OJS aligns closely with Temporal's model. |
| **River** | `timeout` (Go `context.WithTimeout`). Job-level timeout with automatic retry. |
| **Google Cloud Tasks** | `dispatch_deadline` (total time from creation to completion). Maps to OJS `total_timeout`. |

---

## 14. Examples

### 14.1 Quick API Call with Short Timeout

```json
{
  "type": "payment.verify",
  "queue": "payments",
  "args": ["txn_abc123"],
  "timeout": 30,
  "grace_period": 5
}
```

A payment verification that must complete within 30 seconds. If it times out, the handler has 5 seconds to release the payment lock before forceful termination.

### 14.2 Long-Running Batch with Total Timeout

```json
{
  "type": "report.generate",
  "queue": "reports",
  "args": ["quarterly", "2025-Q4"],
  "timeout": 3600,
  "total_timeout": 86400,
  "grace_period": 120,
  "retry": {
    "max_attempts": 5,
    "backoff_coefficient": 2.0
  }
}
```

A report generation job allowed 1 hour per attempt, but no more than 24 hours total. If it fails and retries with exponential backoff, the total timeout prevents it from retrying indefinitely.

### 14.3 Time-Sensitive Job with Enqueue TTL

```json
{
  "type": "notification.push",
  "queue": "notifications",
  "args": ["user_456", "Your order has shipped!"],
  "timeout": 60,
  "enqueue_ttl": 300
}
```

A push notification that becomes stale after 5 minutes in the queue. If no worker picks it up within 300 seconds of creation, it is discarded.

### 14.4 Heartbeat-Intensive ML Training Job

```json
{
  "type": "ml.train",
  "queue": "gpu",
  "args": ["model_v3", {"epochs": 100}],
  "timeout": 86400,
  "heartbeat_timeout": 120,
  "grace_period": 300
}
```

A machine learning training job that runs for up to 24 hours. The worker sends heartbeats every 30 seconds. If no heartbeat arrives for 2 minutes, the job is considered stalled. The 5-minute grace period allows the worker to save model checkpoints before termination.

---

## Appendix A: Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0-rc.1 | 2026-02-15 | Initial release candidate. |
