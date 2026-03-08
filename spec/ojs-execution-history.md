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
   - 7.1 [Get Job History](#71-get-job-history)
   - 7.2 [Get Job Lineage](#72-get-job-lineage)
   - 7.3 [Purge Job History](#73-purge-job-history)
   - 7.4 [Search Job History](#74-search-job-history)
   - 7.5 [Aggregate Statistics](#75-aggregate-statistics)
   - 7.6 [Bulk Purge](#76-bulk-purge)
8. [Conformance Requirements](#8-conformance-requirements)
   - 8.5 [Storage Recommendations](#85-storage-recommendations)
9. [Prior Art](#9-prior-art)
   - 9.5 [History Corruption and Recovery](#95-history-corruption-and-recovery)
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

### 7.4 Search Job History

```
GET /ojs/v1/history?query={query}&start={timestamp}&end={timestamp}&event_types={types}&queues={queues}&limit=50&cursor={cursor}
```

Search across history events for all jobs. This endpoint enables operational dashboards, failure analysis, and compliance auditing without requiring external log aggregation tools.

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | OPTIONAL | Free-text search across event data (error messages, worker IDs) |
| `start` | string | OPTIONAL | RFC 3339 timestamp for range start (inclusive) |
| `end` | string | OPTIONAL | RFC 3339 timestamp for range end (exclusive) |
| `event_types` | string | OPTIONAL | Comma-separated list of event types to filter by |
| `queues` | string | OPTIONAL | Comma-separated list of queue names |
| `job_types` | string | OPTIONAL | Comma-separated list of job types |
| `actor_type` | string | OPTIONAL | Filter by actor type: `worker`, `client`, `system`, `user` |
| `limit` | integer | OPTIONAL | Max results per page (default 50, max 1000) |
| `cursor` | string | OPTIONAL | Opaque pagination cursor from previous response |

**Response** (`200 OK`):
```json
{
  "events": [
    {
      "id": "evt_01HXYZ...",
      "job_id": "01HXYZ...",
      "event_type": "job.attempt_failed",
      "timestamp": "2026-03-01T10:30:00.000Z",
      "actor": {"type": "worker", "id": "worker-abc"},
      "data": {"error": "connection refused", "attempt": 3, "will_retry": false}
    }
  ],
  "next_cursor": "eyJ0...",
  "total_estimate": 1234,
  "query_time_ms": 42
}
```

**Requirements**:

- Backends that support history search MUST support at least `start`, `end`, and `event_types` filters.
- Backends SHOULD support `query` for free-text search but MAY return HTTP `501 Not Implemented` if full-text search is not available.
- Search results MUST be ordered by `timestamp` descending (newest first).
- The `total_estimate` field MAY be an approximation for performance reasons. Exact counts require scanning the full result set, which is impractical for large histories.
- When `limit` exceeds 1000, backends MUST clamp the value to 1000 and SHOULD include a `X-OJS-Limit-Clamped: true` response header.
- The `cursor` value is opaque to clients. Backends MUST NOT require clients to understand cursor internals, and cursors SHOULD remain valid for at least 5 minutes after issuance.

> *Rationale*: History search enables operational dashboards, failure analysis across jobs, and compliance auditing without requiring external log aggregation tools. Cursor-based pagination provides stable iteration over result sets that may change between pages.

### 7.5 Aggregate Statistics

```
GET /ojs/v1/history/stats?start={timestamp}&end={timestamp}&queues={queues}&group_by=hour
```

Return time-bucketed aggregate statistics over history events. This endpoint enables throughput monitoring, trend analysis, and SLO tracking without querying individual events.

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start` | string | OPTIONAL | RFC 3339 timestamp for range start (inclusive) |
| `end` | string | OPTIONAL | RFC 3339 timestamp for range end (exclusive) |
| `queues` | string | OPTIONAL | Comma-separated list of queue names |
| `job_types` | string | OPTIONAL | Comma-separated list of job types |
| `group_by` | string | OPTIONAL | Bucketing granularity: `minute`, `hour`, `day` (default `hour`) |

**Response** (`200 OK`):
```json
{
  "buckets": [
    {
      "timestamp": "2026-03-01T10:00:00Z",
      "events": {
        "job.created": 150,
        "job.attempt_completed": 142,
        "job.attempt_failed": 8,
        "job.discarded": 2
      },
      "avg_duration_ms": 1234,
      "p95_duration_ms": 4567
    }
  ]
}
```

**Requirements**:

- Backends MAY implement aggregate statistics. This endpoint is OPTIONAL.
- If implemented, `group_by` MUST support: `minute`, `hour`, `day`.
- Backends SHOULD pre-compute or cache aggregates for commonly queried ranges to avoid full table scans.
- `avg_duration_ms` and `p95_duration_ms` MUST be computed from `job.attempt_completed` events within each bucket.
- If no events exist for a requested bucket, backends MAY omit the bucket or return it with zero counts.

> *Rationale*: Time-series aggregates enable throughput monitoring and trend analysis without querying individual events. Pre-computed rollups keep dashboard queries fast even with billions of history events.

### 7.6 Bulk Purge

```
DELETE /ojs/v1/history?before={timestamp}&queues={queues}&event_types={types}
```

Purge history events in bulk based on time and filter criteria. Unlike per-job purge (Section 7.3), this endpoint operates across all jobs.

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `before` | string | REQUIRED | RFC 3339 timestamp; purge events with `timestamp` older than this value |
| `queues` | string | OPTIONAL | Comma-separated list of queue names to restrict purge scope |
| `event_types` | string | OPTIONAL | Comma-separated list of event types to restrict purge scope |

**Response** (`200 OK`):
```json
{
  "purged": true,
  "events_purged": 15234,
  "async": false
}
```

If the purge is executed asynchronously:
```json
{
  "purged": false,
  "estimated_events": 1500000,
  "async": true,
  "status_url": "/ojs/v1/history/purge-status/01HPURGE..."
}
```

**Requirements**:

- Backends MUST support the `before` parameter (RFC 3339 timestamp). Events with a `timestamp` strictly older than this value MUST be purged.
- Backends SHOULD support `queues` and `event_types` filters for targeted purge.
- The response MUST include a count of purged events (or an estimate if running asynchronously).
- Backends MUST NOT block other operations during purge. For large purges (more than 100,000 events), backends SHOULD execute the purge asynchronously and return a `status_url` for polling.
- When running asynchronously, backends SHOULD support a `GET {status_url}` endpoint returning `{"status": "running"|"completed"|"failed", "events_purged": N}`.

> *Rationale*: Compliance requirements (GDPR right to erasure) and storage management require bulk purge capability. Asynchronous execution prevents long-running DELETE operations from blocking the API.

## 8. Conformance Requirements

Implementations claiming conformance with this extension:

- MUST record all lifecycle events defined in Section 3.1
- MUST support the history retrieval endpoint (Section 7.1)
- MUST support configurable retention (Section 6)
- MUST support per-job history purge (Section 7.3)
- SHOULD support lineage queries (Section 7.2)
- SHOULD support workflow events (Section 3.3) when the Workflows extension is active
- MAY support history search across jobs
- MAY support aggregate statistics (Section 7.5)
- MAY support bulk purge (Section 7.6)

### 8.5 Storage Recommendations

This section provides non-normative guidance for backend implementers. History data grows significantly larger than active job data over time, and storage strategy directly impacts both query performance and job processing latency.

**General Guidance**:

- Backends SHOULD NOT store history events in the same data structure as active jobs. Mixing hot-path job data with append-only history degrades both read and write performance as history accumulates.
- History tables or collections SHOULD be indexed on `(job_id, timestamp)` at minimum to support the per-job history endpoint (Section 7.1).
- For backends that support search (Section 7.4), an additional index on `(timestamp, event_type)` is RECOMMENDED.

> *Rationale*: History can grow orders of magnitude larger than active job data. Separating storage ensures history queries don't impact job processing latency.

**Redis Backends**:

- SHOULD use sorted sets keyed by `history:{job_id}` with `score = timestamp` (Unix milliseconds) for efficient time-range queries and automatic ordering.
- SHOULD use a secondary sorted set `history:global` with `score = timestamp` and `member = event_id` to support cross-job search (Section 7.4).
- For retention enforcement, SHOULD use `ZRANGEBYSCORE` with periodic cleanup rather than per-event TTL to enable batch deletion.
- MAY use Redis Streams as an alternative for append-heavy workloads, leveraging automatic ID-based ordering and consumer group support.

**PostgreSQL Backends**:

- SHOULD use a partitioned table by timestamp (e.g., monthly partitions) for efficient purge via `DROP PARTITION` and fast range queries.
- SHOULD add a GIN index on the `data` column (cast to `jsonb`) to support free-text search across event payloads.
- SHOULD use `BRIN` indexes on the `timestamp` column for large partitions where B-tree indexes become impractical.
- For aggregate statistics (Section 7.5), SHOULD maintain a materialized view or rollup table refreshed periodically.

**High-Throughput Systems**:

- SHOULD consider write-ahead buffering (batch inserts every 100ms or every 100 events, whichever comes first) to reduce per-event write overhead.
- MAY use an in-memory ring buffer that flushes to persistent storage asynchronously, accepting the risk of losing recent events on crash.
- For systems processing more than 10,000 events per second, SHOULD implement event sampling as described in Section 6 (record 1 in N events) for non-critical event types such as `job.progress`.

## 9. Prior Art

- **Temporal** — Full event-sourced execution history with deterministic replay. More powerful but requires all code to be deterministic.
- **Oban Pro (Elixir)** — Job execution recording with structured metadata. Closest analog to this extension.
- **Sidekiq Pro** — Job execution history with web UI timeline. Limited to Ruby ecosystem.
- **Inngest** — Function run logs with step-level detail. Tightly coupled to their platform.

### 9.5 History Corruption and Recovery

History is a supporting feature, not a critical-path component. Backends MUST ensure that history failures never block or degrade job processing operations.

**Failure Isolation**:

- Backends MUST NOT fail job operations (`push`, `fetch`, `ack`, `nack`) if history recording fails. History recording is best-effort.
- If history storage becomes unavailable, backends MUST continue processing jobs normally and SHOULD emit structured log warnings at a rate-limited interval (no more than once per minute per backend instance).
- Backends SHOULD track a metric `ojs_history_write_failures_total` (counter) to expose history recording failures to monitoring systems.

> *Rationale*: A corrupt or unavailable history store must never prevent job processing. Jobs represent business-critical work; history exists to support observability and debugging.

**History Rebuild**:

Backends SHOULD support reconstructing history from a job's current state when history data is lost or corrupted.

```
POST /ojs/v1/history/rebuild?job_id={id}
```

**Response** (`200 OK`):
```json
{
  "job_id": "01HXYZ...",
  "events_reconstructed": 4,
  "approximate": true,
  "gaps": ["attempt timestamps between attempt 1 and attempt 3 are estimated"]
}
```

**Requirements**:

- The rebuild endpoint SHOULD reconstruct history events from the job's current state, including: creation metadata, attempt count, error history, and current state.
- History reconstruction MAY produce approximate timestamps based on available metadata. The `approximate` field MUST be `true` when any reconstructed event uses an estimated timestamp.
- Reconstructed events SHOULD include a `"reconstructed": true` field in their `metadata` object to distinguish them from original events.
- Backends MAY limit rebuild to jobs that still exist in the system (not yet purged from the job store).

> *Rationale*: History reconstruction provides a recovery path for operators who discover gaps in their audit trail. Approximate timestamps are preferable to no history at all for debugging and compliance purposes.

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

### 10.3 Searching for Failures

```bash
# Find all failures in the last hour
curl "http://localhost:8080/ojs/v1/history?event_types=job.attempt_failed,job.discarded&start=2026-03-01T09:00:00Z&end=2026-03-01T10:00:00Z&limit=20"

# Output:
# {
#   "events": [
#     {
#       "id": "evt_01HFAIL1...",
#       "job_id": "01HJOB1...",
#       "event_type": "job.attempt_failed",
#       "timestamp": "2026-03-01T09:45:12.000Z",
#       "actor": {"type": "worker", "id": "worker-xyz"},
#       "data": {"error": "connection refused", "attempt": 3, "will_retry": false}
#     },
#     {
#       "id": "evt_01HFAIL2...",
#       "job_id": "01HJOB2...",
#       "event_type": "job.discarded",
#       "timestamp": "2026-03-01T09:30:05.000Z",
#       "data": {"total_attempts": 5, "last_error": "SMTP timeout"}
#     }
#   ],
#   "next_cursor": null,
#   "total_estimate": 2,
#   "query_time_ms": 18
# }

# Search for a specific error message across all jobs
curl "http://localhost:8080/ojs/v1/history?query=SMTP+timeout&event_types=job.attempt_failed&limit=100"
```

### 10.4 Compliance Audit Export

```bash
# Export all history for a specific queue in a time range (for SOC2 audit)
curl "http://localhost:8080/ojs/v1/history?queues=payments&start=2026-01-01T00:00:00Z&end=2026-04-01T00:00:00Z&limit=1000" > audit-q1.json

# Paginate through all results using cursor
CURSOR=""
while true; do
  RESPONSE=$(curl -s "http://localhost:8080/ojs/v1/history?queues=payments&start=2026-01-01T00:00:00Z&end=2026-04-01T00:00:00Z&limit=1000&cursor=$CURSOR")
  echo "$RESPONSE" >> audit-q1-full.json
  CURSOR=$(echo "$RESPONSE" | jq -r '.next_cursor // empty')
  [ -z "$CURSOR" ] && break
done

# Bulk purge history older than 90 days (retention policy enforcement)
curl -X DELETE "http://localhost:8080/ojs/v1/history?before=2025-12-01T00:00:00Z"
```
