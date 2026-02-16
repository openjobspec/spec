# Open Job Spec: Queue Configuration

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Queue Configuration Specification          |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-15                                     |
| **Status**  | Release Candidate                              |
| **Maturity** | Beta                                           |
| **Tier**    | Official Extension                             |
| **URI**     | `urn:ojs:ext:queue-config`                     |
| **Requires**| OJS Core Specification (Layer 1)               |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Design Principles](#4-design-principles)
5. [Queue Lifecycle](#5-queue-lifecycle)
   - 5.1 [Queue States](#51-queue-states)
   - 5.2 [Implicit vs. Explicit Creation](#52-implicit-vs-explicit-creation)
   - 5.3 [Queue Deletion](#53-queue-deletion)
6. [Queue Configuration Fields](#6-queue-configuration-fields)
   - 6.1 [Capacity Configuration](#61-capacity-configuration)
   - 6.2 [Processing Configuration](#62-processing-configuration)
   - 6.3 [Retention Configuration](#63-retention-configuration)
   - 6.4 [Dead-Letter Configuration](#64-dead-letter-configuration)
   - 6.5 [Access Control](#65-access-control)
7. [Queue Policies](#7-queue-policies)
   - 7.1 [Default Queue Policy](#71-default-queue-policy)
   - 7.2 [Policy Inheritance](#72-policy-inheritance)
   - 7.3 [Policy Override Rules](#73-policy-override-rules)
8. [Interaction with Other Extensions](#8-interaction-with-other-extensions)
   - 8.1 [Admin API](#81-admin-api)
   - 8.2 [Backpressure](#82-backpressure)
   - 8.3 [Rate Limiting](#83-rate-limiting)
   - 8.4 [Priority](#84-priority)
   - 8.5 [Multi-Tenancy](#85-multi-tenancy)
9. [HTTP Binding](#9-http-binding)
10. [Observability](#10-observability)
11. [Conformance Requirements](#11-conformance-requirements)
12. [Prior Art](#12-prior-art)
13. [Examples](#13-examples)

---

## 1. Introduction

The OJS core specification defines a `queue` attribute on the job envelope but does not define how queues themselves are configured, created, or managed. The Admin API specification (ojs-admin-api.md) provides basic queue configuration (concurrency, rate limits, retention) as part of the operator API, but does not address the full queue lifecycle: explicit creation with capacity limits, dead-letter queue routing, durability guarantees, or policy-based defaults.

In production deployments, queue configuration is a critical operational concern. Without standardized queue configuration, operators must rely on implementation-specific mechanisms (environment variables, YAML files, database migrations) to set up queues. This creates portability problems when migrating between OJS implementations and makes it impossible to define queue topology declaratively.

### 1.1 Scope

This specification defines:

- A queue lifecycle model with explicit states (active, paused, draining, deleted).
- Queue configuration fields for capacity, processing, retention, and dead-letter routing.
- A policy model for default configuration and inheritance.
- Queue creation and deletion semantics.

This specification does **not** define:

- Worker assignment to queues (covered by ojs-worker-protocol.md).
- Queue consumption ordering (covered by ojs-priority.md and ojs-fair-scheduling.md).
- Backpressure strategies (covered by ojs-backpressure.md).
- Queue-level metrics (covered by ojs-observability.md).

### 1.2 Companion Specifications

| Document | Layer | Description |
|----------|-------|-------------|
| **ojs-core.md** | 1 -- Core | Job envelope, `queue` attribute |
| **ojs-admin-api.md** | Extension | Queue listing, pause/resume, basic configuration |
| **ojs-backpressure.md** | Extension | Queue capacity enforcement strategies |
| **ojs-rate-limiting.md** | Extension | Queue-level rate limits |
| **ojs-dead-letter.md** | Extension | Dead-letter queue semantics |
| **ojs-priority.md** | Extension | Queue consumption strategies |

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term | Definition |
|------|------------|
| **Queue** | A named, ordered collection of jobs awaiting processing. |
| **Queue Configuration** | A set of parameters that control a queue's behavior, capacity, and processing characteristics. |
| **Queue Policy** | A named, reusable configuration template that can be applied to multiple queues. |
| **Implicit Queue** | A queue that is automatically created when a job is enqueued to a previously unknown queue name. |
| **Explicit Queue** | A queue that is created via the management API before jobs are enqueued to it. |
| **Dead-Letter Queue (DLQ)** | A designated queue that receives jobs that cannot be processed after exhausting all retry attempts. |
| **Queue Depth** | The total number of jobs in a queue across all non-terminal states. |

---

## 4. Design Principles

1. **Implicit by default, explicit when needed.** Queues are automatically created on first use (matching the behavior of every major job system). Explicit creation is available for operators who need capacity limits, DLQ routing, or access control before the first job arrives.

2. **Configuration as data, not code.** Queue configuration is managed through API endpoints, not configuration files or environment variables. This enables dynamic reconfiguration without redeployment and provides a single source of truth queryable by any component.

3. **Sensible defaults cover 90% of use cases.** A queue with no explicit configuration works correctly with default concurrency, no size limits, and standard retention. Configuration is for tuning, not for basic operation.

4. **Non-destructive reconfiguration.** Changing a queue's configuration MUST NOT affect jobs that are already in the queue. New configuration applies to newly enqueued jobs and future processing decisions.

---

## 5. Queue Lifecycle

### 5.1 Queue States

```
                    ┌──────────┐
    create ────────▶│  active  │◀─── resume
                    └────┬─────┘
                         │
                    pause│         ┌──────────┐
                         ▼         │ draining │
                    ┌──────────┐   └─────┬────┘
                    │  paused  │         │
                    └──────────┘         │ drain complete
                                         ▼
                                   ┌──────────┐
                       delete ────▶│ deleted  │
                                   └──────────┘
```

| State | Description |
|-------|-------------|
| `active` | Queue accepts new jobs and workers process them normally. |
| `paused` | Queue accepts new jobs but workers do NOT fetch from it. Existing active jobs continue. |
| `draining` | Queue does NOT accept new jobs. Workers continue processing until the queue is empty. |
| `deleted` | Queue is removed. All remaining jobs are handled according to the deletion policy. |

Implementations MUST support `active` and `paused` states. Implementations SHOULD support `draining`. Implementations MUST support queue deletion.

### 5.2 Implicit vs. Explicit Creation

**Implicit creation:** When a job is enqueued to a queue name that does not exist, the implementation MUST automatically create the queue with default configuration. This is the baseline behavior.

**Explicit creation:** Operators MAY create queues explicitly via the management API to configure them before the first job arrives:

```http
POST /ojs/v1/queues HTTP/1.1
Content-Type: application/json

{
  "name": "payments",
  "config": {
    "max_size": 100000,
    "concurrency": 20,
    "dead_letter_queue": "payments-dlq"
  }
}
```

Implementations MAY support a `strict_queues` mode where enqueuing to a non-existent queue returns an error instead of auto-creating. This is useful in production environments where queue topology is managed declaratively.

**Rationale:** Implicit creation matches user expectations from every major job system (Sidekiq, BullMQ, Celery). Requiring explicit creation would add friction for simple use cases. Strict mode is an opt-in safeguard for production environments.

### 5.3 Queue Deletion

Deleting a queue requires a decision about remaining jobs. The deletion request MUST specify a strategy:

| Strategy | Behavior |
|----------|----------|
| `reject` | Reject deletion if the queue contains any non-terminal jobs. Return 409 Conflict. |
| `discard` | Discard all remaining jobs. Transition them to `discarded` with error type `"queue_deleted"`. |
| `move` | Move all remaining jobs to a specified target queue. |

```http
DELETE /ojs/v1/queues/old-payments HTTP/1.1
Content-Type: application/json

{
  "strategy": "move",
  "target_queue": "payments"
}
```

Implementations MUST support the `reject` strategy. Implementations SHOULD support `discard` and `move`.

---

## 6. Queue Configuration Fields

### 6.1 Capacity Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_size` | integer | unlimited | Maximum number of non-terminal jobs in the queue. |
| `max_size_bytes` | integer | unlimited | Maximum total serialized size of all jobs in the queue (bytes). |
| `overflow_policy` | string | `"reject"` | Action when `max_size` is exceeded: `"reject"`, `"drop_oldest"`, `"block"`. |

When `max_size` is set and the queue is at capacity:

- `"reject"`: PUSH returns error `QUEUE_FULL`. The producer receives immediate feedback.
- `"drop_oldest"`: The oldest non-active job is discarded to make room. Emits `job.discarded` event with error type `"overflow"`.
- `"block"`: PUSH blocks until space is available or a timeout expires. RECOMMENDED only for in-process producers.

**Rationale:** Queue capacity limits prevent unbounded growth that leads to memory exhaustion. The default is unlimited because most job systems start without capacity limits. Adding them is a production hardening step.

### 6.2 Processing Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `concurrency` | integer | impl-defined | Maximum number of jobs processed concurrently from this queue. |
| `rate_limit` | object | none | Rate limiting configuration (see ojs-rate-limiting.md). |
| `rate_limit.limit` | integer | — | Maximum jobs per period. |
| `rate_limit.period` | string (ISO 8601) | — | Rate limit window (e.g., `"PT1M"` for per-minute). |
| `visibility_timeout` | integer (seconds) | impl-defined | Default visibility timeout for jobs in this queue. |
| `default_timeout` | integer (seconds) | impl-defined | Default execution timeout for jobs in this queue. |
| `default_retry` | object | impl-defined | Default retry policy for jobs in this queue. |

Queue-level processing configuration provides defaults that individual jobs can override. Job-level values take precedence over queue-level defaults.

### 6.3 Retention Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `retention.completed` | string (ISO 8601) | `"P7D"` | How long to retain completed jobs. |
| `retention.discarded` | string (ISO 8601) | `"P30D"` | How long to retain discarded jobs. |
| `retention.cancelled` | string (ISO 8601) | `"P7D"` | How long to retain cancelled jobs. |

After the retention period expires, terminal jobs are eligible for automatic pruning. Implementations MUST support retention-based pruning.

### 6.4 Dead-Letter Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `dead_letter_queue` | string | impl-defined | Queue name to receive jobs that exhaust all retry attempts. |
| `dead_letter_max_size` | integer | unlimited | Maximum size of the dead-letter queue. |
| `dead_letter_ttl` | string (ISO 8601) | `"P30D"` | How long to retain dead-lettered jobs before pruning. |

When a DLQ is configured, jobs that transition to `discarded` via retry exhaustion MUST be re-enqueued to the DLQ instead of remaining in the original queue. The job's `error` object is preserved.

### 6.5 Access Control

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `allowed_job_types` | string[] | `["*"]` | Job types permitted in this queue. Supports wildcards. |
| `producers` | string[] | `["*"]` | Producer identities allowed to enqueue to this queue. |

When `allowed_job_types` is set, a PUSH with a non-matching job type MUST be rejected with error `JOB_TYPE_NOT_ALLOWED`.

**Rationale:** Access control at the queue level prevents accidental cross-contamination (e.g., a developer enqueuing test jobs to the production payments queue).

---

## 7. Queue Policies

### 7.1 Default Queue Policy

Implementations SHOULD support a default queue policy that is applied to all implicitly created queues:

```http
PUT /ojs/v1/queues/_default/config HTTP/1.1
Content-Type: application/json

{
  "concurrency": 10,
  "retention": {
    "completed": "P7D",
    "discarded": "P30D"
  },
  "default_retry": {
    "max_attempts": 3,
    "initial_interval": "PT1S",
    "backoff_coefficient": 2.0
  }
}
```

The `_default` queue name is a reserved virtual queue that serves as the policy template for new queues.

### 7.2 Policy Inheritance

When a queue is created (implicitly or explicitly), its configuration is resolved by layering:

1. **System defaults** (hardcoded implementation defaults).
2. **Default queue policy** (`_default` configuration, if set).
3. **Explicit queue configuration** (values set at creation or via update).

Later layers override earlier layers for any field that is explicitly set.

### 7.3 Policy Override Rules

Job-level configuration takes precedence over queue-level configuration:

| Configuration | Priority (highest first) |
|---------------|-------------------------|
| Job-level `timeout` | 1 |
| Queue-level `default_timeout` | 2 |
| Default queue policy `default_timeout` | 3 |
| System default | 4 |

This layered approach ensures that producers can override queue defaults for specific jobs while operators maintain sensible defaults for the queue as a whole.

---

## 8. Interaction with Other Extensions

### 8.1 Admin API

The Admin API (ojs-admin-api.md) provides queue listing, pause/resume, and basic configuration. This extension extends the Admin API with:

- Queue creation endpoint (`POST /ojs/v1/queues`).
- Queue deletion endpoint (`DELETE /ojs/v1/queues/{name}`).
- Full configuration schema (capacity, DLQ, access control).
- Default queue policy management.

### 8.2 Backpressure

The backpressure extension (ojs-backpressure.md) defines strategies for handling queue capacity overflow. The `overflow_policy` field in queue configuration aligns with backpressure strategies:

- `"reject"` maps to the reject strategy.
- `"drop_oldest"` maps to the drop-oldest strategy.
- `"block"` maps to the block strategy.

### 8.3 Rate Limiting

Queue-level rate limiting (ojs-rate-limiting.md) is configured through the `rate_limit` field in queue configuration. The rate limit applies to the entire queue, independent of individual job rate limits.

### 8.4 Priority

When priority-based consumption (ojs-priority.md) is active, queue configuration does not change priority semantics. Priority ordering operates within a queue; queue configuration controls the queue's capacity and processing characteristics.

### 8.5 Multi-Tenancy

When multi-tenancy (ojs-multi-tenancy.md) is active, queue configuration may be tenant-scoped. A tenant's queue configuration MUST NOT affect other tenants' queues. The `_default` policy may be overridden per tenant.

---

## 9. HTTP Binding

### 9.1 Queue Management Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/ojs/v1/queues` | Create a queue with explicit configuration. |
| GET | `/ojs/v1/queues` | List all queues with status and configuration summary. |
| GET | `/ojs/v1/queues/{name}` | Get queue details and full configuration. |
| PUT | `/ojs/v1/queues/{name}/config` | Update queue configuration. |
| DELETE | `/ojs/v1/queues/{name}` | Delete a queue with a specified strategy. |
| PUT | `/ojs/v1/queues/_default/config` | Set the default queue policy. |
| GET | `/ojs/v1/queues/_default/config` | Get the default queue policy. |

### 9.2 Create Queue

```http
POST /ojs/v1/queues HTTP/1.1
Content-Type: application/json

{
  "name": "payments",
  "config": {
    "max_size": 100000,
    "concurrency": 20,
    "visibility_timeout": 300,
    "default_timeout": 1800,
    "dead_letter_queue": "payments-dlq",
    "retention": {
      "completed": "P3D",
      "discarded": "P30D"
    },
    "allowed_job_types": ["payment.*"],
    "default_retry": {
      "max_attempts": 5,
      "initial_interval": "PT5S",
      "backoff_coefficient": 3.0
    }
  }
}
```

**Response (201 Created):**

```json
{
  "name": "payments",
  "state": "active",
  "config": {
    "max_size": 100000,
    "concurrency": 20,
    "visibility_timeout": 300,
    "default_timeout": 1800,
    "dead_letter_queue": "payments-dlq",
    "retention": {
      "completed": "P3D",
      "discarded": "P30D",
      "cancelled": "P7D"
    },
    "allowed_job_types": ["payment.*"],
    "default_retry": {
      "max_attempts": 5,
      "initial_interval": "PT5S",
      "backoff_coefficient": 3.0,
      "jitter": true,
      "on_exhaustion": "dead_letter"
    }
  },
  "created_at": "2026-02-15T22:00:00Z"
}
```

### 9.3 Get Queue Details

```http
GET /ojs/v1/queues/payments HTTP/1.1

HTTP/1.1 200 OK
Content-Type: application/json

{
  "name": "payments",
  "state": "active",
  "config": { "..." },
  "stats": {
    "depth": 1542,
    "available": 1200,
    "active": 20,
    "retryable": 322,
    "scheduled": 0,
    "completed_today": 45230,
    "failed_today": 127
  },
  "created_at": "2026-02-15T22:00:00Z",
  "updated_at": "2026-02-15T22:30:00Z"
}
```

### 9.4 Delete Queue

```http
DELETE /ojs/v1/queues/old-payments HTTP/1.1
Content-Type: application/json

{
  "strategy": "move",
  "target_queue": "payments"
}

HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "queue": "old-payments",
  "strategy": "move",
  "target_queue": "payments",
  "jobs_affected": 42,
  "state": "draining"
}
```

---

## 10. Observability

### 10.1 Events

| Event Type | Trigger |
|------------|---------|
| `queue.created` | Queue explicitly created via API. |
| `queue.deleted` | Queue deleted. |
| `queue.config_updated` | Queue configuration changed. |
| `queue.full` | Queue reached `max_size`. |
| `queue.overflow` | Job discarded due to `drop_oldest` overflow policy. |

### 10.2 Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `ojs.queue.depth` | Gauge | Current number of non-terminal jobs, labeled by `queue`, `state`. |
| `ojs.queue.max_size` | Gauge | Configured max_size, labeled by `queue`. |
| `ojs.queue.utilization` | Gauge | `depth / max_size` ratio (0.0-1.0), labeled by `queue`. |
| `ojs.queue.overflow.count` | Counter | Jobs rejected or dropped due to capacity, labeled by `queue`, `policy`. |
| `ojs.queue.created.count` | Counter | Queues created (implicit + explicit). |
| `ojs.queue.deleted.count` | Counter | Queues deleted. |

---

## 11. Conformance Requirements

### 11.1 Required

| Capability | Requirement |
|------------|-------------|
| Implicit queue creation | Implementations MUST auto-create queues on first enqueue. |
| Queue configuration retrieval | Implementations MUST support reading queue configuration. |
| Queue configuration update | Implementations MUST support updating concurrency and retention. |
| Queue pause/resume | Implementations MUST support pausing and resuming queues. |
| Queue deletion | Implementations MUST support deleting queues with the `reject` strategy. |
| Retention-based pruning | Implementations MUST support automatic pruning of terminal jobs. |

### 11.2 Recommended

| Capability | Requirement |
|------------|-------------|
| Explicit queue creation | Implementations SHOULD support explicit queue creation via API. |
| Capacity limits | Implementations SHOULD support `max_size`. |
| Dead-letter queue routing | Implementations SHOULD support `dead_letter_queue` configuration. |
| Default queue policy | Implementations SHOULD support the `_default` queue policy. |
| Draining state | Implementations SHOULD support the `draining` queue state. |
| `discard` and `move` deletion strategies | Implementations SHOULD support all three deletion strategies. |

### 11.3 Optional

| Capability | Requirement |
|------------|-------------|
| Strict queue mode | Implementations MAY support `strict_queues` to reject unknown queue names. |
| Size-based capacity | Implementations MAY support `max_size_bytes`. |
| Access control | Implementations MAY support `allowed_job_types` and `producers`. |
| Queue-level timeout defaults | Implementations MAY support `default_timeout` on queues. |

---

## 12. Prior Art

| System | Queue Configuration |
|--------|-------------------|
| **RabbitMQ** | Rich queue configuration via `x-arguments`: `x-max-length`, `x-dead-letter-exchange`, `x-message-ttl`, `x-queue-type`. Queues must be declared before use. OJS supports both implicit and explicit creation. |
| **Amazon SQS** | `CreateQueue` API with configuration attributes: `VisibilityTimeout`, `MaximumMessageSize`, `MessageRetentionPeriod`, `RedrivePolicy` (DLQ). OJS aligns with SQS's attribute model. |
| **Sidekiq** | Queues are implicit (auto-created on first job). Configuration via `sidekiq.yml` (`concurrency`, `queues` with weights). No capacity limits. |
| **BullMQ** | Queues are implicit. Configuration passed at worker instantiation (`concurrency`, `limiter`). No capacity limits or DLQ routing at queue level. |
| **Celery** | Queues declared via `CELERY_QUEUES` setting. Supports routing, priority, and DLQ (`task_reject_on_worker_lost`). |
| **Google Cloud Tasks** | Queues created via API with `rateLimits`, `retryConfig`, and `stackdriverLoggingConfig`. OJS aligns with the API-driven approach. |

---

## 13. Examples

### 13.1 High-Priority Payment Queue

```json
{
  "name": "payments-critical",
  "config": {
    "max_size": 50000,
    "concurrency": 50,
    "visibility_timeout": 120,
    "default_timeout": 60,
    "overflow_policy": "reject",
    "dead_letter_queue": "payments-dlq",
    "retention": {
      "completed": "P30D",
      "discarded": "P90D"
    },
    "allowed_job_types": ["payment.*"],
    "default_retry": {
      "max_attempts": 5,
      "initial_interval": "PT1S",
      "backoff_coefficient": 2.0,
      "on_exhaustion": "dead_letter"
    }
  }
}
```

### 13.2 Bulk Processing Queue with Drop-Oldest

```json
{
  "name": "analytics-ingest",
  "config": {
    "max_size": 1000000,
    "overflow_policy": "drop_oldest",
    "concurrency": 100,
    "retention": {
      "completed": "P1D",
      "discarded": "P1D"
    },
    "default_retry": {
      "max_attempts": 1,
      "on_exhaustion": "discard"
    }
  }
}
```

### 13.3 Default Queue Policy for All Implicit Queues

```json
{
  "concurrency": 10,
  "default_timeout": 1800,
  "retention": {
    "completed": "P7D",
    "discarded": "P30D",
    "cancelled": "P7D"
  },
  "default_retry": {
    "max_attempts": 3,
    "initial_interval": "PT1S",
    "backoff_coefficient": 2.0,
    "jitter": true,
    "on_exhaustion": "dead_letter"
  }
}
```

### 13.4 Migrating Jobs Between Queues

```http
DELETE /ojs/v1/queues/legacy-emails HTTP/1.1
Content-Type: application/json

{
  "strategy": "move",
  "target_queue": "email"
}
```

All pending, available, and retryable jobs are moved from `legacy-emails` to `email`. Active jobs are allowed to complete before the queue is fully removed.

---

## Appendix A: Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0-rc.1 | 2026-02-15 | Initial release candidate. |
