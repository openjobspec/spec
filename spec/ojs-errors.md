# Open Job Spec: Error Catalog

| Field        | Value                                  |
|-------------|----------------------------------------|
| **Title**   | OJS Error Catalog                      |
| **Version** | 1.0.0-rc.1                             |
| **Date**    | 2026-02-15                             |
| **Status**  | Release Candidate 1                    |
| **Layer**   | Cross-cutting (applies to all layers)  |
| **URI**     | https://openjobspec.org/spec/v1/errors |

---

## Table of Contents

1.  [Introduction](#1-introduction)
2.  [Notational Conventions](#2-notational-conventions)
3.  [Error Structure](#3-error-structure)
4.  [Error Code Taxonomy](#4-error-code-taxonomy)
    - 4.1 [Validation Errors](#41-validation-errors-client-errors-never-retryable)
    - 4.2 [Conflict Errors](#42-conflict-errors-client-errors-never-retryable)
    - 4.3 [Authentication & Authorization Errors](#43-authentication--authorization-errors-never-retryable)
    - 4.4 [Resource Errors](#44-resource-errors-conditionally-retryable)
    - 4.5 [Execution Errors](#45-execution-errors-job-level-retryability-depends-on-policy)
    - 4.6 [Backend/Infrastructure Errors](#46-backendinfrastructure-errors-always-retryable)
    - 4.7 [Handler Response Codes](#47-handler-response-codes-worker--backend-signals)
5.  [Protocol Binding Mapping](#5-protocol-binding-mapping)
    - 5.1 [HTTP Status Code Mapping](#51-http-status-code-mapping)
    - 5.2 [gRPC Status Code Mapping](#52-grpc-status-code-mapping)
    - 5.3 [AMQP Error Mapping](#53-amqp-error-mapping)
6.  [Error History](#6-error-history)
7.  [Retryability Rules](#7-retryability-rules)
8.  [Custom Error Codes](#8-custom-error-codes)
9.  [SDK Error Handling Guidance](#9-sdk-error-handling-guidance)
10. [Conformance Requirements](#10-conformance-requirements)
11. [Prior Art](#11-prior-art)
12. [Examples](#12-examples)

---

## 1. Introduction

Every distributed system needs a well-defined error taxonomy. Without one, producers,
backends, and workers invent incompatible error codes, making cross-implementation
interoperability impossible. This document defines the canonical OJS error codes, the
structured error format, and the mapping to every protocol binding.

Analogous to HTTP status codes ([RFC 9110](https://www.rfc-editor.org/rfc/rfc9110)) and
gRPC status codes, OJS defines a closed set of error codes that all implementations
MUST support.

This document is the **single source of truth** for all error codes, error structure, and
error mapping across HTTP, gRPC, and AMQP bindings. Individual binding specifications
(`ojs-http-binding.md`, `ojs-grpc-binding.md`, `ojs-amqp-binding.md`) define
transport-specific details, but this document defines the canonical error taxonomy.

> **Rationale:** A unified error catalog prevents each binding from evolving its own
> incompatible error vocabulary. SDK authors need exactly one place to look up what
> error codes exist, when they are retryable, and how they map to every transport.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD",
"SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be
interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt).

---

## 3. Error Structure

All OJS errors are represented as a JSON object with the following schema:

```json
{
  "code": "VALIDATION_FAILED",
  "message": "Job type 'email.send' is not registered",
  "details": {
    "field": "type",
    "value": "email.send",
    "constraint": "must be a registered job type"
  },
  "retryable": false,
  "doc_url": "https://openjobspec.org/errors/VALIDATION_FAILED"
}
```

### 3.1 Required Fields

| Field       | Type   | Description |
|-------------|--------|-------------|
| `code`      | string | A value from the canonical error code enum (§4). MUST be SCREAMING_SNAKE_CASE. |
| `message`   | string | A human-readable description of the error. MUST be in English. MAY be localized in addition. |

### 3.2 Optional Fields

| Field       | Type    | Default                      | Description |
|-------------|---------|------------------------------|-------------|
| `details`   | object  | *(omitted)*                  | Structured context about the error. Contents are error-code-specific. |
| `retryable` | boolean | *(per category default, §7)* | Whether the caller SHOULD retry the operation. |
| `doc_url`   | string  | *(omitted)*                  | A URL pointing to documentation for this error code. |

### 3.3 Normative Requirements

Backends MUST return errors in this format for all error responses, regardless of
protocol binding.

> **Rationale:** A consistent error structure enables generic error handling in SDKs.
> Without a guaranteed schema, every SDK must defensively handle an unknown set of
> error shapes, increasing complexity and bugs.

The `code` field MUST contain a value from the canonical enum defined in §4, or a
valid custom error code as defined in §8.

> **Rationale:** A closed enum allows SDKs to `switch` on error codes and provide
> typed exception hierarchies.

The `message` field MUST be a non-empty string.

> **Rationale:** Even when SDKs map codes to typed exceptions, the message provides
> essential debugging context that error codes alone cannot convey.

When the `retryable` field is present, it MUST accurately reflect whether the
operation can be meaningfully retried.

> **Rationale:** An incorrect `retryable` flag is worse than no flag — it causes
> SDKs to either retry hopelessly or give up on transient failures.

---

## 4. Error Code Taxonomy

OJS error codes use SCREAMING_SNAKE_CASE and are organized into seven categories.
Each category has a default retryability that applies when the `retryable` field is
omitted from the error response.

### 4.1 Validation Errors (client errors, never retryable)

Validation errors indicate that the request is structurally or semantically invalid.
The caller MUST fix the input before retrying; automated retries will always fail.

| Code | Description | Typical Trigger |
|------|-------------|-----------------|
| `INVALID_PAYLOAD` | Job envelope fails structural validation | Malformed JSON, missing required fields |
| `INVALID_JOB_TYPE` | Job type is not registered or does not match the allowlist | Unknown `type` value |
| `INVALID_QUEUE` | Queue name is invalid or does not exist | Bad characters, too long (>255 bytes) |
| `INVALID_ARGS` | Job args fail type checking or schema validation | Wrong types, constraint violations |
| `INVALID_METADATA` | Meta field is malformed or exceeds size limit (64 KB) | Meta too large, invalid keys |
| `INVALID_STATE_TRANSITION` | Attempted an invalid lifecycle state change | ACK on a non-active job, CANCEL on completed job |
| `INVALID_RETRY_POLICY` | Retry policy fails validation | Negative `max_attempts`, invalid backoff |
| `INVALID_CRON_EXPRESSION` | Cron expression cannot be parsed | Bad syntax |
| `SCHEMA_VALIDATION_FAILED` | Job args don't conform to the registered schema for this job type+version | Schema mismatch |

### 4.2 Conflict Errors (client errors, never retryable)

Conflict errors indicate that the operation violates a uniqueness or state constraint.
The caller MUST resolve the conflict (e.g., wait for the existing job to complete, use
a different uniqueness key) before retrying.

| Code | Description | Typical Trigger |
|------|-------------|-----------------|
| `DUPLICATE_JOB` | Unique job constraint violated | Job with same uniqueness key already exists |
| `JOB_ALREADY_COMPLETED` | Operation attempted on a terminal job | ACK/FAIL on already-completed job |
| `JOB_ALREADY_CANCELLED` | Operation attempted on a cancelled job | ACK/FAIL on cancelled job |

### 4.3 Authentication & Authorization Errors (never retryable)

Auth errors indicate missing, invalid, or insufficient credentials. Automated retries
without fixing credentials will always fail.

| Code | Description | Typical Trigger |
|------|-------------|-----------------|
| `UNAUTHENTICATED` | No credentials provided or credentials invalid | Missing/expired token, bad API key |
| `PERMISSION_DENIED` | Authenticated but lacks required permission | Producer trying to enqueue to restricted queue |
| `TOKEN_EXPIRED` | Authentication token has expired | JWT past expiry |
| `TENANT_ACCESS_DENIED` | Operation on a tenant the caller doesn't have access to | Cross-tenant request |

### 4.4 Resource Errors (conditionally retryable)

Resource errors indicate issues with the target resource or system limits. Some are
retryable (the condition may clear); others are permanent.

| Code | Description | Retryable | Typical Trigger |
|------|-------------|-----------|-----------------|
| `NOT_FOUND` | Requested job, queue, or resource does not exist | No | GET on non-existent job ID |
| `QUEUE_PAUSED` | Target queue is paused and not accepting jobs | Yes | Enqueue to paused queue |
| `QUEUE_FULL` | Queue depth has reached the configured bound | Yes | Backpressure (`ojs-backpressure.md`) |
| `RATE_LIMITED` | Rate limit or concurrency limit exceeded | Yes | `ojs-rate-limiting.md` |
| `PAYLOAD_TOO_LARGE` | Job envelope exceeds backend max payload size | No | >1 MB default, backend-specific |
| `METADATA_TOO_LARGE` | Meta field exceeds 64 KB limit | No | Large metadata |
| `QUEUE_NAME_TOO_LONG` | Queue name exceeds 255 bytes | No | Overly long queue name |
| `JOB_TYPE_TOO_LONG` | Job type exceeds 255 bytes | No | Overly long job type |
| `CHECKSUM_MISMATCH` | External payload reference checksum failed | No | Corrupted external payload |
| `UNSUPPORTED_FEATURE` | Feature requires a conformance level the backend doesn't support | No | Using workflows on Level 0 backend |
| `UNSUPPORTED_COMPRESSION` | Unsupported compression codec | No | Unknown codec name |

### 4.5 Execution Errors (job-level, retryability depends on policy)

Execution errors occur during job handler invocation. Default retryability is governed
by the job's retry policy (see `ojs-retry.md`).

| Code | Description | Default Retryable | Typical Trigger |
|------|-------------|-------------------|-----------------|
| `HANDLER_ERROR` | Job handler threw an exception during execution | Yes (per retry policy) | Unhandled exception in handler |
| `HANDLER_TIMEOUT` | Job handler exceeded the configured execution timeout | Yes (per retry policy) | Slow handler |
| `HANDLER_PANIC` | Job handler caused an unrecoverable error (panic, segfault) | Yes (per retry policy) | Runtime crash |
| `NON_RETRYABLE_ERROR` | Error type matched `non_retryable_errors` in retry policy | No | e.g., `CardStolenError` |
| `JOB_CANCELLED` | Job was cancelled while executing | No | CANCEL during active state |

### 4.6 Backend/Infrastructure Errors (always retryable)

Backend errors indicate internal failures in the OJS backend or its dependencies.
SDKs SHOULD auto-retry these with exponential backoff.

| Code | Description | Typical Trigger |
|------|-------------|-----------------|
| `BACKEND_ERROR` | Internal backend storage or transport failure | Redis connection lost, Postgres query timeout |
| `BACKEND_UNAVAILABLE` | Backend is unreachable | Service down, network partition |
| `REPLICATION_LAG` | Operation failed due to replication consistency issue | Read-after-write on async replica |
| `BACKEND_TIMEOUT` | Backend operation timed out | Slow query, lock contention |

### 4.7 Handler Response Codes (worker → backend signals)

These are **not** error codes but handler-to-runtime signals that control retry
behavior. They are included here for completeness because they interact directly with
the error taxonomy.

| Code | Behavior | Description |
|------|----------|-------------|
| `ACK` | Complete successfully | Handler succeeded |
| `RETRY` | Retry with normal backoff | Handler requests explicit retry (default on failure) |
| `DISCARD` | Discard immediately | No retry, no DLQ, job gone |
| `DEAD_LETTER` | Move to DLQ | Skip remaining retries, preserve for inspection |

Handler response codes are defined normatively in `ojs-worker-protocol.md` and
`ojs-retry.md`. When a handler returns `RETRY`, the backend MUST treat the failure as
retryable regardless of the error code. When a handler returns `DISCARD`, the backend
MUST NOT retry and MUST NOT dead-letter the job.

---

## 5. Protocol Binding Mapping

Each protocol binding maps OJS error codes to transport-native error mechanisms. The
OJS error code is always the authoritative identifier; transport-level codes provide
coarse-grained categorization only.

### 5.1 HTTP Status Code Mapping

| OJS Error Code | HTTP Status | Headers |
|----------------|-------------|---------|
| `INVALID_PAYLOAD` | 400 Bad Request | |
| `INVALID_JOB_TYPE` | 400 Bad Request | |
| `INVALID_QUEUE` | 400 Bad Request | |
| `INVALID_ARGS` | 400 Bad Request | |
| `INVALID_METADATA` | 400 Bad Request | |
| `INVALID_STATE_TRANSITION` | 409 Conflict | |
| `INVALID_RETRY_POLICY` | 400 Bad Request | |
| `INVALID_CRON_EXPRESSION` | 400 Bad Request | |
| `SCHEMA_VALIDATION_FAILED` | 422 Unprocessable Entity | |
| `DUPLICATE_JOB` | 409 Conflict | |
| `JOB_ALREADY_COMPLETED` | 409 Conflict | |
| `JOB_ALREADY_CANCELLED` | 409 Conflict | |
| `UNAUTHENTICATED` | 401 Unauthorized | `WWW-Authenticate` |
| `PERMISSION_DENIED` | 403 Forbidden | |
| `TOKEN_EXPIRED` | 401 Unauthorized | `WWW-Authenticate` |
| `TENANT_ACCESS_DENIED` | 403 Forbidden | |
| `NOT_FOUND` | 404 Not Found | |
| `QUEUE_PAUSED` | 422 Unprocessable Entity | |
| `QUEUE_FULL` | 429 Too Many Requests | `Retry-After` |
| `RATE_LIMITED` | 429 Too Many Requests | `Retry-After`, `X-RateLimit-*` |
| `PAYLOAD_TOO_LARGE` | 413 Payload Too Large | |
| `METADATA_TOO_LARGE` | 413 Payload Too Large | |
| `UNSUPPORTED_FEATURE` | 422 Unprocessable Entity | |
| `BACKEND_ERROR` | 500 Internal Server Error | |
| `BACKEND_UNAVAILABLE` | 503 Service Unavailable | `Retry-After` |
| `BACKEND_TIMEOUT` | 504 Gateway Timeout | |

The HTTP binding MUST include the OJS error code in the JSON response body alongside
the HTTP status code.

> **Rationale:** HTTP has a limited set of status codes; OJS needs finer granularity
> for SDK error handling. For example, HTTP 400 maps to seven distinct OJS validation
> errors, each requiring different corrective action.

HTTP error response body format:

```json
{
  "code": "DUPLICATE_JOB",
  "message": "A job with uniqueness key 'email.send:user@example.com' already exists in state 'active'",
  "details": {
    "existing_job_id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
    "unique_key": "email.send:user@example.com",
    "existing_state": "active"
  },
  "retryable": false,
  "doc_url": "https://openjobspec.org/errors/DUPLICATE_JOB"
}
```

When the HTTP binding returns `429 Too Many Requests`, it MUST include the
`Retry-After` header with either a delay in seconds or an HTTP-date.

> **Rationale:** Without `Retry-After`, clients must guess backoff timing, leading to
> either thundering herd retries or unnecessarily long waits.

### 5.2 gRPC Status Code Mapping

| OJS Error Code | gRPC Status | `google.rpc.ErrorInfo.reason` |
|----------------|-------------|-------------------------------|
| `INVALID_PAYLOAD` | INVALID_ARGUMENT (3) | `OJS_INVALID_PAYLOAD` |
| `INVALID_JOB_TYPE` | INVALID_ARGUMENT (3) | `OJS_INVALID_JOB_TYPE` |
| `INVALID_ARGS` | INVALID_ARGUMENT (3) | `OJS_INVALID_ARGS` |
| `SCHEMA_VALIDATION_FAILED` | INVALID_ARGUMENT (3) | `OJS_SCHEMA_VALIDATION_FAILED` |
| `DUPLICATE_JOB` | ALREADY_EXISTS (6) | `OJS_DUPLICATE_JOB` |
| `INVALID_STATE_TRANSITION` | FAILED_PRECONDITION (9) | `OJS_INVALID_STATE_TRANSITION` |
| `JOB_ALREADY_COMPLETED` | FAILED_PRECONDITION (9) | `OJS_JOB_ALREADY_COMPLETED` |
| `UNAUTHENTICATED` | UNAUTHENTICATED (16) | `OJS_UNAUTHENTICATED` |
| `PERMISSION_DENIED` | PERMISSION_DENIED (7) | `OJS_PERMISSION_DENIED` |
| `NOT_FOUND` | NOT_FOUND (5) | `OJS_NOT_FOUND` |
| `QUEUE_PAUSED` | FAILED_PRECONDITION (9) | `OJS_QUEUE_PAUSED` |
| `QUEUE_FULL` | RESOURCE_EXHAUSTED (8) | `OJS_QUEUE_FULL` |
| `RATE_LIMITED` | RESOURCE_EXHAUSTED (8) | `OJS_RATE_LIMITED` |
| `PAYLOAD_TOO_LARGE` | RESOURCE_EXHAUSTED (8) | `OJS_PAYLOAD_TOO_LARGE` |
| `UNSUPPORTED_FEATURE` | UNIMPLEMENTED (12) | `OJS_UNSUPPORTED_FEATURE` |
| `HANDLER_TIMEOUT` | DEADLINE_EXCEEDED (4) | `OJS_HANDLER_TIMEOUT` |
| `JOB_CANCELLED` | CANCELLED (1) | `OJS_JOB_CANCELLED` |
| `BACKEND_ERROR` | INTERNAL (13) | `OJS_BACKEND_ERROR` |
| `BACKEND_UNAVAILABLE` | UNAVAILABLE (14) | `OJS_BACKEND_UNAVAILABLE` |

gRPC implementations MUST use the `google.rpc.ErrorInfo` detail message to convey
the OJS error code in the `reason` field, with `domain` set to `"openjobspec.org"`.

> **Rationale:** gRPC defines only 16 status codes, which is far too coarse for OJS
> error handling. `ErrorInfo.reason` provides the fine-grained OJS error code that
> SDKs need to make precise retry and error-handling decisions.

The full OJS error object (including `details` and `retryable`) SHOULD be encoded as
a `google.rpc.ErrorInfo.metadata` map or as an additional `google.protobuf.Struct`
detail message.

### 5.3 AMQP Error Mapping

AMQP does not have a request-response error model like HTTP or gRPC. Errors are
propagated through message headers on republished messages.

| OJS Error Code | AMQP Mechanism | Header/Property |
|----------------|----------------|-----------------|
| `HANDLER_ERROR` | Basic.Nack + republish to retry exchange | `x-ojs-error-code: HANDLER_ERROR` |
| `NON_RETRYABLE_ERROR` | Basic.Nack + route to DLX | `x-ojs-error-code: NON_RETRYABLE_ERROR` |
| `HANDLER_TIMEOUT` | Basic.Nack + republish with backoff TTL | `x-ojs-error-code: HANDLER_TIMEOUT` |
| `QUEUE_FULL` | Basic.Return (mandatory flag, unroutable) | — |
| `RATE_LIMITED` | Basic.Nack + requeue with delay | `x-ojs-error-code: RATE_LIMITED` |
| All errors | Error details in message headers | `x-ojs-error-message`, `x-ojs-error-details` |

AMQP implementations MUST propagate the OJS error code in the `x-ojs-error-code`
message header when republishing failed jobs.

> **Rationale:** AMQP lacks a structured error response mechanism. Message headers
> are the only reliable mechanism for conveying error metadata alongside the job
> payload, enabling consumers and monitoring tools to inspect failure reasons.

AMQP implementations SHOULD also set `x-ojs-error-message` with the human-readable
error message, and MAY set `x-ojs-error-details` with a JSON-encoded string of the
`details` object.

---

## 6. Error History

When a job fails one or more times, the backend MUST record error information in the
`errors` array within the job's system-managed attributes.

```json
{
  "errors": [
    {
      "code": "HANDLER_ERROR",
      "message": "SMTP connection refused on port 25",
      "type": "SmtpConnectionError",
      "attempt": 1,
      "occurred_at": "2026-02-15T10:30:00Z"
    },
    {
      "code": "HANDLER_TIMEOUT",
      "message": "Handler exceeded 30s timeout",
      "type": "TimeoutError",
      "attempt": 2,
      "occurred_at": "2026-02-15T10:35:00Z"
    }
  ]
}
```

### 6.1 Error History Entry Fields

| Field         | Type   | Required | Description |
|---------------|--------|----------|-------------|
| `code`        | string | Yes      | OJS error code from §4 |
| `message`     | string | Yes      | Human-readable error description |
| `type`        | string | No       | Language-specific error/exception type name |
| `attempt`     | integer| Yes      | The attempt number that produced this error (1-indexed) |
| `occurred_at` | string | Yes      | ISO 8601 timestamp of when the error occurred |

### 6.2 Retention Requirements

Backends MUST preserve at least the **10 most recent** error entries per job (as
specified in `ojs-retry.md`).

> **Rationale:** Error history is critical for debugging failed jobs. Ten entries
> covers the default `max_attempts` of 3 with generous headroom, while bounding
> storage for jobs with very high retry counts.

Each entry MUST include `code`, `message`, `attempt`, and `occurred_at`.

> **Rationale:** These four fields are the minimum needed to reconstruct a timeline
> of failures for debugging. Without `attempt`, errors cannot be correlated with
> retry count. Without `occurred_at`, time-dependent failures (e.g., transient
> network issues) cannot be diagnosed.

---

## 7. Retryability Rules

Default retryability is determined by the error category. The `retryable` field in the
error response, when present, overrides the default.

| Category | Default Retryable | Override |
|----------|-------------------|----------|
| Validation (§4.1) | No | Never — fix the input |
| Conflict (§4.2) | No | Never — resolve the conflict |
| Auth (§4.3) | No | Never — fix credentials/permissions |
| Resource (§4.4) | Varies (per code) | `retryable` field in response |
| Execution (§4.5) | Yes (per retry policy) | `non_retryable_errors`, handler response code |
| Backend (§4.6) | Yes | SDK SHOULD auto-retry with backoff |

SDKs MUST respect the `retryable` field when present in the error response. When
the field is absent, SDKs MUST use the default retryability for the error category.

> **Rationale:** Explicit retryability prevents wasted retry attempts on permanent
> errors and ensures transient errors are retried. The two-tier system (category
> default + per-response override) provides both simplicity for common cases and
> flexibility for edge cases.

SDKs MUST NOT automatically retry validation errors (§4.1), conflict errors (§4.2),
or authentication errors (§4.3), even if a custom `retryable: true` is set.

> **Rationale:** These error categories represent permanent conditions that cannot
> be resolved by retrying. Allowing override would mask bugs in producers.

For backend errors (§4.6), SDKs SHOULD implement automatic retry with exponential
backoff and jitter, using a maximum of 5 retry attempts with initial delay of 100ms.

---

## 8. Custom Error Codes

Implementations MAY define custom error codes for domain-specific errors that fall
outside the canonical taxonomy.

### 8.1 Naming Convention

Custom error codes MUST use a namespaced prefix to avoid collisions with canonical
codes:

**Format:** `{NAMESPACE}_{CODE}`

- `NAMESPACE` MUST be uppercase alphanumeric (A–Z, 0–9), 2–30 characters.
- `CODE` MUST be uppercase alphanumeric with underscores, following the same
  SCREAMING_SNAKE_CASE convention as canonical codes.

**Examples:**

- `ACME_CREDIT_CHECK_FAILED`
- `STRIPE_CARD_DECLINED`
- `MYAPP_INSUFFICIENT_BALANCE`

### 8.2 Restrictions

Custom error codes MUST NOT use any prefix that starts with `OJS_` or that matches
a canonical code defined in §4.

> **Rationale:** The `OJS_` prefix is reserved for future canonical codes. Collision
> with canonical codes would break SDK error handling.

### 8.3 SDK Handling of Unknown Codes

SDKs that encounter an unknown error code MUST treat it as **non-retryable** unless
the `retryable` field is explicitly `true`.

> **Rationale:** Defaulting to non-retryable is the safe choice. An unknown code
> may represent a permanent error, and retrying could cause side effects.

---

## 9. SDK Error Handling Guidance

This section provides non-normative guidance for SDK implementors.

### 9.1 Requirements

- SDKs MUST map OJS error codes to language-idiomatic exception/error types.
- SDKs MUST include the OJS error code, message, and details in the error object.
- SDKs MUST expose the `retryable` property for programmatic retry decisions.
- SDKs SHOULD provide typed error classes for each category.

### 9.2 Recommended Error Class Hierarchy

SDKs SHOULD provide a base `OjsError` class with subclasses for each category:

```
OjsError (base)
├── OjsValidationError      ← INVALID_PAYLOAD, INVALID_JOB_TYPE, INVALID_QUEUE, ...
├── OjsConflictError        ← DUPLICATE_JOB, JOB_ALREADY_COMPLETED, JOB_ALREADY_CANCELLED
├── OjsAuthError            ← UNAUTHENTICATED, PERMISSION_DENIED, TOKEN_EXPIRED, ...
├── OjsResourceError        ← NOT_FOUND, QUEUE_PAUSED, QUEUE_FULL, RATE_LIMITED, ...
├── OjsExecutionError       ← HANDLER_ERROR, HANDLER_TIMEOUT, HANDLER_PANIC, ...
└── OjsBackendError         ← BACKEND_ERROR, BACKEND_UNAVAILABLE, BACKEND_TIMEOUT, ...
```

### 9.3 Error Code Mapping (pseudocode)

```
INVALID_PAYLOAD          → OjsValidationError
INVALID_JOB_TYPE         → OjsValidationError
INVALID_QUEUE            → OjsValidationError
INVALID_ARGS             → OjsValidationError
INVALID_METADATA         → OjsValidationError
INVALID_STATE_TRANSITION → OjsValidationError
INVALID_RETRY_POLICY     → OjsValidationError
INVALID_CRON_EXPRESSION  → OjsValidationError
SCHEMA_VALIDATION_FAILED → OjsValidationError
DUPLICATE_JOB            → OjsConflictError
JOB_ALREADY_COMPLETED    → OjsConflictError
JOB_ALREADY_CANCELLED    → OjsConflictError
UNAUTHENTICATED          → OjsAuthError
PERMISSION_DENIED        → OjsAuthError
TOKEN_EXPIRED            → OjsAuthError
TENANT_ACCESS_DENIED     → OjsAuthError
NOT_FOUND                → OjsResourceError  (retryable=false)
QUEUE_PAUSED             → OjsResourceError  (retryable=true)
QUEUE_FULL               → OjsResourceError  (retryable=true)
RATE_LIMITED             → OjsResourceError  (retryable=true)
PAYLOAD_TOO_LARGE        → OjsResourceError  (retryable=false)
HANDLER_ERROR            → OjsExecutionError (retryable=per policy)
HANDLER_TIMEOUT          → OjsExecutionError (retryable=per policy)
HANDLER_PANIC            → OjsExecutionError (retryable=per policy)
NON_RETRYABLE_ERROR      → OjsExecutionError (retryable=false)
JOB_CANCELLED            → OjsExecutionError (retryable=false)
BACKEND_ERROR            → OjsBackendError   (retryable=true)
BACKEND_UNAVAILABLE      → OjsBackendError   (retryable=true)
REPLICATION_LAG          → OjsBackendError   (retryable=true)
BACKEND_TIMEOUT          → OjsBackendError   (retryable=true)
```

---

## 10. Conformance Requirements

The following conformance requirements apply to all OJS implementations.

| ID | Requirement | Level |
|----|-------------|-------|
| **ERR-001** | Backends MUST return errors in the canonical structure defined in §3. | MUST |
| **ERR-002** | Backends MUST use canonical error codes (§4) for standard error conditions, not custom codes. | MUST |
| **ERR-003** | Backends MUST include the `code` field in all error responses. | MUST |
| **ERR-004** | Backends MUST include the `message` field in all error responses. | MUST |
| **ERR-005** | HTTP binding MUST include the OJS error code in the JSON response body alongside the HTTP status code. | MUST |
| **ERR-006** | HTTP binding MUST include `Retry-After` header when returning 429 or 503 status codes. | MUST |
| **ERR-007** | gRPC binding MUST use `google.rpc.ErrorInfo` with `domain` set to `"openjobspec.org"` and `reason` set to the OJS error code prefixed with `OJS_`. | MUST |
| **ERR-008** | AMQP binding MUST propagate the OJS error code in the `x-ojs-error-code` message header when republishing failed jobs. | MUST |
| **ERR-009** | SDKs MUST map OJS error codes to language-idiomatic typed exceptions/errors. | MUST |
| **ERR-010** | SDKs MUST expose the `retryable` property on error objects for programmatic retry decisions. | MUST |
| **ERR-011** | Backends MUST preserve at least the 10 most recent error history entries per job. | MUST |
| **ERR-012** | Error history entries MUST include `code`, `message`, `attempt`, and `occurred_at` fields. | MUST |
| **ERR-013** | Custom error codes MUST use a namespaced prefix and MUST NOT use the `OJS_` prefix. | MUST |
| **ERR-014** | SDKs MUST treat unknown error codes as non-retryable unless `retryable` is explicitly `true`. | MUST |
| **ERR-015** | SDKs MUST NOT automatically retry validation (§4.1), conflict (§4.2), or auth (§4.3) errors. | MUST |
| **ERR-016** | SDKs SHOULD auto-retry backend errors (§4.6) with exponential backoff and jitter. | SHOULD |

---

## 11. Prior Art

This section surveys existing error taxonomies that informed the OJS error catalog.

### HTTP Status Codes (RFC 9110)

HTTP defines a well-known set of status codes (1xx–5xx) that provide coarse-grained
error categorization. OJS maps to HTTP status codes for the HTTP binding, but HTTP
alone is insufficient — for example, HTTP 400 must cover seven distinct OJS
validation errors, and HTTP 429 covers both `QUEUE_FULL` and `RATE_LIMITED` with
different semantics. OJS error codes provide the finer granularity needed.

### gRPC Status Codes + google.rpc

gRPC defines 16 status codes and a rich error model via `google.rpc.Status` with
detail messages like `ErrorInfo`, `BadRequest`, and `RetryInfo`. The OJS gRPC binding
leverages `ErrorInfo.reason` to convey the OJS error code, demonstrating that
domain-specific codes are necessary even when the transport provides its own.

### Stripe API Errors

Stripe's error taxonomy uses a `type/code/message/param` structure that distinguishes
between `card_error`, `api_error`, `authentication_error`, and `invalid_request_error`.
The OJS error structure (code + message + details) is inspired by this approach, with
the addition of `retryable` for automated retry decisions.

### AWS Error Codes

AWS services return service-specific error codes (e.g., `ThrottlingException`,
`ValidationException`) with a consistent structure. OJS follows this pattern of
defining a closed set of error codes with predictable behavior.

### Temporal Failure Types

Temporal defines typed failures — `ApplicationFailure`, `TimeoutFailure`,
`CancelledFailure`, `TerminatedFailure` — that map well to OJS execution errors.
Temporal's `non_retryable` flag on `ApplicationFailure` directly inspired the
`retryable` field in OJS errors and the `non_retryable_errors` list in OJS retry
policy.

### CloudEvents

CloudEvents (CNCF) defines no error taxonomy because events are fire-and-forget.
This highlights the gap that OJS fills: job systems are bidirectional (producer →
backend → worker → backend → producer), and every link in the chain can fail in
ways that need structured reporting.

---

## 12. Examples

### 12.1 HTTP 400 — Validation Error

A producer submits a job with a missing required field.

**Request:**

```http
POST /v1/jobs HTTP/1.1
Content-Type: application/json

{
  "queue": "emails",
  "args": { "to": "user@example.com", "subject": "Hello" }
}
```

**Response:**

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "code": "INVALID_PAYLOAD",
  "message": "Missing required field 'type' in job envelope",
  "details": {
    "field": "type",
    "constraint": "required"
  },
  "retryable": false,
  "doc_url": "https://openjobspec.org/errors/INVALID_PAYLOAD"
}
```

### 12.2 HTTP 429 — Rate Limit Error with Retry-After

A producer exceeds the rate limit for a queue.

**Response:**

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 30
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1739613630

{
  "code": "RATE_LIMITED",
  "message": "Rate limit exceeded for queue 'emails': 100 requests per minute",
  "details": {
    "queue": "emails",
    "limit": 100,
    "window": "60s",
    "retry_after_seconds": 30
  },
  "retryable": true,
  "doc_url": "https://openjobspec.org/errors/RATE_LIMITED"
}
```

### 12.3 gRPC Error with ErrorInfo Detail

A gRPC client attempts to enqueue a job with a duplicate uniqueness key.

```
Status: ALREADY_EXISTS (code 6)
Message: "A job with uniqueness key 'email.send:user@example.com' already exists"

Detail[0]: google.rpc.ErrorInfo {
  reason: "OJS_DUPLICATE_JOB"
  domain: "openjobspec.org"
  metadata: {
    "existing_job_id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
    "unique_key": "email.send:user@example.com",
    "existing_state": "active",
    "retryable": "false"
  }
}
```

### 12.4 AMQP Error Propagation via Headers on Retry

A worker fails to process a job. The runtime Nack's the message and republishes it
to the retry exchange with error metadata in headers.

**Original message headers:**

```
x-ojs-job-id: 019539a4-b68c-7def-8000-1a2b3c4d5e6f
x-ojs-queue: emails
x-ojs-attempt: 1
```

**Republished message headers (after failure):**

```
x-ojs-job-id: 019539a4-b68c-7def-8000-1a2b3c4d5e6f
x-ojs-queue: emails
x-ojs-attempt: 2
x-ojs-error-code: HANDLER_ERROR
x-ojs-error-message: SMTP connection refused on port 25
x-ojs-error-details: {"type":"SmtpConnectionError","attempt":1,"occurred_at":"2026-02-15T10:30:00Z"}
expiration: 5000
```

The `expiration` property implements the backoff delay (5 seconds) before the message
is re-delivered from the retry exchange to the work queue.

### 12.5 Error History — Job Retried 3 Times Then Dead-Lettered

A job fails three times with different errors and is then moved to the dead-letter
queue after exhausting its retry policy (`max_attempts: 3`).

```json
{
  "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "type": "email.send",
  "queue": "emails",
  "state": "dead",
  "attempt": 3,
  "retry_policy": {
    "max_attempts": 3,
    "backoff": "exponential",
    "initial_interval": "1s",
    "max_interval": "60s",
    "multiplier": 2.0,
    "on_exhaustion": "dead_letter"
  },
  "errors": [
    {
      "code": "HANDLER_ERROR",
      "message": "SMTP connection refused on port 25",
      "type": "SmtpConnectionError",
      "attempt": 1,
      "occurred_at": "2026-02-15T10:30:00Z"
    },
    {
      "code": "HANDLER_TIMEOUT",
      "message": "Handler exceeded 30s timeout",
      "type": "TimeoutError",
      "attempt": 2,
      "occurred_at": "2026-02-15T10:31:05Z"
    },
    {
      "code": "HANDLER_ERROR",
      "message": "SMTP authentication failed: invalid credentials",
      "type": "SmtpAuthError",
      "attempt": 3,
      "occurred_at": "2026-02-15T10:33:10Z"
    }
  ],
  "dead_lettered_at": "2026-02-15T10:33:10Z"
}
```

In this example:

- **Attempt 1** failed due to a transient SMTP connection refusal.
- **Attempt 2** was retried after a 1-second backoff but timed out after 30 seconds.
- **Attempt 3** was retried after a 2-second backoff but failed with an auth error.
- After 3 attempts, `on_exhaustion: "dead_letter"` moved the job to the DLQ for
  manual inspection.

The `errors` array preserves the full failure timeline, enabling operators to
diagnose whether the root cause was transient (attempt 1) or permanent (attempt 3).
