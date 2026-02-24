# Open Job Spec: Durable Execution Extension

> **⚠️ EXPERIMENTAL**: This extension is under active development. The specification
> may change in breaking ways between versions. Implementations and SDKs that adopt
> this extension should expect migration work when the spec evolves. Feedback is
> encouraged via the OJS RFC process.

| Field        | Value                                                    |
|-------------|----------------------------------------------------------|
| **Title**   | OJS Durable Execution                                    |
| **Version** | 0.1.0                                                    |
| **Date**    | 2026-02-19                                               |
| **Status**  | Draft                                                    |
| **Maturity** | Experimental                                             |
| **Layer**   | Extension                                                |
| **URI**     | `urn:ojs:ext:experimental:durable-execution`             |
| **Requires**| OJS Core Specification (Layer 1)                         |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Checkpoint API](#4-checkpoint-api)
5. [Checkpoint Storage](#5-checkpoint-storage)
6. [Resume Protocol](#6-resume-protocol)
7. [HTTP Binding](#7-http-binding)
8. [SDK Integration](#8-sdk-integration)
9. [Limitations](#9-limitations)
10. [Conformance Requirements](#10-conformance-requirements)
11. [Prior Art](#11-prior-art)
12. [Examples](#12-examples)

---

## 1. Introduction

Long-running jobs present a fundamental reliability challenge: if a worker crashes mid-execution, all progress is lost and the job must restart from the beginning. For jobs that take minutes or hours (data migrations, ML training, report generation), this is unacceptable in production systems.

Durable execution addresses this by allowing workers to persist intermediate state — checkpoints — during job processing. If the worker crashes, the job resumes from the last checkpoint rather than restarting from scratch. Temporal pioneered this pattern with its deterministic replay model. This specification brings a simpler, checkpoint-based approach to OJS.

The OJS durable execution model is intentionally simpler than Temporal's full replay engine. Instead of recording every side effect and replaying deterministically, OJS provides explicit checkpoints that workers control. This trades some automation for simplicity and predictability.

### 1.1 Scope

This specification defines:

- A checkpoint API for persisting intermediate job state.
- Checkpoint storage semantics for backend implementations.
- A resume protocol for restarting jobs from the last checkpoint.
- HTTP endpoints for checkpoint management.
- SDK integration patterns for worker libraries.
- Limitations of the v0.1 checkpoint model.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term                     | Definition                                                                                      |
|--------------------------|-------------------------------------------------------------------------------------------------|
| checkpoint               | A snapshot of intermediate job state persisted during execution.                                 |
| durable execution        | A job execution model where progress is preserved across worker failures.                       |
| resume                   | The act of restarting a job from its last checkpoint after a failure.                            |
| checkpoint sequence      | A monotonically increasing counter identifying the order of checkpoints for a job.              |
| checkpoint state         | The JSON-serializable data representing the job's intermediate progress.                        |

---

## 4. Checkpoint API

### 4.1 Saving a Checkpoint

Workers call the checkpoint API to persist intermediate state during job execution:

```
POST /ojs/v1/jobs/{id}/checkpoint
Content-Type: application/json

{
  "state": {
    "processed_count": 5000,
    "last_cursor": "cursor_abc123",
    "partial_results": [...]
  }
}
```

**Response** (200 OK):
```json
{
  "checkpoint": {
    "job_id": "019503e1-7b2a-7000-8000-000000000001",
    "sequence": 3,
    "created_at": "2026-02-19T12:05:00.000Z"
  }
}
```

The `state` field MUST be a valid JSON value (object, array, string, number, boolean, or null).

Each checkpoint call increments the sequence number. Only the latest checkpoint is retained; previous checkpoints are overwritten.

### 4.2 Checkpoint Preconditions

A checkpoint can only be saved when:

1. The job exists and is in the `active` state.
2. The job is currently assigned to the requesting worker.
3. The checkpoint state is valid JSON and does not exceed the size limit.

If any precondition fails, the implementation MUST return an appropriate error:

- `404 Not Found` if the job does not exist.
- `409 Conflict` if the job is not in `active` state.
- `413 Content Too Large` if the checkpoint exceeds the size limit.

### 4.3 Getting the Latest Checkpoint

Retrieve the most recent checkpoint for a job:

```
GET /ojs/v1/jobs/{id}/checkpoint
```

**Response** (200 OK):
```json
{
  "checkpoint": {
    "job_id": "019503e1-7b2a-7000-8000-000000000001",
    "state": {
      "processed_count": 5000,
      "last_cursor": "cursor_abc123",
      "partial_results": [...]
    },
    "sequence": 3,
    "created_at": "2026-02-19T12:05:00.000Z"
  }
}
```

If no checkpoint exists for the job, the implementation MUST return `404 Not Found`.

### 4.4 Deleting a Checkpoint

Clear the checkpoint for a job:

```
DELETE /ojs/v1/jobs/{id}/checkpoint
```

**Response** (200 OK):
```json
{
  "deleted": true,
  "job_id": "019503e1-7b2a-7000-8000-000000000001"
}
```

---

## 5. Checkpoint Storage

### 5.1 Storage Model

Backends MUST store checkpoints alongside the job data. The checkpoint is a single JSON document per job, overwritten on each checkpoint call.

The storage model:

| Field       | Type            | Description                                              |
|-------------|-----------------|----------------------------------------------------------|
| `job_id`    | string          | The ID of the job this checkpoint belongs to.            |
| `state`     | JSON            | The checkpoint state (any valid JSON value).             |
| `sequence`  | integer         | Monotonically increasing checkpoint counter.             |
| `created_at`| string (ISO 8601)| Timestamp of the most recent checkpoint.               |

### 5.2 Lifecycle

Checkpoints follow the job lifecycle:

1. **Created**: When a worker calls `POST /ojs/v1/jobs/{id}/checkpoint` for the first time.
2. **Updated**: On subsequent checkpoint calls (state and sequence are updated, previous state is overwritten).
3. **Deleted**: When the job reaches a terminal state (`completed`, `cancelled`, `discarded`). Implementations MUST automatically delete checkpoints when a job completes or is discarded.

### 5.3 Backend-Specific Storage

| Backend     | Storage Strategy                                                              |
|-------------|-------------------------------------------------------------------------------|
| Redis       | `ojs:checkpoints:{job_id}` key containing JSON-encoded checkpoint.           |
| PostgreSQL  | JSONB column on the jobs table or a separate `checkpoints` table.            |
| SQLite      | JSON column on the jobs table or a separate `checkpoints` table.             |

---

## 6. Resume Protocol

### 6.1 Resuming from a Checkpoint

When a job is re-fetched after a worker crash or visibility timeout expiration, the backend MUST include the last checkpoint state in the job envelope:

```json
{
  "id": "019503e1-7b2a-7000-8000-000000000001",
  "type": "data.migrate",
  "state": "active",
  "args": { "source": "old_db", "target": "new_db", "batch_size": 1000 },
  "attempt": 2,
  "checkpoint": {
    "state": {
      "processed_count": 5000,
      "last_cursor": "cursor_abc123"
    },
    "sequence": 3
  }
}
```

The `checkpoint` field is present ONLY when a checkpoint exists for the job. On the first attempt (no prior checkpoint), this field is absent.

### 6.2 Worker Responsibility

Workers MUST check for the `checkpoint` field when receiving a job:

1. If `checkpoint` is present, resume processing from the checkpoint state.
2. If `checkpoint` is absent, start processing from the beginning using `args`.

The worker is responsible for interpreting the checkpoint state and resuming correctly. The backend provides storage and delivery; the worker provides the resume logic.

### 6.3 Checkpoint and Retry Interaction

Checkpoints persist across retry attempts. When a job is retried (after NACK or visibility timeout):

1. The checkpoint from the previous attempt is preserved.
2. The next worker to fetch the job receives the checkpoint.
3. The worker can choose to resume from the checkpoint or ignore it and restart.

When a job is explicitly retried from the dead letter queue, the checkpoint is preserved unless the operator explicitly clears it.

---

## 7. HTTP Binding

| Method | Path                                    | Description                                  |
|--------|-----------------------------------------|----------------------------------------------|
| POST   | `/ojs/v1/jobs/{id}/checkpoint`          | Save a checkpoint for an active job.         |
| GET    | `/ojs/v1/jobs/{id}/checkpoint`          | Get the latest checkpoint for a job.         |
| DELETE | `/ojs/v1/jobs/{id}/checkpoint`          | Delete the checkpoint for a job.             |

---

## 8. SDK Integration

### 8.1 Go SDK

The Go SDK provides a `Checkpoint` method on the job context:

```go
func (ctx *JobContext) Checkpoint(state interface{}) error
```

Usage:

```go
func HandleDataMigration(ctx *ojs.JobContext) error {
    var cursor string
    var processed int

    // Resume from checkpoint if available
    if ctx.HasCheckpoint() {
        var cp MigrationCheckpoint
        ctx.LoadCheckpoint(&cp)
        cursor = cp.LastCursor
        processed = cp.ProcessedCount
    }

    for {
        batch, nextCursor, err := fetchBatch(cursor, 1000)
        if err != nil {
            return err
        }
        if len(batch) == 0 {
            break
        }

        processBatch(batch)
        processed += len(batch)
        cursor = nextCursor

        // Checkpoint every batch
        ctx.Checkpoint(MigrationCheckpoint{
            LastCursor:     cursor,
            ProcessedCount: processed,
        })
    }

    return nil
}
```

### 8.2 Other SDKs

All language SDKs SHOULD provide an equivalent checkpoint API:

| Language   | Method                                        |
|------------|-----------------------------------------------|
| Go         | `ctx.Checkpoint(state interface{})`           |
| Python     | `ctx.checkpoint(state: dict)`                 |
| JavaScript | `ctx.checkpoint(state: object)`               |
| Ruby       | `ctx.checkpoint(state:)`                      |
| Rust       | `ctx.checkpoint(state: &impl Serialize)`      |
| Java       | `ctx.checkpoint(Object state)`                |
| .NET       | `ctx.Checkpoint(object state)`                |

---

## 9. Limitations

### 9.1 v0.1 Limitations

The following limitations apply to the v0.1 durable execution model:

1. **Sequential execution only.** Checkpoints support a single linear execution path. Parallel durable steps (e.g., fork-join with per-branch checkpoints) are not supported. Use workflows for parallel execution patterns.

2. **Checkpoint size limit.** Checkpoints are capped at **1 MB** (1,048,576 bytes). This prevents checkpoints from becoming a storage burden. Jobs that need to persist large intermediate state should use external storage (S3, database) and store only references in the checkpoint.

3. **No deterministic replay.** Unlike Temporal, OJS does not record side effects or replay them deterministically. The worker is responsible for making resumed execution produce correct results. Side effects (HTTP calls, database writes) may be repeated on resume.

4. **Single checkpoint per job.** Only the latest checkpoint is retained. There is no checkpoint history or rollback to earlier checkpoints.

5. **No checkpoint compression.** Checkpoints are stored as-is. Implementations MAY add compression in future versions.

### 9.2 Future Directions

Future versions may add:

- **Named checkpoints** for multi-step jobs with non-linear progress.
- **Checkpoint history** for debugging and rollback.
- **Deterministic replay** for side-effect recording (inspired by Temporal).
- **Parallel durable steps** with per-branch checkpointing.
- **Checkpoint compression** for large state.

---

## 10. Conformance Requirements

An implementation declaring support for the durable-execution extension MUST support:

| ID           | Requirement                                                                      |
|--------------|----------------------------------------------------------------------------------|
| DUR-001      | Save checkpoint state for active jobs via HTTP API.                              |
| DUR-002      | Retrieve the latest checkpoint for a job.                                        |
| DUR-003      | Delete checkpoint for a job.                                                     |
| DUR-004      | Include checkpoint state in job envelope when re-fetching a previously checkpointed job. |
| DUR-005      | Automatically delete checkpoints when a job reaches a terminal state.            |
| DUR-006      | Enforce 1 MB checkpoint size limit.                                              |
| DUR-007      | Reject checkpoint saves for jobs not in `active` state with 409 Conflict.        |
| DUR-008      | Maintain monotonically increasing checkpoint sequence numbers per job.           |

Recommended:

| ID           | Requirement                                                                      |
|--------------|----------------------------------------------------------------------------------|
| DUR-R001     | Preserve checkpoints across retry attempts.                                      |
| DUR-R002     | Provide SDK `Checkpoint()` method on job context.                                |
| DUR-R003     | Emit `job.checkpointed` event when a checkpoint is saved.                        |

---

## 11. Prior Art

| System              | Durable Execution Approach                                                           |
|---------------------|--------------------------------------------------------------------------------------|
| **Temporal**        | Full deterministic replay. Records all side effects. Replays execution from start.   |
| **Azure Durable Functions** | Orchestrator replay with checkpoint-based state. Similar to Temporal.        |
| **Restate**         | Journaling of side effects with deterministic replay. Virtual objects for state.     |
| **AWS Step Functions** | State machine with explicit state transitions. State passed between steps.        |
| **Inngest**         | Step-based execution with memoization. Each step is checkpointed automatically.     |

OJS takes the simplest approach: explicit worker-controlled checkpoints without automatic replay. This trades sophistication for predictability and ease of implementation across backends.

---

## 12. Examples

### 12.1 Data Migration with Checkpoints

```json
// Initial job
{
  "type": "data.migrate",
  "args": { "source": "old_db", "target": "new_db", "total_rows": 1000000 }
}

// After processing 250,000 rows, worker saves checkpoint
POST /ojs/v1/jobs/019503e1-7b2a-7000/checkpoint
{
  "state": {
    "processed": 250000,
    "last_id": 250000,
    "errors": []
  }
}

// Worker crashes. Job is re-fetched with checkpoint:
{
  "id": "019503e1-7b2a-7000",
  "type": "data.migrate",
  "state": "active",
  "attempt": 2,
  "args": { "source": "old_db", "target": "new_db", "total_rows": 1000000 },
  "checkpoint": {
    "state": { "processed": 250000, "last_id": 250000, "errors": [] },
    "sequence": 1
  }
}
```

### 12.2 ML Training with Periodic Checkpoints

```json
// Checkpoint saved every 10 epochs
POST /ojs/v1/jobs/019503e1-abc0-1234/checkpoint
{
  "state": {
    "epoch": 50,
    "loss": 0.0342,
    "model_weights_ref": "s3://models/training-run-42/epoch-50.pt",
    "learning_rate": 0.001
  }
}
```

Note: Large artifacts (model weights) are stored externally; only the reference is checkpointed.

### 12.3 Report Generation with Section Tracking

```json
POST /ojs/v1/jobs/019503e1-def0-5678/checkpoint
{
  "state": {
    "sections_completed": ["summary", "financials", "charts"],
    "sections_remaining": ["appendix", "glossary"],
    "temp_file": "/tmp/report-partial-019503e1.pdf"
  }
}
```

---

## Appendix A: Changelog

| Date       | Change                          |
|------------|---------------------------------|
| 2026-02-19 | Initial draft.                  |
