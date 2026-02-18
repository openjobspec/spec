# Open Job Spec: SDK Error Catalog

| Field        | Value                                           |
|-------------|------------------------------------------------|
| **Title**   | OJS SDK Error Catalog                           |
| **Version** | 1.0.0                                           |
| **Date**    | 2025-07-16                                      |
| **Status**  | Draft                                           |
| **Layer**   | Cross-cutting (applies to all SDKs)             |
| **URI**     | https://openjobspec.org/spec/v1/error-catalog   |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Error Code Format](#3-error-code-format)
4. [Error Code Categories](#4-error-code-categories)
   - 4.1 [OJS-1xxx: Client Errors](#41-ojs-1xxx-client-errors)
   - 4.2 [OJS-2xxx: Server Errors](#42-ojs-2xxx-server-errors)
   - 4.3 [OJS-3xxx: Job Lifecycle Errors](#43-ojs-3xxx-job-lifecycle-errors)
   - 4.4 [OJS-4xxx: Workflow Errors](#44-ojs-4xxx-workflow-errors)
   - 4.5 [OJS-5xxx: Authentication & Authorization Errors](#45-ojs-5xxx-authentication--authorization-errors)
   - 4.6 [OJS-6xxx: Rate Limiting & Backpressure Errors](#46-ojs-6xxx-rate-limiting--backpressure-errors)
   - 4.7 [OJS-7xxx: Extension Errors](#47-ojs-7xxx-extension-errors)
5. [Mapping to Canonical Error Codes](#5-mapping-to-canonical-error-codes)
6. [SDK Implementation Requirements](#6-sdk-implementation-requirements)
7. [Usage Examples](#7-usage-examples)

---

## 1. Introduction

This document defines a standardized numeric error code catalog for Open Job Spec SDKs.
While the [OJS Error Specification](spec/ojs-errors.md) defines the canonical
SCREAMING_SNAKE_CASE error codes used on the wire (e.g., `INVALID_PAYLOAD`,
`DUPLICATE_JOB`), this catalog assigns each error a stable **OJS-XXXX** numeric
identifier for use in SDK constants, logging, monitoring dashboards, and documentation
cross-references.

The numeric codes provide:

- **Stable references** — numeric codes never change even if string names are refined.
- **Structured categorization** — the leading digit indicates the error family.
- **Cross-SDK consistency** — all six OJS SDKs (Go, JS/TS, Python, Java, Rust, Ruby) expose the same codes.
- **Searchability** — `OJS-3001` is unambiguous in logs, dashboards, and issue trackers.

> **Relationship to ojs-errors.md:** The canonical wire-format error codes remain
> SCREAMING_SNAKE_CASE strings (e.g., `DUPLICATE_JOB`). The OJS-XXXX numeric codes
> are a supplementary SDK-level identifier that maps 1:1 to the canonical codes.
> Backends continue to send string codes; SDKs expose both the string code and the
> numeric OJS-XXXX code.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD",
"SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be
interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt).

---

## 3. Error Code Format

Each error code follows the format:

```
OJS-XNNN
```

Where:
- `OJS-` is the fixed prefix identifying Open Job Spec errors.
- `X` (leading digit, 1–7) indicates the error **category**.
- `NNN` (three digits, 000–999) is the sequential error number within the category.

### 3.1 Category Ranges

| Range       | Category                            | Default Retryable |
|-------------|-------------------------------------|-------------------|
| `OJS-1xxx`  | Client errors                       | No                |
| `OJS-2xxx`  | Server / infrastructure errors      | Yes               |
| `OJS-3xxx`  | Job lifecycle errors                | Varies            |
| `OJS-4xxx`  | Workflow errors                     | Varies            |
| `OJS-5xxx`  | Authentication & authorization      | No                |
| `OJS-6xxx`  | Rate limiting & backpressure        | Yes               |
| `OJS-7xxx`  | Extension errors                    | Varies            |

### 3.2 Stability Guarantees

Once assigned, a numeric code MUST NOT be reassigned to a different error. Codes MAY
be deprecated but MUST NOT be removed or reused.

---

## 4. Error Code Categories

### 4.1 OJS-1xxx: Client Errors

Client errors indicate that the request is invalid and MUST be fixed by the caller
before retrying. Automated retries will always fail.

| Code       | Name                       | HTTP Status | Canonical Code               | Description                                                    | Retryable |
|------------|----------------------------|-------------|------------------------------|----------------------------------------------------------------|-----------|
| `OJS-1000` | InvalidPayload             | 400         | `INVALID_PAYLOAD`            | Job envelope fails structural validation (malformed JSON, missing required fields). | No |
| `OJS-1001` | InvalidJobType             | 400         | `INVALID_JOB_TYPE`           | Job type is not registered or does not match the allowlist.    | No        |
| `OJS-1002` | InvalidQueue               | 400         | `INVALID_QUEUE`              | Queue name is invalid or does not match naming rules.          | No        |
| `OJS-1003` | InvalidArgs                | 400         | `INVALID_ARGS`               | Job args fail type checking or schema validation.              | No        |
| `OJS-1004` | InvalidMetadata            | 400         | `INVALID_METADATA`           | Metadata field is malformed or exceeds the 64 KB size limit.   | No        |
| `OJS-1005` | InvalidStateTransition     | 409         | `INVALID_STATE_TRANSITION`   | Attempted an invalid lifecycle state change (e.g., ACK on non-active job). | No |
| `OJS-1006` | InvalidRetryPolicy         | 400         | `INVALID_RETRY_POLICY`       | Retry policy configuration is invalid (negative max_attempts, invalid backoff). | No |
| `OJS-1007` | InvalidCronExpression      | 400         | `INVALID_CRON_EXPRESSION`    | Cron expression syntax cannot be parsed.                       | No        |
| `OJS-1008` | SchemaValidationFailed     | 422         | `SCHEMA_VALIDATION_FAILED`   | Job args do not conform to the registered schema for this job type. | No |
| `OJS-1009` | PayloadTooLarge            | 413         | `PAYLOAD_TOO_LARGE`          | Job envelope exceeds the server's maximum payload size (default 1 MiB). | No |
| `OJS-1010` | MetadataTooLarge           | 413         | `METADATA_TOO_LARGE`         | Metadata field exceeds the 64 KB limit.                        | No        |
| `OJS-1011` | ConnectionError            | —           | *(client-side)*              | Could not establish a connection to the OJS server.            | Yes       |
| `OJS-1012` | RequestTimeout             | —           | *(client-side)*              | HTTP request to the OJS server timed out before receiving a response. | Yes |
| `OJS-1013` | SerializationError         | —           | *(client-side)*              | Failed to serialize the request or deserialize the response.   | No        |
| `OJS-1014` | QueueNameTooLong           | 400         | `QUEUE_NAME_TOO_LONG`        | Queue name exceeds the 255-byte maximum length.                | No        |
| `OJS-1015` | JobTypeTooLong             | 400         | `JOB_TYPE_TOO_LONG`          | Job type exceeds the 255-byte maximum length.                  | No        |
| `OJS-1016` | ChecksumMismatch           | 400         | `CHECKSUM_MISMATCH`          | External payload reference checksum verification failed.       | No        |
| `OJS-1017` | UnsupportedCompression     | 400         | `UNSUPPORTED_COMPRESSION`    | The specified compression codec is not supported.              | No        |

### 4.2 OJS-2xxx: Server Errors

Server and infrastructure errors indicate internal failures. SDKs SHOULD auto-retry
these with exponential backoff and jitter.

| Code       | Name                | HTTP Status | Canonical Code          | Description                                                    | Retryable |
|------------|---------------------|-------------|-------------------------|----------------------------------------------------------------|-----------|
| `OJS-2000` | BackendError        | 500         | `BACKEND_ERROR`         | Internal backend storage or transport failure.                 | Yes       |
| `OJS-2001` | BackendUnavailable  | 503         | `BACKEND_UNAVAILABLE`   | Backend storage system is unreachable (service down, network partition). | Yes |
| `OJS-2002` | BackendTimeout      | 504         | `BACKEND_TIMEOUT`       | Backend operation timed out (slow query, lock contention).     | Yes       |
| `OJS-2003` | ReplicationLag      | 500         | `REPLICATION_LAG`       | Operation failed due to replication consistency issue (read-after-write on async replica). | Yes |
| `OJS-2004` | InternalServerError | 500         | *(generic)*             | Unclassified internal server error.                            | Yes       |

### 4.3 OJS-3xxx: Job Lifecycle Errors

Job lifecycle errors relate to job state management, dequeue operations, and handler
execution. Retryability varies by error.

| Code       | Name                  | HTTP Status | Canonical Code            | Description                                                    | Retryable |
|------------|-----------------------|-------------|---------------------------|----------------------------------------------------------------|-----------|
| `OJS-3000` | JobNotFound           | 404         | `NOT_FOUND`               | The requested job, queue, or resource does not exist.          | No        |
| `OJS-3001` | DuplicateJob          | 409         | `DUPLICATE_JOB`           | A unique job constraint was violated; another job with the same uniqueness key exists. | No |
| `OJS-3002` | JobAlreadyCompleted   | 409         | `JOB_ALREADY_COMPLETED`   | Operation attempted on a job that has already completed.       | No        |
| `OJS-3003` | JobAlreadyCancelled   | 409         | `JOB_ALREADY_CANCELLED`   | Operation attempted on a job that has already been cancelled.  | No        |
| `OJS-3004` | QueuePaused           | 422         | `QUEUE_PAUSED`            | The target queue is paused and not accepting new jobs or fetches. | Yes    |
| `OJS-3005` | HandlerError          | —           | `HANDLER_ERROR`           | Job handler threw an exception during execution.               | Per retry policy |
| `OJS-3006` | HandlerTimeout        | —           | `HANDLER_TIMEOUT`         | Job handler exceeded the configured execution timeout.         | Per retry policy |
| `OJS-3007` | HandlerPanic          | —           | `HANDLER_PANIC`           | Job handler caused an unrecoverable error (panic, segfault).   | Per retry policy |
| `OJS-3008` | NonRetryableError     | —           | `NON_RETRYABLE_ERROR`     | Error type matched `non_retryable_errors` in the retry policy. | No        |
| `OJS-3009` | JobCancelled          | —           | `JOB_CANCELLED`           | Job was cancelled while it was executing.                      | No        |
| `OJS-3010` | NoHandlerRegistered   | —           | *(client-side)*           | No handler is registered in the worker for the received job type. | No     |

### 4.4 OJS-4xxx: Workflow Errors

Workflow errors occur during chain, group, or batch workflow execution.

| Code       | Name                  | HTTP Status | Canonical Code               | Description                                                    | Retryable |
|------------|-----------------------|-------------|------------------------------|----------------------------------------------------------------|-----------|
| `OJS-4000` | WorkflowNotFound      | 404         | *(server)*                   | The specified workflow does not exist.                          | No        |
| `OJS-4001` | ChainStepFailed       | 422         | *(server)*                   | A step in a chain workflow failed, halting subsequent steps.   | No        |
| `OJS-4002` | GroupTimeout          | 504         | *(server)*                   | A group (fan-out) workflow did not complete within the allowed timeout. | Yes |
| `OJS-4003` | DependencyFailed      | 422         | *(server)*                   | A required dependency job failed, preventing execution.        | No        |
| `OJS-4004` | CyclicDependency      | 400         | *(server)*                   | The workflow definition contains circular dependencies.        | No        |
| `OJS-4005` | BatchCallbackFailed   | 422         | *(server)*                   | The batch completion callback job failed.                      | Per retry policy |
| `OJS-4006` | WorkflowCancelled     | 409         | *(server)*                   | The entire workflow was cancelled.                             | No        |

### 4.5 OJS-5xxx: Authentication & Authorization Errors

Auth errors indicate missing, invalid, or insufficient credentials. Automated retries
without fixing credentials will always fail.

| Code       | Name                | HTTP Status | Canonical Code          | Description                                                    | Retryable |
|------------|---------------------|-------------|-------------------------|----------------------------------------------------------------|-----------|
| `OJS-5000` | Unauthenticated     | 401         | `UNAUTHENTICATED`       | No authentication credentials provided or credentials are invalid. | No    |
| `OJS-5001` | PermissionDenied    | 403         | `PERMISSION_DENIED`     | Authenticated but lacks the required permission for this operation. | No   |
| `OJS-5002` | TokenExpired        | 401         | `TOKEN_EXPIRED`         | The authentication token has expired and must be refreshed.    | No        |
| `OJS-5003` | TenantAccessDenied  | 403         | `TENANT_ACCESS_DENIED`  | Operation on a tenant the caller does not have access to.      | No        |

### 4.6 OJS-6xxx: Rate Limiting & Backpressure Errors

Rate limiting errors indicate the caller has exceeded capacity limits. SDKs SHOULD
respect `Retry-After` headers and back off before retrying.

| Code       | Name                  | HTTP Status | Canonical Code       | Description                                                    | Retryable |
|------------|-----------------------|-------------|----------------------|----------------------------------------------------------------|-----------|
| `OJS-6000` | RateLimited           | 429         | `RATE_LIMITED`       | The client has exceeded the rate limit. Respect `Retry-After` header. | Yes |
| `OJS-6001` | QueueFull             | 429         | `QUEUE_FULL`         | The queue has reached its configured maximum depth.            | Yes       |
| `OJS-6002` | ConcurrencyLimited    | 429         | *(server)*           | The per-queue or global concurrency limit has been reached.    | Yes       |
| `OJS-6003` | BackpressureApplied   | 429         | *(server)*           | The server is applying backpressure to protect backend resources. | Yes    |

### 4.7 OJS-7xxx: Extension Errors

Extension errors are raised by OJS extensions (retry, cron, unique jobs, middleware).

| Code       | Name                   | HTTP Status | Canonical Code               | Description                                                    | Retryable |
|------------|------------------------|-------------|------------------------------|----------------------------------------------------------------|-----------|
| `OJS-7000` | UnsupportedFeature     | 422         | `UNSUPPORTED_FEATURE`        | The requested feature requires a conformance level the backend does not support. | No |
| `OJS-7001` | CronScheduleConflict   | 409         | *(server)*                   | The cron schedule conflicts with an existing schedule.         | No        |
| `OJS-7002` | UniqueKeyInvalid       | 400         | *(server)*                   | The unique key specification is invalid or malformed.          | No        |
| `OJS-7003` | MiddlewareError        | 500         | *(client-side)*              | An error occurred in the middleware chain during processing.   | Yes       |
| `OJS-7004` | MiddlewareTimeout      | 504         | *(client-side)*              | A middleware handler exceeded its allowed execution time.      | Yes       |

---

## 5. Mapping to Canonical Error Codes

The following table maps each OJS-XXXX numeric code to the canonical SCREAMING_SNAKE_CASE
wire-format code defined in `spec/ojs-errors.md`. SDKs MUST expose both identifiers.

| OJS Code    | Canonical Code               | Category       |
|-------------|------------------------------|----------------|
| `OJS-1000`  | `INVALID_PAYLOAD`            | Client         |
| `OJS-1001`  | `INVALID_JOB_TYPE`           | Client         |
| `OJS-1002`  | `INVALID_QUEUE`              | Client         |
| `OJS-1003`  | `INVALID_ARGS`               | Client         |
| `OJS-1004`  | `INVALID_METADATA`           | Client         |
| `OJS-1005`  | `INVALID_STATE_TRANSITION`   | Client         |
| `OJS-1006`  | `INVALID_RETRY_POLICY`       | Client         |
| `OJS-1007`  | `INVALID_CRON_EXPRESSION`    | Client         |
| `OJS-1008`  | `SCHEMA_VALIDATION_FAILED`   | Client         |
| `OJS-1009`  | `PAYLOAD_TOO_LARGE`          | Client         |
| `OJS-1010`  | `METADATA_TOO_LARGE`         | Client         |
| `OJS-1011`  | *(client-side)*              | Client         |
| `OJS-1012`  | *(client-side)*              | Client         |
| `OJS-1013`  | *(client-side)*              | Client         |
| `OJS-1014`  | `QUEUE_NAME_TOO_LONG`        | Client         |
| `OJS-1015`  | `JOB_TYPE_TOO_LONG`          | Client         |
| `OJS-1016`  | `CHECKSUM_MISMATCH`          | Client         |
| `OJS-1017`  | `UNSUPPORTED_COMPRESSION`    | Client         |
| `OJS-2000`  | `BACKEND_ERROR`              | Server         |
| `OJS-2001`  | `BACKEND_UNAVAILABLE`        | Server         |
| `OJS-2002`  | `BACKEND_TIMEOUT`            | Server         |
| `OJS-2003`  | `REPLICATION_LAG`            | Server         |
| `OJS-2004`  | *(generic)*                  | Server         |
| `OJS-3000`  | `NOT_FOUND`                  | Job Lifecycle  |
| `OJS-3001`  | `DUPLICATE_JOB`              | Job Lifecycle  |
| `OJS-3002`  | `JOB_ALREADY_COMPLETED`      | Job Lifecycle  |
| `OJS-3003`  | `JOB_ALREADY_CANCELLED`      | Job Lifecycle  |
| `OJS-3004`  | `QUEUE_PAUSED`               | Job Lifecycle  |
| `OJS-3005`  | `HANDLER_ERROR`              | Job Lifecycle  |
| `OJS-3006`  | `HANDLER_TIMEOUT`            | Job Lifecycle  |
| `OJS-3007`  | `HANDLER_PANIC`              | Job Lifecycle  |
| `OJS-3008`  | `NON_RETRYABLE_ERROR`        | Job Lifecycle  |
| `OJS-3009`  | `JOB_CANCELLED`              | Job Lifecycle  |
| `OJS-3010`  | *(client-side)*              | Job Lifecycle  |
| `OJS-4000`  | *(server)*                   | Workflow       |
| `OJS-4001`  | *(server)*                   | Workflow       |
| `OJS-4002`  | *(server)*                   | Workflow       |
| `OJS-4003`  | *(server)*                   | Workflow       |
| `OJS-4004`  | *(server)*                   | Workflow       |
| `OJS-4005`  | *(server)*                   | Workflow       |
| `OJS-4006`  | *(server)*                   | Workflow       |
| `OJS-5000`  | `UNAUTHENTICATED`            | Auth           |
| `OJS-5001`  | `PERMISSION_DENIED`          | Auth           |
| `OJS-5002`  | `TOKEN_EXPIRED`              | Auth           |
| `OJS-5003`  | `TENANT_ACCESS_DENIED`       | Auth           |
| `OJS-6000`  | `RATE_LIMITED`               | Rate Limiting  |
| `OJS-6001`  | `QUEUE_FULL`                 | Rate Limiting  |
| `OJS-6002`  | *(server)*                   | Rate Limiting  |
| `OJS-6003`  | *(server)*                   | Rate Limiting  |
| `OJS-7000`  | `UNSUPPORTED_FEATURE`        | Extension      |
| `OJS-7001`  | *(server)*                   | Extension      |
| `OJS-7002`  | *(server)*                   | Extension      |
| `OJS-7003`  | *(client-side)*              | Extension      |
| `OJS-7004`  | *(client-side)*              | Extension      |

---

## 6. SDK Implementation Requirements

### 6.1 Mandatory

- SDKs MUST define constants or an enum for all OJS-XXXX codes listed in this document.
- SDKs MUST include the numeric code (`OJS-XXXX`), the canonical string code, the
  default HTTP status, and a human-readable message for each error code entry.
- SDKs MUST use language-idiomatic constructs (constants in Go, `enum` in Java/Rust,
  `const` objects in TypeScript, module constants in Python/Ruby).
- SDKs MUST make error code constants importable from a dedicated module or file
  (e.g., `error_codes.go`, `src/error-codes.ts`, `error_codes.py`).

### 6.2 Recommended

- SDKs SHOULD provide a lookup function to resolve a canonical string code to the
  corresponding OJS-XXXX code.
- SDKs SHOULD include the OJS-XXXX code in formatted error messages for searchability.
- SDKs SHOULD provide a `docURL()` or equivalent method that returns the documentation
  URL for the error code.

### 6.3 Integration with Existing Error Types

The error code constants defined in this catalog are **supplementary** to existing SDK
error types. SDKs SHOULD NOT break existing error handling APIs. Instead, the numeric
codes should be available as additional metadata on existing error objects.

---

## 7. Usage Examples

### Logging with Error Codes

```
ERROR [OJS-3001] DuplicateJob: Unique constraint violated for key
  "email.send:default:user@example.com" (existing_job_id=019414d4-aaaa-7bbb-cccc-ddddeeee0001)
```

### Dashboard Alerts

```
Alert: OJS-2001 BackendUnavailable errors exceeded threshold (>10/min)
  Backend: redis://prod-redis:6379
  Duration: 5 minutes
```

### SDK Usage (pseudocode)

```
try:
    client.enqueue(job)
except OJSError as e:
    if e.catalog_code == "OJS-6000":
        # Rate limited — respect retry-after
        sleep(e.retry_after)
        client.enqueue(job)
    elif e.catalog_code.startswith("OJS-1"):
        # Client error — fix the request, don't retry
        log.error(f"Client error {e.catalog_code}: {e.message}")
    elif e.catalog_code.startswith("OJS-2"):
        # Server error — auto-retry with backoff
        retry_with_backoff(lambda: client.enqueue(job))
```
