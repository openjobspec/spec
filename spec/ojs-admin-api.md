# Open Job Spec: Admin and Operator API

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Admin API Specification                    |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-13                                     |
| **Status**  | Release Candidate                              |
| **Tier**    | Official Extension                             |
| **URI**     | `urn:ojs:ext:admin-api`                        |
| **Requires**| OJS Core Specification (Layer 1), OJS HTTP Binding (Layer 3) |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Design Principles](#4-design-principles)
5. [API Structure](#5-api-structure)
6. [Queue Management](#6-queue-management)
7. [Job Inspection and Search](#7-job-inspection-and-search)
8. [Bulk Operations](#8-bulk-operations)
9. [Worker Management](#9-worker-management)
10. [Metrics and Statistics](#10-metrics-and-statistics)
11. [Dead Letter Management](#11-dead-letter-management)
12. [System Operations](#12-system-operations)
13. [Authentication and Authorization](#13-authentication-and-authorization)
14. [Conformance Requirements](#14-conformance-requirements)
15. [Prior Art](#15-prior-art)
16. [Examples](#16-examples)

---

## 1. Introduction

Every mature infrastructure system separates its core data-plane API from its admin/control-plane API. Temporal cleanly divides WorkflowService (application-facing) from OperatorService (admin-only). Kubernetes uses API groups to separate workload resources from admin resources. Kafka defines five distinct APIs: Producer, Consumer, Admin Client, Streams, and Connect.

The OJS core specification (ojs-core.md) and HTTP binding (ojs-http-binding.md) define the **data-plane API** -- the interface that application code and SDKs use to enqueue jobs, fetch jobs, and report results. This document defines the **control-plane API** -- the interface that dashboards, CLI tools, monitoring systems, and operations teams use to inspect, manage, and operate an OJS deployment.

### 1.1 Why a Separate Admin API

The data-plane and control-plane serve fundamentally different users with different access patterns:

| Dimension          | Data Plane                    | Control Plane (Admin API)           |
|--------------------|-------------------------------|-------------------------------------|
| Primary users      | Application code, SDKs        | Operators, dashboards, CLI tools    |
| Access pattern     | High-frequency, low-latency   | Low-frequency, can tolerate latency |
| Authorization      | Service-level credentials     | Operator-level credentials, RBAC    |
| Operations         | Enqueue, fetch, ack, fail     | Inspect, search, pause, purge, bulk |
| Idempotency needs  | Critical (double-ack, etc.)   | Important but less critical         |

### 1.2 Scope

This specification defines:

- Queue management operations (pause, resume, configure, purge).
- Job inspection and search (filter, list, detail).
- Bulk operations (retry-all, cancel-all, clean).
- Worker management (list, inspect, deregister stale workers).
- Aggregate metrics and statistics.
- Dead letter queue management.
- System-level operations (maintenance mode).

This specification does **not** define:

- Data-plane operations (enqueue, fetch, ack, fail) -- see ojs-http-binding.md.
- Dashboard UI requirements -- this defines the API that dashboards consume.
- Authentication protocols -- this defines RBAC scopes, not auth mechanisms.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term                | Definition                                                                                  |
|---------------------|---------------------------------------------------------------------------------------------|
| control plane       | The set of APIs used to manage and observe the OJS deployment.                              |
| data plane          | The set of APIs used by application code to enqueue and process jobs.                       |
| admin endpoint      | An HTTP endpoint under the `/ojs/v1/admin/` path prefix.                                    |
| bulk operation      | An operation that acts on multiple jobs simultaneously.                                      |
| queue configuration | Server-side settings for a queue (concurrency, rate limits, pause state).                   |
| stale worker        | A worker that has not sent a heartbeat within the expected interval.                        |

---

## 4. Design Principles

1. **Separate path prefix.** All admin endpoints live under `/ojs/v1/admin/` to enable path-based access control. A reverse proxy or API gateway can restrict admin access by path without understanding OJS semantics.

2. **Read-heavy by design.** The admin API is primarily used for inspection and monitoring. Write operations (pause, purge, bulk retry) are infrequent and can tolerate higher latency.

3. **Filterable and paginated.** All list operations MUST support pagination. List operations that return jobs MUST support filtering by state, queue, type, and time range.

4. **Safe by default.** Destructive operations (purge, bulk cancel, delete) MUST require explicit confirmation. Either via a `confirm: true` field in the request body or a separate confirmation endpoint.

---

## 5. API Structure

All admin API endpoints are prefixed with `/ojs/v1/admin/`. This prefix MUST NOT overlap with data-plane endpoints.

| Category          | Endpoints                                               |
|-------------------|---------------------------------------------------------|
| Queue Management  | `/admin/queues`, `/admin/queues/{name}`                 |
| Job Inspection    | `/admin/jobs`, `/admin/jobs/{id}`                       |
| Bulk Operations   | `/admin/jobs/bulk/{action}`                             |
| Worker Management | `/admin/workers`, `/admin/workers/{id}`                 |
| Statistics        | `/admin/stats`, `/admin/stats/history`                  |
| Dead Letter       | `/admin/dead-letter`, `/admin/dead-letter/{id}`         |
| System            | `/admin/system/maintenance`, `/admin/system/config`     |

---

## 6. Queue Management

### 6.1 List Queues

```
GET /ojs/v1/admin/queues
```

Returns all known queues with summary statistics.

**Response** (200 OK):

```json
{
  "items": [
    {
      "name": "default",
      "state": "active",
      "counts": {
        "available": 142,
        "active": 12,
        "scheduled": 38,
        "retryable": 5,
        "completed": 10482,
        "discarded": 23,
        "cancelled": 7
      },
      "throughput": {
        "processed_per_minute": 87.3,
        "failed_per_minute": 2.1
      },
      "latency_ms": {
        "p50": 12,
        "p95": 45,
        "p99": 120
      },
      "paused": false,
      "created_at": "2026-01-15T10:00:00Z"
    }
  ],
  "pagination": {
    "total": 5,
    "page": 1,
    "per_page": 20
  }
}
```

Implementations MUST include at minimum the `name`, `state`, and `counts` fields for each queue.

**Rationale**: Queue listing is the entry point for every dashboard and monitoring tool. Without it, operators cannot discover what queues exist or their health status.

### 6.2 Get Queue Detail

```
GET /ojs/v1/admin/queues/{name}
```

Returns detailed information about a specific queue, including configuration and rate limits.

**Response** (200 OK):

```json
{
  "name": "email",
  "state": "active",
  "counts": {
    "available": 42,
    "active": 8,
    "scheduled": 15,
    "retryable": 2,
    "completed": 5841,
    "discarded": 12,
    "cancelled": 3
  },
  "configuration": {
    "concurrency": 20,
    "rate_limit": {
      "limit": 1000,
      "period": "PT1H"
    },
    "retention": {
      "completed": "P7D",
      "discarded": "P30D"
    }
  },
  "paused": false,
  "oldest_available_at": "2026-02-13T11:58:22Z",
  "created_at": "2026-01-15T10:00:00Z"
}
```

### 6.3 Pause Queue

```
POST /ojs/v1/admin/queues/{name}/pause
```

Pauses a queue. When paused, FETCH operations for this queue MUST return no jobs. Jobs MAY still be enqueued into a paused queue (they accumulate as `available`).

**Response** (200 OK):

```json
{
  "name": "email",
  "paused": true,
  "paused_at": "2026-02-13T12:00:00Z"
}
```

**Rationale**: Queue pause is an operational necessity for deployment, debugging, and incident response. Every production job system supports this.

### 6.4 Resume Queue

```
POST /ojs/v1/admin/queues/{name}/resume
```

Resumes a paused queue. FETCH operations begin returning jobs again.

### 6.5 Purge Queue

```
DELETE /ojs/v1/admin/queues/{name}/jobs
```

Removes jobs from a queue. Supports filtering by state.

**Request body**:

```json
{
  "states": ["completed", "discarded"],
  "older_than": "2026-02-06T00:00:00Z",
  "confirm": true
}
```

| Field        | Type     | Required | Description                                                  |
|--------------|----------|----------|--------------------------------------------------------------|
| `states`     | string[] | Yes      | States of jobs to purge.                                     |
| `older_than` | string   | No       | Only purge jobs with terminal timestamp before this time.    |
| `confirm`    | boolean  | Yes      | MUST be `true`. Safety interlock against accidental purges.  |

The `confirm` field MUST be set to `true`. Requests with `confirm: false` or missing `confirm` MUST be rejected with 400 Bad Request.

**Rationale**: Purge is a destructive, irreversible operation. The `confirm` field is a programmatic safety interlock (equivalent to "Are you sure?" in a UI). This pattern is used by AWS S3 for bucket deletion and by Terraform for resource destruction.

**Response** (200 OK):

```json
{
  "purged_count": 10482,
  "states": ["completed", "discarded"]
}
```

### 6.6 Update Queue Configuration

```
PUT /ojs/v1/admin/queues/{name}/config
```

Updates queue-level configuration. Changes take effect immediately.

```json
{
  "concurrency": 30,
  "rate_limit": {
    "limit": 2000,
    "period": "PT1H"
  },
  "retention": {
    "completed": "P14D",
    "discarded": "P90D"
  }
}
```

---

## 7. Job Inspection and Search

### 7.1 List Jobs

```
GET /ojs/v1/admin/jobs
```

Returns a paginated, filterable list of jobs.

**Query parameters**:

| Parameter   | Type   | Description                                              |
|-------------|--------|----------------------------------------------------------|
| `queue`     | string | Filter by queue name.                                    |
| `state`     | string | Filter by state (`available`, `active`, `completed`, etc.). |
| `type`      | string | Filter by job type (exact match or prefix with `*`).     |
| `since`     | string | Jobs created after this RFC 3339 timestamp.              |
| `until`     | string | Jobs created before this RFC 3339 timestamp.             |
| `page`      | integer| Page number (1-indexed). Default: 1.                     |
| `per_page`  | integer| Items per page. Default: 20. Max: 100.                   |
| `sort`      | string | Sort field: `created_at`, `scheduled_at`, `priority`. Default: `created_at`. |
| `order`     | string | Sort order: `asc` or `desc`. Default: `desc`.            |

**Response** (200 OK):

```json
{
  "items": [
    {
      "id": "019503e1-7b2a-7000-8000-000000000001",
      "type": "email.send",
      "queue": "email",
      "state": "completed",
      "priority": 0,
      "attempt": 1,
      "created_at": "2026-02-13T11:00:00Z",
      "completed_at": "2026-02-13T11:00:05Z"
    }
  ],
  "pagination": {
    "total": 5841,
    "page": 1,
    "per_page": 20
  }
}
```

### 7.2 Get Job Detail

```
GET /ojs/v1/admin/jobs/{id}
```

Returns the full job envelope including all metadata, history, and errors.

**Response** (200 OK):

```json
{
  "id": "019503e1-7b2a-7000-8000-000000000001",
  "specversion": "1.0",
  "type": "email.send",
  "queue": "email",
  "args": [{"to": "user@example.com", "template": "welcome"}],
  "meta": {"tenant_id": "acme-corp", "trace_id": "abc123"},
  "state": "retryable",
  "priority": 0,
  "attempt": 2,
  "max_attempts": 3,
  "retry_policy": {
    "max_attempts": 3,
    "initial_interval": "PT1S",
    "backoff_coefficient": 2.0
  },
  "errors": [
    {
      "attempt": 1,
      "type": "ConnectionError",
      "message": "SMTP connection refused",
      "occurred_at": "2026-02-13T11:00:03Z"
    },
    {
      "attempt": 2,
      "type": "ConnectionError",
      "message": "SMTP connection timeout",
      "occurred_at": "2026-02-13T11:00:08Z"
    }
  ],
  "result": null,
  "metadata": {
    "created_at": "2026-02-13T11:00:00Z",
    "enqueued_at": "2026-02-13T11:00:00Z",
    "started_at": "2026-02-13T11:00:07Z",
    "scheduled_at": null,
    "completed_at": null,
    "cancelled_at": null,
    "discarded_at": null
  }
}
```

### 7.3 Cancel Job

```
POST /ojs/v1/admin/jobs/{id}/cancel
```

Cancels a job. This is the same operation as the data-plane CANCEL but exposed under the admin path for access control convenience.

### 7.4 Retry Job

```
POST /ojs/v1/admin/jobs/{id}/retry
```

Re-enqueues a discarded or cancelled job. The job's attempt counter is reset and the job is moved to `available` state.

**Rationale**: Manual retry of individual failed jobs is the most common dead letter queue operation. Every dashboard needs this.

---

## 8. Bulk Operations

All bulk operations require explicit confirmation and return a summary of the action taken.

### 8.1 Bulk Retry

```
POST /ojs/v1/admin/jobs/bulk/retry
```

Retries multiple jobs matching a filter.

**Request**:

```json
{
  "filter": {
    "queue": "email",
    "state": "discarded",
    "type": "email.send",
    "since": "2026-02-13T00:00:00Z"
  },
  "confirm": true
}
```

**Response** (200 OK):

```json
{
  "action": "retry",
  "matched": 23,
  "succeeded": 22,
  "failed": 1,
  "errors": [
    {
      "job_id": "019503e1-7b2a-7000-8000-000000000099",
      "error": "Job is currently active and cannot be retried"
    }
  ]
}
```

### 8.2 Bulk Cancel

```
POST /ojs/v1/admin/jobs/bulk/cancel
```

Cancels multiple jobs matching a filter. Only jobs in non-terminal states can be cancelled.

### 8.3 Bulk Delete

```
POST /ojs/v1/admin/jobs/bulk/delete
```

Permanently deletes jobs matching a filter. Only jobs in terminal states (`completed`, `discarded`, `cancelled`) can be deleted.

```json
{
  "filter": {
    "state": "completed",
    "until": "2026-02-06T00:00:00Z"
  },
  "confirm": true
}
```

---

## 9. Worker Management

### 9.1 List Workers

```
GET /ojs/v1/admin/workers
```

Returns all known workers with their current state.

**Response** (200 OK):

```json
{
  "items": [
    {
      "id": "worker-01HXYZ",
      "hostname": "worker-pod-abc123",
      "state": "running",
      "queues": ["default", "email"],
      "concurrency": 10,
      "active_jobs": 7,
      "started_at": "2026-02-13T08:00:00Z",
      "last_heartbeat_at": "2026-02-13T12:00:15Z",
      "version": "1.2.0",
      "metadata": {
        "kubernetes_pod": "worker-abc123",
        "node": "node-pool-1-xyz"
      }
    }
  ],
  "summary": {
    "total": 12,
    "running": 10,
    "quiet": 1,
    "stale": 1
  },
  "pagination": {
    "total": 12,
    "page": 1,
    "per_page": 20
  }
}
```

### 9.2 Get Worker Detail

```
GET /ojs/v1/admin/workers/{id}
```

Returns detailed information about a specific worker, including its currently active jobs.

### 9.3 Quiet Worker

```
POST /ojs/v1/admin/workers/{id}/quiet
```

Signals a worker to stop fetching new jobs but finish its active jobs. The signal is delivered via the next heartbeat response.

**Rationale**: This is essential for graceful deployment. During a rolling restart, the orchestrator must be able to tell a worker to drain before stopping it.

### 9.4 Deregister Stale Worker

```
DELETE /ojs/v1/admin/workers/{id}
```

Removes a stale worker record and reschedules its active jobs. Only workers that have missed their heartbeat deadline can be deregistered.

---

## 10. Metrics and Statistics

### 10.1 Aggregate Statistics

```
GET /ojs/v1/admin/stats
```

Returns system-wide aggregate statistics.

**Response** (200 OK):

```json
{
  "queues": 5,
  "workers": 12,
  "jobs": {
    "available": 184,
    "active": 47,
    "scheduled": 92,
    "retryable": 8,
    "completed": 52341,
    "discarded": 127,
    "cancelled": 45
  },
  "throughput": {
    "processed_per_minute": 312.5,
    "failed_per_minute": 4.2
  },
  "uptime_seconds": 864000
}
```

### 10.2 Historical Statistics

```
GET /ojs/v1/admin/stats/history
```

Returns time-series statistics for dashboards.

**Query parameters**:

| Parameter    | Type   | Description                                              |
|--------------|--------|----------------------------------------------------------|
| `period`     | string | Aggregation period: `1m`, `5m`, `1h`, `1d`. Default: `5m`. |
| `since`      | string | Start of time range. Default: 1 hour ago.                |
| `until`      | string | End of time range. Default: now.                         |
| `queue`      | string | Filter to a specific queue. Default: all queues.         |

**Response** (200 OK):

```json
{
  "period": "5m",
  "data": [
    {
      "timestamp": "2026-02-13T11:50:00Z",
      "processed": 1562,
      "failed": 21,
      "enqueued": 1598,
      "latency_p50_ms": 15,
      "latency_p99_ms": 142
    },
    {
      "timestamp": "2026-02-13T11:55:00Z",
      "processed": 1487,
      "failed": 18,
      "enqueued": 1501,
      "latency_p50_ms": 12,
      "latency_p99_ms": 98
    }
  ]
}
```

Implementations SHOULD retain at least 24 hours of 1-minute granularity data and 30 days of 1-hour granularity data.

---

## 11. Dead Letter Management

### 11.1 List Dead Letter Jobs

```
GET /ojs/v1/admin/dead-letter
```

Returns jobs in the dead letter queue (state: `discarded`), paginated and filterable.

**Query parameters**: Same as job listing (Section 7.1).

### 11.2 Retry Dead Letter Job

```
POST /ojs/v1/admin/dead-letter/{id}/retry
```

Re-enqueues a dead letter job. Resets the attempt counter.

### 11.3 Purge Dead Letter Queue

```
DELETE /ojs/v1/admin/dead-letter
```

Removes all or filtered dead letter jobs.

```json
{
  "older_than": "2026-01-13T00:00:00Z",
  "confirm": true
}
```

---

## 12. System Operations

### 12.1 Maintenance Mode

```
POST /ojs/v1/admin/system/maintenance
```

Enables or disables maintenance mode. In maintenance mode:
- All queues are paused (FETCH returns empty).
- Enqueue operations continue to accept jobs (queuing for later).
- Scheduled job promotion is paused.
- Cron triggers are paused.

```json
{
  "enabled": true,
  "reason": "Database migration in progress",
  "estimated_duration": "PT30M"
}
```

**Response** (200 OK):

```json
{
  "maintenance": true,
  "reason": "Database migration in progress",
  "enabled_at": "2026-02-13T12:00:00Z",
  "estimated_end": "2026-02-13T12:30:00Z"
}
```

### 12.2 System Configuration

```
GET /ojs/v1/admin/system/config
```

Returns the current server configuration (non-sensitive values only).

---

## 13. Authentication and Authorization

### 13.1 RBAC Scopes

This specification defines authorization scopes that implementations SHOULD enforce when an authentication mechanism is in place. The specific authentication mechanism (API keys, OAuth2, mTLS) is a deployment concern, not a spec concern.

| Scope             | Grants Access To                                    |
|-------------------|-----------------------------------------------------|
| `ojs:admin:read`  | All GET endpoints under `/ojs/v1/admin/`.           |
| `ojs:admin:write` | All POST/PUT/DELETE endpoints under `/ojs/v1/admin/`. |
| `ojs:admin:purge` | Purge and bulk delete operations (destructive).     |
| `ojs:data:read`   | Data-plane read operations (get job, health).       |
| `ojs:data:write`  | Data-plane write operations (enqueue, ack, fail).   |

### 13.2 Path-Based Separation

All admin endpoints MUST be under the `/ojs/v1/admin/` prefix to enable path-based access control at the reverse proxy or API gateway level.

**Rationale**: Path-based separation is the simplest, most universally supported access control mechanism. It works with every reverse proxy (Nginx, Envoy, Traefik, HAProxy), every API gateway (Kong, AWS API Gateway), and every service mesh (Istio, Linkerd). No OJS-specific middleware is needed.

---

## 14. Conformance Requirements

An implementation declaring support for the admin-api extension MUST support:

| ID           | Requirement                                                                  |
|--------------|------------------------------------------------------------------------------|
| ADM-001      | Queue listing: `GET /ojs/v1/admin/queues` with counts per state.            |
| ADM-002      | Queue pause and resume operations.                                           |
| ADM-003      | Job listing: `GET /ojs/v1/admin/jobs` with pagination and state filter.     |
| ADM-004      | Job detail: `GET /ojs/v1/admin/jobs/{id}` returning full envelope.          |
| ADM-005      | Aggregate statistics: `GET /ojs/v1/admin/stats`.                            |
| ADM-006      | Worker listing: `GET /ojs/v1/admin/workers`.                                |
| ADM-007      | Bulk retry: `POST /ojs/v1/admin/jobs/bulk/retry` with filter and confirm.   |
| ADM-008      | All admin endpoints under `/ojs/v1/admin/` prefix.                          |

Recommended capabilities:

| ID           | Requirement                                                                  |
|--------------|------------------------------------------------------------------------------|
| ADM-R001     | Queue purge with state and time filtering.                                   |
| ADM-R002     | Historical statistics with time-series data.                                 |
| ADM-R003     | Worker quiet signal via admin API.                                           |
| ADM-R004     | Maintenance mode.                                                            |
| ADM-R005     | Bulk cancel and bulk delete operations.                                      |
| ADM-R006     | Queue configuration updates.                                                 |

---

## 15. Prior Art

| System           | Admin API Approach                                                                       |
|------------------|------------------------------------------------------------------------------------------|
| **Temporal**     | Separate OperatorService for admin (namespace management, search attributes, Nexus).     |
| **Kubernetes**   | API groups with RBAC separating workload from admin resources.                           |
| **Kafka**        | Dedicated AdminClient API for topics, consumer groups, ACLs.                             |
| **Sidekiq Web**  | Embedded Rack app with dashboard, queue management, retry/delete, statistics.            |
| **Oban Web**     | Phoenix LiveView dashboard with queue stats, job detail, filtering, bulk operations.     |
| **Bull Board**   | Separate `@bull-board/api` package with framework adapters (Express, Fastify, Koa).      |
| **Faktory**      | Embedded web UI with queue inspection, job detail, retry, and worker management.         |

All systems converge on the same seven data categories: queue stats, job listing, job detail, job actions, worker status, aggregate metrics, and time-series data. This specification standardizes all seven.

---

## 16. Examples

### 16.1 Dashboard Polling Loop

A dashboard application querying the admin API every 5 seconds:

```javascript
async function pollDashboard(adminUrl) {
  const [stats, queues, workers] = await Promise.all([
    fetch(`${adminUrl}/ojs/v1/admin/stats`).then(r => r.json()),
    fetch(`${adminUrl}/ojs/v1/admin/queues`).then(r => r.json()),
    fetch(`${adminUrl}/ojs/v1/admin/workers`).then(r => r.json()),
  ]);

  updateDashboard({ stats, queues: queues.items, workers: workers.items });
}

setInterval(() => pollDashboard('http://localhost:8080'), 5000);
```

### 16.2 Incident Response: Pause and Drain

During an incident where a downstream email API is down:

```bash
# Pause the email queue to stop sending
curl -X POST http://localhost:8080/ojs/v1/admin/queues/email/pause

# Check how many jobs are waiting
curl http://localhost:8080/ojs/v1/admin/queues/email

# When the API recovers, resume
curl -X POST http://localhost:8080/ojs/v1/admin/queues/email/resume
```

### 16.3 Bulk Retry After Fix

After deploying a fix for a bug that caused failures:

```bash
curl -X POST http://localhost:8080/ojs/v1/admin/jobs/bulk/retry \
  -H "Content-Type: application/json" \
  -d '{
    "filter": {
      "queue": "billing",
      "state": "discarded",
      "type": "invoice.generate",
      "since": "2026-02-12T00:00:00Z"
    },
    "confirm": true
  }'
```

### 16.4 Cleanup Old Completed Jobs

Removing completed jobs older than 7 days to free storage:

```bash
curl -X DELETE http://localhost:8080/ojs/v1/admin/queues/default/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "states": ["completed"],
    "older_than": "2026-02-06T00:00:00Z",
    "confirm": true
  }'
```

---

## Appendix A: Changelog

| Date       | Change                        |
|------------|-------------------------------|
| 2026-02-13 | Initial release candidate.    |
