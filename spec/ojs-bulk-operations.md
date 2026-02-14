# Open Job Spec: Bulk Operations

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Bulk Operations Specification              |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-15                                     |
| **Status**  | Release Candidate                              |
| **Tier**    | Official Extension                             |
| **URI**     | `urn:ojs:ext:bulk-operations`                  |
| **Requires**| OJS Core Specification (Layer 1), OJS HTTP Binding (Layer 3) |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Design Principles](#4-design-principles)
5. [Bulk Enqueue](#5-bulk-enqueue)
   - 5.1 [Request Format](#51-request-format)
   - 5.2 [Response Format](#52-response-format)
   - 5.3 [Atomicity Modes](#53-atomicity-modes)
   - 5.4 [Partial Failure Semantics](#54-partial-failure-semantics)
6. [Bulk Cancel](#6-bulk-cancel)
7. [Bulk Retry](#7-bulk-retry)
8. [Bulk Delete](#8-bulk-delete)
9. [Request Limits](#9-request-limits)
10. [Idempotent Bulk Operations](#10-idempotent-bulk-operations)
11. [HTTP Binding](#11-http-binding)
12. [Observability](#12-observability)
13. [Conformance Requirements](#13-conformance-requirements)
14. [Prior Art](#14-prior-art)
15. [Examples](#15-examples)

---

## 1. Introduction

Background job systems frequently need to enqueue, cancel, or retry large numbers of jobs in a single operation. An application migrating millions of records may need to enqueue a job per record. An operator responding to an incident may need to cancel thousands of in-flight jobs. A recovery process may need to retry all failed jobs from the last hour.

Without a bulk operations API, clients must make individual HTTP requests for each job -- creating O(n) round trips, O(n) database transactions, and O(n) event emissions. This is inefficient, slow, and fragile: a network interruption partway through leaves the system in an inconsistent state with no clear indication of which jobs were enqueued and which were not.

This specification defines bulk counterparts for the most common job operations: enqueue, cancel, retry, and delete. Each bulk operation supports configurable atomicity (all-or-nothing vs. best-effort) and provides detailed per-item result reporting.

### 1.1 Scope

This specification defines:

- Bulk enqueue with atomicity modes and partial failure semantics.
- Bulk cancel, retry, and delete operations.
- Request size limits and pagination for large batches.
- Idempotent bulk operations for safe retries.
- HTTP binding for all bulk endpoints.

This specification does **not** define:

- Streaming or chunked upload for very large batches (implementations MAY support streaming but the protocol is not specified).
- Background bulk operations that run asynchronously (all operations in this spec are synchronous request/response).
- Bulk FETCH (job dispatch remains per-worker via the standard FETCH operation).

### 1.2 Companion Specifications

| Document | Layer | Description |
|----------|-------|-------------|
| **ojs-core.md** | 1 -- Core | Job envelope format and lifecycle |
| **ojs-http-binding.md** | 3 -- Binding | HTTP method mapping, status codes |
| **ojs-unique-jobs.md** | Extension | Uniqueness constraints affect bulk enqueue |
| **ojs-errors.md** | Extension | Error catalog for failure responses |

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

Every MUST requirement includes a rationale explaining why the requirement is mandatory.

---

## 3. Terminology

| Term                  | Definition                                                                                         |
|-----------------------|----------------------------------------------------------------------------------------------------|
| bulk operation        | A single API request that operates on multiple jobs simultaneously.                               |
| atomicity mode        | Determines whether a bulk operation is all-or-nothing (`atomic`) or best-effort (`partial`).       |
| partial failure       | A condition where some items in a bulk operation succeed and others fail.                           |
| item result           | The per-job outcome of a bulk operation, indicating success or failure with error details.          |
| idempotency key       | A client-generated unique identifier for a bulk request that enables safe retries.                 |
| batch size limit      | The maximum number of items allowed in a single bulk request.                                      |

---

## 4. Design Principles

1. **Explicit atomicity.** Clients choose between atomic (all-or-nothing) and partial (best-effort) semantics. The spec does not impose one model because both are valid: atomic operations are essential for workflows where partial enqueue creates inconsistency, while partial operations are essential for large batches where a single validation error should not block the other 9,999 valid jobs.

2. **Detailed result reporting.** Every bulk response includes per-item results. Clients MUST be able to determine exactly which items succeeded and which failed, along with failure reasons. "500 Internal Server Error" for a batch of 1,000 jobs is unacceptable.

3. **Bounded request size.** Bulk operations have a maximum batch size to prevent resource exhaustion (memory, transaction size, response payload). Clients that need to process more items than the limit MUST split their work into multiple requests.

4. **Safe retries.** Bulk operations support idempotency keys, allowing clients to safely retry a failed bulk request without creating duplicate jobs. This is critical for reliability: a network timeout on a bulk enqueue leaves the client uncertain about which jobs were created.

---

## 5. Bulk Enqueue

### 5.1 Request Format

```http
POST /ojs/v1/jobs/bulk
Content-Type: application/json

{
  "atomicity": "partial",
  "idempotency_key": "bulk-import-2026-02-15-001",
  "jobs": [
    {
      "type": "user.import",
      "queue": "imports",
      "args": [{"user_id": "u_001", "source": "csv"}],
      "priority": 3
    },
    {
      "type": "user.import",
      "queue": "imports",
      "args": [{"user_id": "u_002", "source": "csv"}],
      "priority": 3
    },
    {
      "type": "user.import",
      "queue": "imports",
      "args": [{"user_id": "u_003", "source": "csv"}],
      "priority": 3
    }
  ]
}
```

| Field              | Type    | Required | Default      | Description                                                        |
|--------------------|---------|----------|--------------|--------------------------------------------------------------------|
| `jobs`             | array   | Yes      | --           | Array of job envelopes to enqueue. Each element follows the standard job envelope format. |
| `atomicity`        | string  | No       | `"partial"`  | Atomicity mode: `"atomic"` or `"partial"`.                         |
| `idempotency_key`  | string  | No       | --           | Client-generated unique key for safe retries. See Section 10.       |

Each element in the `jobs` array follows the standard OJS job envelope format defined in [ojs-core.md](./ojs-core.md) and [ojs-json-format.md](./ojs-json-format.md). All standard fields (`type`, `queue`, `args`, `priority`, `scheduled_at`, `meta`, `retry`, `unique`, `rate_limit`, etc.) are supported.

### 5.2 Response Format

The response includes a summary and per-item results:

```json
{
  "total": 3,
  "succeeded": 3,
  "failed": 0,
  "items": [
    {
      "index": 0,
      "status": "created",
      "job": {
        "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
        "type": "user.import",
        "state": "available"
      }
    },
    {
      "index": 1,
      "status": "created",
      "job": {
        "id": "019539a4-b68c-7def-8000-2b3c4d5e6f70",
        "type": "user.import",
        "state": "available"
      }
    },
    {
      "index": 2,
      "status": "created",
      "job": {
        "id": "019539a4-b68c-7def-8000-3c4d5e6f7081",
        "type": "user.import",
        "state": "available"
      }
    }
  ]
}
```

| Field       | Type    | Description                                              |
|-------------|---------|----------------------------------------------------------|
| `total`     | integer | Total number of items in the request.                    |
| `succeeded` | integer | Number of items that succeeded.                          |
| `failed`    | integer | Number of items that failed.                             |
| `items`     | array   | Per-item results, ordered by `index` matching the request array position. |

Each item in the `items` array:

| Field      | Type    | Description                                              |
|------------|---------|----------------------------------------------------------|
| `index`    | integer | Position in the request `jobs` array (0-based).          |
| `status`   | string  | `"created"`, `"duplicate"`, or `"failed"`.               |
| `job`      | object  | Created job summary (present when `status` is `"created"` or `"duplicate"`). |
| `error`    | object  | Error details (present when `status` is `"failed"`). Follows the error format in [ojs-errors.md](./ojs-errors.md). |

The `items` array MUST contain exactly one entry for each item in the request `jobs` array, in the same order.

**Rationale**: Positional correspondence between request and response arrays is the simplest way for clients to correlate results. This is the approach used by AWS SQS SendMessageBatch, Elasticsearch Bulk API, and most other batch APIs.

### 5.3 Atomicity Modes

#### `"atomic"` Mode

In atomic mode, either all jobs are enqueued or none are. If any single job fails validation or insertion, the entire operation is rolled back.

- The backend MUST use a database transaction or equivalent mechanism to ensure atomicity.

**Rationale**: Atomic bulk operations are essential for workflows where partial enqueue creates inconsistency. For example, when enqueuing a chain of dependent jobs, enqueuing steps 1 and 3 but failing on step 2 leaves the workflow in a broken state.

- When an atomic bulk operation fails, the HTTP response status MUST be `422 Unprocessable Entity`.
- The response body MUST include per-item results identifying which items caused the failure.
- No jobs from the batch are created.

#### `"partial"` Mode

In partial mode, each job is enqueued independently. Failures on individual items do not affect other items.

- The backend MUST attempt to enqueue all jobs, collecting per-item results.
- The HTTP response status MUST be `200 OK` when all items succeed.
- The HTTP response status MUST be `207 Multi-Status` when some items succeed and some fail.
- The HTTP response status MUST be `422 Unprocessable Entity` when all items fail.

**Rationale**: The `207 Multi-Status` code (defined in RFC 4918) is the standard HTTP mechanism for reporting per-item results in batch operations. Returning `200` when all items succeed allows simple success checks without inspecting the response body.

### 5.4 Partial Failure Semantics

When a bulk enqueue operates in `"partial"` mode and some items fail:

1. Successfully enqueued jobs MUST be durable and visible to workers immediately.
2. Failed items MUST NOT be enqueued. They MUST be reported in the response with error details.
3. The client is responsible for retrying failed items (optionally using the idempotency key mechanism).

Common failure reasons for individual items:

| Error Code                | Description                                              |
|---------------------------|----------------------------------------------------------|
| `VALIDATION_ERROR`        | Job envelope is malformed or missing required fields.    |
| `DUPLICATE_JOB`           | Job violates a uniqueness constraint (see [ojs-unique-jobs.md](./ojs-unique-jobs.md)). |
| `QUEUE_NOT_FOUND`         | The specified queue does not exist (when strict queue mode is enabled). |
| `PAYLOAD_TOO_LARGE`       | Job payload exceeds size limits (see [ojs-payload-limits.md](./ojs-payload-limits.md)). |
| `RATE_LIMIT_EXCEEDED`     | Enqueue rate limit exceeded (when enqueue-side rate limiting is enabled). |

---

## 6. Bulk Cancel

Cancel multiple jobs in a single request:

```http
POST /ojs/v1/jobs/bulk/cancel
Content-Type: application/json

{
  "atomicity": "partial",
  "job_ids": [
    "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
    "019539a4-b68c-7def-8000-2b3c4d5e6f70",
    "019539a4-b68c-7def-8000-3c4d5e6f7081"
  ]
}
```

| Field        | Type    | Required | Default     | Description                                    |
|--------------|---------|----------|-------------|------------------------------------------------|
| `job_ids`    | array   | Yes*     | --          | List of job IDs to cancel.                     |
| `filter`     | object  | No*      | --          | Filter criteria for selecting jobs to cancel.  |
| `atomicity`  | string  | No       | `"partial"` | Atomicity mode: `"atomic"` or `"partial"`.     |

*Either `job_ids` or `filter` MUST be provided, but not both.

### 6.1 Filter-Based Cancel

Cancel jobs matching filter criteria:

```http
POST /ojs/v1/jobs/bulk/cancel
Content-Type: application/json

{
  "filter": {
    "type": "report.generate",
    "queue": "reports",
    "state": ["available", "scheduled"],
    "enqueued_before": "2026-02-15T12:00:00Z"
  }
}
```

| Field                | Type          | Description                                              |
|----------------------|---------------|----------------------------------------------------------|
| `filter.type`        | string        | Cancel jobs matching this type.                          |
| `filter.queue`       | string        | Cancel jobs in this queue.                               |
| `filter.state`       | array[string] | Cancel jobs in these states. Defaults to `["available", "scheduled"]`. |
| `filter.enqueued_before` | string    | Cancel jobs enqueued before this ISO 8601 timestamp.     |
| `filter.enqueued_after`  | string    | Cancel jobs enqueued after this ISO 8601 timestamp.      |
| `filter.priority`    | integer       | Cancel jobs with this priority.                          |
| `filter.meta`        | object        | Cancel jobs with matching metadata key-value pairs.      |

Filter-based cancel MUST only cancel jobs in cancellable states (`available`, `scheduled`, `retryable`). Jobs in `active` state SHOULD be signaled for cancellation (see [ojs-graceful-shutdown.md](./ojs-graceful-shutdown.md)) rather than immediately cancelled.

### 6.2 Cancel Response

```json
{
  "total_matched": 3,
  "cancelled": 2,
  "skipped": 1,
  "items": [
    { "index": 0, "job_id": "...", "status": "cancelled" },
    { "index": 1, "job_id": "...", "status": "cancelled" },
    { "index": 2, "job_id": "...", "status": "skipped", "reason": "Job is in active state" }
  ]
}
```

---

## 7. Bulk Retry

Retry multiple failed or discarded jobs:

```http
POST /ojs/v1/jobs/bulk/retry
Content-Type: application/json

{
  "job_ids": [
    "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
    "019539a4-b68c-7def-8000-2b3c4d5e6f70"
  ]
}
```

Bulk retry transitions jobs from `discarded` or `retryable` states back to `available`. The response format follows the same pattern as bulk cancel.

| Field        | Type    | Required | Default     | Description                                    |
|--------------|---------|----------|-------------|------------------------------------------------|
| `job_ids`    | array   | Yes*     | --          | List of job IDs to retry.                      |
| `filter`     | object  | No*      | --          | Filter criteria for selecting jobs to retry.   |
| `atomicity`  | string  | No       | `"partial"` | Atomicity mode: `"atomic"` or `"partial"`.     |

*Either `job_ids` or `filter` MUST be provided, but not both.

Implementations MUST only retry jobs in retriable states (`discarded`, `retryable`). Attempting to retry a job in any other state MUST result in a per-item error.

**Rationale**: Retrying a `completed` job would create duplicate processing. Retrying an `active` job is nonsensical. Restricting retry to appropriate states prevents accidental re-execution.

---

## 8. Bulk Delete

Permanently delete multiple jobs:

```http
POST /ojs/v1/jobs/bulk/delete
Content-Type: application/json

{
  "job_ids": [
    "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
    "019539a4-b68c-7def-8000-2b3c4d5e6f70"
  ]
}
```

Bulk delete permanently removes jobs from the system. This operation is irreversible.

Implementations MUST only delete jobs in terminal states (`completed`, `cancelled`, `discarded`). Attempting to delete a job in a non-terminal state MUST result in a per-item error.

**Rationale**: Deleting an `available` or `active` job would silently drop work. Terminal-state restriction prevents accidental data loss while allowing cleanup of historical job data.

---

## 9. Request Limits

### 9.1 Batch Size Limit

Implementations MUST enforce a maximum batch size on bulk requests. The maximum batch size MUST be at least 100 and SHOULD be at least 1,000.

**Rationale**: Unbounded batch sizes risk memory exhaustion (holding the entire request and response in memory), transaction timeout (large database transactions), and response timeout (the HTTP request exceeding server/proxy timeouts). A minimum of 100 ensures the feature is useful; a recommendation of 1,000 covers most practical use cases.

When a request exceeds the batch size limit, the backend MUST reject the entire request with HTTP `413 Payload Too Large` and include the maximum allowed size in the response:

```json
{
  "error": {
    "code": "BATCH_SIZE_EXCEEDED",
    "message": "Batch size 5000 exceeds maximum of 1000",
    "max_batch_size": 1000
  }
}
```

### 9.2 Recommended Client Behavior

Clients that need to process more items than the batch size limit SHOULD:

1. Split the items into chunks of at most `max_batch_size`.
2. Send each chunk as a separate bulk request.
3. Use idempotency keys per chunk for safe retries.
4. Track per-chunk results to identify and retry failures.

---

## 10. Idempotent Bulk Operations

### 10.1 Idempotency Key

When an `idempotency_key` is provided, the backend MUST ensure that repeated requests with the same key produce the same result:

1. On the first request with a given key, process the operation normally and cache the response.
2. On subsequent requests with the same key, return the cached response without re-executing the operation.

**Rationale**: Network failures during bulk operations leave the client uncertain about whether the request was processed. Without idempotency keys, retrying a bulk enqueue creates duplicate jobs. This is the standard idempotency pattern used by Stripe, AWS, and other APIs that handle financial or data-sensitive operations.

### 10.2 Key Requirements

- Idempotency keys MUST be strings of at most 256 characters.
- The backend MUST retain idempotency key results for at least 24 hours.

**Rationale**: 24 hours provides a generous window for retries while preventing unbounded state growth.

- After the retention period, a request with the same key MUST be treated as a new request.
- Idempotency keys are scoped per operation type (a key used for bulk enqueue does not conflict with the same key used for bulk cancel).

---

## 11. HTTP Binding

### 11.1 Endpoint Summary

| Method | Path                     | Description                        |
|--------|--------------------------|------------------------------------|
| POST   | `/ojs/v1/jobs/bulk`      | Bulk enqueue jobs.                 |
| POST   | `/ojs/v1/jobs/bulk/cancel` | Bulk cancel jobs.                |
| POST   | `/ojs/v1/jobs/bulk/retry`  | Bulk retry failed jobs.          |
| POST   | `/ojs/v1/jobs/bulk/delete` | Bulk delete terminal jobs.       |

### 11.2 HTTP Status Codes

| Status Code | Condition                                                     |
|-------------|---------------------------------------------------------------|
| `200 OK`    | All items in a partial-mode request succeeded.                |
| `201 Created` | All items in a partial-mode bulk enqueue succeeded.         |
| `207 Multi-Status` | Some items succeeded and some failed in partial mode.  |
| `413 Payload Too Large` | Request exceeds batch size limit.                  |
| `422 Unprocessable Entity` | All items failed, or an atomic operation was rolled back. |
| `409 Conflict` | Idempotency key conflict (same key, different request body). |

### 11.3 Headers

| Header               | Direction | Description                                              |
|----------------------|-----------|----------------------------------------------------------|
| `Idempotency-Key`   | Request   | Alternative to the `idempotency_key` body field. When both are present, the header takes precedence. |
| `X-OJS-Batch-Size`  | Response  | The number of items processed in this request.           |
| `X-OJS-Max-Batch-Size` | Response (on 413) | The maximum allowed batch size.              |

---

## 12. Observability

### 12.1 Events

Implementations MUST emit the following events for bulk operations:

| Event Type                   | Trigger                                          | Data Fields                              |
|------------------------------|--------------------------------------------------|------------------------------------------|
| `bulk.enqueue.completed`     | A bulk enqueue request completed.                | `total`, `succeeded`, `failed`, `atomicity` |
| `bulk.cancel.completed`      | A bulk cancel request completed.                 | `total`, `cancelled`, `skipped`          |
| `bulk.retry.completed`       | A bulk retry request completed.                  | `total`, `retried`, `skipped`            |
| `bulk.delete.completed`      | A bulk delete request completed.                 | `total`, `deleted`, `skipped`            |

### 12.2 Metrics

Implementations SHOULD expose the following metrics:

| Metric Name                         | Type      | Labels                     | Description                               |
|-------------------------------------|-----------|----------------------------|-------------------------------------------|
| `ojs.bulk.requests_total`           | Counter   | `operation`, `atomicity`   | Total bulk requests.                      |
| `ojs.bulk.items_total`              | Counter   | `operation`, `status`      | Total items across all bulk requests.     |
| `ojs.bulk.duration`                 | Histogram | `operation`, `atomicity`   | Bulk request processing duration.         |
| `ojs.bulk.batch_size`               | Histogram | `operation`                | Distribution of batch sizes.              |

---

## 13. Conformance Requirements

### 13.1 Required Capabilities

An implementation declaring support for the bulk-operations extension MUST support:

| ID          | Requirement                                                                              |
|-------------|------------------------------------------------------------------------------------------|
| BLK-001     | Bulk enqueue via `POST /ojs/v1/jobs/bulk` with per-item results.                         |
| BLK-002     | Partial atomicity mode with `207 Multi-Status` for mixed results.                        |
| BLK-003     | Batch size limit enforcement with `413 Payload Too Large`.                               |
| BLK-004     | Per-item result reporting with `index`, `status`, and `error` fields.                    |
| BLK-005     | Minimum batch size limit of 100.                                                         |

### 13.2 Recommended Capabilities

| ID          | Requirement                                                                              |
|-------------|------------------------------------------------------------------------------------------|
| BLK-R001    | Atomic mode with transactional rollback.                                                 |
| BLK-R002    | Idempotency keys for safe retries.                                                       |
| BLK-R003    | Bulk cancel with both ID-based and filter-based selection.                                |
| BLK-R004    | Bulk retry for `discarded` and `retryable` jobs.                                         |
| BLK-R005    | Bulk delete for terminal-state jobs.                                                     |
| BLK-R006    | Batch size limit of at least 1,000.                                                      |

---

## 14. Prior Art

| System               | Approach                                                                                  |
|----------------------|-------------------------------------------------------------------------------------------|
| **Sidekiq**          | `Sidekiq::Client.push_bulk` enqueues jobs in a single Redis pipeline. All-or-nothing (pipeline atomicity). No partial failure reporting. |
| **BullMQ**           | `queue.addBulk()` adds multiple jobs in a single Redis transaction. Returns array of created jobs. No partial failure; transaction fails entirely on error. |
| **AWS SQS**          | `SendMessageBatch` accepts up to 10 messages. Returns per-message success/failure. Partial mode only. |
| **Celery**           | `group()` or `chunks()` for batch dispatch. No native bulk enqueue with partial failure reporting. |
| **Hangfire**         | Hangfire Pro provides `BatchJob.StartNew()` with atomic batch creation and continuation callbacks. |
| **Elasticsearch**    | Bulk API processes up to thousands of actions per request. Per-item results with independent success/failure. HTTP 200 even on partial failure (check `errors` field). |
| **Stripe**           | Idempotency keys on all mutating requests. 24-hour key retention. Conflict on same key with different parameters. |

OJS combines the per-item result reporting of AWS SQS and Elasticsearch with the atomicity option of BullMQ and the idempotency model of Stripe, providing a comprehensive bulk operations API for background job processing.

---

## 15. Examples

### 15.1 Basic Bulk Enqueue

Enqueue three jobs with default settings (partial mode, no idempotency key):

```json
{
  "jobs": [
    { "type": "email.send", "args": ["alice@example.com", "welcome"] },
    { "type": "email.send", "args": ["bob@example.com", "welcome"] },
    { "type": "email.send", "args": ["carol@example.com", "welcome"] }
  ]
}
```

### 15.2 Atomic Bulk Enqueue for Workflow Setup

Enqueue a set of related jobs atomically:

```json
{
  "atomicity": "atomic",
  "jobs": [
    {
      "type": "order.validate",
      "queue": "orders",
      "args": [{"order_id": "ord_789"}],
      "priority": 1
    },
    {
      "type": "order.charge",
      "queue": "payments",
      "args": [{"order_id": "ord_789"}],
      "priority": 1,
      "scheduled_at": "2026-02-15T22:00:00Z"
    },
    {
      "type": "order.fulfill",
      "queue": "fulfillment",
      "args": [{"order_id": "ord_789"}],
      "priority": 1,
      "scheduled_at": "2026-02-15T22:05:00Z"
    }
  ]
}
```

If any job fails validation, none are enqueued.

### 15.3 Bulk Enqueue with Partial Failure

Request:

```json
{
  "atomicity": "partial",
  "jobs": [
    { "type": "user.import", "args": [{"user_id": "u_001"}] },
    { "type": "", "args": [] },
    { "type": "user.import", "args": [{"user_id": "u_003"}] }
  ]
}
```

Response (207 Multi-Status):

```json
{
  "total": 3,
  "succeeded": 2,
  "failed": 1,
  "items": [
    {
      "index": 0,
      "status": "created",
      "job": { "id": "019539a4-...", "type": "user.import", "state": "available" }
    },
    {
      "index": 1,
      "status": "failed",
      "error": {
        "code": "VALIDATION_ERROR",
        "message": "Job type must not be empty"
      }
    },
    {
      "index": 2,
      "status": "created",
      "job": { "id": "019539a5-...", "type": "user.import", "state": "available" }
    }
  ]
}
```

### 15.4 Idempotent Bulk Enqueue

First request:

```http
POST /ojs/v1/jobs/bulk
Idempotency-Key: import-batch-42

{
  "jobs": [
    { "type": "user.import", "args": [{"user_id": "u_100"}] },
    { "type": "user.import", "args": [{"user_id": "u_101"}] }
  ]
}
```

Response: `201 Created` with two created jobs.

Retry (same idempotency key):

```http
POST /ojs/v1/jobs/bulk
Idempotency-Key: import-batch-42

{
  "jobs": [
    { "type": "user.import", "args": [{"user_id": "u_100"}] },
    { "type": "user.import", "args": [{"user_id": "u_101"}] }
  ]
}
```

Response: `201 Created` with the same two job IDs (no duplicates created).

### 15.5 Filter-Based Bulk Cancel

Cancel all analytics jobs enqueued before noon:

```json
{
  "filter": {
    "type": "analytics.aggregate",
    "state": ["available", "scheduled"],
    "enqueued_before": "2026-02-15T12:00:00Z"
  }
}
```

---

## Appendix A: Changelog

| Date       | Change                        |
|------------|-------------------------------|
| 2026-02-15 | Initial release candidate.    |
