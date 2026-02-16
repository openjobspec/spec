# Open Job Spec: Job Progress Reporting

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Job Progress Specification                 |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-15                                     |
| **Status**  | Release Candidate                              |
| **Maturity** | Experimental                                   |
| **Tier**    | Official Extension                             |
| **URI**     | `urn:ojs:ext:progress`                         |
| **Requires**| OJS Core Specification (Layer 1)               |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Design Principles](#4-design-principles)
5. [Progress Model](#5-progress-model)
   - 5.1 [Numeric Progress](#51-numeric-progress)
   - 5.2 [Structured Progress](#52-structured-progress)
   - 5.3 [Progress Lifecycle](#53-progress-lifecycle)
6. [Reporting Progress](#6-reporting-progress)
   - 6.1 [Worker API](#61-worker-api)
   - 6.2 [Update Frequency](#62-update-frequency)
   - 6.3 [Progress as Heartbeat](#63-progress-as-heartbeat)
7. [Retrieving Progress](#7-retrieving-progress)
   - 7.1 [Polling](#71-polling)
   - 7.2 [Server-Sent Events](#72-server-sent-events)
8. [Progress on Completion and Failure](#8-progress-on-completion-and-failure)
9. [Progress in Workflows](#9-progress-in-workflows)
10. [HTTP Binding](#10-http-binding)
11. [Observability](#11-observability)
12. [Conformance Requirements](#12-conformance-requirements)
13. [Prior Art](#13-prior-art)
14. [Examples](#14-examples)

---

## 1. Introduction

Long-running background jobs present a visibility problem: once a job begins processing, the system and its users have no insight into how much work has been completed, how much remains, or whether the job is making progress at all. A video transcoding job, a data migration, a large CSV import -- these operations can take minutes or hours, and without progress reporting, the only observable states are "running" and "done."

Progress reporting closes this visibility gap by allowing workers to report incremental progress as they execute a job. Clients, dashboards, and monitoring systems can then display meaningful status ("47% complete", "processing row 14,000 of 30,000") rather than a binary active/complete indicator.

This specification defines a progress model, reporting mechanism, and retrieval API that enable real-time job progress visibility.

### 1.1 Scope

This specification defines:

- A progress model supporting both numeric (percentage) and structured (arbitrary data) progress.
- A worker-side API for reporting progress updates during job execution.
- A client-side API for retrieving job progress via polling and server-sent events.
- Integration with the heartbeat mechanism for liveness detection.
- Progress semantics for workflow jobs.

This specification does **not** define:

- UI rendering of progress (client responsibility).
- Progress prediction or ETA calculation (application logic, not protocol concern).
- Progress persistence guarantees after job completion (retention is implementation-defined).

### 1.2 Companion Specifications

| Document | Layer | Description |
|----------|-------|-------------|
| **ojs-core.md** | 1 -- Core | Job envelope, lifecycle, ACK/FAIL operations |
| **ojs-worker-protocol.md** | Extension | Heartbeat mechanism that progress extends |
| **ojs-workflows.md** | Extension | Workflow progress aggregation |
| **ojs-events.md** | Extension | Progress events in the event vocabulary |

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

Every MUST requirement includes a rationale explaining why the requirement is mandatory.

---

## 3. Terminology

| Term                  | Definition                                                                                         |
|-----------------------|----------------------------------------------------------------------------------------------------|
| progress              | A report of how much work a job has completed, expressed as a numeric percentage, structured data, or both. |
| numeric progress      | A floating-point value between 0.0 and 1.0 representing the fraction of work completed.           |
| structured progress   | An arbitrary JSON object containing application-specific progress details.                         |
| progress update       | A message sent by a worker to the backend reporting the current progress of an active job.          |
| progress event        | An event emitted by the backend when a job's progress changes, available to subscribers.           |
| checkpoint            | A progress update that also includes recoverable state, enabling the job to resume from its last reported position after a failure. |

---

## 4. Design Principles

1. **Fire-and-forget updates.** Progress updates are best-effort. A failed progress update MUST NOT affect job execution. Workers should not block on progress reporting or retry failed updates. Progress is observational, not transactional.

2. **Dual representation.** Progress can be reported as a simple number (0.0–1.0) for generic UI display, as structured data for application-specific detail, or both. This dual model serves both the generic dashboard use case and the application-specific status page use case.

3. **Heartbeat integration.** Progress updates serve double duty as heartbeats. A worker that reports progress is demonstrably alive and making progress. This integration reduces protocol overhead (one message serves two purposes) and provides richer liveness signals than a bare heartbeat.

4. **Bounded overhead.** Progress updates add overhead to job processing (network I/O, backend storage). The specification defines rate limiting on progress updates to prevent a tight loop from flooding the backend with thousands of updates per second.

---

## 5. Progress Model

### 5.1 Numeric Progress

Numeric progress is a floating-point value between `0.0` (not started) and `1.0` (complete).

```json
{
  "progress": 0.47
}
```

The backend MUST accept values in the range `[0.0, 1.0]` inclusive. Values outside this range MUST be clamped: values less than `0.0` are treated as `0.0`; values greater than `1.0` are treated as `1.0`.

**Rationale**: Clamping rather than rejecting out-of-range values follows the fire-and-forget principle. A progress update with `1.3` due to a calculation error should not fail the update or disrupt job processing. Clamping to `1.0` is the least surprising behavior.

Numeric progress MUST be monotonically non-decreasing within a single job execution. If a progress update reports a value lower than the previously reported value, the backend MUST ignore the update (retain the higher value).

**Rationale**: Non-decreasing progress matches user expectations. A progress bar that goes backward is confusing and suggests an error. If a job genuinely needs to restart or re-process earlier work, it should report structured progress with an explanation rather than decreasing the numeric percentage.

### 5.2 Structured Progress

Structured progress is an arbitrary JSON object that provides application-specific detail:

```json
{
  "progress": 0.47,
  "data": {
    "phase": "processing",
    "rows_processed": 14000,
    "rows_total": 30000,
    "current_file": "data_chunk_14.csv",
    "errors_encountered": 3
  }
}
```

| Field      | Type    | Required | Description                                              |
|------------|---------|----------|----------------------------------------------------------|
| `progress` | number  | No       | Numeric progress (0.0–1.0). May be omitted if only structured data is reported. |
| `data`     | object  | No       | Arbitrary JSON object with application-specific progress details. |

At least one of `progress` or `data` MUST be present in a progress update.

**Rationale**: Requiring at least one field prevents empty progress updates (which serve no purpose). Allowing either or both gives applications flexibility: a simple job can report just a percentage, a complex job can report detailed metadata, and a well-instrumented job can report both.

The `data` object SHOULD be kept small (RECOMMENDED maximum 4 KB serialized). Large progress payloads consume storage and bandwidth on every update.

### 5.3 Progress Lifecycle

Progress is associated with a single job execution (one attempt). When a job is retried:

1. Progress from the previous attempt is cleared.
2. The new attempt starts with no progress reported.
3. Previous attempts' progress MAY be retained in the job's history for diagnostic purposes.

**Rationale**: Starting each attempt with fresh progress prevents confusion when a retry re-processes work. If progress from the failed attempt were retained, a retried job might show "80% complete" immediately, which is misleading if it is restarting from scratch.

---

## 6. Reporting Progress

### 6.1 Worker API

Workers report progress by sending a PROGRESS operation to the backend for an active job:

```http
PUT /ojs/v1/jobs/{id}/progress
Content-Type: application/json

{
  "progress": 0.47,
  "data": {
    "rows_processed": 14000,
    "rows_total": 30000
  }
}
```

The backend MUST accept progress updates only for jobs in the `active` state. Progress updates for jobs in any other state MUST be silently ignored (not rejected with an error).

**Rationale**: A job may complete or fail between the time a worker calculates progress and the time the update arrives at the backend. Silently ignoring stale updates (rather than returning an error) follows the fire-and-forget principle and prevents race condition errors from disrupting worker logic.

### 6.2 Update Frequency

Workers SHOULD NOT send progress updates more frequently than once per second.

Implementations MUST accept at least one progress update per second per job. Implementations MAY throttle updates that arrive more frequently by accepting the update but rate-limiting the storage and event emission.

**Rationale**: A progress update on every loop iteration (potentially thousands per second) would overwhelm the backend with writes and event emissions. One update per second provides sufficient granularity for UI display while keeping overhead manageable.

When throttling is applied:
- The backend MUST store the most recent progress value (not an intermediate one).
- The backend MAY batch multiple progress updates into a single storage write.
- The backend SHOULD emit at most one progress event per second per job.

### 6.3 Progress as Heartbeat

A progress update implicitly serves as a heartbeat. When a worker sends a progress update:

1. The backend MUST reset the job's visibility timeout as if a BEAT (heartbeat) had been received.
2. The backend MUST NOT require a separate BEAT message when progress updates are being sent.

**Rationale**: Progress updates prove that the worker is alive and actively processing the job -- a stronger signal than a bare heartbeat. Requiring both a progress update and a separate heartbeat wastes bandwidth and introduces the risk of the heartbeat being missed while progress updates succeed, leading to spurious timeout.

### 6.4 Checkpoint Progress

Workers MAY include a `checkpoint` field in progress updates to enable resumable jobs:

```json
{
  "progress": 0.47,
  "data": {
    "rows_processed": 14000,
    "rows_total": 30000
  },
  "checkpoint": {
    "last_processed_id": "row_14000",
    "batch_offset": 14000
  }
}
```

| Field        | Type    | Required | Description                                              |
|--------------|---------|----------|----------------------------------------------------------|
| `checkpoint` | object  | No       | Arbitrary JSON object containing state needed to resume the job from this point. |

When a job with checkpoint data fails and is retried, the checkpoint from the last successful progress update SHOULD be made available to the worker on the retry attempt via the job's `last_checkpoint` field.

**Rationale**: Checkpoint-based resumption is critical for long-running jobs. Without it, a job that fails at 90% must restart from scratch. Temporal's activity heartbeat with progress details serves the same purpose and is one of its most-valued features.

---

## 7. Retrieving Progress

### 7.1 Polling

Clients retrieve the current progress of a job via GET:

```http
GET /ojs/v1/jobs/{id}/progress
```

**Response** (200 OK):

```json
{
  "job_id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "state": "active",
  "progress": 0.47,
  "data": {
    "rows_processed": 14000,
    "rows_total": 30000
  },
  "updated_at": "2026-02-15T21:45:30Z"
}
```

When no progress has been reported, the response MUST return `progress: null` and `data: null` (not a 404).

**Rationale**: A 404 is ambiguous -- it could mean the job doesn't exist or that no progress has been reported. Returning a valid response with null fields distinguishes "no progress yet" from "job not found" (which returns 404).

### 7.2 Server-Sent Events

For real-time progress updates, implementations SHOULD support Server-Sent Events (SSE):

```http
GET /ojs/v1/jobs/{id}/progress/stream
Accept: text/event-stream
```

**Event stream**:

```
event: progress
data: {"progress": 0.47, "data": {"rows_processed": 14000}, "updated_at": "2026-02-15T21:45:30Z"}

event: progress
data: {"progress": 0.52, "data": {"rows_processed": 15600}, "updated_at": "2026-02-15T21:45:31Z"}

event: completed
data: {"progress": 1.0, "state": "completed", "updated_at": "2026-02-15T21:46:02Z"}
```

The stream MUST emit a `completed`, `failed`, or `cancelled` event when the job reaches a terminal state, then close the connection.

**Rationale**: SSE is the simplest real-time transport for progress updates. It requires no additional dependencies (unlike WebSockets), works through proxies and load balancers, and is natively supported by all modern browsers via `EventSource`. For background job progress -- which is a unidirectional data flow from server to client -- SSE is the ideal transport.

---

## 8. Progress on Completion and Failure

### 8.1 Automatic Progress on Completion

When a job completes successfully (ACK), the backend MUST set numeric progress to `1.0` if progress reporting was used during execution.

**Rationale**: A completed job is 100% done. If the worker reported progress but forgot to send a final `1.0` update, the progress should still reflect completion. This prevents the confusing state of a completed job showing 87% progress.

### 8.2 Progress on Failure

When a job fails (FAIL), the backend MUST retain the last reported progress. The progress is NOT reset to `0.0` or set to `1.0`.

**Rationale**: Retaining progress on failure provides diagnostic value. If a job failed at 73%, that information tells the operator approximately where in the processing pipeline the failure occurred.

### 8.3 Progress Retention

After a job reaches a terminal state, implementations SHOULD retain progress data for at least as long as the job record itself is retained.

---

## 9. Progress in Workflows

### 9.1 Workflow Progress Aggregation

When a job is part of a workflow (chain, group, or batch), the workflow's aggregate progress can be derived from its constituent jobs:

- **Chain**: Progress = (completed steps / total steps) + (current step progress / total steps).
- **Group**: Progress = average of all parallel job progresses.
- **Batch**: Progress = completed jobs / total jobs.

Implementations MAY compute aggregate workflow progress automatically. When computed, the aggregate progress MUST be available via the workflow's progress endpoint.

### 9.2 Workflow Progress Retrieval

```http
GET /ojs/v1/workflows/{id}/progress
```

**Response** (200 OK):

```json
{
  "workflow_id": "wf_019539a4-b68c-7def-8000-aabbccddeeff",
  "type": "chain",
  "progress": 0.58,
  "steps": [
    {
      "job_id": "019539a4-...",
      "type": "data.extract",
      "state": "completed",
      "progress": 1.0
    },
    {
      "job_id": "019539a5-...",
      "type": "data.transform",
      "state": "active",
      "progress": 0.73,
      "data": { "records_transformed": 21900, "records_total": 30000 }
    },
    {
      "job_id": "019539a6-...",
      "type": "data.load",
      "state": "pending",
      "progress": null
    }
  ]
}
```

---

## 10. HTTP Binding

### 10.1 Endpoint Summary

| Method | Path                                | Description                          |
|--------|-------------------------------------|--------------------------------------|
| PUT    | `/ojs/v1/jobs/{id}/progress`        | Report progress (worker → backend).  |
| GET    | `/ojs/v1/jobs/{id}/progress`        | Retrieve progress (client → backend).|
| GET    | `/ojs/v1/jobs/{id}/progress/stream` | SSE stream for real-time progress.   |
| GET    | `/ojs/v1/workflows/{id}/progress`   | Aggregate workflow progress.         |

### 10.2 HTTP Status Codes

| Status Code | Condition                                              |
|-------------|--------------------------------------------------------|
| `200 OK`    | Progress retrieved or updated successfully.            |
| `204 No Content` | Progress update accepted (no response body needed). |
| `404 Not Found` | Job does not exist.                               |
| `429 Too Many Requests` | Progress update rate limit exceeded.       |

### 10.3 Headers

| Header                  | Direction | Description                                              |
|-------------------------|-----------|----------------------------------------------------------|
| `X-OJS-Progress`        | Response  | Numeric progress as a header for quick access without parsing the body. |
| `Last-Modified`         | Response  | Timestamp of the last progress update (for caching).     |
| `Cache-Control`         | Response  | `no-cache` for progress endpoints (progress changes frequently). |

---

## 11. Observability

### 11.1 Events

Implementations SHOULD emit the following events:

| Event Type              | Trigger                                         | Data Fields                              |
|-------------------------|-------------------------------------------------|------------------------------------------|
| `progress.updated`      | A worker reported progress on a job.            | `job_id`, `progress`, `data`             |
| `progress.completed`    | A job's progress reached 1.0 (via ACK).         | `job_id`, `progress`, `duration`         |
| `progress.stalled`      | No progress update received within expected interval. | `job_id`, `last_progress`, `last_update` |

### 11.2 Metrics

Implementations SHOULD expose the following metrics:

| Metric Name                          | Type      | Labels                     | Description                               |
|--------------------------------------|-----------|----------------------------|-------------------------------------------|
| `ojs.progress.updates_total`         | Counter   | `queue`, `job_type`        | Total progress updates received.          |
| `ojs.progress.update_rate`           | Gauge     | `queue`                    | Progress updates per second.              |
| `ojs.progress.stalled_jobs`          | Gauge     | `queue`                    | Jobs with stale progress.                 |
| `ojs.progress.checkpoint_size_bytes` | Histogram | `job_type`                 | Size of checkpoint data in progress updates. |

---

## 12. Conformance Requirements

### 12.1 Required Capabilities

An implementation declaring support for the progress extension MUST support:

| ID          | Requirement                                                                              |
|-------------|------------------------------------------------------------------------------------------|
| PRG-001     | Accept progress updates via `PUT /ojs/v1/jobs/{id}/progress`.                            |
| PRG-002     | Accept numeric progress as a float in range [0.0, 1.0] with clamping.                   |
| PRG-003     | Enforce monotonically non-decreasing numeric progress within a single execution.         |
| PRG-004     | Retrieve progress via `GET /ojs/v1/jobs/{id}/progress`.                                  |
| PRG-005     | Automatically set progress to 1.0 on successful job completion.                          |
| PRG-006     | Retain last progress value on job failure.                                                |
| PRG-007     | Silently ignore progress updates for jobs not in `active` state.                         |
| PRG-008     | Treat progress updates as implicit heartbeats (reset visibility timeout).                |

### 12.2 Recommended Capabilities

| ID          | Requirement                                                                              |
|-------------|------------------------------------------------------------------------------------------|
| PRG-R001    | Support structured progress via the `data` field.                                        |
| PRG-R002    | Support checkpoint progress for resumable jobs.                                          |
| PRG-R003    | SSE streaming via `GET /ojs/v1/jobs/{id}/progress/stream`.                               |
| PRG-R004    | Workflow progress aggregation via `GET /ojs/v1/workflows/{id}/progress`.                 |
| PRG-R005    | Rate-limit progress updates to at most one per second per job.                           |
| PRG-R006    | Emit `progress.stalled` event when updates stop for an active job.                       |

---

## 13. Prior Art

| System               | Approach                                                                                  |
|----------------------|-------------------------------------------------------------------------------------------|
| **BullMQ**           | `job.updateProgress(data)` where data is a number or object. Progress stored in Redis hash. `progress` event emitted via pub/sub. Sandboxed processor support. |
| **Temporal**         | Activity heartbeat with progress details. Last heartbeat data available on retry for resumption. `HeartbeatTimeout` for liveness detection. SDK-level throttling of heartbeat calls. |
| **Celery**           | `self.update_state(state='PROGRESS', meta={'current': 10, 'total': 50})`. Custom states for progress. Result backend stores state. No built-in streaming. |
| **Sidekiq**          | No built-in progress reporting. Community gem `sidekiq-status` provides `at(step, total)` API stored in Redis with TTL. |
| **Hangfire**         | Server monitoring with real-time dashboard. No per-job progress API. Background job methods can update progress via custom patterns. |
| **Faktory**          | No built-in progress reporting. Heartbeat-based liveness detection only.                 |
| **Oban**             | `Oban.Notifier` for real-time events. No built-in per-job progress. Custom metadata can be used for progress tracking. |

OJS combines BullMQ's dual progress model (numeric + structured), Temporal's heartbeat-integrated progress with checkpoint resumption, and SSE streaming for real-time client updates into a unified progress specification.

---

## 14. Examples

### 14.1 Simple Percentage Progress

A video transcoding job reporting progress:

Worker reports:
```json
PUT /ojs/v1/jobs/019539a4-.../progress

{
  "progress": 0.35
}
```

Client polls:
```json
GET /ojs/v1/jobs/019539a4-.../progress

{
  "job_id": "019539a4-...",
  "state": "active",
  "progress": 0.35,
  "data": null,
  "updated_at": "2026-02-15T21:45:30Z"
}
```

### 14.2 Structured Progress for Data Migration

Worker reports detailed progress:

```json
PUT /ojs/v1/jobs/019539a5-.../progress

{
  "progress": 0.47,
  "data": {
    "phase": "migrating",
    "table": "users",
    "rows_migrated": 47000,
    "rows_total": 100000,
    "tables_completed": ["products", "orders"],
    "tables_remaining": ["users", "transactions"],
    "errors": 3
  }
}
```

### 14.3 Checkpoint-Based Resumable Job

First attempt (fails at 73%):

```json
PUT /ojs/v1/jobs/019539a6-.../progress

{
  "progress": 0.73,
  "data": { "files_processed": 73, "files_total": 100 },
  "checkpoint": {
    "last_file_index": 72,
    "last_file_path": "/data/chunk_072.parquet"
  }
}
```

Retry attempt receives checkpoint:

```json
{
  "id": "019539a6-...",
  "type": "data.process",
  "args": [{"dataset": "ds_123"}],
  "attempt": 2,
  "last_checkpoint": {
    "last_file_index": 72,
    "last_file_path": "/data/chunk_072.parquet"
  }
}
```

The worker resumes from file 73 instead of restarting from file 0.

### 14.4 Real-Time Progress via SSE

```http
GET /ojs/v1/jobs/019539a7-.../progress/stream
Accept: text/event-stream
```

```
event: progress
data: {"progress": 0.10, "data": {"step": "downloading"}, "updated_at": "2026-02-15T21:50:00Z"}

event: progress
data: {"progress": 0.40, "data": {"step": "processing"}, "updated_at": "2026-02-15T21:50:12Z"}

event: progress
data: {"progress": 0.90, "data": {"step": "uploading"}, "updated_at": "2026-02-15T21:50:45Z"}

event: completed
data: {"progress": 1.0, "state": "completed", "updated_at": "2026-02-15T21:50:52Z"}
```

### 14.5 Workflow Chain Progress

A three-step ETL pipeline where the middle step is active:

```json
GET /ojs/v1/workflows/wf_019539a8-.../progress

{
  "workflow_id": "wf_019539a8-...",
  "type": "chain",
  "progress": 0.58,
  "steps": [
    {
      "job_id": "019539a8-...",
      "type": "etl.extract",
      "state": "completed",
      "progress": 1.0
    },
    {
      "job_id": "019539a9-...",
      "type": "etl.transform",
      "state": "active",
      "progress": 0.73
    },
    {
      "job_id": "019539aa-...",
      "type": "etl.load",
      "state": "pending",
      "progress": null
    }
  ]
}
```

Aggregate progress: (1.0 + 0.73 + 0.0) / 3 = 0.58.

---

## Appendix A: Changelog

| Date       | Change                        |
|------------|-------------------------------|
| 2026-02-15 | Initial release candidate.    |
