# Open Job Spec: Migration Guide

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Migration Guide                            |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-15                                     |
| **Status**  | Release Candidate 1                            |
| **Tier**    | Guidance Document                              |
| **URI**     | `urn:ojs:guide:migration`                      |
| **Requires**| OJS Core Specification (Layer 1)               |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [General Migration Strategy](#2-general-migration-strategy)
3. [Sidekiq (Ruby / Redis)](#3-sidekiq-ruby--redis)
4. [BullMQ (Node.js / Redis)](#4-bullmq-nodejs--redis)
5. [Celery (Python / Multi-broker)](#5-celery-python--multi-broker)
6. [Faktory (Polyglot)](#6-faktory-polyglot)
7. [Temporal (Go / Java / Multi-language)](#7-temporal-go--java--multi-language)
8. [River (Go / PostgreSQL)](#8-river-go--postgresql)
9. [Common Pitfalls](#9-common-pitfalls)
10. [Prior Art](#10-prior-art)

---

## 1. Introduction

Organizations adopting Open Job Spec (OJS) typically have existing job-processing infrastructure built on framework-specific formats. This guide provides concrete, framework-by-framework migration paths that map existing concepts, attributes, and behaviors to their OJS equivalents.

### 1.1 Why Migrate to OJS

| Benefit                | Description                                                                 |
|------------------------|-----------------------------------------------------------------------------|
| **Vendor-neutrality**  | Decouple job definitions from any single broker, language, or runtime.      |
| **Multi-language support** | A single job envelope understood by Ruby, Python, Go, Node.js, Java, and Rust SDKs. |
| **Standardized semantics** | Retry policies, lifecycle states, scheduling, and observability follow one specification rather than framework-specific conventions. |
| **Ecosystem portability** | Move jobs between brokers (Redis, PostgreSQL, RabbitMQ, SQS) without rewriting envelope logic. |
| **Interoperability**   | Producers in one language can enqueue jobs consumed by workers in another language. |

### 1.2 Scope

This document covers six frameworks:

- **Sidekiq** -- the dominant Ruby background-job processor.
- **BullMQ** -- the leading Node.js/TypeScript job queue.
- **Celery** -- the standard Python distributed task queue.
- **Faktory** -- a polyglot job server with its own wire protocol.
- **Temporal** -- a durable execution platform (fundamentally different model).
- **River** -- a Go-native, PostgreSQL-backed job queue.

For each framework, we provide attribute mapping tables, behavioral difference analysis, side-by-side JSON comparisons, and step-by-step migration procedures.

### 1.3 Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 2. General Migration Strategy

Migrating a production job-processing system requires a phased approach. The following four-phase strategy minimizes risk regardless of the source framework.

### 2.1 Phase 1: Dual-Write

During the dual-write phase, producers emit jobs in **both** the legacy format and OJS format simultaneously. Legacy workers continue processing as before; OJS workers are deployed but not yet active.

**Duration**: 1--2 weeks.

**Goals**:
- Validate that the OJS envelope captures all information required by workers.
- Identify edge cases in attribute mapping (e.g., framework-specific metadata that has no OJS equivalent).
- Build confidence that the OJS pipeline can accept production traffic volume.

### 2.2 Phase 2: Shadow Mode

Both the legacy pipeline and the OJS pipeline process every job. Results are compared but only the legacy result is considered authoritative.

**Duration**: 1--4 weeks depending on job volume and criticality.

**Goals**:
- Detect semantic differences (e.g., retry timing, state transitions, error handling).
- Measure OJS pipeline latency against the legacy pipeline.
- Identify jobs that produce different outcomes due to behavioral differences.

**Implementation**: Deploy a shadow comparator that logs discrepancies. Track a `shadow_match_rate` metric; proceed to Phase 3 only when this exceeds 99.9%.

### 2.3 Phase 3: Cutover

Disable legacy producers. All new jobs are enqueued exclusively in OJS format. Legacy workers are shut down after the last legacy job drains.

**Duration**: 1 day to 1 week.

**Goals**:
- Confirm that OJS is the sole job format in production.
- Remove dual-write code paths.
- Update monitoring dashboards and alerting to use OJS-native metrics.

### 2.4 Phase 4: Rollback Plan

Every migration MUST have a documented rollback plan. At minimum:

- **Dual-write rollback**: Re-enable legacy-only producers. This is trivial during Phase 1.
- **Shadow-mode rollback**: Stop OJS workers, continue with legacy workers. No data loss.
- **Post-cutover rollback**: Re-deploy legacy producers and workers. Requires that the legacy broker is still operational. RECOMMENDED: keep the legacy broker running (read-only) for at least 2 weeks after cutover.

---

## 3. Sidekiq (Ruby / Redis)

### 3.1 Attribute Mapping

| Sidekiq Concept       | Sidekiq Field     | OJS Equivalent                  | Notes                                              |
|-----------------------|-------------------|---------------------------------|----------------------------------------------------|
| Job class             | `class`           | `type`                          | OJS uses dot-notation (`email.send`) instead of Ruby class names (`EmailSendWorker`). |
| Arguments             | `args`            | `args`                          | Sidekiq uses a positional array; OJS uses a JSON object (named keys). |
| Job ID                | `jid`             | `id`                            | Both are unique string identifiers.                |
| Queue                 | `queue`           | `queue`                         | Direct mapping.                                    |
| Retry flag/count      | `retry`           | `retry_policy.max_attempts`     | Sidekiq `retry: true` defaults to 25; OJS requires an explicit integer. |
| Created timestamp     | `created_at`      | `created_at`                    | Sidekiq uses Unix float; OJS uses ISO 8601.        |
| Enqueued timestamp    | `enqueued_at`     | `enqueued_at`                   | Sidekiq uses Unix float; OJS uses ISO 8601.        |
| Scheduled time        | `at`              | `scheduled_at`                  | Sidekiq uses Unix float; OJS uses ISO 8601.        |
| Dead state            | `dead`            | `discarded` state               | OJS models this as a lifecycle state, not a flag.  |
| Retry count           | `retry_count`     | `attempt`                       | OJS `attempt` starts at 1 on the first execution.  |

### 3.2 Behavioral Differences

**Retry semantics**: Sidekiq defaults to 25 retry attempts with an exponential backoff formula: `(retry_count ** 4) + 15 + (rand(10) * (retry_count + 1))` seconds. OJS retry policies are explicit and deterministic -- there is no random jitter by default. To replicate Sidekiq's behavior, configure:

```json
{
  "retry_policy": {
    "max_attempts": 25,
    "backoff_strategy": "exponential",
    "backoff_base_seconds": 15,
    "backoff_multiplier": 4
  }
}
```

**Middleware**: Sidekiq uses a Ruby middleware chain (client-side and server-side). OJS defines middleware as a specification-level concept (see `ojs-middleware.md`) that is language-agnostic and transport-agnostic.

**Dead set**: Sidekiq moves jobs to a "dead" set after exhausting retries. OJS transitions jobs to the `discarded` state and emits a `job.discarded` event.

### 3.3 JSON Format Comparison

**Sidekiq format**:

```json
{
  "class": "EmailSendWorker",
  "args": ["user_42", "welcome_template"],
  "jid": "abc123def456",
  "queue": "mailers",
  "retry": 5,
  "created_at": 1700000000.0,
  "enqueued_at": 1700000001.0
}
```

**OJS format**:

```json
{
  "specversion": "1.0.0-rc.1",
  "id": "abc123def456",
  "type": "email.send",
  "queue": "mailers",
  "args": {
    "user_id": "user_42",
    "template": "welcome_template"
  },
  "retry_policy": {
    "max_attempts": 5,
    "backoff_strategy": "exponential"
  },
  "created_at": "2023-11-14T22:13:20Z",
  "enqueued_at": "2023-11-14T22:13:21Z"
}
```

### 3.4 Step-by-Step Migration

1. **Install the OJS Ruby SDK** alongside Sidekiq. Both can coexist in the same application.
2. **Create a type registry** that maps Sidekiq class names to OJS type identifiers (e.g., `EmailSendWorker` → `email.send`).
3. **Convert positional args to named args**. This is the most labor-intensive step. Each worker's `perform(user_id, template)` signature becomes `{ "user_id": "...", "template": "..." }`.
4. **Enable dual-write** by wrapping `SidekiqWorker.perform_async` to also call `OJS::Client.enqueue`.
5. **Deploy OJS workers** in shadow mode. Compare outcomes using the shadow comparator.
6. **Migrate retry configuration**. Convert `sidekiq_options retry: N` to OJS `retry_policy` objects.
7. **Cut over** by replacing `perform_async` calls with `OJS::Client.enqueue` calls.
8. **Remove Sidekiq dependencies** after the rollback window expires.

---

## 4. BullMQ (Node.js / Redis)

### 4.1 Attribute Mapping

| BullMQ Concept        | BullMQ Field          | OJS Equivalent                  | Notes                                              |
|-----------------------|-----------------------|---------------------------------|----------------------------------------------------|
| Job name              | `name`                | `type`                          | BullMQ names are per-queue; OJS types are global.  |
| Job data              | `data`                | `args`                          | Both use JSON objects. Direct mapping.             |
| Job ID                | `jobId`               | `id`                            | BullMQ auto-generates if omitted; OJS requires `id`. |
| Delay                 | `opts.delay`          | `scheduled_at`                  | BullMQ uses millisecond offset; OJS uses absolute ISO 8601 timestamp. |
| Max attempts          | `opts.attempts`       | `retry_policy.max_attempts`     | Direct mapping.                                    |
| Backoff               | `opts.backoff`        | `retry_policy.backoff_strategy` | BullMQ supports `fixed` and `exponential`; OJS supports both plus `linear`. |
| Flow (parent/child)   | Flow API              | OJS workflows                   | See `ojs-workflows.md` for `chain`, `group`, `batch` primitives. |
| Priority              | `opts.priority`       | `priority`                      | BullMQ uses integer priority (lower = higher); OJS uses integer priority (1 = highest). |

### 4.2 Behavioral Differences

**Flows vs. OJS workflows**: BullMQ's Flow API creates parent-child job dependencies where a parent job waits for all children to complete. OJS provides three workflow primitives:

- **`chain`**: Sequential execution (A → B → C).
- **`group`**: Parallel execution (A + B + C, all must complete).
- **`batch`**: Fire-and-forget parallel execution (no aggregation).

BullMQ's parent-child model maps most closely to OJS `group` (parallel children) followed by a `chain` step (the parent).

**Rate limiter**: BullMQ has a built-in queue-level rate limiter (`limiter: { max: 10, duration: 1000 }`). OJS defines rate limiting in `ojs-rate-limiting.md` with richer options (sliding window, token bucket, concurrency limiters).

**Events**: BullMQ emits events via Redis Pub/Sub (`completed`, `failed`, `progress`). OJS defines a standardized event schema in `ojs-events.md` that is transport-agnostic.

### 4.3 JSON Format Comparison

**BullMQ format** (as stored in Redis):

```json
{
  "name": "payment.process",
  "data": {
    "order_id": "ord_9f8e7d",
    "amount_cents": 4999,
    "currency": "USD"
  },
  "opts": {
    "jobId": "pay_abc123",
    "attempts": 3,
    "backoff": {
      "type": "exponential",
      "delay": 1000
    },
    "delay": 0
  }
}
```

**OJS format**:

```json
{
  "specversion": "1.0.0-rc.1",
  "id": "pay_abc123",
  "type": "payment.process",
  "queue": "payments",
  "args": {
    "order_id": "ord_9f8e7d",
    "amount_cents": 4999,
    "currency": "USD"
  },
  "retry_policy": {
    "max_attempts": 3,
    "backoff_strategy": "exponential",
    "backoff_base_seconds": 1
  },
  "created_at": "2023-11-14T22:13:20Z"
}
```

### 4.4 Step-by-Step Migration

1. **Install the OJS Node.js SDK** alongside BullMQ. Both can coexist.
2. **Map job names to OJS types**. BullMQ names are typically already in dot-notation; verify consistency.
3. **Convert `opts.delay` to `scheduled_at`**. Replace relative offsets with absolute timestamps: `new Date(Date.now() + opts.delay).toISOString()`.
4. **Map backoff configuration**. Convert `{ type: "exponential", delay: 1000 }` to `{ "backoff_strategy": "exponential", "backoff_base_seconds": 1 }`.
5. **Migrate Flows to OJS workflows**. Identify parent-child relationships and express them as `chain` or `group` primitives.
6. **Enable dual-write** in the producer layer.
7. **Deploy OJS workers** in shadow mode. Use BullMQ's event listeners to compare outcomes.
8. **Migrate rate-limiter configuration** to OJS rate-limiting policies.
9. **Cut over** and remove BullMQ dependencies.

---

## 5. Celery (Python / Multi-broker)

### 5.1 Attribute Mapping

| Celery Concept        | Celery Field          | OJS Equivalent                  | Notes                                              |
|-----------------------|-----------------------|---------------------------------|----------------------------------------------------|
| Task name             | `task`                | `type`                          | Celery uses Python dotted path (`myapp.tasks.send_email`); OJS uses short dot-notation (`email.send`). |
| Positional arguments  | `args`                | `args`                          | Celery uses a tuple/list; OJS uses a JSON object.  |
| Keyword arguments     | `kwargs`              | `args`                          | OJS merges `args` and `kwargs` into a single `args` object. |
| Task ID               | `task_id` / `id`      | `id`                            | Direct mapping.                                    |
| Queue                 | `queue`               | `queue`                         | Direct mapping.                                    |
| ETA                   | `eta`                 | `scheduled_at`                  | Celery `eta` is an ISO 8601 datetime; direct mapping. |
| Countdown             | `countdown`           | `scheduled_at`                  | Celery `countdown` is seconds from now; convert to absolute timestamp. |
| Max retries           | `max_retries`         | `retry_policy.max_attempts`     | Celery default is 3; OJS has no implicit default.  |
| Canvas: chain         | `chain()`             | OJS `chain` workflow            | Conceptually equivalent.                           |
| Canvas: group         | `group()`             | OJS `group` workflow            | Conceptually equivalent.                           |
| Canvas: chord         | `chord(group, callback)` | OJS `group` + `chain`       | OJS does not have a first-class chord; model as group followed by chain step. |

### 5.2 Behavioral Differences

**Canvas vs. OJS workflow primitives**: Celery's Canvas provides `chain`, `group`, `chord`, `starmap`, and `chunks`. OJS provides `chain`, `group`, and `batch`. The mapping:

| Celery Canvas | OJS Equivalent | Notes |
|---------------|----------------|-------|
| `chain(a, b, c)` | `chain: [a, b, c]` | Direct mapping. |
| `group(a, b, c)` | `group: [a, b, c]` | Direct mapping. |
| `chord(group(a, b), c)` | `chain: [group: [a, b], c]` | Nest a `group` inside a `chain`. |
| `starmap(task, [(1,), (2,)])` | Multiple individual jobs | No direct equivalent; enqueue N jobs. |
| `chunks(task, items, n)` | Multiple individual jobs | No direct equivalent; partition and enqueue. |

**Result backend**: Celery stores task results in a configurable result backend (Redis, database, AMQP). OJS does not define a result storage mechanism. Instead, OJS emits `job.completed` and `job.failed` events (see `ojs-events.md`) that consumers can use to capture results.

**Celery Beat**: Celery Beat is a scheduler that dispatches tasks on a cron-like schedule. OJS defines cron jobs in `ojs-cron.md` with equivalent semantics.

### 5.3 JSON Format Comparison

**Celery format** (AMQP message body):

```json
{
  "task": "myapp.tasks.generate_report",
  "id": "rpt_f47ac10b",
  "args": ["monthly", "2023-11"],
  "kwargs": {
    "format": "pdf",
    "recipients": ["finance@example.com"]
  },
  "eta": "2023-11-15T06:00:00Z",
  "retries": 0,
  "timelimit": [300, 600]
}
```

**OJS format**:

```json
{
  "specversion": "1.0.0-rc.1",
  "id": "rpt_f47ac10b",
  "type": "report.generate",
  "queue": "reports",
  "args": {
    "period": "monthly",
    "month": "2023-11",
    "format": "pdf",
    "recipients": ["finance@example.com"]
  },
  "retry_policy": {
    "max_attempts": 3,
    "backoff_strategy": "exponential"
  },
  "scheduled_at": "2023-11-15T06:00:00Z",
  "created_at": "2023-11-14T22:13:20Z"
}
```

### 5.4 Step-by-Step Migration

1. **Install the OJS Python SDK** alongside Celery.
2. **Create a type registry** mapping Celery task paths to OJS types (e.g., `myapp.tasks.generate_report` → `report.generate`).
3. **Merge `args` and `kwargs`**. Convert positional arguments to named keys: `args=["monthly", "2023-11"], kwargs={"format": "pdf"}` becomes `{"period": "monthly", "month": "2023-11", "format": "pdf"}`.
4. **Convert `countdown` to `scheduled_at`**. Replace `task.apply_async(countdown=60)` with `ojs.enqueue(scheduled_at=now + timedelta(seconds=60))`.
5. **Migrate Canvas workflows**. Map `chain()`, `group()`, and `chord()` to OJS workflow primitives.
6. **Migrate Celery Beat schedules** to OJS cron job definitions.
7. **Enable dual-write** by decorating existing Celery tasks to also enqueue via OJS.
8. **Deploy OJS workers** in shadow mode.
9. **Migrate result backend consumers** to listen for OJS events (`job.completed`, `job.failed`).
10. **Cut over** and remove Celery dependencies.

---

## 6. Faktory (Polyglot)

### 6.1 Attribute Mapping

| Faktory Concept       | Faktory Field         | OJS Equivalent                  | Notes                                              |
|-----------------------|-----------------------|---------------------------------|----------------------------------------------------|
| Job type              | `jobtype`             | `type`                          | Direct mapping. Faktory already uses short names.  |
| Arguments             | `args`                | `args`                          | Faktory uses a positional array; OJS uses a JSON object. |
| Job ID                | `jid`                 | `id`                            | Direct mapping.                                    |
| Queue                 | `queue`               | `queue`                         | Direct mapping.                                    |
| Scheduled time        | `at`                  | `scheduled_at`                  | Faktory uses RFC 3339; OJS uses ISO 8601 (compatible). |
| Retry count           | `retry`               | `retry_policy.max_attempts`     | Faktory default is 25; OJS requires explicit value. |
| Reservation timeout   | `reserve_for`         | visibility timeout              | OJS does not define a top-level field; model as a queue-level configuration or middleware concern. |
| Uniqueness window     | `unique_for`          | `unique_policy.ttl`             | See `ojs-unique-jobs.md`.                          |
| Uniqueness scope      | `unique_until`        | `unique_policy.scope`           | Faktory supports `start` and `success`; OJS supports `enqueue`, `start`, `complete`. |

### 6.2 Behavioral Differences

**Worker protocol**: Faktory defines its own text-based worker protocol (RESP-like) with `HELLO`, `FETCH`, `ACK`, `FAIL` commands. OJS defines a worker protocol in `ojs-worker-protocol.md` that is transport-agnostic and supports both HTTP and gRPC bindings. Migrating from Faktory requires replacing the Faktory client library with an OJS SDK.

**Batches**: Faktory Enterprise provides a batch primitive that groups jobs and fires callbacks on `success` and `complete`. OJS provides a `batch` workflow primitive (see `ojs-workflows.md`) with similar semantics. The key difference: Faktory batches are a server-side feature; OJS batches are defined in the job envelope and can be implemented by any conformant runtime.

**Uniqueness**: Faktory's `unique_for` and `unique_until` fields map closely to OJS's `unique_policy` (see `ojs-unique-jobs.md`). The scoping semantics differ slightly: Faktory's `unique_until: start` means the lock is released when a worker fetches the job; OJS's `scope: start` has equivalent behavior.

### 6.3 JSON Format Comparison

**Faktory format**:

```json
{
  "jid": "eml_a1b2c3d4",
  "jobtype": "email.send",
  "args": ["user_42", "password_reset"],
  "queue": "critical",
  "retry": 5,
  "at": "2023-11-15T08:00:00Z",
  "reserve_for": 300,
  "unique_for": 3600,
  "unique_until": "start"
}
```

**OJS format**:

```json
{
  "specversion": "1.0.0-rc.1",
  "id": "eml_a1b2c3d4",
  "type": "email.send",
  "queue": "critical",
  "args": {
    "user_id": "user_42",
    "template": "password_reset"
  },
  "retry_policy": {
    "max_attempts": 5,
    "backoff_strategy": "exponential"
  },
  "scheduled_at": "2023-11-15T08:00:00Z",
  "unique_policy": {
    "ttl": 3600,
    "scope": "start"
  },
  "created_at": "2023-11-14T22:13:20Z"
}
```

### 6.4 Step-by-Step Migration

1. **Install the OJS SDK** for your worker language(s). Faktory's polyglot nature means you may have workers in multiple languages -- install the corresponding OJS SDK for each.
2. **Map `jobtype` to `type`**. Faktory already uses short names, so this mapping is typically 1:1.
3. **Convert positional `args` to named `args`**. As with Sidekiq, this requires updating both producers and workers.
4. **Migrate uniqueness configuration**. Convert `unique_for` / `unique_until` to OJS `unique_policy`.
5. **Map `reserve_for` to queue-level configuration**. OJS does not have a per-job visibility timeout; configure this at the queue level or via middleware.
6. **Migrate batch jobs** to OJS `batch` workflow primitives.
7. **Enable dual-write** in producers.
8. **Deploy OJS workers**. Replace Faktory `FETCH`/`ACK`/`FAIL` protocol calls with OJS worker protocol calls.
9. **Cut over** and decommission the Faktory server.

---

## 7. Temporal (Go / Java / Multi-language)

### 7.1 Concept Mapping

Temporal is a **durable execution** platform, not a job queue. The conceptual models are fundamentally different. This section helps teams understand what maps cleanly, what does not, and when to keep Temporal alongside OJS.

| Temporal Concept      | OJS Equivalent                  | Mapping Quality | Notes                                              |
|-----------------------|---------------------------------|-----------------|----------------------------------------------------|
| Activity              | `job`                           | ✅ Clean        | An Activity is a unit of work; so is an OJS job.   |
| Task Queue            | `queue`                         | ✅ Clean        | Both route work to specific worker pools.          |
| Retry Policy          | `retry_policy`                  | ✅ Clean        | Temporal's retry policy fields map directly to OJS retry policy fields. |
| Schedule              | `cron_job` (see `ojs-cron.md`)  | ✅ Clean        | Temporal Schedules map to OJS cron jobs.           |
| Workflow              | *Not directly mapped*           | ❌ No mapping   | Temporal Workflows are durable, stateful, long-running functions. OJS does not provide equivalent functionality. |
| Signal                | *Not directly mapped*           | ❌ No mapping   | OJS jobs are fire-and-forget; they cannot receive external signals during execution. |
| Query                 | *Not directly mapped*           | ❌ No mapping   | OJS jobs do not expose queryable state during execution. |
| Child Workflow        | OJS `chain` / `group`           | ⚠️ Partial     | Simple parent-child patterns map; complex orchestration does not. |
| Saga / Compensation   | *Not directly mapped*           | ❌ No mapping   | OJS does not define compensation logic.            |
| Continue-As-New       | *Not directly mapped*           | ❌ No mapping   | OJS has no concept of workflow history truncation.  |

### 7.2 When to Use Temporal vs. OJS

| Use Case                              | Recommended         | Rationale                                       |
|---------------------------------------|---------------------|-------------------------------------------------|
| Send a welcome email                  | **OJS**             | Simple, stateless, fire-and-forget.             |
| Process a payment                     | **OJS**             | Idempotent operation with retry logic.          |
| Generate a report                     | **OJS**             | Background task with no long-running state.     |
| Multi-step order fulfillment          | **Temporal**        | Requires durable state across steps spanning hours/days. |
| Saga with compensation                | **Temporal**        | Requires automatic rollback of prior steps on failure. |
| Human-in-the-loop approval            | **Temporal**        | Requires pausing execution and waiting for external signal. |
| Long-running data pipeline            | **Temporal**        | Requires checkpointing and continue-as-new.    |
| Scheduled nightly batch               | **Either**          | OJS cron for simple dispatch; Temporal Schedule for complex orchestration. |

### 7.3 What Maps Cleanly vs. What Does Not

**Maps cleanly**: Any Temporal Activity that is stateless, idempotent, and short-lived (< 30 minutes) can be modeled as an OJS job. Extract the Activity function body, define an OJS `type`, and enqueue it.

**Does not map**: Any Temporal Workflow that relies on durable execution guarantees -- Signals, Queries, Continue-As-New, Saga patterns, or Workflow-level timers -- has no OJS equivalent. Do not attempt to migrate these to OJS.

### 7.4 Hybrid Architecture Guidance

Many organizations SHOULD run Temporal and OJS side-by-side:

- **OJS** handles high-volume, simple background jobs (emails, webhooks, notifications, data sync).
- **Temporal** handles complex orchestration (order fulfillment, payment sagas, multi-step pipelines).

In this architecture, a Temporal Workflow can enqueue OJS jobs as a side effect of an Activity, and OJS job completion events can trigger Temporal Signals. This avoids forcing either system into use cases it was not designed for.

---

## 8. River (Go / PostgreSQL)

### 8.1 Attribute Mapping

| River Concept         | River Field           | OJS Equivalent                  | Notes                                              |
|-----------------------|-----------------------|---------------------------------|----------------------------------------------------|
| Job kind              | `Kind`                | `type`                          | River uses Go struct names; OJS uses dot-notation. |
| Arguments             | `Args` (Go struct)    | `args`                          | River marshals a Go struct to JSON; OJS uses a JSON object directly. |
| Job ID                | `ID`                  | `id`                            | River uses `int64`; OJS uses a string.             |
| Queue                 | `Queue`               | `queue`                         | Direct mapping. River defaults to `"default"`.     |
| Scheduled time        | `ScheduledAt`         | `scheduled_at`                  | River uses `time.Time`; OJS uses ISO 8601 string.  |
| Max attempts          | `MaxAttempts`         | `retry_policy.max_attempts`     | River default is 25; OJS requires explicit value.  |
| Unique options        | `UniqueOpts`          | `unique_policy`                 | See mapping details below.                         |
| Priority              | `Priority`            | `priority`                      | River uses 1--4 (1 = highest); OJS uses integer priority (1 = highest). Direct mapping. |
| Tags                  | `Tags`                | `tags`                          | Both support string arrays.                        |

**Uniqueness mapping detail**:

| River `UniqueOpts`       | OJS `unique_policy`     | Notes                              |
|--------------------------|-------------------------|------------------------------------|
| `ByArgs()`               | `"on": ["args"]`        | Scope uniqueness to job arguments. |
| `ByQueue()`              | `"on": ["queue"]`       | Scope uniqueness to queue.         |
| `ByPeriod(1 * time.Hour)`| `"ttl": 3600`           | Time-based uniqueness window.      |
| `ByState([]...)`         | `"scope": "enqueue"`    | River supports state-based scoping; OJS uses lifecycle scoping. |

### 8.2 Behavioral Differences

**Go-native args vs. OJS JSON args**: River defines job arguments as Go structs that implement the `river.JobArgs` interface:

```go
type EmailSendArgs struct {
    UserID   string `json:"user_id"`
    Template string `json:"template"`
}

func (EmailSendArgs) Kind() string { return "email.send" }
```

In OJS, the same job is a plain JSON object. The Go SDK wraps this, but the on-the-wire format is always JSON:

```json
{
  "args": {
    "user_id": "user_42",
    "template": "welcome"
  }
}
```

**Periodic jobs**: River provides `river.PeriodicJob` for recurring work, using cron expressions. OJS defines cron jobs in `ojs-cron.md` with equivalent cron expression support.

**Snooze**: River allows workers to "snooze" a job -- reschedule it for a later time from within the worker. OJS supports this via a `reschedule` operation that sets a new `scheduled_at` value.

### 8.3 JSON Format Comparison

**River format** (as stored in PostgreSQL `river_job` table):

```json
{
  "id": 12345,
  "kind": "payment.process",
  "queue": "payments",
  "args": {
    "order_id": "ord_9f8e7d",
    "amount_cents": 4999,
    "currency": "USD"
  },
  "state": "available",
  "max_attempts": 5,
  "scheduled_at": "2023-11-15T08:00:00Z",
  "created_at": "2023-11-14T22:13:20Z",
  "tags": ["high-value"]
}
```

**OJS format**:

```json
{
  "specversion": "1.0.0-rc.1",
  "id": "pay_12345",
  "type": "payment.process",
  "queue": "payments",
  "args": {
    "order_id": "ord_9f8e7d",
    "amount_cents": 4999,
    "currency": "USD"
  },
  "retry_policy": {
    "max_attempts": 5,
    "backoff_strategy": "exponential"
  },
  "scheduled_at": "2023-11-15T08:00:00Z",
  "created_at": "2023-11-14T22:13:20Z",
  "tags": ["high-value"]
}
```

### 8.4 Step-by-Step Migration

1. **Install the OJS Go SDK** alongside River. Both use PostgreSQL; they can share the same database.
2. **Map `Kind()` to OJS `type`**. River already uses short names (e.g., `email.send`); verify consistency.
3. **Migrate `JobArgs` structs**. Ensure the JSON serialization of River args matches the OJS `args` schema you define.
4. **Convert `UniqueOpts` to `unique_policy`**. Map `ByArgs`, `ByQueue`, and `ByPeriod` to OJS equivalents.
5. **Migrate periodic jobs** to OJS cron job definitions.
6. **Enable dual-write** by inserting into both `river_job` and the OJS job table.
7. **Deploy OJS workers** in shadow mode. Compare results by querying both tables.
8. **Migrate snooze logic**. Replace `river.JobSnooze(duration)` with OJS `reschedule` operation.
9. **Cut over** and drop the `river_job` table after the rollback window.

---

## 9. Common Pitfalls

### 9.1 Semantic Differences That Cause Bugs

| Pitfall                               | Frameworks Affected       | Description                                                    | Mitigation                                      |
|---------------------------------------|---------------------------|----------------------------------------------------------------|-------------------------------------------------|
| Positional vs. named arguments        | Sidekiq, Celery, Faktory  | Positional arrays are order-dependent; named objects are not. Swapping argument order silently produces wrong behavior. | Write explicit mapping functions with unit tests. |
| Unix timestamp vs. ISO 8601           | Sidekiq                   | Mixing float timestamps with ISO strings causes scheduling errors. | Centralize timestamp conversion in one utility function. |
| Implicit retry defaults               | Sidekiq (25), Faktory (25), River (25) | Frameworks with high default retry counts will retry far more than expected if the OJS policy is not explicitly configured. | Always set `retry_policy.max_attempts` explicitly. |
| Retry attempt numbering               | All                       | Some frameworks count retries from 0, others from 1. OJS `attempt` starts at 1 (first execution). | Add integration tests that verify retry count at each attempt. |
| Result storage expectations            | Celery                    | Celery code may call `result.get()` to retrieve task output. OJS does not store results; use events instead. | Migrate result consumers to event listeners before cutting over. |
| Queue name conventions                | All                       | Sidekiq uses `"mailers"`, BullMQ uses `"bull:payments"`, Celery uses `"celery"` as default. OJS has no default queue name. | Define an explicit queue naming convention and validate during dual-write. |
| Uniqueness scope semantics            | Faktory, River            | `unique_until: start` (Faktory) vs. `ByState` (River) vs. OJS `scope` have subtly different lock-release timing. | Test uniqueness behavior explicitly with concurrent enqueue tests. |

### 9.2 Data Migration Considerations

**In-flight jobs**: During migration, jobs already enqueued in the legacy system MUST be allowed to drain. Do not attempt to convert in-flight jobs from the legacy format to OJS mid-execution.

**Historical data**: If your system retains completed/failed job records for auditing, decide whether to:
- **Migrate historical records** to OJS format (expensive, but enables unified querying).
- **Freeze legacy data** in its original format and only write new records in OJS format (simpler, but requires querying two systems during the transition).
- **Archive and ignore** historical records if they are not needed for ongoing operations.

**Idempotency keys**: If the legacy system uses job IDs as idempotency keys (e.g., to prevent double-processing), ensure that the OJS `id` values are globally unique and do not collide with legacy IDs. RECOMMENDED: use a prefix or namespace (e.g., `ojs_` prefix) during the dual-write phase.

### 9.3 Testing Strategy During Migration

**Unit tests**: For each job type, write a test that:
1. Creates a job in the legacy format.
2. Converts it to OJS format using the migration mapping.
3. Asserts that all fields are correctly mapped.

**Integration tests**: Deploy both legacy and OJS workers against a staging environment. Enqueue identical workloads and compare:
- Execution outcomes (success/failure).
- Retry behavior (number of attempts, timing).
- Event emissions (correct event types and payloads).
- State transitions (matches expected lifecycle).

**Canary testing**: Route a small percentage (1--5%) of production traffic to OJS workers before full cutover. Monitor error rates, latency percentiles, and retry counts.

**Rollback tests**: Practice the rollback procedure at least once in staging before attempting production cutover. Verify that:
- Legacy workers can resume processing after OJS workers are stopped.
- No jobs are lost or double-processed during rollback.
- Monitoring and alerting correctly reflects the rollback state.

---

## 10. Prior Art

This migration guide draws inspiration from established migration practices in the software industry:

### 10.1 Stripe API Versioning

Stripe's API versioning strategy demonstrates how to evolve a widely-used API without breaking existing consumers. Key lessons applied to OJS migration:

- **Pin a version**: Stripe allows clients to pin to a specific API version. Similarly, OJS uses `specversion` in the job envelope so that producers and consumers can negotiate format compatibility.
- **Rolling upgrades**: Stripe maintains backward compatibility within a version. OJS migration supports dual-write phases where both old and new formats coexist.
- **Changelog-driven migration**: Stripe publishes detailed changelogs for each version. OJS migration guides enumerate every attribute mapping change.

### 10.2 Rails Upgrade Guides

The Ruby on Rails framework publishes comprehensive upgrade guides for each major version (e.g., "Upgrading from Rails 6.1 to 7.0"). Key lessons:

- **Deprecation warnings first**: Rails deprecates features one version before removing them. The OJS dual-write phase serves the same purpose -- it gives teams time to validate the new format before the old one is removed.
- **Automated tooling**: Rails provides `rails app:update` to automate configuration changes. OJS SDKs SHOULD provide migration utilities (e.g., `ojs migrate --from sidekiq`) that automate attribute mapping.
- **Step-by-step procedures**: Rails upgrade guides are numbered, sequential, and testable. This document follows the same structure.

### 10.3 Python 2 → 3 Migration

The Python 2 to Python 3 migration is a cautionary tale about what happens when migration is too difficult or poorly supported. Key lessons:

- **Provide a bridge**: Python provided `2to3` and the `__future__` module. OJS provides the dual-write phase and shadow mode as the migration bridge.
- **Make migration incremental**: Python 3 migration failed when teams attempted a "big bang" cutover. OJS migration explicitly discourages big-bang approaches in favor of phased rollout.
- **Maintain backward compatibility during transition**: Python's `six` library allowed code to run on both versions. OJS dual-write serves the same purpose -- both formats are valid simultaneously.
- **Set a deadline**: Python 2 end-of-life (2020-01-01) created urgency. Organizations adopting OJS SHOULD set an internal deadline for completing migration to prevent indefinite dual-write overhead.
