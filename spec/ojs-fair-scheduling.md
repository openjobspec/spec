# Open Job Spec: Fair Scheduling and Consumer Groups

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Fair Scheduling Specification              |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-19                                     |
| **Status**  | Release Candidate                              |
| **Maturity** | Experimental                                   |
| **Tier**    | Official Extension                             |
| **URI**     | `urn:ojs:ext:fair-scheduling`                  |
| **Requires**| OJS Core Specification (Layer 1)               |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Design Principles](#4-design-principles)
5. [Competing Consumers](#5-competing-consumers)
   - 5.1 [Single-Queue Competing Consumers](#51-single-queue-competing-consumers)
   - 5.2 [Multi-Queue Competing Consumers](#52-multi-queue-competing-consumers)
6. [Worker Pools](#6-worker-pools)
   - 6.1 [Pool Definition](#61-pool-definition)
   - 6.2 [Queue Assignment](#62-queue-assignment)
   - 6.3 [Pool Isolation](#63-pool-isolation)
7. [Fair Distribution Strategies](#7-fair-distribution-strategies)
   - 7.1 [Round-Robin](#71-round-robin)
   - 7.2 [Least-Loaded](#72-least-loaded)
   - 7.3 [Weighted Fair Queuing](#73-weighted-fair-queuing)
8. [Starvation Prevention](#8-starvation-prevention)
   - 8.1 [Queue Rotation](#81-queue-rotation)
   - 8.2 [Minimum Throughput Guarantees](#82-minimum-throughput-guarantees)
9. [Per-Tenant Fairness](#9-per-tenant-fairness)
10. [HTTP Binding](#10-http-binding)
11. [Observability](#11-observability)
12. [Conformance Requirements](#12-conformance-requirements)
13. [Prior Art](#13-prior-art)
14. [Examples](#14-examples)

---

## 1. Introduction

When multiple workers consume jobs from shared queues, the distribution of work across workers and across queues directly impacts system performance, latency fairness, and resource utilization. Without explicit scheduling policies, a fast worker can monopolize a queue, a burst of jobs in one queue can starve others, and a single tenant's workload can crowd out all other tenants.

Fair scheduling addresses these problems by defining how the backend distributes jobs across competing consumers and how it balances work across multiple queues. These are operational concerns that every production deployment encounters, yet most job processing specifications leave them entirely to implementation discretion.

This specification defines the competing consumers model, worker pool management, fair distribution strategies, and starvation prevention mechanisms that enable predictable, equitable job processing at scale.

### 1.1 Scope

This specification defines:

- The competing consumers model for OJS queues.
- Worker pool definitions and queue assignment.
- Fair distribution strategies: round-robin, least-loaded, and weighted fair queuing.
- Starvation prevention mechanisms for multi-queue deployments.
- Per-tenant fairness for multi-tenant workloads.
- HTTP binding for pool and scheduling operations.

This specification does **not** define:

- Worker auto-scaling algorithms (infrastructure concern, not protocol concern).
- Network topology or service discovery for workers.
- CPU/memory-based scheduling (job processing is I/O-bound, not compute-scheduled).

### 1.2 Companion Specifications

| Document | Layer | Description |
|----------|-------|-------------|
| **ojs-core.md** | 1 -- Core | Job envelope, lifecycle, FETCH operation |
| **ojs-worker-protocol.md** | Extension | Worker registration, heartbeats, shutdown |
| **ojs-priority.md** | Extension | Priority ordering within queues |
| **ojs-multi-tenancy.md** | Extension | Tenant isolation and resource limits |

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

Every MUST requirement includes a rationale explaining why the requirement is mandatory.

---

## 3. Terminology

| Term                  | Definition                                                                                         |
|-----------------------|----------------------------------------------------------------------------------------------------|
| competing consumers   | Multiple workers that independently poll the same queue for jobs, where each job is delivered to exactly one worker. |
| worker pool           | A named group of workers that share a common queue assignment and concurrency configuration.       |
| fair distribution     | A scheduling approach that distributes work equitably across workers or queues to prevent monopolization. |
| queue rotation        | A technique where the backend cycles through queues in a defined order to prevent starvation.      |
| weighted fair queuing | A scheduling strategy where queues receive dispatch attention proportional to assigned weights.     |
| starvation            | A condition where a queue or tenant receives no job dispatches for an extended period due to sustained load elsewhere. |
| least-loaded          | A dispatch strategy that assigns jobs to the worker with the fewest currently active jobs.          |
| pool isolation         | A configuration where worker pools are restricted to specific queues, preventing cross-pool job dispatch. |

---

## 4. Design Principles

1. **At-most-once dispatch.** Each job is delivered to exactly one worker. The competing consumers model MUST NOT result in the same job being dispatched to multiple workers simultaneously. This is the foundational guarantee of any job queue.

2. **Backend-driven scheduling.** Fair scheduling decisions are made by the backend during FETCH, not by workers. Workers request jobs; the backend decides which job to assign based on scheduling policy. This centralized approach ensures consistent behavior regardless of the number or configuration of workers.

3. **Configurable fairness.** No single fairness strategy is optimal for all workloads. Strict priority maximizes throughput for urgent work; round-robin provides equal attention; weighted queuing balances throughput and fairness. Implementations SHOULD support multiple strategies and allow operators to choose.

4. **Graceful degradation.** When a worker pool is overloaded, the system should degrade gracefully: increasing latency for lower-priority work rather than dropping jobs or failing unpredictably.

---

## 5. Competing Consumers

### 5.1 Single-Queue Competing Consumers

The basic OJS model is inherently a competing consumers system. When multiple workers call FETCH on the same queue:

- The backend MUST assign each available job to at most one worker.

**Rationale**: Double-dispatch (delivering the same job to two workers) causes duplicate processing, data corruption, and inconsistent state. This is the most fundamental correctness requirement of any job queue.

- The backend MUST use atomic operations (locking, CAS, transactions) to prevent race conditions during job assignment.

**Rationale**: Non-atomic FETCH implementations are the most common source of double-dispatch bugs. Both Redis (using Lua scripts or RPOPLPUSH) and PostgreSQL (using SELECT FOR UPDATE SKIP LOCKED) provide atomic primitives specifically for this pattern.

- Workers MUST NOT coordinate with each other to divide work. All coordination is handled by the backend.

### 5.2 Multi-Queue Competing Consumers

When a worker is configured to consume from multiple queues, the backend MUST determine which queue to service on each FETCH request. The strategy for this decision is defined in [Section 7](#7-fair-distribution-strategies).

Workers MAY specify their queue preferences in the FETCH request:

```json
{
  "queues": ["critical", "default", "low"],
  "strategy": "weighted",
  "weights": { "critical": 5, "default": 2, "low": 1 }
}
```

The backend MAY override worker-specified preferences with server-side configuration. When server-side configuration exists, it takes precedence.

**Rationale**: Server-side precedence ensures that operational constraints (e.g., "the analytics queue must never consume more than 20% of capacity") cannot be bypassed by worker misconfiguration.

---

## 6. Worker Pools

### 6.1 Pool Definition

A worker pool is a named group of workers that share a common configuration. Pools enable operators to dedicate workers to specific queues or workloads.

```json
{
  "pool": {
    "name": "critical-workers",
    "queues": ["critical", "payments"],
    "concurrency": 20,
    "strategy": "strict"
  }
}
```

| Field         | Type    | Required | Default          | Description                                                 |
|---------------|---------|----------|------------------|-------------------------------------------------------------|
| `name`        | string  | Yes      | --               | Unique identifier for the worker pool.                      |
| `queues`      | array   | Yes      | --               | List of queue names this pool consumes from.                |
| `concurrency` | integer | No       | implementation-defined | Maximum concurrent active jobs across all workers in the pool. |
| `strategy`    | string  | No       | `"round-robin"`  | Queue consumption strategy: `"strict"`, `"round-robin"`, `"weighted"`, or `"least-loaded"`. |
| `weights`     | object  | No       | --               | Queue weights for the `"weighted"` strategy. Keys are queue names, values are positive integers. |

### 6.2 Queue Assignment

Workers MUST declare their pool membership at registration time (see [ojs-worker-protocol.md](./ojs-worker-protocol.md)). A worker MUST belong to exactly one pool.

**Rationale**: Multi-pool membership creates ambiguity about which pool's scheduling policy governs a particular FETCH request. Single-pool membership keeps the model simple and predictable.

### 6.3 Pool Isolation

When pool isolation is enabled, the backend MUST NOT dispatch jobs from a queue to workers outside the pool assigned to that queue.

Pool isolation prevents a scenario where a general-purpose worker pool drains jobs from a queue that a specialized pool is designed to handle (e.g., GPU-accelerated workers for image processing jobs).

When pool isolation is NOT enabled, any worker pool configured to consume from a queue MAY receive jobs from that queue. If multiple pools consume from the same queue, the backend distributes jobs across all eligible workers regardless of pool membership.

---

## 7. Fair Distribution Strategies

### 7.1 Round-Robin

**Definition**: The backend cycles through queues in order, dispatching one job from each queue per cycle.

**Semantics**:

Given queues `[A, B, C]`:
1. Cycle 1: dispatch from A, then B, then C.
2. Cycle 2: dispatch from A, then B, then C.
3. If a queue is empty during its turn, skip it and move to the next.

Round-robin provides equal attention to all queues regardless of their depth. This is the simplest fairness strategy and is RECOMMENDED as the default.

**Trade-offs**: Round-robin does not account for queue depth. A queue with 10,000 jobs gets the same attention as a queue with 1 job. This is often desirable (preventing a backlog in one queue from starving others) but can increase latency for the deep queue.

### 7.2 Least-Loaded

**Definition**: The backend assigns jobs to the worker with the fewest currently active jobs.

**Semantics**:

When a FETCH request arrives:
1. Identify the requesting worker's current active job count.
2. Dispatch a job if the worker has capacity (active count < worker concurrency limit).
3. Among eligible queues, select the one with the deepest backlog (most available jobs).

Least-loaded balances work across workers, preventing hot-spotting where one worker processes significantly more jobs than others.

**Trade-offs**: Least-loaded requires the backend to track per-worker active job counts, adding state management overhead. It is most beneficial when job processing times vary significantly.

### 7.3 Weighted Fair Queuing

**Definition**: The backend distributes dispatch attention across queues proportionally to assigned weights.

**Semantics**:

Given queues with weights `{A: 3, B: 2, C: 1}`:
- For every 6 dispatch cycles, approximately 3 service A, 2 service B, and 1 services C.
- The implementation MAY use probabilistic selection, deficit round-robin, or any algorithm that achieves proportional distribution over time.

Implementations MUST ensure that a queue with weight > 0 receives at least one dispatch attempt within a bounded time period.

**Rationale**: Weighted fair queuing is the most flexible strategy, allowing operators to express relative importance without the starvation risk of strict priority. Sidekiq's weighted queue configuration demonstrates that this approach works well in production at scale.

---

## 8. Starvation Prevention

### 8.1 Queue Rotation

When using strict priority or weighted strategies, implementations SHOULD support queue rotation to prevent indefinite starvation of low-priority queues.

Queue rotation works by periodically cycling the queue that receives the next dispatch, regardless of weights or priority. The rotation interval is configurable:

```json
{
  "starvation_prevention": {
    "enabled": true,
    "rotation_interval": "PT30S",
    "min_dispatch_ratio": 0.05
  }
}
```

| Field                  | Type    | Required | Default   | Description                                                  |
|------------------------|---------|----------|-----------|--------------------------------------------------------------|
| `enabled`              | boolean | No       | `false`   | Whether starvation prevention is active.                     |
| `rotation_interval`    | string  | No       | `"PT30S"` | ISO 8601 duration. How often to force-dispatch from starved queues. |
| `min_dispatch_ratio`   | number  | No       | `0.05`    | Minimum fraction of dispatches guaranteed to each queue (0.0–1.0). |

### 8.2 Minimum Throughput Guarantees

When `min_dispatch_ratio` is configured, the backend MUST ensure that each queue receives at least the specified fraction of total dispatches over any sliding window equal to the `rotation_interval`.

**Rationale**: A `min_dispatch_ratio` of 0.05 means that even the lowest-priority queue receives at least 5% of dispatches, preventing complete starvation while still allowing high-priority queues to consume the majority of capacity.

**Example**: With 3 queues and `min_dispatch_ratio: 0.05`:
- Each queue is guaranteed at least 5% of dispatches.
- The remaining 85% is distributed according to the configured strategy (strict, weighted, etc.).

---

## 9. Per-Tenant Fairness

In multi-tenant deployments, a single tenant's burst of jobs can monopolize shared queues, degrading service for other tenants. Per-tenant fairness ensures equitable queue access across tenants.

### 9.1 Tenant-Aware Scheduling

When per-tenant fairness is enabled, the backend SHOULD interleave jobs from different tenants rather than processing them in strict enqueue order. This prevents a tenant that enqueues 10,000 jobs from blocking other tenants who each enqueue 10 jobs.

The tenant identifier is derived from the job's `meta.tenant_id` field (see [ojs-multi-tenancy.md](./ojs-multi-tenancy.md)).

### 9.2 Fair Share Scheduling

Implementations MAY support fair share scheduling, where each tenant receives an equal share of dispatch capacity by default, with the ability to assign per-tenant weights.

```json
{
  "tenant_fairness": {
    "enabled": true,
    "strategy": "fair-share",
    "weights": {
      "tenant:enterprise-a": 5,
      "tenant:startup-b": 1
    },
    "default_weight": 1
  }
}
```

When fair share scheduling is active and no weights are configured, all tenants receive equal dispatch capacity.

### 9.3 Interaction with Priority

Per-tenant fairness operates within priority levels, not across them. A high-priority job from tenant A is always dispatched before a low-priority job from tenant B, regardless of tenant fairness settings. Within the same priority level, tenant fairness determines the dispatch order.

---

## 10. HTTP Binding

### 10.1 Pool Management

**List pools:**

```
GET /ojs/v1/admin/pools
```

**Response** (200 OK):

```json
{
  "items": [
    {
      "name": "critical-workers",
      "queues": ["critical", "payments"],
      "concurrency": 20,
      "strategy": "strict",
      "active_workers": 4,
      "active_jobs": 12
    },
    {
      "name": "default-workers",
      "queues": ["default", "email", "notifications"],
      "concurrency": 50,
      "strategy": "weighted",
      "weights": { "default": 3, "email": 2, "notifications": 1 },
      "active_workers": 8,
      "active_jobs": 31
    }
  ]
}
```

**Create or update pool:**

```
PUT /ojs/v1/admin/pools/{name}
Content-Type: application/json

{
  "queues": ["critical", "payments"],
  "concurrency": 20,
  "strategy": "strict"
}
```

### 10.2 Scheduling Statistics

```
GET /ojs/v1/admin/scheduling/stats
```

**Response** (200 OK):

```json
{
  "queues": [
    {
      "name": "critical",
      "dispatch_count_1m": 142,
      "dispatch_ratio_1m": 0.45,
      "avg_wait_ms": 12,
      "active_jobs": 8
    },
    {
      "name": "default",
      "dispatch_count_1m": 134,
      "dispatch_ratio_1m": 0.43,
      "avg_wait_ms": 89,
      "active_jobs": 24
    },
    {
      "name": "low",
      "dispatch_count_1m": 38,
      "dispatch_ratio_1m": 0.12,
      "avg_wait_ms": 340,
      "active_jobs": 5
    }
  ],
  "window": "PT1M"
}
```

---

## 11. Observability

### 11.1 Events

Implementations SHOULD emit the following events:

| Event Type                    | Trigger                                              | Data Fields                              |
|-------------------------------|------------------------------------------------------|------------------------------------------|
| `scheduling.queue_starved`    | A queue received no dispatches for > rotation_interval. | `queue`, `duration`, `available_count`   |
| `scheduling.pool_overloaded`  | All workers in a pool are at maximum concurrency.     | `pool`, `active_jobs`, `waiting_jobs`    |
| `scheduling.rebalanced`       | Queue weights or strategy was changed at runtime.     | `pool`, `previous_strategy`, `new_strategy` |

### 11.2 Metrics

Implementations SHOULD expose the following metrics:

| Metric Name                            | Type      | Labels                     | Description                               |
|----------------------------------------|-----------|----------------------------|-------------------------------------------|
| `ojs.scheduling.dispatch_total`        | Counter   | `queue`, `pool`            | Total jobs dispatched per queue and pool.  |
| `ojs.scheduling.dispatch_ratio`        | Gauge     | `queue`                    | Current dispatch ratio per queue.          |
| `ojs.scheduling.queue_wait_duration`   | Histogram | `queue`                    | Time from availability to dispatch.        |
| `ojs.scheduling.pool_utilization`      | Gauge     | `pool`                     | Active jobs / concurrency limit per pool.  |
| `ojs.scheduling.starvation_events`     | Counter   | `queue`                    | Times a queue was identified as starved.   |

---

## 12. Conformance Requirements

### 12.1 Required Capabilities

An implementation declaring support for the fair-scheduling extension MUST support:

| ID          | Requirement                                                                              |
|-------------|------------------------------------------------------------------------------------------|
| FS-001      | At-most-once dispatch: each job is delivered to exactly one worker via atomic FETCH.      |
| FS-002      | Multi-queue consumption: workers MAY consume from multiple queues.                        |
| FS-003      | At least one fair distribution strategy (round-robin, weighted, or least-loaded).         |
| FS-004      | Pool listing via `GET /ojs/v1/admin/pools`.                                              |

### 12.2 Recommended Capabilities

| ID          | Requirement                                                                              |
|-------------|------------------------------------------------------------------------------------------|
| FS-R001     | Worker pools with queue assignment and concurrency limits.                                |
| FS-R002     | Weighted fair queuing with configurable weights.                                          |
| FS-R003     | Starvation prevention with configurable rotation interval.                                |
| FS-R004     | Scheduling statistics via `GET /ojs/v1/admin/scheduling/stats`.                           |
| FS-R005     | Per-tenant fairness for multi-tenant deployments.                                        |
| FS-R006     | Pool isolation to prevent cross-pool job dispatch.                                       |

---

## 13. Prior Art

| System               | Approach                                                                                  |
|----------------------|-------------------------------------------------------------------------------------------|
| **Sidekiq**          | Strict and weighted queue ordering. Workers list queues in priority order or with weights. Queue order randomized per cycle for weighted mode. |
| **Kafka**            | Consumer groups with partition assignment. Each partition assigned to exactly one consumer in the group. Rebalancing on consumer join/leave. |
| **RabbitMQ**         | Competing consumers via round-robin dispatch. `basic.qos` prefetch controls per-consumer parallelism. Multiple consumers on the same queue share messages. |
| **BullMQ**           | Single-queue model with optional named processors. No built-in multi-queue fairness; fairness achieved via separate worker processes per queue. |
| **Celery**           | Worker `-Q` flag assigns queues. `-O fair` option enables fair scheduling (assigns new tasks only when previous ones are complete). Default mode prefetches aggressively. |
| **Temporal**         | Task queue pollers with configurable concurrency. Task queue rate limiting for cross-worker fairness. Sticky queues for workflow affinity. |
| **Azure Service Bus**| Competing consumers pattern with session-based ordering. Auto-forwarding for fan-out. Dead-letter for poison messages. |

OJS synthesizes these approaches into a unified model: worker pools define queue assignments, fair distribution strategies govern dispatch ordering, and starvation prevention ensures no queue is indefinitely ignored.

---

## 14. Examples

### 14.1 Basic Multi-Queue Worker

A worker consuming from three queues with weighted fairness:

```json
{
  "worker": {
    "id": "worker-abc-123",
    "pool": "general",
    "queues": ["critical", "default", "low"],
    "strategy": "weighted",
    "weights": { "critical": 5, "default": 3, "low": 1 },
    "concurrency": 10
  }
}
```

This worker will service `critical` approximately 5/9 of the time, `default` 3/9, and `low` 1/9.

### 14.2 Dedicated Pool for Critical Work

Isolating payment processing on dedicated workers:

```json
{
  "pools": [
    {
      "name": "payment-workers",
      "queues": ["payments"],
      "concurrency": 10,
      "strategy": "strict",
      "isolated": true
    },
    {
      "name": "general-workers",
      "queues": ["default", "email", "notifications"],
      "concurrency": 50,
      "strategy": "round-robin"
    }
  ]
}
```

The `payment-workers` pool exclusively handles the `payments` queue. No general worker can pick up payment jobs.

### 14.3 Starvation Prevention

Ensuring the `analytics` queue gets at least 10% of dispatch capacity:

```json
{
  "pool": {
    "name": "general",
    "queues": ["critical", "default", "analytics"],
    "strategy": "strict",
    "starvation_prevention": {
      "enabled": true,
      "rotation_interval": "PT30S",
      "min_dispatch_ratio": 0.10
    }
  }
}
```

Even under heavy `critical` load, `analytics` will receive at least 10% of dispatches every 30 seconds.

### 14.4 Per-Tenant Fairness

Preventing a single tenant from monopolizing the queue:

```json
{
  "tenant_fairness": {
    "enabled": true,
    "strategy": "fair-share",
    "default_weight": 1
  }
}
```

With this configuration, if tenant A enqueues 10,000 jobs and tenant B enqueues 100 jobs, the backend interleaves dispatches so both tenants receive approximately equal throughput.

---

## Appendix A: Changelog

| Date       | Change                        |
|------------|-------------------------------|
| 2026-02-15 | Initial release candidate.    |
