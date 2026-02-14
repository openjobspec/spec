# Open Job Spec: Dead Letter Queue Specification

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Dead Letter Queue Specification            |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-13                                     |
| **Status**  | Release Candidate                              |
| **Tier**    | Official Extension                             |
| **URI**     | `urn:ojs:ext:dead-letter`                      |
| **Requires**| OJS Core Specification (Layer 1), OJS Retry Specification |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Dead Letter Semantics](#4-dead-letter-semantics)
5. [Retention Policies](#5-retention-policies)
6. [Manual Retry](#6-manual-retry)
7. [Automatic Replay](#7-automatic-replay)
8. [Pruning](#8-pruning)
9. [Dead Letter Inspection](#9-dead-letter-inspection)
10. [HTTP Binding](#10-http-binding)
11. [Observability](#11-observability)
12. [Conformance Requirements](#12-conformance-requirements)
13. [Prior Art](#13-prior-art)
14. [Examples](#14-examples)

---

## 1. Introduction

Every background job system MUST answer the question: what happens when all retries are exhausted? The job is permanently failed, but the data it carries -- the customer order, the payment attempt, the notification -- still has business value. Simply discarding it is unacceptable in production systems.

The dead letter queue (DLQ) is the holding area for jobs that have exhausted all retry attempts. It preserves the full job envelope and error history for inspection, manual retry, and debugging. Sidekiq retains dead jobs for 6 months and limits the set to 10,000 entries. Oban's Lifeline plugin rescues orphaned jobs. Every production deployment eventually needs DLQ management.

The OJS core specification defines the `discarded` state as a terminal state for permanently failed jobs. The retry specification defines the `on_exhaustion` field with `"dead_letter"` as an option. This specification brings those concepts together into a complete dead letter management system.

### 1.1 Scope

This specification defines:

- When and how jobs enter the dead letter queue.
- Retention policies (time-based and count-based).
- Manual retry of individual and bulk dead letter jobs.
- Automatic replay rules.
- Pruning strategies.
- Inspection and search of dead letter jobs.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term                | Definition                                                                                       |
|---------------------|--------------------------------------------------------------------------------------------------|
| dead letter queue   | A holding area for jobs that have exhausted all retry attempts or been explicitly discarded.      |
| dead letter job     | A job in the `discarded` state that is stored in the dead letter queue.                           |
| retention policy    | Rules governing how long dead letter jobs are kept before automatic pruning.                      |
| manual retry        | The act of re-enqueuing a dead letter job for another execution attempt.                         |
| automatic replay    | Rule-based re-enqueuing of dead letter jobs matching specific criteria.                          |
| pruning             | The automatic removal of dead letter jobs that have exceeded retention limits.                    |

---

## 4. Dead Letter Semantics

### 4.1 Entry Conditions

A job enters the dead letter queue when:

1. **Retry exhaustion with `on_exhaustion: "dead_letter"`**: The job has failed `max_attempts` times and the retry policy specifies dead letter as the exhaustion action. This is the most common path.

2. **Explicit discard by handler**: The handler returns a `DEAD_LETTER` error response code, sending the job directly to the DLQ regardless of remaining retry attempts.

3. **Non-retryable error**: The error type matches `non_retryable_errors` in the retry policy, AND the retry policy specifies `on_exhaustion: "dead_letter"`.

When a job enters the DLQ:
- The job's state MUST be set to `discarded`.
- The `discarded_at` timestamp MUST be set.
- The full error history (all attempts) MUST be preserved.
- The original job envelope (type, args, meta, queue) MUST be preserved unmodified.

### 4.2 Discard vs. Dead Letter

The OJS retry specification defines two exhaustion actions:

| Action       | Behavior                                                              |
|--------------|-----------------------------------------------------------------------|
| `discard`    | Job is moved to `discarded` state. MAY be pruned immediately.        |
| `dead_letter`| Job is moved to `discarded` state. MUST be retained in the DLQ for the configured retention period. |

Implementations MUST distinguish between discarded jobs (can be pruned) and dead-lettered jobs (must be retained). This distinction enables operators to configure different retention for each.

---

## 5. Retention Policies

### 5.1 Configuration

Dead letter retention is configured at the queue level and/or globally:

```json
{
  "dead_letter": {
    "retention": {
      "max_age": "P180D",
      "max_count": 10000
    }
  }
}
```

| Field                          | Type    | Default   | Description                                              |
|--------------------------------|---------|-----------|----------------------------------------------------------|
| `dead_letter.retention.max_age`| string  | `"P180D"` | ISO 8601 duration. Jobs older than this are pruned.      |
| `dead_letter.retention.max_count`| integer| `10000`  | Maximum dead letter jobs retained. Oldest pruned first.  |

When both limits are configured, the most restrictive applies. A job is pruned when it exceeds **either** limit.

### 5.2 Defaults

The default retention mirrors Sidekiq's proven defaults:

- **Max age**: 180 days (6 months). Long enough for post-mortems and auditing.
- **Max count**: 10,000 jobs. Prevents unbounded growth.

Implementations MUST apply a retention policy. Unbounded dead letter queues are a storage risk.

**Rationale**: Dead letter jobs accumulate in every production system. Without retention limits, the DLQ grows indefinitely, consuming storage and degrading query performance. Sidekiq's 6-month / 10,000 defaults have been validated across thousands of production deployments.

### 5.3 Per-Queue Configuration

Retention policies MAY be configured per-queue to accommodate different compliance requirements:

```json
{
  "queue": "billing",
  "dead_letter": {
    "retention": {
      "max_age": "P365D",
      "max_count": 50000
    }
  }
}
```

---

## 6. Manual Retry

### 6.1 Individual Retry

Operators can re-enqueue a single dead letter job:

```http
POST /ojs/v1/dead-letter/{id}/retry
```

When retried:
- The job's state changes from `discarded` to `available`.
- The `attempt` counter is reset to 0.
- The retry policy is preserved (the job gets fresh retry attempts).
- The error history is preserved (for debugging if the job fails again).
- A new `enqueued_at` timestamp is set.
- The original `id` is preserved (for traceability).

### 6.2 Bulk Retry

Operators can retry multiple dead letter jobs matching a filter:

```http
POST /ojs/v1/dead-letter/retry
Content-Type: application/json

{
  "filter": {
    "queue": "billing",
    "type": "invoice.generate",
    "since": "2026-02-12T00:00:00Z",
    "error_type": "DatabaseConnectionError"
  },
  "confirm": true
}
```

This is the most common DLQ operation: after deploying a fix for a bug, retry all jobs that failed with that specific error.

### 6.3 Retry with Modifications

Operators MAY retry a dead letter job with modified arguments or options:

```http
POST /ojs/v1/dead-letter/{id}/retry
Content-Type: application/json

{
  "override": {
    "queue": "billing-retry",
    "meta": { "retry_source": "manual_dlq_retry" },
    "retry": { "max_attempts": 1 }
  }
}
```

**Rationale**: Sometimes a dead letter job needs small adjustments before retry (e.g., routing to a different queue, reducing retry attempts for manual monitoring, or adding metadata for tracking).

---

## 7. Automatic Replay

### 7.1 Replay Rules

Implementations MAY support automatic replay rules that re-enqueue dead letter jobs matching specific criteria after a configurable delay:

```json
{
  "replay_rules": [
    {
      "name": "retry-connection-errors",
      "filter": {
        "error_type": "ConnectionError"
      },
      "delay": "PT1H",
      "max_replays": 3,
      "enabled": true
    }
  ]
}
```

| Field          | Type    | Description                                                           |
|----------------|---------|-----------------------------------------------------------------------|
| `name`         | string  | Human-readable name for the rule.                                     |
| `filter`       | object  | Criteria for matching dead letter jobs (same as bulk retry filter).   |
| `delay`        | string  | ISO 8601 duration to wait before replaying.                           |
| `max_replays`  | integer | Maximum times a job can be replayed by this rule.                     |
| `enabled`      | boolean | Whether the rule is active.                                           |

### 7.2 Replay Tracking

Each dead letter job MUST track how many times it has been replayed (to enforce `max_replays`):

```json
{
  "meta": {
    "ojs.replay_count": 2,
    "ojs.last_replayed_at": "2026-02-13T12:00:00Z",
    "ojs.replay_rule": "retry-connection-errors"
  }
}
```

---

## 8. Pruning

### 8.1 Pruning Strategy

Implementations MUST run a pruning process that removes dead letter jobs exceeding retention limits.

The pruning process SHOULD:

1. Run periodically (RECOMMENDED: every 5 minutes).
2. Remove jobs older than `max_age` first.
3. If count still exceeds `max_count`, remove oldest jobs until under the limit.
4. Emit a `dead_letter.pruned` event with the count of removed jobs.

### 8.2 Pruning and Compliance

For compliance-sensitive queues, implementations SHOULD support a `pruning_policy` that controls what happens to pruned data:

| Policy             | Behavior                                                           |
|--------------------|--------------------------------------------------------------------|
| `delete`           | Permanently remove the job. Default.                               |
| `archive`          | Move to a cold storage archive before deletion.                    |

**Rationale**: Financial services and healthcare regulations may require audit trails. The archive policy enables compliance without keeping the DLQ unbounded.

---

## 9. Dead Letter Inspection

### 9.1 Search and Filter

Dead letter jobs MUST be searchable by:

- **Queue**: Which queue the job originated from.
- **Type**: The job type.
- **Error type**: The error class/type from the most recent failure.
- **Time range**: When the job was discarded.
- **Args content**: Substring or JSON path match within job arguments (RECOMMENDED).

### 9.2 Job Detail

Each dead letter job MUST expose the full error history:

```json
{
  "id": "019503e1-7b2a-7000-8000-000000000001",
  "type": "invoice.generate",
  "queue": "billing",
  "args": [{ "customer_id": "cust_123", "amount": 9999 }],
  "state": "discarded",
  "attempt": 3,
  "max_attempts": 3,
  "errors": [
    {
      "attempt": 1,
      "type": "DatabaseConnectionError",
      "message": "connection refused to billing-db:5432",
      "backtrace": ["at db.go:142", "at handler.go:58"],
      "occurred_at": "2026-02-13T10:00:03Z"
    },
    {
      "attempt": 2,
      "type": "DatabaseConnectionError",
      "message": "connection timeout to billing-db:5432",
      "occurred_at": "2026-02-13T10:01:05Z"
    },
    {
      "attempt": 3,
      "type": "DatabaseConnectionError",
      "message": "connection refused to billing-db:5432",
      "occurred_at": "2026-02-13T10:03:09Z"
    }
  ],
  "metadata": {
    "created_at": "2026-02-13T10:00:00Z",
    "discarded_at": "2026-02-13T10:03:09Z"
  }
}
```

---

## 10. HTTP Binding

| Method | Path                                | Description                           |
|--------|-------------------------------------|---------------------------------------|
| GET    | `/ojs/v1/dead-letter`               | List dead letter jobs (paginated).    |
| GET    | `/ojs/v1/dead-letter/{id}`          | Get dead letter job detail.           |
| POST   | `/ojs/v1/dead-letter/{id}/retry`    | Retry a single dead letter job.       |
| POST   | `/ojs/v1/dead-letter/retry`         | Bulk retry with filter.               |
| DELETE | `/ojs/v1/dead-letter/{id}`          | Delete a single dead letter job.      |
| DELETE | `/ojs/v1/dead-letter`               | Purge dead letter jobs (with filter). |
| GET    | `/ojs/v1/dead-letter/stats`         | DLQ statistics.                       |

### 10.1 DLQ Statistics

```http
GET /ojs/v1/dead-letter/stats
```

```json
{
  "total": 847,
  "by_queue": {
    "billing": 312,
    "email": 201,
    "default": 334
  },
  "by_error_type": {
    "DatabaseConnectionError": 412,
    "TimeoutError": 198,
    "ValidationError": 142,
    "Unknown": 95
  },
  "oldest_at": "2026-01-15T10:00:00Z",
  "newest_at": "2026-02-13T10:03:09Z",
  "retention": {
    "max_age": "P180D",
    "max_count": 10000,
    "next_prune_at": "2026-02-13T12:05:00Z"
  }
}
```

---

## 11. Observability

### 11.1 Events

| Event Type                  | Trigger                                              |
|-----------------------------|------------------------------------------------------|
| `dead_letter.added`         | A job enters the dead letter queue.                  |
| `dead_letter.retried`       | A dead letter job is manually retried.               |
| `dead_letter.replayed`      | A dead letter job is automatically replayed.         |
| `dead_letter.pruned`        | Dead letter jobs are pruned by the retention policy. |
| `dead_letter.deleted`       | A dead letter job is manually deleted.               |

### 11.2 Metrics

| Metric Name                       | Type    | Labels       | Description                            |
|-----------------------------------|---------|--------------|----------------------------------------|
| `ojs.dead_letter.total`           | Gauge   | `queue`      | Current DLQ size per queue.            |
| `ojs.dead_letter.added_total`     | Counter | `queue`,`type`| Total jobs added to DLQ.             |
| `ojs.dead_letter.retried_total`   | Counter | `queue`      | Total manual retries from DLQ.         |
| `ojs.dead_letter.pruned_total`    | Counter | `queue`      | Total jobs pruned from DLQ.            |

---

## 12. Conformance Requirements

An implementation declaring support for the dead-letter extension MUST support:

| ID           | Requirement                                                                    |
|--------------|--------------------------------------------------------------------------------|
| DLQ-001      | Jobs with `on_exhaustion: "dead_letter"` enter the DLQ on retry exhaustion.   |
| DLQ-002      | Full error history preserved for dead letter jobs.                             |
| DLQ-003      | Manual retry of individual dead letter jobs.                                   |
| DLQ-004      | Retention policy with `max_age` and `max_count`.                              |
| DLQ-005      | Periodic pruning of expired dead letter jobs.                                  |
| DLQ-006      | DLQ listing with pagination and filtering by queue and type.                   |

Recommended:

| ID           | Requirement                                                                    |
|--------------|--------------------------------------------------------------------------------|
| DLQ-R001     | Bulk retry with filter.                                                        |
| DLQ-R002     | Retry with modifications (override args, queue, meta).                         |
| DLQ-R003     | Automatic replay rules.                                                        |
| DLQ-R004     | DLQ statistics endpoint.                                                       |
| DLQ-R005     | Error type filtering in DLQ search.                                            |

---

## 13. Prior Art

| System           | DLQ Approach                                                                              |
|------------------|-------------------------------------------------------------------------------------------|
| **Sidekiq**      | "Dead" set retained for 6 months, max 10,000. Manual retry via Web UI. `DeadSet` API.    |
| **Oban**         | `discarded` state. Lifeline plugin rescues orphaned jobs. Oban Web for DLQ management.   |
| **BullMQ**       | Failed jobs stay in "failed" list. Manual retry via API. No automatic pruning.            |
| **Celery**       | No built-in DLQ. Failed tasks logged. Custom result backend can store failures.           |
| **AWS SQS**      | First-class DLQ support. `RedrivePolicy` with `maxReceiveCount`. Redrive to source queue. |
| **RabbitMQ**     | DLQ via `x-dead-letter-exchange`. Per-queue DLQ routing with reason headers.              |

AWS SQS's `RedrivePolicy` (redrive from DLQ back to source queue) is the closest prior art for automatic replay. OJS extends this with filter-based rules and replay count limits.

---

## Appendix A: Changelog

| Date       | Change                        |
|------------|-------------------------------|
| 2026-02-13 | Initial release candidate.    |
