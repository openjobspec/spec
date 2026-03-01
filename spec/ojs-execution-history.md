# Open Job Spec: Execution History Extension

| Field        | Value                                    |
|-------------|------------------------------------------|
| **Title**   | OJS Execution History                    |
| **Version** | 0.1.0                                    |
| **Date**    | 2026-03-04                               |
| **Status**  | Draft                                    |
| **Maturity** | Experimental                             |
| **Layer**   | Extension                                |
| **URI**     | `urn:ojs:ext:execution-history`          |
| **Requires**| OJS Core Specification (Layer 1)         |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Event Types](#3-event-types)
4. [History Record Structure](#4-history-record-structure)
5. [Lineage Model](#5-lineage-model)
6. [Retention Policies](#6-retention-policies)
7. [HTTP Binding](#7-http-binding)
8. [Conformance Requirements](#8-conformance-requirements)
9. [Prior Art](#9-prior-art)
10. [Examples](#10-examples)

---

## 1. Introduction

Production job processing systems require audit trails, debugging tools, and compliance-grade record keeping. Without execution history, operators cannot answer fundamental questions: "Why did this job fail?", "How many times was it retried?", "Who cancelled it?", "What was the execution timeline?"

This extension defines a standard for recording, storing, and querying job execution history. It addresses three use cases:

1. **Operational debugging** — Understanding why a job failed, how long each attempt took, and what state transitions occurred.
2. **Compliance auditing** — Satisfying SOC 2 Type II, GDPR, and HIPAA requirements for data access audit trails.
3. **Lineage tracking** — Understanding parent-child relationships between jobs, workflow membership, and job provenance.

> *Rationale*: Temporal's full execution history is its most cited advantage over traditional job queues. This extension brings structured history to OJS without requiring deterministic replay, providing 80% of the value with 20% of the complexity.

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt).

## 3. Event Types

### 3.1 Lifecycle Events

Backends MUST record the following events when they occur:

| Event Type | Trigger | Required Data Fields |
|------------|---------|---------------------|
| `job.created` | PUSH operation completes | `queue`, `type`, `args_size_bytes` |
| `job.state_changed` | Any state transition | `from`, `to` |
| `job.attempt_started` | Worker begins processing | `worker_id`, `attempt` |
| `job.attempt_completed` | Worker ACKs successfully | `duration_ms`, `attempt` |
| `job.attempt_failed` | Worker NACKs | `error`, `will_retry`, `attempt` |
| `job.cancelled` | CANCEL operation | `reason` (optional) |
| `job.discarded` | Max retries exceeded | `total_attempts`, `last_error` |

> *Rationale*: These events capture the complete lifecycle of a job from creation through terminal state. Each event type maps directly to a core OJS operation, ensuring coverage without ambiguity.

### 3.2 Optional Events

Backends MAY record the following events:

| Event Type | Trigger | Required Data Fields |
|------------|---------|---------------------|
| `job.checkpoint_saved` | Durable execution checkpoint | `sequence`, `size_bytes` |
| `job.progress` | Progress report | `percent`, `message` |
| `job.purged` | Data deletion (GDPR) | — |

### 3.3 Workflow Events

When the Workflows extension is active, backends MUST record:

| Event Type | Trigger | Required Data Fields |
|------------|---------|---------------------|
| `workflow.created` | Workflow creation | `workflow_type`, `total_jobs` |
| `workflow.step_completed` | Chain step completes | `step_index`, `job_id` |
| `workflow.completed` | All workflow jobs done | `duration_ms`, `status` |

## 4. History Record Structure

Each history event MUST be represented as a JSON object with the following fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | REQUIRED | Unique event identifier (UUIDv7 RECOMMENDED) |
| `job_id` | string | REQUIRED | Job ID this event relates to |
| `event_type` | string | REQUIRED | One of the event types defined in Section 3 |
| `timestamp` | string | REQUIRED | RFC 3339 timestamp with timezone |
| `actor` | object | OPTIONAL | Who triggered the event |
| `data` | object | OPTIONAL | Event-specific payload |
| `metadata` | object | OPTIONAL | Request context (request_id, ip) |

> *Rationale*: The structure mirrors CloudEvents for familiarity. The `actor` field enables audit trail requirements by identifying whether a state change was triggered by a worker, client, system timer, or human operator.

### 4.1 Actor Object

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | One of: `worker`, `client`, `system`, `user` |
| `id` | string | Worker ID, API key hash prefix, or user identifier |

## 5. Lineage Model

To support parent-child tracking and workflow membership, the core Job envelope MAY include the following optional attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `parent_id` | string | UUIDv7 of the job that spawned this job |
| `workflow_id` | string | UUIDv7 of the workflow this job belongs to |
| `root_id` | string | UUIDv7 of the root ancestor in a job chain |

These fields MUST be preserved by backends that support them and MUST be returned in job responses.

> *Rationale*: Lineage enables debugging of complex job graphs. `root_id` allows tracing back to the original trigger in deeply nested chains without recursive queries.

## 6. Retention Policies

Backends MUST support configurable retention:

| Configuration | Default | Description |
|---------------|---------|-------------|
| `OJS_HISTORY_ENABLED` | `true` | Enable or disable history recording |
| `OJS_HISTORY_RETENTION_DAYS` | `30` | Days to retain history events |
| `OJS_HISTORY_MAX_EVENTS_PER_JOB` | `1000` | Maximum events stored per job |

Backends SHOULD support a background process that purges expired history events.

Backends MAY support per-queue retention overrides and sampling (record 1 in N events) for high-throughput queues.

> *Rationale*: Unbounded history storage is the primary concern for high-throughput systems. Sensible defaults (30 days, 1000 events) cover most debugging and compliance needs while bounding storage costs.

## 7. HTTP Binding

### 7.1 Get Job History

```
GET /ojs/v1/jobs/{id}/history?limit=50&cursor={cursor}
```

**Response** (`200 OK`):
```json
{
  "events": [
    {
      "id": "evt_01HXYZ...",
      "job_id": "01HXYZ...",
      "event_type": "job.state_changed",
      "timestamp": "2026-03-01T10:30:00.000Z",
      "actor": {"type": "worker", "id": "worker-abc"},
      "data": {"from": "active", "to": "completed"}
    }
  ],
  "next_cursor": "eyJ0...",
  "total": 5
}
```

### 7.2 Get Job Lineage

```
GET /ojs/v1/jobs/{id}/lineage
```

**Response** (`200 OK`):
```json
{
  "job_id": "01HXYZ...",
  "parent_id": "01HABC...",
  "workflow_id": "01HWKF...",
  "root_id": "01HABC...",
  "children": [
    {"job_id": "01HCHILD1...", "children": []},
    {"job_id": "01HCHILD2...", "children": []}
  ]
}
```

### 7.3 Purge Job History

```
DELETE /ojs/v1/jobs/{id}/history
```

**Response** (`200 OK`):
```json
{
  "deleted": true,
  "events_deleted": 5
}
```

## 8. Conformance Requirements

Implementations claiming conformance with this extension:

- MUST record all lifecycle events defined in Section 3.1
- MUST support the history retrieval endpoint (Section 7.1)
- MUST support configurable retention (Section 6)
- MUST support per-job history purge (Section 7.3)
- SHOULD support lineage queries (Section 7.2)
- SHOULD support workflow events (Section 3.3) when the Workflows extension is active
- MAY support history search across jobs

## 9. Prior Art

- **Temporal** — Full event-sourced execution history with deterministic replay. More powerful but requires all code to be deterministic.
- **Oban Pro (Elixir)** — Job execution recording with structured metadata. Closest analog to this extension.
- **Sidekiq Pro** — Job execution history with web UI timeline. Limited to Ruby ecosystem.
- **Inngest** — Function run logs with step-level detail. Tightly coupled to their platform.

## 10. Examples

### 10.1 Debugging a Failed Job

```bash
# Get the execution timeline
curl http://localhost:8080/ojs/v1/jobs/01HXYZ.../history | jq '.events[] | {event_type, timestamp, data}'

# Output:
# {"event_type": "job.created", "timestamp": "2026-03-01T10:00:00Z", "data": {"queue": "emails"}}
# {"event_type": "job.state_changed", "timestamp": "2026-03-01T10:00:01Z", "data": {"from": "available", "to": "active"}}
# {"event_type": "job.attempt_failed", "timestamp": "2026-03-01T10:00:05Z", "data": {"error": "SMTP timeout", "attempt": 1, "will_retry": true}}
# {"event_type": "job.state_changed", "timestamp": "2026-03-01T10:00:05Z", "data": {"from": "active", "to": "retryable"}}
# {"event_type": "job.state_changed", "timestamp": "2026-03-01T10:01:05Z", "data": {"from": "retryable", "to": "available"}}
# {"event_type": "job.attempt_failed", "timestamp": "2026-03-01T10:01:10Z", "data": {"error": "SMTP timeout", "attempt": 2, "will_retry": false}}
# {"event_type": "job.discarded", "timestamp": "2026-03-01T10:01:10Z", "data": {"total_attempts": 2, "last_error": "SMTP timeout"}}
```

### 10.2 GDPR Data Purge

```bash
# Delete all history for a specific job (right to erasure)
curl -X DELETE http://localhost:8080/ojs/v1/jobs/01HXYZ.../history
```
