# OJS Workflow Primitives Specification

**Version**: 1.0.0-rc.1
**Date**: 2026-02-12
**Status**: Release Candidate
**Spec Layer**: Layer 1 (Core Specification)

---

## Table of Contents

1. [Overview and Rationale](#1-overview-and-rationale)
2. [Terminology](#2-terminology)
3. [Workflow Envelope](#3-workflow-envelope)
4. [Primitive: Chain (Sequential Execution)](#4-primitive-chain-sequential-execution)
5. [Primitive: Group (Parallel Execution)](#5-primitive-group-parallel-execution)
6. [Primitive: Batch (Parallel with Callbacks)](#6-primitive-batch-parallel-with-callbacks)
7. [Data Passing Semantics](#7-data-passing-semantics)
8. [Workflow Lifecycle States](#8-workflow-lifecycle-states)
9. [Error Handling and Failure Propagation](#9-error-handling-and-failure-propagation)
10. [Composition and Nesting](#10-composition-and-nesting)
11. [API Operations](#11-api-operations)
12. [Complete Examples](#12-complete-examples)
13. [Prior Art](#13-prior-art)
14. [Future Work](#14-future-work)

---

## 1. Overview and Rationale

This document defines the workflow primitives for the Open Job Spec (OJS) v1.0. A workflow is a higher-order construct that composes multiple jobs into a coordinated unit of work with defined execution order, data flow, and failure semantics.

### 1.1 Why Only Three Primitives

OJS v1.0 defines exactly three workflow primitives:

| Primitive | Execution Model | Summary |
|-----------|----------------|---------|
| **Chain** | Sequential | Jobs execute one after another; result of step N feeds step N+1. |
| **Group** | Parallel | Jobs execute concurrently and independently. |
| **Batch** | Parallel with callbacks | Like group, but fires callbacks on completion, success, or failure. |

This deliberately limited set reflects hard-won lessons from production systems. Full directed acyclic graph (DAG) support -- where arbitrary dependency edges connect arbitrary nodes -- is deferred to OJS v1.1 or a companion specification. The rationale for this constraint:

1. **Chain, group, and batch cover the vast majority of real-world workflows.** Sequential pipelines (ETL, order processing), fan-out parallelism (multi-format export, notification broadcast), and fan-out-with-aggregation (bulk operations with summary callbacks) account for an estimated 90% of workflow use cases in production job systems.

2. **Simpler primitives are dramatically easier to implement correctly.** Celery's `chord` primitive (the closest analog to a DAG fan-in) is so unreliable that Celery's own documentation warns "avoid chords as much as possible." BullMQ's `FlowProducer` supports only tree structures -- no fan-in, no diamond dependencies. These limitations exist because correct DAG execution requires solving distributed consensus problems (exactly-once callback firing, partial failure recovery, cycle detection) that are orthogonal to job processing.

3. **Composition of simple primitives yields complex workflows.** Chains can contain groups as steps (fan-out within a sequence), and groups can contain chains as jobs (sequential within parallel). This nesting provides significant expressive power without DAG complexity.

4. **Implementations can ship workflow support faster.** A chain requires only a counter and a pointer to the next step. A group requires only a counter of remaining jobs. A batch adds three optional callback pointers. A full DAG engine requires topological sorting, cycle detection, concurrent dependency tracking, and partial completion semantics.

### 1.2 Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt).

All JSON examples in this document are normative unless explicitly marked otherwise.

All timestamps use ISO 8601 / RFC 3339 format with timezone (UTC preferred, with `Z` suffix).

All identifiers (workflow IDs, job IDs) SHOULD use UUIDv7 for time-sortability.

The job envelope uses `args` (JSON array) as the positional argument field, not `payload`. This aligns with the OJS Core Specification.

---

## 2. Terminology

**Workflow**: A named, identifiable composition of one or more jobs with defined execution semantics (ordering, parallelism, data flow, failure handling).

**Step**: An individual job within a chain. Steps are ordered and execute sequentially.

**Job (within a group or batch)**: An individual job within a group or batch. Jobs are unordered and execute concurrently.

**Callback**: A job that is automatically enqueued when a batch reaches a specific terminal condition (all complete, all succeeded, any failed).

**Parent Result**: The return value of a completed job, made available to downstream jobs via `JobContext.parent_results`.

**Nesting**: Embedding one workflow primitive inside another (e.g., a group as a step within a chain).

---

## 3. Workflow Envelope

Every workflow is represented as a JSON object with a common set of fields. Implementations MUST support the fields defined below.

**Rationale**: A consistent envelope enables implementations to route, store, and inspect workflows uniformly regardless of primitive type.

### 3.1 Common Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | REQUIRED | The workflow primitive type. MUST be one of: `"chain"`, `"group"`, `"batch"`. |
| `id` | string | REQUIRED | Globally unique workflow identifier. SHOULD be UUIDv7. |
| `name` | string | OPTIONAL | Human-readable name for the workflow. Used for display and filtering. |
| `state` | string | Set by system | Current workflow state. See [Section 8](#8-workflow-lifecycle-states). |
| `metadata` | object | Set by system | System-managed metadata (timestamps, counters). |

**Rationale for `type` as REQUIRED**: Implementations MUST know the workflow primitive to determine execution semantics. Without `type`, an implementation cannot distinguish between sequential and parallel execution, which would lead to undefined behavior.

**Rationale for `id` as REQUIRED**: Workflows MUST be individually addressable for status queries, cancellation, and observability. Without a stable identifier, there is no way to correlate workflow events or retrieve workflow state.

### 3.2 Job Envelope Within Workflows

Each job within a workflow uses the standard OJS job envelope. At minimum, a job within a workflow MUST include:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | REQUIRED | The job type (dot-namespaced handler identifier). |
| `args` | array | REQUIRED | Positional arguments for the job handler. MAY be empty (`[]`). |

Jobs within workflows MAY include any standard OJS job option (queue, retry policy, timeout, tags, etc.).

**Rationale for `args` as array**: Positional arguments as a JSON array enforce clean serialization boundaries, prevent stale object references, and enable inspection without language-specific deserialization. This follows the convention established by Sidekiq, which proved that "simple types only" is the correct constraint for cross-process job arguments.

```json
{
  "type": "email.send",
  "args": ["user@example.com", "welcome"],
  "options": {
    "queue": "email",
    "retry": { "max_attempts": 3 }
  }
}
```

### 3.3 Metadata Fields

Implementations MUST populate the following metadata fields on workflow creation and state transitions:

| Field | Type | Description |
|-------|------|-------------|
| `created_at` | ISO 8601 | When the workflow was created. |
| `started_at` | ISO 8601 | When the first job began executing. |
| `completed_at` | ISO 8601 | When the workflow reached a terminal state. |
| `job_count` | integer | Total number of jobs in the workflow (including nested). |
| `completed_count` | integer | Number of jobs that have completed (succeeded). |
| `failed_count` | integer | Number of jobs that have failed (terminal). |

**Rationale for system-managed metadata**: Clients MUST NOT set these fields directly. System-managed timestamps and counters ensure consistency and prevent clock skew issues between clients and the server. Implementations rely on these counters for state transition logic (e.g., a group completes when `completed_count + failed_count == job_count`).

---

## 4. Primitive: Chain (Sequential Execution)

A **chain** executes jobs one after another in a defined order. The result of step N is passed as input context to step N+1. If any step fails (after retries are exhausted), the chain stops and transitions to the `failed` state.

### 4.1 Schema

```json
{
  "type": "chain",
  "id": "wf_019539a4-chain-example",
  "name": "order-processing",
  "steps": [
    { "type": "order.validate", "args": [{"order_id": "ord_123"}] },
    { "type": "payment.charge", "args": [] },
    { "type": "inventory.reserve", "args": [] },
    { "type": "notification.send", "args": [] }
  ]
}
```

### 4.2 Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | REQUIRED | MUST be `"chain"`. |
| `id` | string | REQUIRED | Unique workflow identifier. |
| `name` | string | OPTIONAL | Human-readable name. |
| `steps` | array | REQUIRED | Ordered array of job envelopes. MUST contain at least one step. |

**Rationale for `steps` as REQUIRED with minimum length 1**: A chain with zero steps has no meaningful semantics. Requiring at least one step prevents degenerate workflows that would immediately transition to `completed` with no work performed, which complicates state machine logic and confuses operators.

### 4.3 Execution Semantics

1. When a chain is created, the implementation MUST enqueue only the first step (index 0) for execution. All subsequent steps MUST remain in a `waiting` state.

   **Rationale**: Enqueueing all steps simultaneously would cause them to execute concurrently, violating the sequential guarantee that defines a chain. The "enqueue one at a time" invariant is the fundamental correctness property of chains.

2. When step N completes successfully, the implementation MUST enqueue step N+1 for execution. The result of step N MUST be made available to step N+1 via `JobContext.parent_results` (see [Section 7](#7-data-passing-semantics)).

   **Rationale**: Automatic progression is essential for hands-off operation. Without it, an external orchestrator would need to poll and advance the chain, defeating the purpose of a workflow primitive.

3. If step N fails (transitions to a terminal failure state after all retries are exhausted), the implementation MUST NOT enqueue any subsequent steps. The chain MUST transition to the `failed` state.

   **Rationale**: Continuing execution after a failure would produce undefined results. Step N+1 typically depends on step N's output. Executing it without that output would cause cascading errors or data corruption. Operators can inspect the chain state to determine which step failed and why.

4. The chain transitions to `completed` when the last step completes successfully.

5. Each step within a chain retains its individual retry policy. A step failure means "this step exhausted all its retries." The chain does not add an additional retry layer on top of individual step retries.

### 4.4 Step States

Each step within a chain tracks its own state:

| State | Description |
|-------|-------------|
| `waiting` | Step has not been enqueued yet (a predecessor has not completed). |
| `pending` | Step has been enqueued and is awaiting a worker. |
| `active` | Step is currently being executed by a worker. |
| `completed` | Step completed successfully. |
| `failed` | Step failed after all retries were exhausted. |
| `cancelled` | Step was cancelled (chain was cancelled before this step ran). |

Implementations MUST track step-level state to enable inspection and debugging.

**Rationale**: Without per-step state, operators cannot determine where a chain failed or how far it progressed. This is critical for debugging production issues and for resumption strategies.

---

## 5. Primitive: Group (Parallel Execution)

A **group** executes jobs concurrently and independently. All jobs are enqueued immediately. The group completes when all jobs complete. The group fails if any job fails (after retries are exhausted). Individual job failures do not affect other jobs in the group.

### 5.1 Schema

```json
{
  "type": "group",
  "id": "wf_019539a4-group-example",
  "name": "multi-format-export",
  "jobs": [
    { "type": "export.csv", "args": [{"report_id": "rpt_456"}] },
    { "type": "export.pdf", "args": [{"report_id": "rpt_456"}] },
    { "type": "export.xlsx", "args": [{"report_id": "rpt_456"}] }
  ]
}
```

### 5.2 Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | REQUIRED | MUST be `"group"`. |
| `id` | string | REQUIRED | Unique workflow identifier. |
| `name` | string | OPTIONAL | Human-readable name. |
| `jobs` | array | REQUIRED | Array of job envelopes. MUST contain at least one job. |

**Rationale for `jobs` (not `steps`)**: The field is named `jobs` (not `steps`) to distinguish unordered parallel work from ordered sequential work. The naming signals that there is no implied ordering or dependency between items.

### 5.3 Execution Semantics

1. When a group is created, the implementation MUST enqueue ALL jobs immediately for concurrent execution.

   **Rationale**: Immediate concurrent enqueue is the defining property of a group. Any sequencing or batching of enqueue operations would undermine the parallelism guarantee. Workers SHOULD be able to pick up group jobs as soon as the group is created.

2. The group transitions to `completed` when ALL jobs have completed successfully.

3. The group transitions to `failed` if ANY job fails (transitions to a terminal failure state after all retries are exhausted).

   **Rationale**: A group represents a logical unit of work. If any component fails, the group as a whole has not achieved its purpose. Callers can inspect individual job states to determine partial results.

4. Individual job failures MUST NOT affect other running jobs in the group. If job A fails, jobs B and C MUST continue executing.

   **Rationale**: Cancelling healthy jobs upon a sibling failure would waste completed work and complicate recovery. The fail-independent model allows maximum work to complete, and callers can decide whether partial results are useful.

5. Jobs within a group have no guaranteed execution order. Implementations MUST NOT make ordering guarantees for group jobs.

   **Rationale**: Ordering guarantees would require coordination between workers, which reduces throughput and adds complexity. If ordering is needed, use a chain instead.

---

## 6. Primitive: Batch (Parallel with Callbacks)

A **batch** is a group of concurrently executed jobs with automatic callback dispatch based on the collective outcome. It extends the group primitive with three callback hooks: `on_complete`, `on_success`, and `on_failure`.

### 6.1 Schema

```json
{
  "type": "batch",
  "id": "wf_019539a4-batch-example",
  "name": "bulk-email-send",
  "jobs": [
    { "type": "email.send", "args": ["user1@example.com", "welcome"] },
    { "type": "email.send", "args": ["user2@example.com", "welcome"] },
    { "type": "email.send", "args": ["user3@example.com", "welcome"] }
  ],
  "callbacks": {
    "on_complete": { "type": "batch.report", "args": [] },
    "on_success": { "type": "batch.celebrate", "args": [] },
    "on_failure": { "type": "batch.alert", "args": [] }
  }
}
```

### 6.2 Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | REQUIRED | MUST be `"batch"`. |
| `id` | string | REQUIRED | Unique workflow identifier. |
| `name` | string | OPTIONAL | Human-readable name. |
| `jobs` | array | REQUIRED | Array of job envelopes. MUST contain at least one job. |
| `callbacks` | object | REQUIRED | Callback definitions. MUST contain at least one callback. |

**Rationale for `callbacks` as REQUIRED with at least one callback**: A batch without callbacks is semantically identical to a group. Requiring at least one callback justifies the batch primitive's existence and prevents confusion about which primitive to use. If no callbacks are needed, use a group.

### 6.3 Callback Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `callbacks.on_complete` | Job envelope | OPTIONAL | Enqueued when ALL jobs finish, regardless of outcome. |
| `callbacks.on_success` | Job envelope | OPTIONAL | Enqueued only if ALL jobs succeeded. |
| `callbacks.on_failure` | Job envelope | OPTIONAL | Enqueued if ANY job failed. |

At least one of `on_complete`, `on_success`, or `on_failure` MUST be present.

### 6.4 Execution Semantics

1. When a batch is created, the implementation MUST enqueue ALL jobs immediately for concurrent execution, identical to group behavior.

2. The implementation MUST track the outcome of every job in the batch.

   **Rationale**: Accurate outcome tracking is necessary to determine which callbacks to fire. A race condition or missed outcome could cause the wrong callback to fire (or no callback at all), leading to silent data loss.

3. When ALL jobs have reached a terminal state (completed or failed), the implementation MUST evaluate and fire the appropriate callbacks:

   - **`on_complete`** MUST be enqueued when all jobs have finished, regardless of whether they succeeded or failed. This callback fires in all cases.

   - **`on_success`** MUST be enqueued only if every job in the batch completed successfully (zero failures). If `on_complete` is also defined, both `on_complete` and `on_success` MUST be enqueued.

   - **`on_failure`** MUST be enqueued if one or more jobs in the batch failed. If `on_complete` is also defined, both `on_complete` and `on_failure` MUST be enqueued.

   **Rationale**: The three-callback model covers the complete decision space: "always run cleanup" (`on_complete`), "celebrate full success" (`on_success`), "handle any failure" (`on_failure`). This mirrors Sidekiq Pro's batch callbacks, which have proven to be the correct abstraction in production systems processing millions of batches.

4. Callbacks MUST be enqueued exactly once. Implementations MUST use atomic operations (e.g., compare-and-swap, database transactions, Lua scripts) to prevent duplicate callback firing.

   **Rationale**: Duplicate callback execution is the most common batch implementation bug. Celery's chord primitive suffers from this exact problem -- when multiple group members complete simultaneously, the callback can fire multiple times. OJS mandates exactly-once callback dispatch to avoid this class of bugs.

5. Callbacks receive the aggregated results of all batch jobs via `JobContext.parent_results` (see [Section 7](#7-data-passing-semantics)).

6. Individual job failures within a batch MUST NOT affect other running jobs, identical to group behavior.

7. The batch transitions to `completed` when all callbacks have been enqueued and executed. The batch transitions to `failed` if a callback itself fails.

### 6.5 Callback Firing Matrix

| All jobs succeeded | Any job failed | on_complete | on_success | on_failure |
|--------------------|----------------|-------------|------------|------------|
| Yes | No | Fires | Fires | Does not fire |
| No | Yes | Fires | Does not fire | Fires |

---

## 7. Data Passing Semantics

Workflow primitives enable data flow between jobs. This section defines how job results are propagated to downstream jobs.

### 7.1 JobContext.parent_results

When a job executes within a workflow context, its `JobContext` MUST include a `parent_results` field containing the results of upstream jobs.

**Rationale**: Without a standardized data passing mechanism, workflow steps would need to use external storage (databases, caches) to share data, defeating the purpose of a workflow primitive. `parent_results` provides a built-in, inspectable data channel.

```
JobContext {
  job: Job,
  attempt: integer,
  parent_results: object,
  workflow_id: string,
  ...
}
```

### 7.2 Chain Data Passing

In a chain, the `parent_results` object for step N contains the result of step N-1, keyed by the step's index.

- Step 0 (the first step) receives an empty `parent_results` (`{}`).
- Step 1 receives `parent_results` containing step 0's result.
- Step N receives `parent_results` containing step N-1's result.

Implementations MUST populate `parent_results` with at minimum the immediately preceding step's result. Implementations SHOULD include all preceding steps' results for maximum flexibility.

**Rationale for including previous results**: The immediately preceding step's result is the most common use case (pipeline pattern). Including all prior results enables steps that need to reference earlier stages without requiring those stages to forward data explicitly.

Example for a three-step chain:

```
Step 0 executes with parent_results: {}
Step 0 returns: { "order": { "id": "ord_123", "total": 99.99 } }

Step 1 executes with parent_results: {
  "0": { "order": { "id": "ord_123", "total": 99.99 } }
}
Step 1 returns: { "charge_id": "ch_abc", "amount": 99.99 }

Step 2 executes with parent_results: {
  "0": { "order": { "id": "ord_123", "total": 99.99 } },
  "1": { "charge_id": "ch_abc", "amount": 99.99 }
}
```

### 7.3 Group Data Passing

Groups do not pass data between jobs (jobs are independent). However, if a group is used as a step within a chain, the group's collective results are passed to the next chain step.

When a group completes within a chain, the `parent_results` entry for that step MUST be an object keyed by job index, containing each job's result.

Example: a chain with a group as step 1:

```
Step 0 returns: { "report_id": "rpt_456" }

Step 1 (group) completes. Each group job's result:
  Job 0 (export.csv): { "path": "/exports/rpt_456.csv" }
  Job 1 (export.pdf): { "path": "/exports/rpt_456.pdf" }
  Job 2 (export.xlsx): { "path": "/exports/rpt_456.xlsx" }

Step 2 executes with parent_results: {
  "0": { "report_id": "rpt_456" },
  "1": {
    "0": { "path": "/exports/rpt_456.csv" },
    "1": { "path": "/exports/rpt_456.pdf" },
    "2": { "path": "/exports/rpt_456.xlsx" }
  }
}
```

### 7.4 Batch Data Passing

Batch callbacks receive the results of all batch jobs via `parent_results`. The object is keyed by job index.

```
Batch jobs complete:
  Job 0 (email.send user1): { "message_id": "msg_001", "status": "sent" }
  Job 1 (email.send user2): { "message_id": "msg_002", "status": "sent" }
  Job 2 (email.send user3): { "message_id": null, "status": "bounced" }

on_complete callback executes with parent_results: {
  "0": { "message_id": "msg_001", "status": "sent" },
  "1": { "message_id": "msg_002", "status": "sent" },
  "2": { "message_id": null, "status": "bounced" }
}

on_failure callback executes with parent_results: {
  "0": { "message_id": "msg_001", "status": "sent" },
  "1": { "message_id": "msg_002", "status": "sent" },
  "2": { "message_id": null, "status": "bounced" }
}
```

Callback `parent_results` MUST include results from ALL jobs, not just successful or failed ones. This enables callbacks to perform aggregation, reporting, and error analysis across the full batch.

**Rationale**: Providing only partial results (e.g., only failed jobs to `on_failure`) would force callbacks to make separate API calls to retrieve the full picture, adding latency and complexity.

### 7.5 Large Result Handling

Job results SHOULD be kept small. Results larger than 64 KB SHOULD use references (URIs, S3 paths, database keys) rather than inline data.

**Rationale**: Inline large results consume backend storage, increase serialization overhead, and can exceed message size limits in transport layers. Reference-based passing scales to arbitrary result sizes.

Example of reference-based result:

```json
{
  "result_ref": "s3://my-bucket/results/job_019539a4.json",
  "result_size_bytes": 15728640,
  "result_content_type": "application/json"
}
```

Implementations MUST NOT impose a maximum result size below 64 KB. Implementations MAY impose limits above 64 KB and MUST document those limits.

**Rationale for 64 KB minimum**: Most job results (status codes, identifiers, small summaries) fit well within 64 KB. This minimum ensures that common use cases work without requiring external storage, while the SHOULD guidance for larger results prevents backend overload.

---

## 8. Workflow Lifecycle States

Every workflow instance tracks a top-level state that reflects the aggregate progress of its constituent jobs.

### 8.1 States

| State | Description |
|-------|-------------|
| `pending` | Workflow has been created but no jobs have started executing yet. |
| `running` | At least one job is active (executing) or pending (enqueued, awaiting a worker). |
| `completed` | All jobs (and callbacks, for batches) completed successfully. Terminal state. |
| `failed` | A job failed with no remaining retries, causing the workflow to fail. Terminal state. |
| `cancelled` | The workflow was explicitly cancelled via the API. Terminal state. |

Implementations MUST track and expose workflow state.

**Rationale**: Workflow state is the primary mechanism for monitoring, alerting, and programmatic decision-making. Without it, callers would need to poll individual job states and compute the aggregate themselves, which is error-prone and wasteful.

### 8.2 State Transitions

```
             ┌───────────┐
             │  pending   │
             └─────┬─────┘
                   │ first job starts
                   v
             ┌───────────┐
         ┌───│  running   │───┐
         │   └─────┬─────┘   │
         │         │         │
         v         v         v
   ┌───────────┐ ┌────────┐ ┌───────────┐
   │ completed │ │ failed │ │ cancelled │
   └───────────┘ └────────┘ └───────────┘
```

Valid transitions:

| From | To | Trigger |
|------|----|---------|
| `pending` | `running` | First job begins execution. |
| `pending` | `cancelled` | Workflow cancelled before any job starts. |
| `running` | `completed` | All jobs (and callbacks) completed successfully. |
| `running` | `failed` | A job failed with no remaining retries (chain stops; group/batch marks failure). |
| `running` | `cancelled` | Workflow cancelled while jobs are in progress. |

Implementations MUST enforce valid state transitions. Any transition not listed above MUST be rejected.

**Rationale**: Enforcing valid transitions prevents impossible states (e.g., a `completed` workflow transitioning to `failed`) that would corrupt workflow tracking and confuse monitoring systems.

### 8.3 State Transition Rules by Primitive

**Chain**:
- Transitions to `running` when step 0 begins execution.
- Transitions to `completed` when the last step completes successfully.
- Transitions to `failed` when any step fails (after retries exhausted).

**Group**:
- Transitions to `running` when any job begins execution.
- Transitions to `completed` when ALL jobs complete successfully.
- Transitions to `failed` when ALL jobs have reached a terminal state AND at least one job failed.

**Batch**:
- Transitions to `running` when any job begins execution.
- Remains in `running` while callbacks are executing.
- Transitions to `completed` when ALL jobs have reached a terminal state AND all triggered callbacks have completed successfully.
- Transitions to `failed` when ALL jobs have reached a terminal state AND a triggered callback fails.

---

## 9. Error Handling and Failure Propagation

### 9.1 Individual Job Failures

Each job within a workflow retains its own retry policy. A job is considered "failed" for workflow purposes only when it has exhausted all retries and transitions to a terminal failure state.

Implementations MUST NOT consider a job "failed" while retries remain. A job in `retryable` state is not a workflow failure.

**Rationale**: Premature failure propagation would cause workflows to fail on transient errors that retries would have resolved. The retry policy is the job's own error handling mechanism and MUST be fully exhausted before the workflow reacts.

### 9.2 Chain Failure Propagation

When a chain step fails:

1. The chain MUST transition to the `failed` state.
2. All subsequent steps MUST transition to the `cancelled` state.
3. The chain MUST NOT enqueue any further steps.
4. The chain's metadata MUST record which step failed and the error details.

**Rationale**: Chain steps have implicit dependencies. Step N+1 typically depends on step N's output. Skipping a failed step and continuing would produce undefined behavior in downstream steps.

### 9.3 Group Failure Propagation

When a group job fails:

1. Other running jobs in the group MUST NOT be affected. They continue executing.
2. The group remains in `running` state until all jobs reach a terminal state.
3. Once all jobs are terminal, if any job failed, the group transitions to `failed`.

**Rationale**: Group jobs are independent by definition. Stopping healthy jobs because a sibling failed wastes completed work. The group waits for all jobs to finish so that partial results are available for inspection.

### 9.4 Batch Failure Propagation

When a batch job fails:

1. Other running jobs MUST NOT be affected (same as group).
2. The batch remains in `running` until all jobs reach a terminal state.
3. Once all jobs are terminal, the appropriate callbacks are fired (see [Section 6.4](#64-execution-semantics)).
4. If a callback itself fails (after retries), the batch transitions to `failed`.

### 9.5 Callback Failure Handling

Callbacks are regular jobs and MUST support retry policies. If a callback fails after exhausting its retries:

1. The batch MUST transition to the `failed` state.
2. The failure MUST be recorded in the batch metadata with the callback type (`on_complete`, `on_success`, or `on_failure`) and error details.

**Rationale**: Callback failures are operationally significant -- they typically represent failed cleanup, alerting, or aggregation. Silent callback failures would mask data integrity issues.

### 9.6 Error Reporting

Workflow-level error information MUST include:

| Field | Type | Description |
|-------|------|-------------|
| `failed_step_index` | integer | (Chain only) Index of the step that failed. |
| `failed_job_ids` | string[] | IDs of jobs that failed. |
| `errors` | object[] | Array of error objects from failed jobs. |

Each error object MUST include at minimum:

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string | The ID of the failed job. |
| `code` | string | Standard OJS error code. |
| `message` | string | Human-readable error description. |
| `attempt` | integer | The attempt number on which the final failure occurred. |

---

## 10. Composition and Nesting

Workflow primitives MAY be nested to create more complex execution patterns. This section defines the rules for composition.

### 10.1 Allowed Compositions

| Outer Primitive | Inner Primitive | Pattern | Description |
|----------------|-----------------|---------|-------------|
| Chain | Group | Fan-out within sequence | A chain step is a group of parallel jobs. The chain advances when the group completes. |
| Chain | Batch | Fan-out with callbacks within sequence | A chain step is a batch. The chain advances when the batch (including callbacks) completes. |
| Group | Chain | Sequential within parallel | A group job is a chain of sequential steps. The group job completes when the chain completes. |
| Group | Batch | Batch within parallel | A group job is a batch. |
| Batch | Chain | Sequential within batch | A batch job is a chain of sequential steps. |
| Batch | Group | Parallel within batch | A batch job is a group. |

### 10.2 Nesting Depth

Implementations SHOULD support at least 3 levels of nesting.

**Rationale**: Three levels covers the most common real-world patterns: a chain containing a group containing chains (e.g., "for each stage in the pipeline, fan out to multiple processors, each of which runs a multi-step sub-pipeline"). Deeper nesting is theoretically valid but practically rare and difficult to debug.

Implementations MAY support deeper nesting and MUST document their maximum nesting depth.

Implementations MUST reject workflows that exceed their supported nesting depth at creation time with a clear error message.

**Rationale for creation-time rejection**: Failing at runtime when a deeply nested step is reached would leave the workflow in a partially completed, unrecoverable state. Validation at creation time prevents wasted work.

### 10.3 Nested Workflow Example

A chain where step 2 is a group (fan-out) and step 3 depends on the group's results:

```json
{
  "type": "chain",
  "id": "wf_019539a4-nested-example",
  "name": "etl-pipeline",
  "steps": [
    {
      "type": "data.extract",
      "args": [{"source": "api.example.com/v2/records"}]
    },
    {
      "type": "group",
      "id": "wf_019539a4-transform-group",
      "name": "parallel-transforms",
      "jobs": [
        { "type": "transform.csv", "args": [] },
        { "type": "transform.parquet", "args": [] },
        { "type": "transform.json", "args": [] }
      ]
    },
    {
      "type": "data.load",
      "args": [{"destination": "warehouse"}]
    }
  ]
}
```

Execution flow:
1. `data.extract` runs and produces raw data.
2. Three transform jobs run in parallel, each receiving the extract result via `parent_results`.
3. `data.load` runs after all three transforms complete, receiving all transform results via `parent_results`.

### 10.4 Nesting State Propagation

When a nested workflow is used as a step (in a chain) or a job (in a group/batch):

1. The nested workflow's state MUST propagate to the outer workflow. If the inner group `completed`, the outer chain step is `completed`. If the inner group `failed`, the outer chain step is `failed`.

2. Implementations MUST track nested workflow state independently. The outer workflow queries the inner workflow's state to determine progress.

**Rationale**: State propagation ensures that the outer workflow's state machine operates correctly without special-casing nested primitives. A chain does not need to know whether its step is a single job or a group -- it only needs to know whether the step completed or failed.

---

## 11. API Operations

This section defines the HTTP API operations for workflow management. These endpoints correspond to the OJS HTTP Protocol Binding (Layer 3) and are served under the `/ojs/v1` base path.

### 11.1 Create Workflow

**`POST /ojs/v1/workflows`**

Creates and starts a workflow. The workflow begins execution immediately upon creation.

Implementations MUST validate the workflow structure before starting execution.

**Rationale**: Validation at creation time (cycle detection, nesting depth, minimum job count) prevents runtime failures that would leave workflows in inconsistent states.

Request:

```json
{
  "type": "chain",
  "name": "order-processing",
  "steps": [
    { "type": "order.validate", "args": [{"order_id": "ord_123"}] },
    { "type": "payment.charge", "args": [] },
    { "type": "inventory.reserve", "args": [] },
    { "type": "notification.send", "args": [] }
  ]
}
```

Response (`201 Created`):

```json
{
  "workflow": {
    "id": "wf_019539a4-0001-7000-8000-000000000001",
    "type": "chain",
    "name": "order-processing",
    "state": "running",
    "steps": [
      {
        "index": 0,
        "type": "order.validate",
        "state": "pending",
        "job_id": "job_019539a4-0001-7000-8000-000000000010"
      },
      {
        "index": 1,
        "type": "payment.charge",
        "state": "waiting",
        "job_id": null
      },
      {
        "index": 2,
        "type": "inventory.reserve",
        "state": "waiting",
        "job_id": null
      },
      {
        "index": 3,
        "type": "notification.send",
        "state": "waiting",
        "job_id": null
      }
    ],
    "metadata": {
      "created_at": "2026-02-12T10:30:00Z",
      "job_count": 4,
      "completed_count": 0,
      "failed_count": 0
    }
  }
}
```

Validation errors MUST return `400 Bad Request` with a structured error:

```json
{
  "error": {
    "code": "invalid_workflow",
    "message": "Workflow validation failed",
    "details": {
      "validation_errors": [
        { "path": "$.steps", "message": "steps array must contain at least one element" }
      ]
    }
  }
}
```

### 11.2 Get Workflow

**`GET /ojs/v1/workflows/:id`**

Returns the current state of a workflow, including per-step/per-job status.

Implementations MUST return the full workflow state including all step/job states and metadata.

**Rationale**: Complete state visibility is essential for monitoring dashboards, debugging, and programmatic workflow management. Partial state responses would force clients to make additional calls to reconstruct the full picture.

Response (`200 OK`):

```json
{
  "workflow": {
    "id": "wf_019539a4-0001-7000-8000-000000000001",
    "type": "chain",
    "name": "order-processing",
    "state": "running",
    "steps": [
      {
        "index": 0,
        "type": "order.validate",
        "state": "completed",
        "job_id": "job_019539a4-0001-7000-8000-000000000010",
        "result": { "valid": true, "total": 99.99 },
        "started_at": "2026-02-12T10:30:01Z",
        "completed_at": "2026-02-12T10:30:02Z"
      },
      {
        "index": 1,
        "type": "payment.charge",
        "state": "active",
        "job_id": "job_019539a4-0001-7000-8000-000000000011",
        "started_at": "2026-02-12T10:30:02.100Z"
      },
      {
        "index": 2,
        "type": "inventory.reserve",
        "state": "waiting",
        "job_id": null
      },
      {
        "index": 3,
        "type": "notification.send",
        "state": "waiting",
        "job_id": null
      }
    ],
    "metadata": {
      "created_at": "2026-02-12T10:30:00Z",
      "started_at": "2026-02-12T10:30:01Z",
      "job_count": 4,
      "completed_count": 1,
      "failed_count": 0
    }
  }
}
```

If the workflow is not found, implementations MUST return `404 Not Found`:

```json
{
  "error": {
    "code": "not_found",
    "message": "Workflow wf_nonexistent not found"
  }
}
```

### 11.3 Cancel Workflow

**`DELETE /ojs/v1/workflows/:id`**

Cancels a workflow. Active jobs SHOULD be allowed to complete (graceful cancellation). Pending and waiting jobs MUST be cancelled.

**Rationale**: Graceful cancellation (letting active jobs finish rather than killing them mid-execution) prevents data corruption and resource leaks. Active jobs may be holding locks, writing to databases, or performing transactions that require clean completion.

Request: No body required.

Response (`200 OK`):

```json
{
  "workflow": {
    "id": "wf_019539a4-0001-7000-8000-000000000001",
    "state": "cancelled",
    "metadata": {
      "cancelled_at": "2026-02-12T10:35:00Z",
      "completed_count": 2,
      "failed_count": 0
    }
  }
}
```

Cancelling a workflow that is already in a terminal state (`completed`, `failed`, `cancelled`) MUST return `409 Conflict`:

```json
{
  "error": {
    "code": "conflict",
    "message": "Workflow wf_019539a4-0001-7000-8000-000000000001 is already in terminal state 'completed'"
  }
}
```

---

## 12. Complete Examples

### 12.1 Chain: Order Processing Pipeline

This example demonstrates a four-step order processing chain where each step depends on the previous step's result.

```json
{
  "type": "chain",
  "id": "wf_019539a4-chain-example",
  "name": "order-processing",
  "steps": [
    {
      "type": "order.validate",
      "args": [{"order_id": "ord_123"}],
      "options": {
        "queue": "orders",
        "retry": { "max_attempts": 3, "backoff": "exponential", "base_delay_ms": 1000 }
      }
    },
    {
      "type": "payment.charge",
      "args": [],
      "options": {
        "queue": "payments",
        "timeout_ms": 30000,
        "retry": { "max_attempts": 5, "backoff": "exponential", "base_delay_ms": 2000 }
      }
    },
    {
      "type": "inventory.reserve",
      "args": [],
      "options": {
        "queue": "inventory",
        "retry": { "max_attempts": 3 }
      }
    },
    {
      "type": "notification.send",
      "args": [],
      "options": {
        "queue": "notifications",
        "retry": { "max_attempts": 2 }
      }
    }
  ]
}
```

**Execution trace**:

1. `order.validate` executes with `args: [{"order_id": "ord_123"}]`.
   Returns: `{ "order_id": "ord_123", "total": 99.99, "currency": "USD", "items": 3 }`

2. `payment.charge` executes with `parent_results: { "0": { "order_id": "ord_123", "total": 99.99, "currency": "USD", "items": 3 } }`.
   Returns: `{ "charge_id": "ch_abc123", "amount": 99.99 }`

3. `inventory.reserve` executes with `parent_results: { "0": { ... }, "1": { "charge_id": "ch_abc123", "amount": 99.99 } }`.
   Returns: `{ "reservation_id": "res_xyz", "items_reserved": 3 }`

4. `notification.send` executes with `parent_results: { "0": { ... }, "1": { ... }, "2": { "reservation_id": "res_xyz", "items_reserved": 3 } }`.
   Returns: `{ "notification_id": "notif_001", "channel": "email" }`

### 12.2 Group: Multi-Format Export

This example demonstrates parallel export of a report in three formats.

```json
{
  "type": "group",
  "id": "wf_019539a4-group-example",
  "name": "multi-format-export",
  "jobs": [
    {
      "type": "export.csv",
      "args": [{"report_id": "rpt_456"}],
      "options": { "queue": "exports", "timeout_ms": 60000 }
    },
    {
      "type": "export.pdf",
      "args": [{"report_id": "rpt_456"}],
      "options": { "queue": "exports", "timeout_ms": 120000 }
    },
    {
      "type": "export.xlsx",
      "args": [{"report_id": "rpt_456"}],
      "options": { "queue": "exports", "timeout_ms": 90000 }
    }
  ]
}
```

**Execution trace** (jobs run concurrently, order is non-deterministic):

- `export.csv` returns: `{ "path": "s3://exports/rpt_456.csv", "size_bytes": 1048576 }`
- `export.pdf` returns: `{ "path": "s3://exports/rpt_456.pdf", "size_bytes": 2097152 }`
- `export.xlsx` returns: `{ "path": "s3://exports/rpt_456.xlsx", "size_bytes": 1572864 }`

Group completes when all three jobs finish. If `export.pdf` fails, the other two continue. The group transitions to `failed` after all jobs finish because one job failed.

### 12.3 Batch: Bulk Email Campaign

This example demonstrates a batch email send with callbacks for success, failure, and completion.

```json
{
  "type": "batch",
  "id": "wf_019539a4-batch-example",
  "name": "bulk-email-send",
  "jobs": [
    { "type": "email.send", "args": ["user1@example.com", "welcome"] },
    { "type": "email.send", "args": ["user2@example.com", "welcome"] },
    { "type": "email.send", "args": ["user3@example.com", "welcome"] }
  ],
  "callbacks": {
    "on_complete": {
      "type": "batch.report",
      "args": [],
      "options": { "queue": "reporting" }
    },
    "on_success": {
      "type": "batch.celebrate",
      "args": [],
      "options": { "queue": "notifications" }
    },
    "on_failure": {
      "type": "batch.alert",
      "args": [],
      "options": { "queue": "alerts", "retry": { "max_attempts": 5 } }
    }
  }
}
```

**Scenario A: All emails succeed**

1. All three `email.send` jobs complete successfully.
2. `on_complete` fires with all three results in `parent_results`.
3. `on_success` fires with all three results in `parent_results`.
4. `on_failure` does NOT fire.
5. Batch transitions to `completed`.

**Scenario B: One email fails**

1. `email.send` for user1 and user2 succeed. `email.send` for user3 fails after retries.
2. `on_complete` fires with all three results (including the failure) in `parent_results`.
3. `on_success` does NOT fire.
4. `on_failure` fires with all three results in `parent_results`.
5. Batch transitions to `completed` (the callbacks themselves succeeded).

### 12.4 Composed: ETL Pipeline with Fan-Out

This example demonstrates nesting a group inside a chain.

```json
{
  "type": "chain",
  "id": "wf_019539a4-composed-example",
  "name": "etl-with-fanout",
  "steps": [
    {
      "type": "data.extract",
      "args": [{"source": "api.example.com/v2/records", "date": "2026-02-12"}]
    },
    {
      "type": "group",
      "id": "wf_019539a4-transform-group",
      "name": "parallel-transforms",
      "jobs": [
        { "type": "transform.normalize", "args": [{"schema": "v2"}] },
        { "type": "transform.enrich", "args": [{"lookup_table": "geo_ip"}] },
        { "type": "transform.deduplicate", "args": [{"key": "email"}] }
      ]
    },
    {
      "type": "data.load",
      "args": [{"destination": "warehouse", "table": "events_2026_02_12"}]
    }
  ]
}
```

**Execution flow**:

1. `data.extract` runs and returns raw data reference.
2. Three transform jobs run in parallel, each receiving the extract result.
3. After all three transforms complete, `data.load` runs with all transform results.

---

## 13. Prior Art

The design of OJS workflow primitives draws from extensive study of existing systems. This section documents the prior art that informed the specification and the lessons learned from each.

### 13.1 Celery Canvas (Python)

Celery defines a set of workflow primitives called the "canvas":
- **chain**: Sequential execution, result passing. OJS chains directly borrow this concept.
- **group**: Parallel execution. OJS groups directly borrow this concept.
- **chord**: A group with a callback that fires when all group tasks complete. OJS batches generalize this with three callback types instead of one.
- **map/starmap**: Apply a task to a list of arguments. Not included in OJS v1.0 as it is syntactic sugar over groups.

**Key lesson**: Celery's chord primitive has well-documented reliability problems. The chord callback can fire multiple times, fire before all tasks complete, or not fire at all, depending on the result backend and concurrency conditions. Celery's own documentation states: "avoid chords as much as possible." This failure mode directly motivates OJS's requirement for exactly-once callback dispatch (Section 6.4, rule 4) and the choice to use atomic operations for callback firing.

**Reference**: Celery documentation, "Canvas: Designing Workflows" -- https://docs.celeryq.dev/en/stable/userguide/canvas.html

### 13.2 BullMQ FlowProducer (JavaScript/TypeScript)

BullMQ's `FlowProducer` allows defining parent-child job relationships as a tree structure:
- A parent job depends on its children (children must complete before the parent runs).
- Supports tree-shaped dependencies but NOT arbitrary DAGs.
- No fan-in: two different parents cannot depend on the same child.
- No diamond dependencies.

**Key lesson**: BullMQ's tree-only limitation demonstrates the implementation complexity of even partial dependency support. Full DAG support would require BullMQ to implement topological sorting, cycle detection, and multi-parent dependency resolution -- features that the maintainers explicitly chose not to build. This validates OJS's decision to limit v1.0 to three simpler primitives rather than attempting DAG support.

**Reference**: BullMQ documentation, "Flows" -- https://docs.bullmq.io/guide/flows

### 13.3 Oban Pro Workflows (Elixir)

Oban Pro (commercial extension of the open-source Oban library) supports full DAG-based workflows:
- `add(:name, Worker.new(args), deps: [:dep1, :dep2])` syntax for declaring dependencies.
- Supports diamond dependencies and fan-in.
- Uses PostgreSQL transactions for atomic state updates.

**Key lesson**: Oban Pro's DAG support works well but is tightly coupled to Elixir's process model and PostgreSQL's transactional guarantees. Porting these semantics to a language-agnostic, backend-agnostic specification is significantly more complex than implementing them in a single-language, single-backend system. This informed the decision to defer DAG support to a future OJS version after the simpler primitives are battle-tested across multiple implementations.

**Reference**: Oban Pro documentation, "Workflows" -- https://oban.pro/docs/pro/Oban.Pro.Workflow.html

### 13.4 Temporal Workflows (Polyglot)

Temporal provides the most powerful workflow orchestration model:
- Arbitrary control flow (loops, conditionals, nested workflows) expressed in general-purpose code.
- Deterministic replay for fault tolerance.
- Activities (individual units of work) are equivalent to OJS jobs.
- Workflows can be infinitely long-running.

**Key lesson**: Temporal's power comes at the cost of significant complexity. Deterministic replay requires developers to understand non-obvious constraints (no random numbers, no system clock, no network I/O outside activities). The operational overhead of a Temporal cluster (multiple services, Cassandra or PostgreSQL, Elasticsearch) is substantial. OJS deliberately positions itself below Temporal in the complexity spectrum: for teams that need simple job orchestration without the overhead of a full workflow engine, chain/group/batch is sufficient. Teams that outgrow OJS workflow primitives should consider Temporal.

**Reference**: Temporal documentation, "Workflows" -- https://docs.temporal.io/workflows

### 13.5 Summary of Prior Art Influence

| System | What OJS borrowed | What OJS avoided |
|--------|-------------------|------------------|
| Celery | Chain, group, callback patterns | Unreliable chord semantics, pickle serialization |
| BullMQ | Immediate-enqueue parallelism | Tree-only dependency model, complexity of FlowProducer |
| Oban Pro | Callback categorization (complete/success/failure) | Backend-specific DAG implementation |
| Temporal | Workflow-as-first-class-concept | Deterministic replay, heavyweight infrastructure |

---

## 14. Future Work

### 14.1 DAG Support (Targeted for v1.1)

Full directed acyclic graph support, where any job can declare dependencies on any set of other jobs, is the primary planned extension for OJS workflows. This would enable patterns that cannot be expressed with chain/group/batch composition:

- **Diamond dependencies**: Job D depends on both Job B and Job C, which both depend on Job A.
- **Complex fan-in**: Multiple independent branches merge into a single aggregation step.
- **Conditional branching**: Different paths through a workflow based on runtime results.

DAG support will be specified in either OJS v1.1 or a companion specification ("OJS Workflows: DAG Extension"). The specification will need to address:

1. **Dependency declaration format**: How jobs declare their dependencies (likely a `depends_on` field referencing step IDs).
2. **Cycle detection**: Implementations MUST reject workflows with circular dependencies at creation time.
3. **Partial completion semantics**: How to handle the case where some branches complete and others fail.
4. **Topological execution ordering**: How implementations determine which jobs can run next.
5. **Fan-in result aggregation**: How results from multiple parent jobs are presented to a child job.

The experience gained from implementing chain, group, and batch across multiple backends and languages will directly inform the DAG specification. Specifically, the atomic callback dispatch requirement (Section 6.4, rule 4) will extend to atomic fan-in detection, and the data passing semantics (Section 7) will generalize to multi-parent result aggregation.

### 14.2 Workflow Retry and Resumption

OJS v1.0 does not define workflow-level retry (re-running a failed workflow from the failed step). This is a common operational need and is planned for a future version. Considerations include:

- Resuming a failed chain from the failed step (skipping already-completed steps).
- Re-running all failed jobs in a group/batch while keeping successful results.
- Idempotency requirements for resumed workflows.

### 14.3 Workflow Timeouts

OJS v1.0 does not define workflow-level timeouts (maximum wall-clock time for the entire workflow). Individual job timeouts apply, but there is no aggregate timeout. This will be considered for a future version.

### 14.4 Conditional Steps

The ability to skip or branch based on a previous step's result (e.g., "if validation fails, run error handling instead of payment") is not supported in v1.0. This is best addressed by the DAG extension (Section 14.1) combined with a conditional evaluation mechanism.

### 14.5 Map/Starmap Primitives

Celery's `map` and `starmap` primitives (apply a single task type to a list of arguments) are syntactic sugar over groups. They may be added as convenience primitives in a future version if demand warrants.

---

## Appendix A: Workflow JSON Schema Summary

The following table summarizes the JSON structure for each primitive. Full JSON Schema definitions are published in the `ojs-json-schema` repository.

### Chain

```json
{
  "type": "chain",
  "id": "<UUIDv7>",
  "name": "<optional string>",
  "steps": [
    {
      "type": "<job type>",
      "args": [<positional arguments>],
      "options": { <optional job options> }
    }
  ]
}
```

### Group

```json
{
  "type": "group",
  "id": "<UUIDv7>",
  "name": "<optional string>",
  "jobs": [
    {
      "type": "<job type>",
      "args": [<positional arguments>],
      "options": { <optional job options> }
    }
  ]
}
```

### Batch

```json
{
  "type": "batch",
  "id": "<UUIDv7>",
  "name": "<optional string>",
  "jobs": [
    {
      "type": "<job type>",
      "args": [<positional arguments>],
      "options": { <optional job options> }
    }
  ],
  "callbacks": {
    "on_complete": { "type": "<job type>", "args": [<args>] },
    "on_success": { "type": "<job type>", "args": [<args>] },
    "on_failure": { "type": "<job type>", "args": [<args>] }
  }
}
```

---

## Appendix B: Workflow Events

Implementations MUST emit the following events for workflow lifecycle tracking. These events supplement the standard OJS event vocabulary defined in the OJS Events Specification.

| Event | Emitted When |
|-------|-------------|
| `workflow.created` | A workflow is created via the API. |
| `workflow.started` | The first job in a workflow begins execution. |
| `workflow.step_completed` | A chain step completes (chain only). |
| `workflow.step_failed` | A chain step fails (chain only). |
| `workflow.job_completed` | A group/batch job completes. |
| `workflow.job_failed` | A group/batch job fails. |
| `workflow.callback_fired` | A batch callback is enqueued. |
| `workflow.completed` | A workflow reaches the `completed` terminal state. |
| `workflow.failed` | A workflow reaches the `failed` terminal state. |
| `workflow.cancelled` | A workflow is cancelled. |

**Rationale for MUST-level event requirements**: Workflow events are essential for monitoring, alerting, and debugging multi-step job execution. Without standardized events, operators would need to correlate individual job events to reconstruct workflow progress, which is error-prone and impractical at scale.

Event payload example:

```json
{
  "event": "workflow.step_completed",
  "workflow_id": "wf_019539a4-chain-example",
  "workflow_type": "chain",
  "workflow_name": "order-processing",
  "timestamp": "2026-02-12T10:30:02Z",
  "data": {
    "step_index": 0,
    "step_type": "order.validate",
    "job_id": "job_019539a4-0001-7000-8000-000000000010",
    "duration_ms": 1234,
    "remaining_steps": 3
  }
}
```

---

*OJS Workflow Primitives Specification v1.0.0-rc.1 -- February 2026*
*https://openjobspec.org*
