# Open Job Spec: Job Results

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Job Results Specification                  |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-15                                     |
| **Status**  | Release Candidate                              |
| **Tier**    | Official Extension                             |
| **URI**     | `urn:ojs:ext:results`                          |
| **Requires**| OJS Core Specification (Layer 1)               |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Design Principles](#4-design-principles)
5. [Result Model](#5-result-model)
   - 5.1 [Result Storage](#51-result-storage)
   - 5.2 [Result Types](#52-result-types)
   - 5.3 [Result Lifecycle](#53-result-lifecycle)
6. [Result Fields](#6-result-fields)
7. [Result Retention](#7-result-retention)
   - 7.1 [Retention Policies](#71-retention-policies)
   - 7.2 [Size Limits](#72-size-limits)
   - 7.3 [External Result Storage](#73-external-result-storage)
8. [Result Retrieval](#8-result-retrieval)
   - 8.1 [Polling](#81-polling)
   - 8.2 [Blocking Wait](#82-blocking-wait)
   - 8.3 [Streaming](#83-streaming)
9. [Interaction with Other Extensions](#9-interaction-with-other-extensions)
   - 9.1 [Workflows](#91-workflows)
   - 9.2 [Progress](#92-progress)
   - 9.3 [Bulk Operations](#93-bulk-operations)
   - 9.4 [Encryption](#94-encryption)
10. [HTTP Binding](#10-http-binding)
11. [Observability](#11-observability)
12. [Conformance Requirements](#12-conformance-requirements)
13. [Prior Art](#13-prior-art)
14. [Examples](#14-examples)

---

## 1. Introduction

Background jobs frequently produce output: a report generation job produces a downloadable file, an image processing job returns thumbnail URLs, a payment processing job returns a transaction ID. The OJS core specification includes a `result` field on the job envelope that stores the handler's return value on successful ACK. However, it does not define result retention, size limits, retrieval patterns, or behavior for failed jobs. This extension formalizes the complete result lifecycle.

Without standardized result handling, every implementation invents its own approach: some store results in the same backend as the job, some discard them after completion, some impose undocumented size limits, and some provide no way to retrieve results at all. This creates portability problems — a workflow that depends on upstream job results may work on one backend and silently fail on another.

### 1.1 Scope

This specification defines:

- A result model with typed results, metadata, and error results.
- Retention policies controlling how long results are stored after job completion.
- Size limits and external storage patterns for large results.
- Retrieval patterns including polling, blocking wait, and streaming.
- Result passing semantics for workflow composition.

This specification does **not** define:

- Application-level result schemas (the `result` field accepts any JSON-native value).
- Result caching or CDN integration (these are infrastructure concerns outside the job system).
- Result aggregation across multiple independent jobs (workflow aggregation is covered in ojs-workflows.md).

### 1.2 Companion Specifications

| Document | Layer | Description |
|----------|-------|-------------|
| **ojs-core.md** | 1 -- Core | Job envelope, `result` field, ACK operation |
| **ojs-workflows.md** | Core | Result passing via `parent_results` in chains, groups, batches |
| **ojs-progress.md** | Extension | Intermediate progress vs. final result |
| **ojs-encryption.md** | Experimental | Result payload encryption |
| **ojs-payload-limits.md** | Extension | Size constraints, external payload references |

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term | Definition |
|------|------------|
| **Result** | The value returned by a job handler upon successful completion, stored via the ACK operation. |
| **Error Result** | Structured error information stored when a job fails, including type, message, and optional backtrace. |
| **Result Backend** | The storage layer responsible for persisting job results beyond completion. |
| **Result Reference** | A URI pointing to an externally stored result, used when result data exceeds size limits. |
| **Result TTL** | The duration for which a result is retained after the job reaches a terminal state. |
| **Terminal State** | A job state from which no further transitions occur: `completed`, `cancelled`, or `discarded`. |

---

## 4. Design Principles

1. **Results are first-class.** Results are not an afterthought bolted onto the job envelope. They are stored, retained, retrievable, and deletable through well-defined operations. Producers that enqueue a job have a right to retrieve its outcome.

2. **Bounded storage.** Results MUST be bounded by both size and time. Unbounded result storage leads to storage exhaustion. Every result has a TTL and a maximum size, with external storage as the escape hatch for large payloads.

3. **Results survive completion.** A result MUST remain accessible after the job transitions to a terminal state. Deleting results at the moment of completion would make them useless for polling clients and workflow composition.

4. **Symmetric success and failure.** Both successful results and error details are stored using the same retention and retrieval mechanisms. A client that polls for a job's outcome receives either the result or the error, not silence.

---

## 5. Result Model

### 5.1 Result Storage

When a worker ACKs a job, the implementation MUST store the result value provided in the ACK operation. The result is associated with the job ID and persists according to the retention policy.

When a worker FAILs a job and the job transitions to a terminal state (`discarded`), the implementation MUST store the error object. The error is retrievable through the same mechanisms as a successful result.

**Rationale:** Storing both success and failure outcomes ensures that any client waiting for a job's completion can determine the outcome without ambiguity. A missing result is indistinguishable from "not yet completed" without this guarantee.

### 5.2 Result Types

The `result` field accepts any JSON-native value:

| JSON Type | Example | Use Case |
|-----------|---------|----------|
| `null` | `null` | Side-effect-only jobs (email sent, file deleted) |
| `boolean` | `true` | Simple success/failure indicators |
| `number` | `42` | Computed values |
| `string` | `"https://cdn.example.com/report.pdf"` | URLs, identifiers |
| `array` | `["thumb_sm.jpg", "thumb_lg.jpg"]` | Multiple outputs |
| `object` | `{"transaction_id": "txn_123", "amount": 99.99}` | Structured results |

Implementations MUST preserve the JSON type of the result. A result stored as a number MUST be retrievable as a number, not a string.

### 5.3 Result Lifecycle

```
  ┌──────────┐     ACK      ┌──────────────┐  result_ttl  ┌──────────┐
  │  active  │─────────────▶│  completed   │─────────────▶│  pruned  │
  │          │              │  (result     │              │ (result  │
  │          │              │   stored)    │              │  deleted) │
  └──────────┘              └──────────────┘              └──────────┘
       │                                                        ▲
       │ FAIL (exhausted)   ┌──────────────┐  result_ttl        │
       └───────────────────▶│  discarded   │────────────────────┘
                            │  (error      │
                            │   stored)    │
                            └──────────────┘
```

1. **Storage:** Result is stored when the job reaches a terminal state.
2. **Retention:** Result is accessible for the duration of `result_ttl`.
3. **Pruning:** After `result_ttl` expires, the result MAY be deleted by the implementation.

---

## 6. Result Fields

The following fields extend the job envelope and system configuration:

### 6.1 Job Envelope Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `result` | any JSON value | — | Handler return value, set by ACK. Defined in OJS Core. |
| `error` | object | — | Error details, set by FAIL. Defined in OJS Core. |
| `result_ttl` | integer (seconds) | 604800 (7 days) | Duration to retain the result after terminal state. |
| `result_size_limit` | integer (bytes) | impl-defined | Maximum size of the serialized result value. |

### 6.2 Result Metadata

When a result is stored, the implementation MUST also record the following metadata:

| Field | Type | Description |
|-------|------|-------------|
| `result_stored_at` | ISO 8601 timestamp | When the result was persisted. |
| `result_expires_at` | ISO 8601 timestamp | When the result will be eligible for pruning. |
| `result_size_bytes` | integer | Size of the serialized result in bytes. |

### 6.3 External Result Reference

When a result exceeds `result_size_limit`, the handler SHOULD store the payload externally and return a result reference:

```json
{
  "$ref": "ojs://results/external",
  "uri": "s3://my-bucket/results/019539a4-b68c-7def-8000-1a2b3c4d5e6f.json",
  "content_type": "application/json",
  "size_bytes": 52428800,
  "checksum": "sha256:a1b2c3d4..."
}
```

The `$ref` field with value `"ojs://results/external"` signals that the result is a reference, not the actual value. Implementations MUST NOT interpret external references — they are opaque to the job system and meaningful only to the application.

---

## 7. Result Retention

### 7.1 Retention Policies

Implementations MUST support result TTL. The retention clock starts when the job transitions to a terminal state (`completed`, `cancelled`, or `discarded`).

| Policy | `result_ttl` Value | Behavior |
|--------|-------------------|----------|
| **Ephemeral** | 0 | Result is not stored. ACK succeeds but result is discarded. |
| **Short-lived** | 60–3600 | Result available for minutes to hours. Suitable for real-time consumers. |
| **Standard** | 604800 (default) | Result retained for 7 days. Suitable for most use cases. |
| **Long-lived** | 2592000+ | Result retained for 30+ days. Suitable for audit and compliance. |
| **Permanent** | -1 | Result is never automatically pruned. Use with caution. |

Implementations MUST support `result_ttl` values of 0 (ephemeral) and positive integers. Implementations SHOULD support -1 (permanent). Implementations MUST document their maximum supported `result_ttl`.

**Rationale:** Different job types have different retention needs. A real-time payment verification needs its result for seconds; an annual compliance report needs its result for years. The TTL model lets producers declare intent without requiring global configuration changes.

### 7.2 Size Limits

Implementations MUST impose a maximum result size. The RECOMMENDED default limit is 1 MiB (1,048,576 bytes).

When a handler attempts to ACK with a result that exceeds the size limit:

1. The implementation MUST reject the ACK with error code `RESULT_TOO_LARGE`.
2. The job MUST remain in the `active` state.
3. The worker SHOULD store the result externally and retry ACK with a result reference.

**Rationale:** Unbounded results can exhaust backend storage. A single job returning a 1 GB result into Redis would degrade performance for all other jobs. Size limits force producers to use appropriate storage for large outputs.

### 7.3 External Result Storage

For results exceeding the size limit, the RECOMMENDED pattern is:

1. Worker stores the result in external storage (S3, GCS, a database, a filesystem).
2. Worker ACKs the job with a result reference containing the external URI.
3. Consumer retrieves the result reference via INFO/GET and fetches from external storage.

The job system is NOT responsible for managing external storage. It does not fetch, cache, or validate external results. The result reference is an opaque pointer that the application layer interprets.

---

## 8. Result Retrieval

### 8.1 Polling

Clients retrieve results by polling the job's current state via the INFO operation:

```http
GET /ojs/v1/jobs/{id} HTTP/1.1
```

If the job is in a terminal state, the response includes the `result` (or `error`) field. If the job is still active, the client polls again after a delay.

Implementations SHOULD include a `Retry-After` header when responding to INFO requests for non-terminal jobs.

### 8.2 Blocking Wait

Implementations SHOULD support a blocking wait endpoint that holds the connection open until the job reaches a terminal state or a timeout expires:

```http
GET /ojs/v1/jobs/{id}/result?wait=true&timeout=30 HTTP/1.1
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `wait` | boolean | false | When true, block until result is available. |
| `timeout` | integer (seconds) | 30 | Maximum time to block before returning 408. |

**Response codes:**

| Code | Condition |
|------|-----------|
| 200 | Job completed; body contains result. |
| 410 | Job completed but result has been pruned (TTL expired). |
| 404 | Job not found. |
| 408 | Wait timeout expired; job is still active. |

**Rationale:** Blocking wait eliminates the polling overhead for request-response patterns where the producer needs the result before proceeding. This is common in web applications that enqueue a background job and wait for its completion.

### 8.3 Streaming

When both the results extension and the progress extension are supported, implementations MAY offer a combined progress+result SSE stream:

```http
GET /ojs/v1/jobs/{id}/result/stream HTTP/1.1
Accept: text/event-stream
```

The stream emits progress events followed by a final `result` or `error` event:

```
event: progress
data: {"progress": 0.5, "data": {"items_processed": 500}}

event: progress
data: {"progress": 1.0}

event: result
data: {"value": {"total_items": 1000, "report_url": "https://..."}}
```

---

## 9. Interaction with Other Extensions

### 9.1 Workflows

Workflow result passing (defined in ojs-workflows.md) depends on the results extension for storage and retrieval:

- **Chain:** Step N's result is stored and made available to step N+1 via `parent_results`. The result TTL for intermediate steps SHOULD be at least as long as the expected workflow duration.
- **Group:** All job results are aggregated and keyed by position. The group's composite result is stored when all jobs complete.
- **Batch:** Callback jobs receive all batch results via `parent_results`. Both successful results and error objects are included.

Implementations MUST retain intermediate workflow results until the workflow reaches a terminal state, regardless of individual job `result_ttl` values.

### 9.2 Progress

Progress (via ojs-progress.md) and results are complementary:

- **Progress** is intermediate, mutable, and represents work-in-progress.
- **Results** are final, immutable, and represent the job's output.

A progress update at `1.0` does NOT imply the result is stored. The result is stored only when the worker ACKs the job.

### 9.3 Bulk Operations

When retrieving results for multiple jobs (e.g., all jobs in a batch), implementations SHOULD support bulk result retrieval:

```http
POST /ojs/v1/jobs/results HTTP/1.1
Content-Type: application/json

{
  "ids": [
    "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
    "019539a4-b68c-7def-8000-2b3c4d5e6f7a"
  ]
}
```

The response MUST include results for all requested jobs, using `null` for jobs that are not in a terminal state or whose results have been pruned.

### 9.4 Encryption

When the encryption extension is active, result values SHOULD be encrypted at rest using the same codec chain applied to job args. The result MUST be decrypted transparently when retrieved by an authorized client.

---

## 10. HTTP Binding

### 10.1 ACK with Result

```http
POST /ojs/v1/jobs/{id}/ack HTTP/1.1
Content-Type: application/json

{
  "result": {
    "transaction_id": "txn_abc123",
    "amount": 99.99,
    "currency": "USD"
  }
}
```

### 10.2 Retrieve Result

```http
GET /ojs/v1/jobs/{id} HTTP/1.1
Accept: application/openjobspec+json

HTTP/1.1 200 OK
Content-Type: application/openjobspec+json

{
  "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "type": "payment.process",
  "state": "completed",
  "result": {
    "transaction_id": "txn_abc123",
    "amount": 99.99,
    "currency": "USD"
  },
  "result_stored_at": "2026-01-15T10:30:02.789Z",
  "result_expires_at": "2026-01-22T10:30:02.789Z",
  "result_size_bytes": 76
}
```

### 10.3 Blocking Wait

```http
GET /ojs/v1/jobs/019539a4-b68c-7def-8000-1a2b3c4d5e6f/result?wait=true&timeout=30 HTTP/1.1

HTTP/1.1 200 OK
Content-Type: application/json

{
  "job_id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "state": "completed",
  "result": {
    "transaction_id": "txn_abc123"
  }
}
```

### 10.4 Bulk Result Retrieval

```http
POST /ojs/v1/jobs/results HTTP/1.1
Content-Type: application/json

{
  "ids": ["job_1", "job_2", "job_3"]
}

HTTP/1.1 200 OK
Content-Type: application/json

{
  "results": {
    "job_1": {"state": "completed", "result": {"status": "ok"}},
    "job_2": {"state": "completed", "result": null},
    "job_3": {"state": "active", "result": null}
  }
}
```

### 10.5 Result Pruned

```http
GET /ojs/v1/jobs/019539a4-b68c-7def-8000-1a2b3c4d5e6f/result HTTP/1.1

HTTP/1.1 410 Gone
Content-Type: application/json

{
  "error": {
    "code": "RESULT_PRUNED",
    "message": "Result expired at 2026-01-22T10:30:02.789Z"
  }
}
```

---

## 11. Observability

### 11.1 Events

| Event Type | Trigger |
|------------|---------|
| `result.stored` | Result successfully persisted after ACK. |
| `result.pruned` | Result deleted after TTL expiry. |
| `result.rejected` | ACK rejected due to `RESULT_TOO_LARGE`. |
| `result.retrieved` | Result accessed via INFO or blocking wait. |

### 11.2 Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `ojs.result.size_bytes` | Histogram | Result size in bytes, labeled by `queue`, `job_type`. |
| `ojs.result.ttl_seconds` | Histogram | Configured result TTL, labeled by `queue`, `job_type`. |
| `ojs.result.pruned.count` | Counter | Number of results pruned, labeled by `queue`. |
| `ojs.result.retrieval.count` | Counter | Number of result retrievals, labeled by `method` (poll, wait, stream). |
| `ojs.result.rejected.count` | Counter | Number of results rejected due to size limits. |

---

## 12. Conformance Requirements

### 12.1 Required

| Capability | Requirement |
|------------|-------------|
| Result storage on ACK | Implementations MUST store the result value provided in ACK. |
| Error storage on terminal FAIL | Implementations MUST store the error object when a job is discarded. |
| Result TTL | Implementations MUST support `result_ttl` for time-based retention. |
| Result size limits | Implementations MUST impose and enforce a maximum result size. |
| Result retrieval via INFO | Implementations MUST return the result in INFO responses for terminal jobs. |

### 12.2 Recommended

| Capability | Requirement |
|------------|-------------|
| Blocking wait | Implementations SHOULD support blocking wait for result retrieval. |
| Result metadata | Implementations SHOULD store and return `result_stored_at`, `result_expires_at`, `result_size_bytes`. |
| Bulk retrieval | Implementations SHOULD support bulk result retrieval. |
| External result references | Implementations SHOULD recognize and pass through external result references. |

### 12.3 Optional

| Capability | Requirement |
|------------|-------------|
| SSE streaming | Implementations MAY support streaming result delivery. |
| Permanent retention | Implementations MAY support `result_ttl: -1` for permanent results. |
| Result encryption | Implementations MAY encrypt results at rest. |

---

## 13. Prior Art

| System | Result Handling |
|--------|----------------|
| **Celery** | Rich result backend with multiple storage options (Redis, database, S3). `AsyncResult` provides `.get()` with timeout. Result expiry via `result_expires`. Closest model to this specification. |
| **Sidekiq** | No built-in result storage. Results must be stored by the application (database, cache). Sidekiq Pro adds batches with callback results. |
| **BullMQ** | `returnvalue` stored on completed jobs. Retrieved via `job.returnvalue`. No explicit TTL; results persist with the job. |
| **Temporal** | Activity results are first-class, stored durably, and passed to the next workflow step. Size limits enforced (2 MB default). |
| **Faktory** | No result storage. Jobs are fire-and-forget; applications must store results externally. |
| **River** | No built-in result storage. Jobs can write results to a shared database. |
| **Google Cloud Tasks** | HTTP response body from the handler is the "result." No persistent result storage. |

---

## 14. Examples

### 14.1 Simple Result

```json
{
  "type": "thumbnail.generate",
  "queue": "media",
  "args": ["image_001.jpg", "128x128"],
  "result_ttl": 3600
}
```

After completion:

```json
{
  "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "type": "thumbnail.generate",
  "state": "completed",
  "result": "https://cdn.example.com/thumbs/image_001_128x128.jpg",
  "result_stored_at": "2026-01-15T10:30:02.789Z",
  "result_expires_at": "2026-01-15T11:30:02.789Z"
}
```

### 14.2 External Result Reference

```json
{
  "id": "019539a4-b68c-7def-8000-2b3c4d5e6f7a",
  "type": "report.generate",
  "state": "completed",
  "result": {
    "$ref": "ojs://results/external",
    "uri": "s3://reports-bucket/quarterly-2025-Q4.pdf",
    "content_type": "application/pdf",
    "size_bytes": 15728640,
    "checksum": "sha256:e3b0c44298fc1c149afbf4c8996fb924..."
  }
}
```

### 14.3 Failed Job with Error Result

```json
{
  "id": "019539a4-b68c-7def-8000-3c4d5e6f7a8b",
  "type": "payment.process",
  "state": "discarded",
  "error": {
    "type": "payment_declined",
    "message": "Card declined: insufficient funds",
    "code": "CARD_DECLINED",
    "attempt": 3
  },
  "result_stored_at": "2026-01-15T10:35:00.000Z",
  "result_expires_at": "2026-01-22T10:35:00.000Z"
}
```

### 14.4 Workflow with Result Passing

Step 1 (fetch data):
```json
{
  "type": "data.fetch",
  "args": ["dataset_v2"],
  "result": {"rows": 50000, "path": "/tmp/dataset_v2.csv"}
}
```

Step 2 (process data) receives Step 1's result via `parent_results`:
```json
{
  "type": "data.process",
  "args": ["aggregate"],
  "context": {
    "parent_results": {
      "0": {"rows": 50000, "path": "/tmp/dataset_v2.csv"}
    }
  }
}
```

---

## Appendix A: Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0-rc.1 | 2026-02-15 | Initial release candidate. |
