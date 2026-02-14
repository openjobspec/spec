# Open Job Spec: Job Priority

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Job Priority Specification                 |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-15                                     |
| **Status**  | Release Candidate                              |
| **Tier**    | Official Extension                             |
| **URI**     | `urn:ojs:ext:priority`                         |
| **Requires**| OJS Core Specification (Layer 1)               |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Design Principles](#4-design-principles)
5. [Priority Model](#5-priority-model)
   - 5.1 [Priority Levels](#51-priority-levels)
   - 5.2 [Default Priority](#52-default-priority)
   - 5.3 [Priority Ordering](#53-priority-ordering)
6. [Priority Field](#6-priority-field)
7. [Queue Consumption Strategies](#7-queue-consumption-strategies)
   - 7.1 [Strict Priority](#71-strict-priority)
   - 7.2 [Weighted Priority](#72-weighted-priority)
   - 7.3 [Strategy Configuration](#73-strategy-configuration)
8. [Dynamic Priority Adjustment](#8-dynamic-priority-adjustment)
9. [Interaction with Other Extensions](#9-interaction-with-other-extensions)
   - 9.1 [Rate Limiting](#91-rate-limiting)
   - 9.2 [Workflows](#92-workflows)
   - 9.3 [Unique Jobs](#93-unique-jobs)
   - 9.4 [Scheduling](#94-scheduling)
10. [HTTP Binding](#10-http-binding)
11. [Observability](#11-observability)
12. [Conformance Requirements](#12-conformance-requirements)
13. [Prior Art](#13-prior-art)
14. [Examples](#14-examples)

---

## 1. Introduction

Job priority is the most fundamental scheduling control in background job processing. Every production system eventually requires the ability to process urgent jobs before less important ones. Without priority support, a flood of low-importance jobs can delay time-sensitive work -- a billing reconciliation job should not wait behind ten thousand analytics aggregation jobs.

Priority is so universal that every major job processing system supports it: Sidekiq provides strict and weighted queue ordering, BullMQ offers integer priority levels from 0 to 2,097,152, Celery leverages AMQP's native message priority, Faktory supports integer priorities, and even systems that initially omitted priority (like early versions of River and Oban) added it in response to user demand.

This specification defines a priority model for OJS that is simple enough for basic use cases (urgent vs. normal vs. low) while expressive enough for fine-grained ordering when needed.

### 1.1 Scope

This specification defines:

- An integer-based priority model for individual jobs.
- Queue consumption strategies for multi-queue priority ordering.
- Dynamic priority adjustment for in-flight priority changes.
- Interaction semantics with rate limiting, workflows, and other extensions.
- HTTP binding for priority-related operations.

This specification does **not** define:

- Priority inheritance or priority inversion protocols (these are OS-level concepts that do not apply to job queues).
- Preemption of active jobs (a higher-priority job does not cancel or suspend a running lower-priority job).
- Starvation prevention algorithms (implementations MAY add aging or boosting, but the mechanism is not standardized).

### 1.2 Companion Specifications

| Document | Layer | Description |
|----------|-------|-------------|
| **ojs-core.md** | 1 -- Core | Job envelope, lifecycle, required attributes |
| **ojs-rate-limiting.md** | Extension | Rate limiting interacts with priority ordering |
| **ojs-fair-scheduling.md** | Extension | Fair scheduling provides starvation prevention |

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

Every MUST requirement includes a rationale explaining why the requirement is mandatory.

---

## 3. Terminology

| Term                  | Definition                                                                                         |
|-----------------------|----------------------------------------------------------------------------------------------------|
| priority              | An integer value that determines the relative importance of a job within a queue. Lower values indicate higher priority. |
| priority level        | A specific integer value assigned to a job (e.g., 0, 1, 2, 3).                                   |
| strict priority       | A queue consumption strategy where all jobs of a higher priority level are processed before any jobs of a lower priority level. |
| weighted priority     | A queue consumption strategy where jobs from different priority levels are consumed proportionally to assigned weights. |
| starvation            | A condition where low-priority jobs are never executed because higher-priority jobs continuously arrive. |
| priority aging        | An optional technique where a job's effective priority increases the longer it waits, reducing starvation risk. |
| default priority      | The priority assigned to jobs that do not specify an explicit priority value.                      |

---

## 4. Design Principles

1. **Lower is higher.** Priority 0 is the highest priority. This convention aligns with operating system scheduling (Unix nice values, POSIX thread priorities), AMQP message priority semantics (where 0 is the lowest but higher integers mean higher priority is an AMQP-specific inversion), and is the convention used by BullMQ, Faktory, and most modern job systems. OJS adopts lower-is-higher because it produces intuitive code: `priority: 1` reads as "first priority."

2. **Opt-in complexity.** For most applications, three priority levels (high, normal, low) are sufficient. The spec supports fine-grained integer priorities for advanced use cases, but the default behavior works well with coarse levels.

3. **Non-preemptive.** A newly enqueued high-priority job does not interrupt or cancel a running lower-priority job. Preemption introduces complexity (partial work, resource cleanup, job resumption) that is inappropriate for most background job workloads.

4. **FIFO within priority.** Jobs with the same priority level are processed in FIFO order. This preserves the causal ordering that many applications depend on while still allowing priority-based reordering across levels.

5. **Backend-enforced.** Priority ordering is enforced by the backend during job dispatch (FETCH), not by workers or SDKs. This ensures consistent behavior regardless of how many workers are polling.

---

## 5. Priority Model

### 5.1 Priority Levels

OJS uses a non-negative integer priority model where **lower values indicate higher priority**.

| Priority Value | Conventional Name | Use Case                                |
|----------------|-------------------|-----------------------------------------|
| 0              | Critical          | System-critical jobs, incident response |
| 1              | High              | User-facing, time-sensitive operations  |
| 2              | Normal (default)  | Standard background processing          |
| 3              | Low               | Maintenance, analytics, batch work      |
| 4              | Bulk              | Large-scale imports, migrations         |

These conventional names are informational only. Implementations MUST support integer values and MUST NOT restrict priority to a fixed set of named levels.

**Rationale**: Named levels are convenient for documentation but insufficient for real-world use. Production systems frequently need to express "higher priority than normal but lower than critical" -- which requires integer granularity, not named buckets.

The maximum priority value MUST be at least 255.

**Rationale**: 256 levels (0–255) provide enough granularity for any practical use case while fitting in a single unsigned byte. BullMQ supports up to 2,097,152 levels; AMQP supports 0–255. The 0–255 minimum ensures implementations have enough range without imposing excessive storage or sorting overhead.

### 5.2 Default Priority

When a job is enqueued without an explicit `priority` field, the backend MUST assign a default priority of `2`.

**Rationale**: A default of `2` (rather than `0`) leaves room for higher-priority jobs to jump ahead without requiring priority to be set on every job. BullMQ defaults to `0` (highest priority), which means prioritized jobs must always be explicitly lower -- this inverts the natural expectation that "normal jobs don't need configuration." A default of `2` with conventional levels 0–4 places normal work in the middle of the range.

### 5.3 Priority Ordering

Within a single queue, the backend MUST order available jobs by priority (ascending) first, then by enqueue time (ascending, FIFO) second when priorities are equal.

**Rationale**: Priority-then-FIFO ordering is the universally expected behavior. Every system studied (BullMQ, Sidekiq, Celery, Faktory, AMQP) uses this ordering. Violating it would surprise every user who has worked with any previous job system.

When a worker calls FETCH, the backend MUST return the highest-priority (lowest integer value) available job that satisfies all other constraints (rate limits, uniqueness locks, etc.).

**Rationale**: FETCH is the single dispatch point in the OJS architecture. Priority ordering at this point ensures that all workers, regardless of how many are polling, see the same priority-ordered view of the queue.

---

## 6. Priority Field

### 6.1 Field Definition

```json
{
  "type": "email.send",
  "args": ["user@example.com", "welcome"],
  "priority": 1
}
```

| Field      | Type    | Required | Default | Description                                              |
|------------|---------|----------|---------|----------------------------------------------------------|
| `priority` | integer | No       | `2`     | Job priority. Lower values indicate higher priority. MUST be >= 0. |

The `priority` field is a top-level attribute on the job envelope, not nested within an options object.

**Rationale**: Priority is fundamental enough to warrant a top-level attribute (like `queue` and `type`). Nesting it in an options object would increase verbosity for the most commonly used scheduling control.

### 6.2 Validation

Implementations MUST reject jobs with a `priority` value less than `0` with an error response.

**Rationale**: Negative priorities would create ambiguity about whether -1 is higher or lower than 0. Restricting to non-negative integers keeps the model simple and unambiguous.

Implementations SHOULD reject jobs with a `priority` value greater than the implementation's maximum supported level with an error response. The error MUST indicate the maximum supported priority value.

---

## 7. Queue Consumption Strategies

When workers consume jobs from multiple queues, the order in which queues are polled affects which jobs are processed first. OJS defines two queue consumption strategies.

### 7.1 Strict Priority

In strict priority mode, the backend processes all available jobs from higher-priority queues before processing any jobs from lower-priority queues. Queue priority is determined by the order in which queues are listed in the worker configuration.

**Semantics**:

Given queues listed as `[critical, default, low]`:
1. The backend MUST dispatch all available jobs from `critical` before dispatching any from `default`.
2. The backend MUST dispatch all available jobs from `default` before dispatching any from `low`.
3. Within each queue, jobs are ordered by their individual `priority` field, then FIFO.

**Trade-offs**: Strict priority maximizes throughput for high-priority work but risks starvation of lower-priority queues during sustained high load. Implementations SHOULD document this trade-off clearly.

### 7.2 Weighted Priority

In weighted priority mode, the backend distributes polling across queues proportionally to their assigned weights. A queue with weight 5 is polled approximately 5 times as often as a queue with weight 1.

**Semantics**:

Given queues with weights `{critical: 5, default: 2, low: 1}`:
- For every 8 dispatch cycles, approximately 5 will poll `critical`, 2 will poll `default`, and 1 will poll `low`.
- The exact scheduling algorithm (round-robin, probabilistic, etc.) is implementation-defined.
- Within each queue, jobs are ordered by their individual `priority` field, then FIFO.

Implementations MUST ensure that a queue with weight > 0 is eventually polled, even under sustained load on higher-weight queues.

**Rationale**: Weighted priority prevents starvation while still favoring higher-priority queues. This is the approach used by Sidekiq's weighted queue configuration, where queue weights determine polling frequency. It trades strict priority guarantees for fairness.

### 7.3 Strategy Configuration

Queue consumption strategy is a worker-level or backend-level configuration, not a per-job setting. The mechanism for configuring strategies is implementation-defined, but implementations MUST document which strategies they support.

Implementations MUST support at least one of strict or weighted priority. Implementations SHOULD support both.

**Example configuration (informational)**:

```json
{
  "queues": [
    { "name": "critical", "weight": 5 },
    { "name": "default", "weight": 2 },
    { "name": "low", "weight": 1 }
  ],
  "strategy": "weighted"
}
```

---

## 8. Dynamic Priority Adjustment

### 8.1 Priority Update

Implementations SHOULD support changing the priority of a job after enqueue, provided the job is in the `available` or `scheduled` state.

```
PATCH /ojs/v1/jobs/{id}
Content-Type: application/json

{
  "priority": 0
}
```

Implementations MUST NOT allow priority changes on jobs in the `active`, `completed`, `cancelled`, `discarded`, or `retryable` states.

**Rationale**: Changing priority on an active job has no effect (it is already running). Changing priority on terminal states is meaningless. Restricting changes to `available` and `scheduled` states ensures the change has the intended effect on dispatch ordering.

### 8.2 Priority Aging

Implementations MAY support priority aging, where a job's effective priority automatically increases (the integer decreases) the longer it waits in the queue. This is an optional mechanism to prevent starvation in strict priority environments.

When priority aging is supported:

- The **stored priority** (the value set at enqueue or via update) MUST NOT change.
- The **effective priority** (used for ordering during FETCH) MAY be lower than the stored priority.
- Aging parameters (rate, minimum effective priority) are implementation-defined.

**Rationale**: Priority aging is a proven technique from OS scheduling (e.g., Linux's CFS scheduler) adapted for job queues. Making it optional recognizes that many deployments prefer explicit priority control and that aging can produce surprising behavior if not well-understood.

---

## 9. Interaction with Other Extensions

### 9.1 Rate Limiting

When both priority and rate limiting apply to a job:

1. The backend MUST respect priority ordering among rate-limit-eligible jobs.
2. A high-priority job that is rate-limited MUST NOT be dispatched before the rate limit allows.
3. A lower-priority job that is NOT rate-limited SHOULD be dispatched instead of waiting for the rate-limited high-priority job.

**Rationale**: Rate limits are hard constraints (protecting external resources) while priority is a soft preference (ordering work). Hard constraints always win over soft preferences.

### 9.2 Workflows

When a job is part of a workflow (chain, group, or batch):

- Priority on individual jobs within a workflow is respected during dispatch.
- When a workflow step creates successor jobs, those successors SHOULD inherit the priority of the workflow root job unless explicitly overridden.
- Workflow-level priority does not preempt individual job priority within the same queue.

### 9.3 Unique Jobs

When a job is subject to a uniqueness constraint and a duplicate is enqueued:

- If the existing job has a lower priority (higher integer) than the incoming duplicate, implementations MAY update the existing job's priority to the higher priority (lower integer).
- This behavior MUST be opt-in via the uniqueness policy, not automatic.

### 9.4 Scheduling

Scheduled jobs (`scheduled_at` in the future) are not affected by priority until they transition to the `available` state. Once available, they are ordered by priority like any other job.

---

## 10. HTTP Binding

### 10.1 Enqueue with Priority

Priority is set as a top-level field in the job envelope:

```http
POST /ojs/v1/jobs
Content-Type: application/json

{
  "type": "report.generate",
  "queue": "default",
  "args": [{"report_id": "rpt_123"}],
  "priority": 1
}
```

### 10.2 Update Priority

```http
PATCH /ojs/v1/jobs/{id}
Content-Type: application/json

{
  "priority": 0
}
```

**Response** (200 OK):

```json
{
  "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "priority": 0,
  "previous_priority": 1
}
```

### 10.3 Priority Statistics

```http
GET /ojs/v1/queues/{queue}/priority-stats
```

**Response** (200 OK):

```json
{
  "queue": "default",
  "counts_by_priority": {
    "0": 3,
    "1": 12,
    "2": 847,
    "3": 234,
    "4": 1089
  },
  "total": 2185
}
```

---

## 11. Observability

### 11.1 Events

Implementations SHOULD emit the following events:

| Event Type                  | Trigger                                         | Data Fields                              |
|-----------------------------|-------------------------------------------------|------------------------------------------|
| `priority.changed`         | A job's priority was updated after enqueue.      | `job_id`, `previous_priority`, `new_priority` |

### 11.2 Metrics

Implementations SHOULD expose the following metrics:

| Metric Name                          | Type      | Labels                     | Description                               |
|--------------------------------------|-----------|----------------------------|-------------------------------------------|
| `ojs.queue.available_by_priority`    | Gauge     | `queue`, `priority`        | Available jobs per priority level.        |
| `ojs.job.wait_duration_by_priority`  | Histogram | `queue`, `priority`        | Time from enqueue to dispatch by priority.|
| `ojs.job.priority_changes_total`     | Counter   | `queue`                    | Total priority changes after enqueue.     |

---

## 12. Conformance Requirements

### 12.1 Required Capabilities

An implementation declaring support for the priority extension MUST support:

| ID          | Requirement                                                                              |
|-------------|------------------------------------------------------------------------------------------|
| PRI-001     | Accept `priority` field on job envelopes as a non-negative integer.                      |
| PRI-002     | Default to priority `2` when the `priority` field is omitted.                            |
| PRI-003     | Order available jobs by priority (ascending) first, then by enqueue time (ascending).    |
| PRI-004     | Return the highest-priority eligible job on FETCH.                                       |
| PRI-005     | Reject jobs with negative priority values with an appropriate error.                     |
| PRI-006     | Support a maximum priority value of at least 255.                                        |

### 12.2 Recommended Capabilities

| ID          | Requirement                                                                              |
|-------------|------------------------------------------------------------------------------------------|
| PRI-R001    | Support dynamic priority updates via PATCH on `available` and `scheduled` jobs.          |
| PRI-R002    | Support at least one queue consumption strategy (strict or weighted).                    |
| PRI-R003    | Expose `GET /ojs/v1/queues/{queue}/priority-stats` for priority distribution.            |
| PRI-R004    | Emit `priority.changed` events on priority updates.                                      |

---

## 13. Prior Art

| System               | Approach                                                                                  |
|----------------------|-------------------------------------------------------------------------------------------|
| **BullMQ**           | Integer priority 0–2,097,152 (0 = no priority, processed first). Stored in Redis sorted set with O(log n) insertion. Supports `changePriority()` for dynamic updates. |
| **Sidekiq**          | No in-queue priority. Uses queue ordering: strict (process all from first queue before moving to next) or weighted (probabilistic polling by weight). Priority gem adds in-queue sorting. |
| **Celery**           | Delegates to AMQP `x-max-priority` (0–255). Requires broker-side queue declaration. Higher integer = higher priority (opposite of OJS convention). |
| **Faktory**          | Integer priority 1–9 (default 5). Higher integer = higher priority. Jobs sorted within queue by priority. |
| **AMQP 0-9-1**       | Message priority 0–255 via `x-max-priority` queue argument. Higher integer = higher priority. RabbitMQ recommends keeping levels under 10 for performance. |
| **Oban**             | Integer priority 0–3 (0 = highest). Workers can be configured to fetch specific priority ranges. |
| **River**            | Integer priority 1–4 (1 = highest). Simple and constrained by design.                    |

OJS adopts a lower-is-higher convention (like Oban and River) with a wider range (0–255 minimum) and a default of `2` that leaves room for both higher and lower priorities. The queue consumption strategies (strict and weighted) are modeled directly on Sidekiq's proven approach.

---

## 14. Examples

### 14.1 Basic Priority Assignment

A critical job that should be processed before normal work:

```json
{
  "type": "incident.alert",
  "queue": "notifications",
  "args": [{"severity": "critical", "service": "payments"}],
  "priority": 0
}
```

### 14.2 Default Priority (Omitted)

A normal job with no priority specified (defaults to `2`):

```json
{
  "type": "email.send",
  "queue": "default",
  "args": ["user@example.com", "welcome"]
}
```

### 14.3 Low-Priority Bulk Work

Analytics aggregation that should yield to other work:

```json
{
  "type": "analytics.aggregate",
  "queue": "default",
  "args": [{"date": "2026-02-15", "metric": "page_views"}],
  "priority": 4
}
```

### 14.4 Priority with Rate Limiting

A high-priority job that is also rate-limited:

```json
{
  "type": "payment.process",
  "queue": "payments",
  "args": [{"order_id": "ord_123", "amount": 9999}],
  "priority": 1,
  "rate_limit": {
    "key": "payment-api",
    "concurrency": 5
  }
}
```

This job will be dispatched before priority-2 jobs, but only if the `payment-api` concurrency limit has not been reached. If the limit is reached, a lower-priority job without rate limits will be dispatched instead.

### 14.5 Priority in a Workflow Chain

A workflow where all steps inherit the parent's priority:

```json
{
  "type": "order.process",
  "queue": "orders",
  "args": [{"order_id": "ord_456"}],
  "priority": 1,
  "workflow": {
    "chain": [
      { "type": "payment.charge", "args": [{"order_id": "ord_456"}] },
      { "type": "inventory.reserve", "args": [{"order_id": "ord_456"}] },
      { "type": "shipping.schedule", "args": [{"order_id": "ord_456"}] }
    ]
  }
}
```

Each step in the chain inherits priority `1` unless explicitly overridden.

---

## Appendix A: Changelog

| Date       | Change                        |
|------------|-------------------------------|
| 2026-02-15 | Initial release candidate.    |
