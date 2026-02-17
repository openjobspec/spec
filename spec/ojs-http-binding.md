# Open Job Spec -- HTTP/REST Protocol Binding

**OJS v1.0.0-rc.1 | Layer 3: Protocol Binding**

**Status:** Release Candidate 1
**Maturity:** Stable
**Date:** 2026-02-19
**Spec Version:** 1.0.0-rc.1

---

## Abstract

This document defines the HTTP/REST protocol binding for Open Job Spec (OJS). It specifies how the logical operations defined in the OJS Core Specification (Layer 1) map to HTTP methods, URIs, headers, request bodies, and response bodies when transmitted over HTTP/1.1 or HTTP/2.

HTTP is the **REQUIRED** baseline protocol binding. Every networked OJS implementation MUST support this binding. Implementations MAY support additional protocol bindings (gRPC, WebSocket, AMQP) as extensions, but HTTP conformance is mandatory.

**Rationale:** HTTP is the most universally supported application protocol. Requiring it as a baseline ensures that any OJS client can communicate with any OJS server without protocol negotiation, regardless of language, platform, or deployment environment.

---

## Table of Contents

1. [Notation and Conventions](#1-notation-and-conventions)
2. [Protocol Overview](#2-protocol-overview)
3. [Base Path and Versioning](#3-base-path-and-versioning)
4. [Content Negotiation](#4-content-negotiation)
5. [Authentication and Authorization](#5-authentication-and-authorization)
6. [Request and Response Format](#6-request-and-response-format)
7. [Logical Operation Mapping](#7-logical-operation-mapping)
8. [System Endpoints](#8-system-endpoints)
9. [Job Endpoints](#9-job-endpoints)
10. [Worker Endpoints](#10-worker-endpoints)
11. [Queue Endpoints](#11-queue-endpoints)
12. [Dead Letter Endpoints](#12-dead-letter-endpoints)
13. [Cron Endpoints](#13-cron-endpoints)
14. [Workflow Endpoints](#14-workflow-endpoints)
15. [Schema Endpoints](#15-schema-endpoints)
16. [Error Handling](#16-error-handling)
17. [Pagination](#17-pagination)
18. [Rate Limiting](#18-rate-limiting)
19. [Request ID Tracking](#19-request-id-tracking)
20. [CORS Considerations](#20-cors-considerations)
21. [Conformance Manifest](#21-conformance-manifest)

---

## 1. Notation and Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt).

**Rationale for RFC 2119 usage:** OJS is designed for interoperability across languages, frameworks, and backends. Precise normative language eliminates ambiguity that would otherwise lead to incompatible implementations.

All examples in this document use the following conventions:

- **Base URL:** `https://jobs.example.com`
- **Job IDs:** UUIDv7 format (e.g., `019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6`)
- **Timestamps:** ISO 8601 / RFC 3339 with UTC timezone (e.g., `2026-02-12T10:30:00.000Z`)
- **curl:** All curl examples are copy-pasteable and self-contained

The examples throughout this document use consistent sample data for a hypothetical `email.send` job to aid readability.

---

## 2. Protocol Overview

The OJS HTTP binding maps each OJS logical operation to an HTTP method + URI pair. The mapping follows REST conventions where applicable, but prioritizes explicitness over REST purity.

### 2.1 Logical Operation to HTTP Mapping

| Logical Operation | HTTP Method | Path                          | Description                          | Level |
|-------------------|-------------|-------------------------------|--------------------------------------|-------|
| PUSH              | `POST`      | `/ojs/v1/jobs`                | Enqueue a single job                 | 0     |
| PUSH (batch)      | `POST`      | `/ojs/v1/jobs/batch`          | Enqueue multiple jobs                | 4     |
| FETCH             | `POST`      | `/ojs/v1/workers/fetch`       | Dequeue jobs for processing          | 0     |
| ACK               | `POST`      | `/ojs/v1/workers/ack`         | Acknowledge successful completion    | 0     |
| FAIL              | `POST`      | `/ojs/v1/workers/nack`        | Report job failure with error data   | 0     |
| BEAT              | `POST`      | `/ojs/v1/workers/heartbeat`   | Worker heartbeat / extend visibility | 1     |
| CANCEL            | `DELETE`    | `/ojs/v1/jobs/:id`            | Cancel a job                         | 1     |
| ACTIVATE          | `POST`      | `/ojs/v1/jobs/:id/activate`   | Activate a pending job               | 1     |
| INFO              | `GET`       | `/ojs/v1/jobs/:id`            | Get job details                      | 1     |

**Rationale for POST on worker endpoints:** FETCH, ACK, FAIL, and BEAT are command operations that carry request bodies and produce side effects. POST is semantically correct for operations that are neither safe nor idempotent (FETCH modifies queue state) or that carry structured request bodies (ACK, FAIL, BEAT). Using POST uniformly for worker coordination simplifies client implementation and avoids overloading GET semantics.

### 2.2 Additional Endpoints

| HTTP Method | Path                              | Description                    | Level |
|-------------|-----------------------------------|--------------------------------|-------|
| `GET`       | `/ojs/manifest`                   | Conformance manifest           | 0     |
| `GET`       | `/ojs/v1/health`                  | Health check                   | 0     |
| `GET`       | `/ojs/v1/queues`                  | List queues                    | 0     |
| `GET`       | `/ojs/v1/queues/:name/stats`      | Queue statistics               | 4     |
| `POST`      | `/ojs/v1/queues/:name/pause`      | Pause a queue                  | 4     |
| `POST`      | `/ojs/v1/queues/:name/resume`     | Resume a queue                 | 4     |
| `GET`       | `/ojs/v1/dead-letter`             | List dead letter jobs          | 1     |
| `POST`      | `/ojs/v1/dead-letter/:id/retry`   | Retry a dead letter job        | 1     |
| `DELETE`    | `/ojs/v1/dead-letter/:id`         | Discard a dead letter job      | 1     |
| `GET`       | `/ojs/v1/cron`                    | List cron jobs                 | 2     |
| `POST`      | `/ojs/v1/cron`                    | Register a cron job            | 2     |
| `DELETE`    | `/ojs/v1/cron/:name`              | Unregister a cron job          | 2     |
| `POST`      | `/ojs/v1/workflows`               | Create and start a workflow    | 3     |
| `GET`       | `/ojs/v1/workflows/:id`           | Get workflow status            | 3     |
| `DELETE`    | `/ojs/v1/workflows/:id`           | Cancel a workflow              | 3     |
| `GET`       | `/ojs/v1/schemas`                 | List registered schemas        | 0     |
| `POST`      | `/ojs/v1/schemas`                 | Register a schema              | 0     |
| `GET`       | `/ojs/v1/schemas/:uri`            | Get schema by URI              | 0     |
| `DELETE`    | `/ojs/v1/schemas/:uri`            | Remove a schema                | 0     |

---

## 3. Base Path and Versioning

### 3.1 Base Path

All OJS HTTP endpoints MUST be served under the base path `/ojs/v1`.

**Rationale:** A fixed base path enables service discovery and avoids conflicts with application-specific routes. The `/ojs/` prefix provides a clear namespace, and `/v1` allows future major versions to coexist.

The conformance manifest endpoint is the sole exception: it MUST be served at `/ojs/manifest` (without version prefix) so that clients can discover the server's supported versions before making versioned requests.

### 3.2 Version Negotiation

Clients MAY include an `OJS-Version` header to indicate the desired spec version:

```
OJS-Version: 1.0
```

Servers MUST include the `OJS-Version` header in all responses to indicate which spec version was used to process the request.

If a client requests a version the server does not support, the server MUST respond with `422 Unprocessable Entity` and an error code of `unsupported`.

**Rationale:** Embedding the major version in the URL path (`/v1`) handles breaking changes, while the header enables fine-grained negotiation within a major version for non-breaking additions.

---

## 4. Content Negotiation

### 4.1 Content-Type

All request and response bodies MUST use the content type:

```
Content-Type: application/openjobspec+json
```

Servers MUST accept `application/json` as an alias for `application/openjobspec+json`.

**Rationale:** A dedicated media type (`application/openjobspec+json`) enables middleware, proxies, and tools to identify OJS traffic without inspecting request paths. Accepting `application/json` as an alias reduces friction for clients that do not set custom content types.

Servers MUST reject request bodies with unsupported content types by responding with `400 Bad Request`.

### 4.2 Character Encoding

All JSON bodies MUST be encoded as UTF-8. Servers MUST NOT require a `charset` parameter in the `Content-Type` header but MUST treat all JSON bodies as UTF-8.

**Rationale:** RFC 8259 mandates UTF-8 for JSON transmitted over a network. Requiring it eliminates encoding ambiguity.

### 4.3 Accept Header

Clients SHOULD include an `Accept` header:

```
Accept: application/openjobspec+json
```

Servers MUST respond with `application/openjobspec+json` regardless of the `Accept` header value, since JSON is the only required wire format. If the server supports additional formats (e.g., Protobuf via `application/openjobspec+protobuf`), it MAY perform content negotiation.

---

## 5. Authentication and Authorization

Authentication and authorization are **out of scope** for this specification. OJS deliberately does not mandate a specific authentication mechanism.

**Rationale:** Authentication requirements vary dramatically across deployments (internal microservices with mTLS, public APIs with OAuth 2.0, managed platforms with API keys). Mandating a specific mechanism would either be too restrictive or too permissive.

### 5.1 Extension Points

Implementations SHOULD support authentication through the following extension points:

1. **HTTP headers:** Standard `Authorization` header (Bearer tokens, API keys).
2. **Mutual TLS (mTLS):** Client certificates for service-to-service authentication.
3. **Custom headers:** Implementation-specific headers prefixed with `X-OJS-` (e.g., `X-OJS-Tenant-Id`).

### 5.2 Recommendations

Implementations that expose OJS endpoints over public networks SHOULD:

- Require TLS 1.2 or later.
- Support the `Authorization: Bearer <token>` pattern.
- Return `401 Unauthorized` for missing credentials and `403 Forbidden` for insufficient permissions.
- Document their authentication requirements in the conformance manifest under the `extensions` field.

---

## 6. Request and Response Format

### 6.1 Request Bodies

All POST request bodies MUST be valid JSON objects. GET and DELETE requests MUST NOT include request bodies (query parameters are used instead).

**Rationale:** Keeping GET and DELETE body-free ensures compatibility with HTTP clients, proxies, and caches that may strip or ignore bodies on these methods.

### 6.2 Response Bodies

All responses with content MUST be valid JSON objects. Responses with no content (e.g., `204 No Content`) MUST NOT include a body.

### 6.3 Timestamps

All timestamp values MUST be formatted as ISO 8601 / RFC 3339 strings with UTC timezone designator:

```
2026-02-12T10:30:00.000Z
```

**Rationale:** ISO 8601 is unambiguous, human-readable, and natively sortable as strings. UTC eliminates timezone conversion errors. Millisecond precision is RECOMMENDED for sub-second scheduling accuracy.

### 6.4 Identifiers

Job IDs MUST be UUIDv7 (RFC 9562) formatted as lowercase hyphenated strings:

```
019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6
```

**Rationale:** UUIDv7 provides time-ordered, globally unique identifiers that enable efficient database indexing (monotonically increasing) without coordination between distributed systems. The time component supports natural sort ordering of jobs by creation time.

### 6.5 Standard Response Headers

Every response MUST include the following headers:

| Header           | Description                              | Example                              |
|------------------|------------------------------------------|--------------------------------------|
| `OJS-Version`    | Spec version used to process the request | `1.0`                         |
| `Content-Type`   | Response content type                    | `application/openjobspec+json`       |
| `X-Request-Id`   | Unique request identifier                | `req_019414d4-8b2e-7c3a-b5d1-aaa111` |

**Rationale:** `OJS-Version` enables clients to detect version mismatches. `X-Request-Id` enables end-to-end request tracing for debugging and support.

---

## 7. Logical Operation Mapping

This section provides the normative mapping between OJS logical operations (defined in the Core Specification) and their HTTP representations.

### 7.1 PUSH (Enqueue)

The PUSH operation submits a job for processing.

- **HTTP Method:** `POST`
- **Path:** `/ojs/v1/jobs`
- **Success Status:** `201 Created`

The server MUST assign a UUIDv7 `id` to the job if the client does not provide one. The server MUST set `state` to `available` (or `scheduled` if `scheduled_at` is in the future, or `pending` if the `pending` flag is set in the request). The server MUST set the `enqueued_at` timestamp.

**Rationale for 201:** The operation creates a new resource (a job). HTTP semantics require `201 Created` for successful resource creation.

### 7.2 PUSH Batch (Batch Enqueue)

The batch PUSH operation submits multiple jobs atomically.

- **HTTP Method:** `POST`
- **Path:** `/ojs/v1/jobs/batch`
- **Success Status:** `201 Created`

The server MUST process all jobs in the batch atomically: either all jobs are enqueued or none are. If any job in the batch fails validation, the entire batch MUST be rejected.

**Rationale for atomicity:** Partial batch insertion creates ambiguity about which jobs were enqueued. Atomic processing simplifies error handling and retry logic for clients.

### 7.3 FETCH (Dequeue)

The FETCH operation claims one or more jobs for processing by a worker.

- **HTTP Method:** `POST`
- **Path:** `/ojs/v1/workers/fetch`
- **Success Status:** `200 OK`

The server MUST atomically transition fetched jobs from `available` to `active`. The response MAY contain fewer jobs than requested if fewer are available. An empty `jobs` array indicates no work is available.

**Rationale for POST:** FETCH modifies server state (claims jobs, changes their state). GET is inappropriate for operations with side effects. POST also allows a structured request body specifying queues, count, and worker identity.

### 7.4 ACK (Acknowledge Completion)

The ACK operation marks a job as successfully completed.

- **HTTP Method:** `POST`
- **Path:** `/ojs/v1/workers/ack`
- **Success Status:** `200 OK`

The server MUST transition the job from `active` to `completed`. If the job is not in the `active` state, the server MUST respond with `409 Conflict`.

**Rationale for state check:** Acknowledging a job that is not active indicates a logic error (double-ack, ack after timeout). Rejecting it prevents silent data corruption.

### 7.5 FAIL (Report Failure)

The FAIL operation reports that a job handler failed with a structured error.

- **HTTP Method:** `POST`
- **Path:** `/ojs/v1/workers/nack`
- **Success Status:** `200 OK`

The server MUST transition the job to `retryable` if attempts remain, or to `discarded` if the maximum attempts have been exhausted. The response MUST indicate the resulting state and, if retryable, the scheduled time for the next attempt.

**Rationale:** Structured failure reporting (error type, message, retryable flag) enables cross-language debugging. Using the Faktory-inspired `FAIL` model with explicit error data is superior to bare "nack" semantics because it preserves diagnostic information.

### 7.6 BEAT (Heartbeat)

The BEAT operation extends the visibility timeout of an active job and reports worker liveness.

- **HTTP Method:** `POST`
- **Path:** `/ojs/v1/workers/heartbeat`
- **Success Status:** `200 OK`

The server MUST extend the job's visibility timeout by the requested duration. The server MAY include a `state` directive in the response (`quiet` or `terminate`) to signal the worker to change its lifecycle state.

**Rationale:** Heartbeats prevent jobs from being reclaimed by other workers during long-running execution. Server-initiated state changes via heartbeat responses (inspired by Faktory's BEAT protocol) enable graceful shutdown coordination without a separate control channel.

### 7.7 CANCEL

The CANCEL operation stops a job from being processed.

- **HTTP Method:** `DELETE`
- **Path:** `/ojs/v1/jobs/:id`
- **Success Status:** `200 OK`

The server MUST transition the job to `cancelled` if it is in a non-terminal state (`available`, `scheduled`, `pending`, `retryable`). If the job is `active`, the server SHOULD set a cancellation flag that the worker can check via heartbeat. If the job is already in a terminal state (`completed`, `cancelled`, `discarded`), the server MUST respond with `409 Conflict`.

**Rationale for DELETE:** Cancellation semantically removes the job from the processing pipeline. DELETE aligns with the intent of "this job should no longer be processed."

### 7.8 ACTIVATE

The ACTIVATE operation transitions a pending job to the available state, making it eligible for worker processing.

- **HTTP Method:** `POST`
- **Path:** `/ojs/v1/jobs/:id/activate`
- **Success Status:** `200 OK`

The server MUST transition the job from `pending` to `available`. If the job is not in the `pending` state, the server MUST respond with `409 Conflict`. If the job does not exist, the server MUST respond with `404 Not Found`.

**Rationale for POST:** ACTIVATE is a command operation that modifies server state (transitions a job from `pending` to `available`). POST is semantically correct for operations that produce side effects and are not idempotent. A dedicated `/activate` sub-resource clearly communicates the intent, following the same pattern as other action endpoints (e.g., `/pause`, `/resume`).

### 7.9 INFO (Get Job Details)

The INFO operation retrieves the current state and metadata of a job.

- **HTTP Method:** `GET`
- **Path:** `/ojs/v1/jobs/:id`
- **Success Status:** `200 OK`

The server MUST return the complete job object including current state, all metadata timestamps, and result or error data if the job has reached a terminal state.

**Rationale for GET:** This is a pure read operation with no side effects. GET is the correct HTTP method.

---

## 8. System Endpoints

### 8.1 Health Check

**`GET /ojs/v1/health`**

Returns the health status of the OJS server and its backend connection.

Servers MUST implement this endpoint. The response MUST include at minimum a `status` field.

**Rationale:** Health checks are essential for load balancers, orchestrators (Kubernetes), and monitoring systems. A standardized health endpoint eliminates the need for implementation-specific probe configuration.

#### Request

```bash
curl -s https://jobs.example.com/ojs/v1/health \
  -H "Accept: application/openjobspec+json"
```

#### Response -- Healthy (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0001-7000-a000-000000000001

{
  "status": "ok",
  "version": "1.0",
  "uptime_seconds": 86400,
  "backend": {
    "type": "redis",
    "status": "connected",
    "latency_ms": 2
  }
}
```

#### Response -- Unhealthy (`503 Service Unavailable`)

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0001-7000-a000-000000000002

{
  "status": "degraded",
  "version": "1.0",
  "uptime_seconds": 86400,
  "backend": {
    "type": "redis",
    "status": "disconnected",
    "error": "connection refused"
  }
}
```

---

## 9. Job Endpoints

### 9.1 Enqueue a Job -- PUSH

**`POST /ojs/v1/jobs`**

Enqueues a single job for processing. This is the primary entry point for submitting work.

The request body MUST include `type` and `args`. The `args` field MUST be a JSON array.

**Rationale for `args` as array:** Arrays enforce a clean separation between positional job arguments and cross-cutting metadata. This design (proven by Sidekiq over a decade of production use) prevents stale nested objects, enables straightforward inspection, and maps naturally to function parameters across all programming languages.

#### Request

```bash
curl -s -X POST https://jobs.example.com/ojs/v1/jobs \
  -H "Content-Type: application/openjobspec+json" \
  -H "Accept: application/openjobspec+json" \
  -d '{
    "type": "email.send",
    "args": ["user@example.com", "welcome", {"locale": "en"}],
    "meta": {
      "trace_id": "trace_abc123def456",
      "source": "signup-service"
    },
    "options": {
      "queue": "email",
      "priority": 0,
      "timeout_ms": 30000,
      "retry": {
        "max_attempts": 5,
        "initial_interval_ms": 1000,
        "backoff_coefficient": 2.0,
        "max_interval_ms": 300000,
        "jitter": true
      },
      "tags": ["onboarding", "email"]
    }
  }'
```

#### Request Fields

| Field               | Type     | Required | Description                                                      |
|---------------------|----------|----------|------------------------------------------------------------------|
| `type`              | string   | Yes      | Dot-namespaced job type (e.g., `email.send`). Used for routing.  |
| `args`              | array    | Yes      | Positional arguments for the job handler. JSON-native types only.|
| `meta`              | object   | No       | Extensible key-value metadata for cross-cutting concerns.        |
| `schema`            | string   | No       | Schema URI for payload validation (e.g., `urn:ojs:schema:email.send:v1`). |
| `options`           | object   | No       | Enqueue options (see below).                                     |

#### Options Fields

| Field               | Type     | Default     | Description                                                  |
|---------------------|----------|-------------|--------------------------------------------------------------|
| `queue`             | string   | `"default"` | Target queue name.                                           |
| `priority`          | integer  | `0`         | Job priority. Higher values indicate higher priority (Level 4). |
| `timeout_ms`        | integer  | `30000`     | Maximum execution time in milliseconds.                      |
| `delay_until`       | string   | `null`      | ISO 8601 timestamp for delayed execution (Level 2).          |
| `expires_at`        | string   | `null`      | ISO 8601 timestamp after which the job should be discarded.  |
| `retry`             | object   | (default)   | Retry policy override. See Core Specification.               |
| `unique`            | object   | `null`      | Unique job / deduplication policy (Level 4).                 |
| `tags`              | string[] | `[]`        | Tags for filtering and observability.                        |
| `visibility_timeout_ms` | integer | `30000` | Reservation period before job is reclaimed on worker crash.  |
| `pending`           | boolean  | `false`     | If `true`, the job enters the `pending` state instead of `available`. The job will not be available to workers until explicitly activated via the ACTIVATE operation (`POST /ojs/v1/jobs/:id/activate`). This supports patterns where jobs must be confirmed, approved, or staged before execution. |

#### Response -- Success (`201 Created`)

```http
HTTP/1.1 201 Created
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0002-7000-a000-000000000001
Location: /ojs/v1/jobs/019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6

{
  "job": {
    "id": "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6",
    "type": "email.send",
    "state": "available",
    "args": ["user@example.com", "welcome", {"locale": "en"}],
    "meta": {
      "trace_id": "trace_abc123def456",
      "source": "signup-service"
    },
    "queue": "email",
    "priority": 0,
    "attempt": 0,
    "max_attempts": 5,
    "created_at": "2026-02-12T10:30:00.000Z",
    "enqueued_at": "2026-02-12T10:30:00.123Z",
    "tags": ["onboarding", "email"]
  }
}
```

The server MUST include a `Location` header pointing to the newly created job resource.

**Rationale:** The `Location` header follows HTTP/1.1 semantics for `201 Created` responses and enables clients to retrieve the job without parsing the response body.

#### Response -- Validation Error (`400 Bad Request`)

```http
HTTP/1.1 400 Bad Request
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0002-7000-a000-000000000002

{
  "error": {
    "code": "invalid_request",
    "message": "The 'args' field must be a JSON array.",
    "retryable": false,
    "details": {
      "field": "args",
      "expected": "array",
      "received": "object"
    },
    "request_id": "req_019414d4-0002-7000-a000-000000000002"
  }
}
```

#### Response -- Duplicate Job (`409 Conflict`)

When the job's unique policy has `on_conflict: "reject"` and a duplicate exists:

```http
HTTP/1.1 409 Conflict
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0002-7000-a000-000000000003

{
  "error": {
    "code": "duplicate",
    "message": "A job with the same unique key already exists.",
    "retryable": false,
    "details": {
      "existing_job_id": "019414d4-7a1e-7000-b000-111111111111",
      "unique_key": "email.send:user@example.com:welcome"
    },
    "request_id": "req_019414d4-0002-7000-a000-000000000003"
  }
}
```

---

### 9.2 Batch Enqueue -- PUSH (batch)

**`POST /ojs/v1/jobs/batch`**

Enqueues multiple jobs in a single atomic operation. This is a Level 4 capability.

The request MUST include a `jobs` array. Each element MUST follow the same schema as a single enqueue request. The server MUST process the batch atomically.

#### Request

```bash
curl -s -X POST https://jobs.example.com/ojs/v1/jobs/batch \
  -H "Content-Type: application/openjobspec+json" \
  -H "Accept: application/openjobspec+json" \
  -d '{
    "jobs": [
      {
        "type": "email.send",
        "args": ["alice@example.com", "welcome", {"locale": "en"}],
        "options": {
          "queue": "email",
          "tags": ["onboarding"]
        }
      },
      {
        "type": "email.send",
        "args": ["bob@example.com", "welcome", {"locale": "fr"}],
        "options": {
          "queue": "email",
          "tags": ["onboarding"]
        }
      },
      {
        "type": "email.send",
        "args": ["carol@example.com", "welcome", {"locale": "de"}],
        "options": {
          "queue": "email",
          "tags": ["onboarding"]
        }
      }
    ]
  }'
```

#### Response -- Success (`201 Created`)

```http
HTTP/1.1 201 Created
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0003-7000-a000-000000000001

{
  "jobs": [
    {
      "id": "019414d4-8b30-7000-a001-000000000001",
      "type": "email.send",
      "state": "available",
      "queue": "email",
      "created_at": "2026-02-12T10:30:00.000Z",
      "enqueued_at": "2026-02-12T10:30:00.200Z"
    },
    {
      "id": "019414d4-8b30-7000-a001-000000000002",
      "type": "email.send",
      "state": "available",
      "queue": "email",
      "created_at": "2026-02-12T10:30:00.000Z",
      "enqueued_at": "2026-02-12T10:30:00.200Z"
    },
    {
      "id": "019414d4-8b30-7000-a001-000000000003",
      "type": "email.send",
      "state": "available",
      "queue": "email",
      "created_at": "2026-02-12T10:30:00.000Z",
      "enqueued_at": "2026-02-12T10:30:00.200Z"
    }
  ],
  "count": 3
}
```

#### Response -- Batch Validation Error (`400 Bad Request`)

If any job in the batch fails validation, the entire batch is rejected:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0003-7000-a000-000000000002

{
  "error": {
    "code": "invalid_request",
    "message": "Batch validation failed: job at index 1 is missing required field 'type'.",
    "retryable": false,
    "details": {
      "index": 1,
      "field": "type",
      "validation": "required"
    },
    "request_id": "req_019414d4-0003-7000-a000-000000000002"
  }
}
```

---

### 9.3 Get Job Details -- INFO

**`GET /ojs/v1/jobs/:id`**

Retrieves the full details of a job by its ID. This is a Level 1 capability.

#### Request

```bash
curl -s https://jobs.example.com/ojs/v1/jobs/019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6 \
  -H "Accept: application/openjobspec+json"
```

#### Response -- Success (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0004-7000-a000-000000000001

{
  "job": {
    "id": "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6",
    "type": "email.send",
    "state": "completed",
    "args": ["user@example.com", "welcome", {"locale": "en"}],
    "meta": {
      "trace_id": "trace_abc123def456",
      "source": "signup-service"
    },
    "result": {
      "message_id": "msg_019414d5-1234-7000-b000-aabbccddeeff",
      "delivered": true
    },
    "queue": "email",
    "priority": 0,
    "attempt": 1,
    "max_attempts": 5,
    "created_at": "2026-02-12T10:30:00.000Z",
    "enqueued_at": "2026-02-12T10:30:00.123Z",
    "started_at": "2026-02-12T10:30:01.456Z",
    "completed_at": "2026-02-12T10:30:02.789Z",
    "tags": ["onboarding", "email"]
  }
}
```

#### Response -- Not Found (`404 Not Found`)

```http
HTTP/1.1 404 Not Found
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0004-7000-a000-000000000002

{
  "error": {
    "code": "not_found",
    "message": "Job '019414d4-0000-0000-0000-000000000000' not found.",
    "retryable": false,
    "details": {
      "resource_type": "job",
      "resource_id": "019414d4-0000-0000-0000-000000000000"
    },
    "request_id": "req_019414d4-0004-7000-a000-000000000002"
  }
}
```

---

### 9.4 Cancel a Job -- CANCEL

**`DELETE /ojs/v1/jobs/:id`**

Cancels a job, preventing it from being processed. This is a Level 1 capability.

#### Request

```bash
curl -s -X DELETE https://jobs.example.com/ojs/v1/jobs/019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6 \
  -H "Accept: application/openjobspec+json"
```

#### Response -- Success (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0005-7000-a000-000000000001

{
  "job": {
    "id": "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6",
    "type": "email.send",
    "state": "cancelled",
    "cancelled_at": "2026-02-12T10:31:00.000Z",
    "previous_state": "available"
  }
}
```

#### Response -- Conflict (`409 Conflict`)

When the job is already in a terminal state:

```http
HTTP/1.1 409 Conflict
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0005-7000-a000-000000000002

{
  "error": {
    "code": "invalid_request",
    "message": "Cannot cancel job in terminal state 'completed'.",
    "retryable": false,
    "details": {
      "job_id": "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6",
      "current_state": "completed"
    },
    "request_id": "req_019414d4-0005-7000-a000-000000000002"
  }
}
```

---

### 9.5 Activate a Job -- ACTIVATE

**`POST /ojs/v1/jobs/:id/activate`**

Activates a pending job, transitioning it from `pending` to `available` so that it becomes eligible for worker processing. This is a Level 1 capability.

Jobs enter the `pending` state when enqueued with the `"pending": true` option. Pending jobs are staged and will not be made available to workers until explicitly activated via this endpoint. This supports patterns where jobs must be confirmed, approved, or staged before execution (inspired by River's `pending` state for staged job activation).

#### Request

```bash
curl -s -X POST https://jobs.example.com/ojs/v1/jobs/019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6/activate \
  -H "Content-Type: application/openjobspec+json" \
  -H "Accept: application/openjobspec+json"
```

#### Response -- Success (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0006-7000-a000-000000000001

{
  "job": {
    "id": "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6",
    "type": "email.send",
    "state": "available",
    "activated_at": "2026-02-12T10:31:00.000Z",
    "previous_state": "pending"
  }
}
```

#### Response -- Not Found (`404 Not Found`)

```http
HTTP/1.1 404 Not Found
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0006-7000-a000-000000000002

{
  "error": {
    "code": "not_found",
    "message": "Job '019414d4-0000-0000-0000-000000000000' not found.",
    "retryable": false,
    "details": {
      "resource_type": "job",
      "resource_id": "019414d4-0000-0000-0000-000000000000"
    },
    "request_id": "req_019414d4-0006-7000-a000-000000000002"
  }
}
```

#### Response -- Conflict (`409 Conflict`)

When the job is not in the `pending` state:

```http
HTTP/1.1 409 Conflict
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0006-7000-a000-000000000003

{
  "error": {
    "code": "invalid_request",
    "message": "Cannot activate job in state 'available'. Only jobs in 'pending' state can be activated.",
    "retryable": false,
    "details": {
      "job_id": "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6",
      "current_state": "available"
    },
    "request_id": "req_019414d4-0006-7000-a000-000000000003"
  }
}
```

---

## 10. Worker Endpoints

Worker endpoints coordinate job execution between OJS servers and worker processes.

### 10.1 Fetch Jobs -- FETCH

**`POST /ojs/v1/workers/fetch`**

Claims one or more jobs from the specified queues for processing by a worker. This is a Level 0 (Core) operation.

The server MUST atomically transition fetched jobs from `available` to `active` to prevent double-delivery.

**Rationale for atomicity:** Without atomic state transitions, two workers could claim the same job, leading to duplicate execution. Atomic fetch is a non-negotiable reliability requirement, as demonstrated by BullMQ's Lua scripts and Oban's `SELECT FOR UPDATE SKIP LOCKED`.

#### Request

```bash
curl -s -X POST https://jobs.example.com/ojs/v1/workers/fetch \
  -H "Content-Type: application/openjobspec+json" \
  -H "Accept: application/openjobspec+json" \
  -d '{
    "queues": ["email", "default"],
    "count": 5,
    "worker_id": "worker_019414d4-aaaa-7000-c000-111111111111",
    "visibility_timeout_ms": 30000
  }'
```

#### Request Fields

| Field                  | Type     | Required | Default     | Description                                          |
|------------------------|----------|----------|-------------|------------------------------------------------------|
| `queues`               | string[] | Yes      | --          | Ordered list of queues to fetch from.                |
| `count`                | integer  | No       | `1`         | Maximum number of jobs to fetch.                     |
| `worker_id`            | string   | No       | --          | Identifier for the worker process.                   |
| `visibility_timeout_ms`| integer  | No       | `30000`     | How long the job is reserved before being reclaimed. |

#### Response -- Jobs Available (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0006-7000-a000-000000000001

{
  "jobs": [
    {
      "id": "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6",
      "type": "email.send",
      "state": "active",
      "args": ["user@example.com", "welcome", {"locale": "en"}],
      "meta": {
        "trace_id": "trace_abc123def456",
        "source": "signup-service"
      },
      "queue": "email",
      "attempt": 1,
      "max_attempts": 5,
      "timeout_ms": 30000,
      "created_at": "2026-02-12T10:30:00.000Z",
      "enqueued_at": "2026-02-12T10:30:00.123Z",
      "started_at": "2026-02-12T10:30:05.000Z",
      "tags": ["onboarding", "email"]
    }
  ]
}
```

#### Response -- No Jobs Available (`200 OK`)

An empty `jobs` array indicates no work is currently available. This is not an error.

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0006-7000-a000-000000000002

{
  "jobs": []
}
```

**Rationale for 200 on empty:** An empty queue is a normal operational state, not an error. Using 200 with an empty array (rather than 204 or 404) allows clients to use a uniform response parsing path regardless of whether jobs were returned.

---

### 10.2 Acknowledge Completion -- ACK

**`POST /ojs/v1/workers/ack`**

Reports that a job has been successfully processed. The server transitions the job to `completed`.

#### Request

```bash
curl -s -X POST https://jobs.example.com/ojs/v1/workers/ack \
  -H "Content-Type: application/openjobspec+json" \
  -H "Accept: application/openjobspec+json" \
  -d '{
    "job_id": "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6",
    "result": {
      "message_id": "msg_019414d5-1234-7000-b000-aabbccddeeff",
      "delivered": true
    }
  }'
```

#### Request Fields

| Field    | Type   | Required | Description                                          |
|----------|--------|----------|------------------------------------------------------|
| `job_id` | string | Yes      | The UUIDv7 of the job being acknowledged.            |
| `result` | object | No       | Optional result data produced by the job handler.    |

#### Response -- Success (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0007-7000-a000-000000000001

{
  "acknowledged": true,
  "job_id": "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6",
  "state": "completed",
  "completed_at": "2026-02-12T10:30:02.789Z"
}
```

#### Response -- Conflict (`409 Conflict`)

When the job is not in the `active` state (e.g., already completed or timed out):

```http
HTTP/1.1 409 Conflict
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0007-7000-a000-000000000002

{
  "error": {
    "code": "invalid_request",
    "message": "Cannot acknowledge job not in 'active' state. Current state: 'completed'.",
    "retryable": false,
    "details": {
      "job_id": "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6",
      "current_state": "completed",
      "expected_state": "active"
    },
    "request_id": "req_019414d4-0007-7000-a000-000000000002"
  }
}
```

---

### 10.3 Report Failure -- FAIL

**`POST /ojs/v1/workers/nack`**

Reports that a job handler failed. The server determines whether to retry or discard the job based on the retry policy and the error data.

#### Request

```bash
curl -s -X POST https://jobs.example.com/ojs/v1/workers/nack \
  -H "Content-Type: application/openjobspec+json" \
  -H "Accept: application/openjobspec+json" \
  -d '{
    "job_id": "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6",
    "error": {
      "code": "handler_error",
      "message": "SMTP connection refused: Connection timed out after 10000ms",
      "retryable": true,
      "details": {
        "smtp_host": "mail.example.com",
        "smtp_port": 587,
        "error_class": "SMTPConnectionError"
      }
    }
  }'
```

#### Request Fields

| Field              | Type    | Required | Description                                              |
|--------------------|---------|----------|----------------------------------------------------------|
| `job_id`           | string  | Yes      | The UUIDv7 of the failed job.                            |
| `error`            | object  | Yes      | Structured error information.                            |
| `error.code`       | string  | Yes      | Error code from the standard error codes vocabulary.     |
| `error.message`    | string  | Yes      | Human-readable error description.                        |
| `error.retryable`  | boolean | No       | Whether the client considers this error retryable.       |
| `error.details`    | object  | No       | Additional error context (language-specific stack traces, etc.). |

#### Response -- Will Retry (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0008-7000-a000-000000000001

{
  "job_id": "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6",
  "state": "retryable",
  "attempt": 1,
  "max_attempts": 5,
  "next_attempt_at": "2026-02-12T10:30:06.789Z"
}
```

#### Response -- Discarded (Max Attempts Exhausted) (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0008-7000-a000-000000000002

{
  "job_id": "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6",
  "state": "discarded",
  "attempt": 5,
  "max_attempts": 5,
  "discarded_at": "2026-02-12T10:45:00.000Z"
}
```

---

### 10.4 Worker Heartbeat -- BEAT

**`POST /ojs/v1/workers/heartbeat`**

Extends the visibility timeout of active jobs and reports worker liveness. The server MAY respond with lifecycle directives. This is a Level 1 capability.

#### Request

```bash
curl -s -X POST https://jobs.example.com/ojs/v1/workers/heartbeat \
  -H "Content-Type: application/openjobspec+json" \
  -H "Accept: application/openjobspec+json" \
  -d '{
    "worker_id": "worker_019414d4-aaaa-7000-c000-111111111111",
    "active_jobs": [
      "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6"
    ],
    "visibility_timeout_ms": 30000
  }'
```

#### Request Fields

| Field                  | Type     | Required | Description                                            |
|------------------------|----------|----------|--------------------------------------------------------|
| `worker_id`            | string   | Yes      | Unique identifier for this worker process.             |
| `active_jobs`          | string[] | No       | List of job IDs the worker is currently processing.    |
| `visibility_timeout_ms`| integer  | No       | Requested visibility extension in milliseconds.        |

#### Response -- Normal (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0009-7000-a000-000000000001

{
  "state": "running",
  "jobs_extended": [
    "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6"
  ],
  "server_time": "2026-02-12T10:30:15.000Z"
}
```

#### Response -- Quiet Directive (`200 OK`)

The server instructs the worker to stop fetching new jobs and finish active ones:

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0009-7000-a000-000000000002

{
  "state": "quiet",
  "jobs_extended": [
    "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6"
  ],
  "server_time": "2026-02-12T10:30:15.000Z"
}
```

#### Response -- Terminate Directive (`200 OK`)

The server instructs the worker to shut down immediately:

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0009-7000-a000-000000000003

{
  "state": "terminate",
  "jobs_extended": [],
  "server_time": "2026-02-12T10:30:15.000Z"
}
```

**Worker lifecycle states:**

| State       | Meaning                                                                 |
|-------------|-------------------------------------------------------------------------|
| `running`   | Normal operation. Worker SHOULD continue fetching and processing jobs.  |
| `quiet`     | Worker MUST stop fetching new jobs but MUST finish active jobs.         |
| `terminate` | Worker SHOULD shut down as soon as possible after finishing active jobs.|

---

## 11. Queue Endpoints

### 11.1 List Queues

**`GET /ojs/v1/queues`**

Returns the list of all known queues and their current status.

#### Request

```bash
curl -s https://jobs.example.com/ojs/v1/queues \
  -H "Accept: application/openjobspec+json"
```

#### Response (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0010-7000-a000-000000000001

{
  "queues": [
    {
      "name": "default",
      "status": "active",
      "created_at": "2026-01-01T00:00:00.000Z"
    },
    {
      "name": "email",
      "status": "active",
      "created_at": "2026-01-15T08:00:00.000Z"
    },
    {
      "name": "reports",
      "status": "paused",
      "created_at": "2026-01-15T08:00:00.000Z"
    }
  ],
  "pagination": {
    "total": 3,
    "limit": 50,
    "offset": 0,
    "has_more": false
  }
}
```

---

### 11.2 Queue Statistics

**`GET /ojs/v1/queues/:name/stats`**

Returns detailed statistics for a specific queue. This is a Level 4 capability.

#### Request

```bash
curl -s https://jobs.example.com/ojs/v1/queues/email/stats \
  -H "Accept: application/openjobspec+json"
```

#### Response (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0011-7000-a000-000000000001

{
  "queue": "email",
  "status": "active",
  "stats": {
    "available": 1234,
    "active": 42,
    "scheduled": 56,
    "retryable": 8,
    "discarded": 3,
    "completed_last_hour": 8920,
    "failed_last_hour": 12,
    "avg_duration_ms": 234,
    "avg_wait_ms": 1456,
    "throughput_per_second": 2.48
  },
  "computed_at": "2026-02-12T10:30:00.000Z"
}
```

---

### 11.3 Pause Queue

**`POST /ojs/v1/queues/:name/pause`**

Pauses a queue, preventing workers from fetching new jobs from it. Jobs already being processed (in `active` state) are not affected. This is a Level 4 capability.

#### Request

```bash
curl -s -X POST https://jobs.example.com/ojs/v1/queues/email/pause \
  -H "Content-Type: application/openjobspec+json" \
  -H "Accept: application/openjobspec+json"
```

#### Response (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0012-7000-a000-000000000001

{
  "queue": "email",
  "status": "paused",
  "paused_at": "2026-02-12T10:32:00.000Z"
}
```

#### Response -- Queue Paused Enqueue Attempt (`422 Unprocessable Entity`)

When a client attempts to enqueue a job to a paused queue:

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0012-7000-a000-000000000002

{
  "error": {
    "code": "queue_paused",
    "message": "Queue 'email' is currently paused. Jobs cannot be enqueued or fetched.",
    "retryable": true,
    "details": {
      "queue": "email",
      "paused_at": "2026-02-12T10:32:00.000Z"
    },
    "request_id": "req_019414d4-0012-7000-a000-000000000002"
  }
}
```

---

### 11.4 Resume Queue

**`POST /ojs/v1/queues/:name/resume`**

Resumes a paused queue, allowing workers to fetch jobs again. This is a Level 4 capability.

#### Request

```bash
curl -s -X POST https://jobs.example.com/ojs/v1/queues/email/resume \
  -H "Content-Type: application/openjobspec+json" \
  -H "Accept: application/openjobspec+json"
```

#### Response (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0013-7000-a000-000000000001

{
  "queue": "email",
  "status": "active",
  "resumed_at": "2026-02-12T10:35:00.000Z"
}
```

---

## 12. Dead Letter Endpoints

Dead letter endpoints manage jobs that have exhausted all retry attempts and been moved to the dead letter queue. These are Level 1 capabilities.

### 12.1 List Dead Letter Jobs

**`GET /ojs/v1/dead-letter`**

Returns a paginated list of dead letter jobs.

#### Request

```bash
curl -s "https://jobs.example.com/ojs/v1/dead-letter?queue=email&limit=10&offset=0" \
  -H "Accept: application/openjobspec+json"
```

#### Query Parameters

| Parameter | Type    | Default | Description                              |
|-----------|---------|---------|------------------------------------------|
| `queue`   | string  | --      | Filter by originating queue.             |
| `limit`   | integer | `50`    | Maximum number of results (max 100).     |
| `offset`  | integer | `0`     | Number of results to skip.               |

#### Response (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0014-7000-a000-000000000001

{
  "jobs": [
    {
      "id": "019414d4-cccc-7000-d000-000000000001",
      "type": "email.send",
      "state": "discarded",
      "args": ["failed-user@example.com", "welcome", {"locale": "en"}],
      "queue": "email",
      "attempt": 5,
      "max_attempts": 5,
      "error": {
        "code": "handler_error",
        "message": "SMTP connection refused: Connection timed out after 10000ms",
        "retryable": true
      },
      "created_at": "2026-02-12T08:00:00.000Z",
      "discarded_at": "2026-02-12T10:30:00.000Z"
    }
  ],
  "pagination": {
    "total": 1,
    "limit": 10,
    "offset": 0,
    "has_more": false
  }
}
```

---

### 12.2 Retry a Dead Letter Job

**`POST /ojs/v1/dead-letter/:id/retry`**

Re-enqueues a dead letter job for another attempt. The job's attempt counter is reset and it transitions to `available`.

#### Request

```bash
curl -s -X POST https://jobs.example.com/ojs/v1/dead-letter/019414d4-cccc-7000-d000-000000000001/retry \
  -H "Content-Type: application/openjobspec+json" \
  -H "Accept: application/openjobspec+json"
```

#### Response (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0015-7000-a000-000000000001

{
  "job": {
    "id": "019414d4-cccc-7000-d000-000000000001",
    "type": "email.send",
    "state": "available",
    "queue": "email",
    "attempt": 0,
    "max_attempts": 5,
    "re_enqueued_at": "2026-02-12T10:35:00.000Z"
  }
}
```

---

### 12.3 Discard a Dead Letter Job

**`DELETE /ojs/v1/dead-letter/:id`**

Permanently removes a dead letter job. This operation is irreversible.

#### Request

```bash
curl -s -X DELETE https://jobs.example.com/ojs/v1/dead-letter/019414d4-cccc-7000-d000-000000000001 \
  -H "Accept: application/openjobspec+json"
```

#### Response (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0016-7000-a000-000000000001

{
  "deleted": true,
  "job_id": "019414d4-cccc-7000-d000-000000000001"
}
```

#### Response -- Not Found (`404 Not Found`)

```http
HTTP/1.1 404 Not Found
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0016-7000-a000-000000000002

{
  "error": {
    "code": "not_found",
    "message": "Dead letter job '019414d4-0000-0000-0000-000000000000' not found.",
    "retryable": false,
    "details": {
      "resource_type": "dead_letter_job",
      "resource_id": "019414d4-0000-0000-0000-000000000000"
    },
    "request_id": "req_019414d4-0016-7000-a000-000000000002"
  }
}
```

---

## 13. Cron Endpoints

Cron endpoints manage recurring/periodic job schedules. These are Level 2 capabilities.

### 13.1 List Cron Jobs

**`GET /ojs/v1/cron`**

Returns all registered cron job definitions.

#### Request

```bash
curl -s "https://jobs.example.com/ojs/v1/cron?limit=50&offset=0" \
  -H "Accept: application/openjobspec+json"
```

#### Response (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0017-7000-a000-000000000001

{
  "cron_jobs": [
    {
      "name": "daily-report",
      "cron": "0 9 * * *",
      "timezone": "America/New_York",
      "type": "report.generate",
      "args": ["daily_summary"],
      "options": {
        "queue": "reports",
        "timeout_ms": 300000
      },
      "status": "active",
      "last_run_at": "2026-02-12T09:00:00.000Z",
      "next_run_at": "2026-02-13T09:00:00.000Z",
      "created_at": "2026-01-01T00:00:00.000Z"
    },
    {
      "name": "hourly-cleanup",
      "cron": "0 * * * *",
      "timezone": "UTC",
      "type": "maintenance.cleanup",
      "args": [{"older_than_days": 30}],
      "options": {
        "queue": "default",
        "timeout_ms": 60000
      },
      "status": "active",
      "last_run_at": "2026-02-12T10:00:00.000Z",
      "next_run_at": "2026-02-12T11:00:00.000Z",
      "created_at": "2026-01-01T00:00:00.000Z"
    }
  ],
  "pagination": {
    "total": 2,
    "limit": 50,
    "offset": 0,
    "has_more": false
  }
}
```

---

### 13.2 Register a Cron Job

**`POST /ojs/v1/cron`**

Registers a new recurring job schedule. If a cron job with the same `name` already exists, the server MUST respond with `409 Conflict`.

**Rationale:** Cron job names serve as unique identifiers for recurring schedules. Rejecting duplicates prevents accidental double-scheduling. To update a cron job, delete the existing one and create a new one.

#### Request

```bash
curl -s -X POST https://jobs.example.com/ojs/v1/cron \
  -H "Content-Type: application/openjobspec+json" \
  -H "Accept: application/openjobspec+json" \
  -d '{
    "name": "daily-report",
    "cron": "0 9 * * *",
    "timezone": "America/New_York",
    "type": "report.generate",
    "args": ["daily_summary"],
    "meta": {
      "owner": "analytics-team"
    },
    "options": {
      "queue": "reports",
      "timeout_ms": 300000,
      "retry": {
        "max_attempts": 3,
        "initial_interval_ms": 5000,
        "backoff_coefficient": 2.0,
        "max_interval_ms": 60000,
        "jitter": true
      }
    }
  }'
```

#### Request Fields

| Field      | Type   | Required | Description                                                |
|------------|--------|----------|------------------------------------------------------------|
| `name`     | string | Yes      | Unique name for the cron schedule.                         |
| `cron`     | string | Yes      | Cron expression (5-field standard format).                 |
| `timezone` | string | No       | IANA timezone (default: `UTC`).                            |
| `type`     | string | Yes      | Job type to create on each trigger.                        |
| `args`     | array  | Yes      | Arguments for the created job.                             |
| `meta`     | object | No       | Metadata to attach to each created job.                    |
| `options`  | object | No       | Enqueue options for each created job.                      |

#### Response (`201 Created`)

```http
HTTP/1.1 201 Created
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0018-7000-a000-000000000001

{
  "cron_job": {
    "name": "daily-report",
    "cron": "0 9 * * *",
    "timezone": "America/New_York",
    "type": "report.generate",
    "args": ["daily_summary"],
    "options": {
      "queue": "reports",
      "timeout_ms": 300000
    },
    "status": "active",
    "next_run_at": "2026-02-13T09:00:00.000Z",
    "created_at": "2026-02-12T10:30:00.000Z"
  }
}
```

---

### 13.3 Unregister a Cron Job

**`DELETE /ojs/v1/cron/:name`**

Removes a cron job schedule. Jobs already enqueued by this cron schedule are not affected.

#### Request

```bash
curl -s -X DELETE https://jobs.example.com/ojs/v1/cron/daily-report \
  -H "Accept: application/openjobspec+json"
```

#### Response (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0019-7000-a000-000000000001

{
  "deleted": true,
  "name": "daily-report"
}
```

---

## 14. Workflow Endpoints

Workflow endpoints manage composed job graphs. OJS v1.0 supports three workflow primitives: **chain** (sequential), **group** (parallel), and **batch** (group with callbacks). These are Level 3 capabilities.

### 14.1 Create a Workflow

**`POST /ojs/v1/workflows`**

Creates and starts a workflow. The server MUST validate the workflow definition (no cycles, all dependencies exist) and enqueue the initial step(s).

**Rationale for server-side validation:** Cycle detection must happen before any jobs are enqueued to prevent infinite loops. Validating on the server ensures all clients benefit from the check regardless of language or library.

#### Request

```bash
curl -s -X POST https://jobs.example.com/ojs/v1/workflows \
  -H "Content-Type: application/openjobspec+json" \
  -H "Accept: application/openjobspec+json" \
  -d '{
    "name": "onboarding-pipeline",
    "steps": [
      {
        "id": "send-welcome",
        "type": "email.send",
        "args": ["user@example.com", "welcome", {"locale": "en"}],
        "depends_on": []
      },
      {
        "id": "create-profile",
        "type": "user.create_profile",
        "args": ["user@example.com", {"plan": "free"}],
        "depends_on": []
      },
      {
        "id": "send-confirmation",
        "type": "email.send",
        "args": ["user@example.com", "profile_ready", {"locale": "en"}],
        "depends_on": ["send-welcome", "create-profile"]
      }
    ],
    "options": {
      "queue": "email"
    }
  }'
```

#### Request Fields

| Field              | Type     | Required | Description                                     |
|--------------------|----------|----------|-------------------------------------------------|
| `name`             | string   | Yes      | Human-readable workflow name.                   |
| `steps`            | array    | Yes      | Array of workflow step definitions.             |
| `steps[].id`       | string   | Yes      | Unique step identifier within the workflow.     |
| `steps[].type`     | string   | Yes      | Job type to execute for this step.              |
| `steps[].args`     | array    | Yes      | Arguments for the step's job.                   |
| `steps[].depends_on` | string[] | Yes  | IDs of steps that must complete before this one.|
| `steps[].options`  | object   | No       | Per-step enqueue option overrides.              |
| `options`          | object   | No       | Default enqueue options for all steps.          |

#### Response (`201 Created`)

```http
HTTP/1.1 201 Created
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0020-7000-a000-000000000001
Location: /ojs/v1/workflows/019414d4-dddd-7000-e000-000000000001

{
  "workflow": {
    "id": "019414d4-dddd-7000-e000-000000000001",
    "name": "onboarding-pipeline",
    "state": "running",
    "steps": [
      {
        "id": "send-welcome",
        "type": "email.send",
        "state": "available",
        "job_id": "019414d4-dddd-7001-e000-000000000001",
        "depends_on": []
      },
      {
        "id": "create-profile",
        "type": "user.create_profile",
        "state": "available",
        "job_id": "019414d4-dddd-7001-e000-000000000002",
        "depends_on": []
      },
      {
        "id": "send-confirmation",
        "type": "email.send",
        "state": "pending",
        "job_id": null,
        "depends_on": ["send-welcome", "create-profile"]
      }
    ],
    "created_at": "2026-02-12T10:30:00.000Z"
  }
}
```

---

### 14.2 Get Workflow Status

**`GET /ojs/v1/workflows/:id`**

Retrieves the current state of a workflow and all its steps.

#### Request

```bash
curl -s https://jobs.example.com/ojs/v1/workflows/019414d4-dddd-7000-e000-000000000001 \
  -H "Accept: application/openjobspec+json"
```

#### Response (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0021-7000-a000-000000000001

{
  "workflow": {
    "id": "019414d4-dddd-7000-e000-000000000001",
    "name": "onboarding-pipeline",
    "state": "running",
    "steps": [
      {
        "id": "send-welcome",
        "type": "email.send",
        "state": "completed",
        "job_id": "019414d4-dddd-7001-e000-000000000001",
        "started_at": "2026-02-12T10:30:01.000Z",
        "completed_at": "2026-02-12T10:30:02.500Z",
        "result": {
          "message_id": "msg_019414d5-1234-7000-b000-aabbccddeeff"
        },
        "depends_on": []
      },
      {
        "id": "create-profile",
        "type": "user.create_profile",
        "state": "active",
        "job_id": "019414d4-dddd-7001-e000-000000000002",
        "started_at": "2026-02-12T10:30:01.200Z",
        "depends_on": []
      },
      {
        "id": "send-confirmation",
        "type": "email.send",
        "state": "pending",
        "job_id": null,
        "depends_on": ["send-welcome", "create-profile"]
      }
    ],
    "created_at": "2026-02-12T10:30:00.000Z"
  }
}
```

---

### 14.3 Cancel a Workflow

**`DELETE /ojs/v1/workflows/:id`**

Cancels a workflow and all its non-terminal steps.

#### Request

```bash
curl -s -X DELETE https://jobs.example.com/ojs/v1/workflows/019414d4-dddd-7000-e000-000000000001 \
  -H "Accept: application/openjobspec+json"
```

#### Response (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0022-7000-a000-000000000001

{
  "workflow": {
    "id": "019414d4-dddd-7000-e000-000000000001",
    "name": "onboarding-pipeline",
    "state": "cancelled",
    "cancelled_at": "2026-02-12T10:31:00.000Z",
    "steps_cancelled": 2,
    "steps_already_completed": 1
  }
}
```

---

## 15. Schema Endpoints

Schema endpoints manage JSON Schema definitions used for job argument validation. Schema validation is an optional capability at any conformance level.

### 15.1 List Schemas

**`GET /ojs/v1/schemas`**

Returns all registered schemas.

#### Request

```bash
curl -s "https://jobs.example.com/ojs/v1/schemas?limit=50&offset=0" \
  -H "Accept: application/openjobspec+json"
```

#### Response (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0023-7000-a000-000000000001

{
  "schemas": [
    {
      "uri": "urn:ojs:schema:email.send:v1",
      "type": "email.send",
      "version": 1,
      "created_at": "2026-01-01T00:00:00.000Z"
    },
    {
      "uri": "urn:ojs:schema:report.generate:v1",
      "type": "report.generate",
      "version": 1,
      "created_at": "2026-01-15T00:00:00.000Z"
    }
  ],
  "pagination": {
    "total": 2,
    "limit": 50,
    "offset": 0,
    "has_more": false
  }
}
```

---

### 15.2 Register a Schema

**`POST /ojs/v1/schemas`**

Registers a new JSON Schema for job argument validation.

#### Request

```bash
curl -s -X POST https://jobs.example.com/ojs/v1/schemas \
  -H "Content-Type: application/openjobspec+json" \
  -H "Accept: application/openjobspec+json" \
  -d '{
    "uri": "urn:ojs:schema:email.send:v1",
    "type": "email.send",
    "version": 1,
    "schema": {
      "$schema": "https://json-schema.org/draft/2020-12/schema",
      "type": "array",
      "prefixItems": [
        {
          "type": "string",
          "format": "email",
          "description": "Recipient email address"
        },
        {
          "type": "string",
          "enum": ["welcome", "password_reset", "invoice"],
          "description": "Email template name"
        },
        {
          "type": "object",
          "description": "Template variables",
          "properties": {
            "locale": { "type": "string" }
          }
        }
      ],
      "minItems": 2,
      "maxItems": 3
    }
  }'
```

#### Response (`201 Created`)

```http
HTTP/1.1 201 Created
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0024-7000-a000-000000000001

{
  "schema": {
    "uri": "urn:ojs:schema:email.send:v1",
    "type": "email.send",
    "version": 1,
    "created_at": "2026-02-12T10:30:00.000Z"
  }
}
```

#### Response -- Schema Validation Error (`400 Bad Request`)

When the submitted schema itself is invalid:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0024-7000-a000-000000000002

{
  "error": {
    "code": "invalid_request",
    "message": "The provided JSON Schema is not valid draft 2020-12.",
    "retryable": false,
    "details": {
      "schema_error": "$schema must reference draft 2020-12"
    },
    "request_id": "req_019414d4-0024-7000-a000-000000000002"
  }
}
```

---

### 15.3 Get Schema by URI

**`GET /ojs/v1/schemas/:uri`**

Retrieves a schema by its URI. The `:uri` parameter MUST be URL-encoded.

#### Request

```bash
curl -s "https://jobs.example.com/ojs/v1/schemas/urn%3Aojs%3Aschema%3Aemail.send%3Av1" \
  -H "Accept: application/openjobspec+json"
```

#### Response (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0025-7000-a000-000000000001

{
  "schema": {
    "uri": "urn:ojs:schema:email.send:v1",
    "type": "email.send",
    "version": 1,
    "schema": {
      "$schema": "https://json-schema.org/draft/2020-12/schema",
      "type": "array",
      "prefixItems": [
        {
          "type": "string",
          "format": "email",
          "description": "Recipient email address"
        },
        {
          "type": "string",
          "enum": ["welcome", "password_reset", "invoice"],
          "description": "Email template name"
        },
        {
          "type": "object",
          "description": "Template variables",
          "properties": {
            "locale": { "type": "string" }
          }
        }
      ],
      "minItems": 2,
      "maxItems": 3
    },
    "created_at": "2026-02-12T10:30:00.000Z"
  }
}
```

---

### 15.4 Delete a Schema

**`DELETE /ojs/v1/schemas/:uri`**

Removes a schema registration. Jobs already enqueued with this schema reference are not affected. The `:uri` parameter MUST be URL-encoded.

#### Request

```bash
curl -s -X DELETE "https://jobs.example.com/ojs/v1/schemas/urn%3Aojs%3Aschema%3Aemail.send%3Av1" \
  -H "Accept: application/openjobspec+json"
```

#### Response (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0026-7000-a000-000000000001

{
  "deleted": true,
  "uri": "urn:ojs:schema:email.send:v1"
}
```

---

## 16. Error Handling

### 16.1 Error Response Format

All error responses MUST use the following JSON structure:

```json
{
  "error": {
    "code": "invalid_payload",
    "message": "Human-readable description of the error.",
    "retryable": false,
    "details": {},
    "request_id": "req_019414d4-0000-7000-a000-000000000000"
  }
}
```

**Rationale:** A consistent error structure enables clients to implement uniform error handling regardless of the specific failure. The `retryable` field allows automated retry logic without parsing error messages. The `request_id` enables support correlation.

#### Error Response Fields

| Field              | Type    | Required | Description                                                    |
|--------------------|---------|----------|----------------------------------------------------------------|
| `error`            | object  | Yes      | Error envelope.                                                |
| `error.code`       | string  | Yes      | Machine-readable error code from the standard vocabulary.      |
| `error.message`    | string  | Yes      | Human-readable description. MUST NOT contain sensitive data.   |
| `error.retryable`  | boolean | Yes      | Whether the client should retry the request.                   |
| `error.details`    | object  | No       | Additional structured error context.                           |
| `error.request_id` | string  | Yes      | The request ID for this request (mirrors `X-Request-Id` header).|

**Rationale for `retryable`:** Clients in different languages need a machine-readable signal to determine retry behavior. Without this field, every client library would need to maintain its own mapping of error codes to retry decisions, leading to inconsistency.

### 16.2 HTTP Status Code Mapping

Servers MUST use the following HTTP status codes:

| Status Code | Meaning                     | When Used                                                      |
|-------------|-----------------------------|----------------------------------------------------------------|
| `200`       | OK                          | Successful read, update, or command operation.                 |
| `201`       | Created                     | Job or resource successfully created.                          |
| `202`       | Accepted                    | Request accepted for asynchronous processing.                  |
| `400`       | Bad Request                 | Malformed JSON, missing required fields, invalid types.        |
| `404`       | Not Found                   | Job, queue, or resource does not exist.                        |
| `409`       | Conflict                    | Duplicate job (reject policy), invalid state transition.       |
| `422`       | Unprocessable Entity        | Valid syntax but cannot process (queue paused, unsupported level). |
| `429`       | Too Many Requests           | Rate limit exceeded.                                           |
| `500`       | Internal Server Error       | Unexpected server-side failure.                                |
| `503`       | Service Unavailable         | Backend (Redis, Postgres, etc.) is unreachable.                |

**Rationale for 409 on duplicates:** `409 Conflict` correctly indicates that the request conflicts with the current state of the server (an existing job with the same unique key). This is distinct from `400` (malformed request) and `422` (valid but unprocessable).

**Rationale for 422 on paused queues:** The request is syntactically valid but the server cannot process it due to the queue's current state. `422` conveys "I understand your request but cannot fulfill it right now" which is distinct from `400` (I cannot parse your request).

### 16.3 Standard Error Codes

Implementations MUST use these error codes in the `error.code` field:

| Code                | Description                                     | Retryable | HTTP Status |
|---------------------|-------------------------------------------------|-----------|-------------|
| `handler_error`     | Unhandled exception in job handler              | yes       | --          |
| `timeout`           | Job exceeded its execution timeout              | yes       | --          |
| `cancelled`         | Job was explicitly cancelled                    | no        | --          |
| `invalid_payload`   | Job args failed schema validation               | no        | `400`       |
| `invalid_request`   | Malformed HTTP request                          | no        | `400`       |
| `not_found`         | Requested resource does not exist               | no        | `404`       |
| `backend_error`     | Backend storage or transport failure            | yes       | `500`       |
| `rate_limited`      | Rate limit exceeded for queue or client         | yes       | `429`       |
| `duplicate`         | Unique job constraint violated                  | no        | `409`       |
| `queue_paused`      | Target queue is currently paused                | yes       | `422`       |
| `schema_validation` | Job args do not conform to registered schema    | no        | `400`       |
| `unsupported`       | Feature requires a higher conformance level     | no        | `422`       |

**Rationale:** A fixed vocabulary of error codes enables interoperable error handling. The `handler_error` and `timeout` codes do not map to HTTP status codes because they describe job execution failures reported through the FAIL (nack) endpoint, not HTTP request failures.

Implementations MAY define additional error codes prefixed with `x_` (e.g., `x_custom_validation`). Clients MUST treat unrecognized error codes as non-retryable.

**Rationale for `x_` prefix:** Namespacing custom error codes prevents collisions with future standard codes while still allowing implementation-specific extensions.

---

## 17. Pagination

### 17.1 Request Parameters

All list endpoints MUST support the following query parameters for pagination:

| Parameter | Type    | Default | Max   | Description                      |
|-----------|---------|---------|-------|----------------------------------|
| `limit`   | integer | `50`    | `100` | Maximum number of results.       |
| `offset`  | integer | `0`     | --    | Number of results to skip.       |

**Rationale:** Offset-based pagination is simple, predictable, and sufficient for administrative endpoints. Cursor-based pagination is more efficient for high-volume streams but adds complexity that is unnecessary for OJS management endpoints. Implementations MAY additionally support cursor-based pagination via a `cursor` parameter.

### 17.2 Response Format

All paginated responses MUST include a `pagination` object:

```json
{
  "pagination": {
    "total": 1234,
    "limit": 50,
    "offset": 0,
    "has_more": true
  }
}
```

| Field      | Type    | Description                                           |
|------------|---------|-------------------------------------------------------|
| `total`    | integer | Total number of results matching the query.           |
| `limit`    | integer | The limit that was applied.                           |
| `offset`   | integer | The offset that was applied.                          |
| `has_more` | boolean | Whether more results exist beyond this page.          |

Servers MUST NOT return more results than the requested `limit`. Servers MUST return `has_more: true` if `offset + limit < total`.

#### Example: Paginated Request

```bash
curl -s "https://jobs.example.com/ojs/v1/dead-letter?queue=email&limit=10&offset=20" \
  -H "Accept: application/openjobspec+json"
```

#### Example: Paginated Response

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0027-7000-a000-000000000001

{
  "jobs": [
    {
      "id": "019414d4-cccc-7000-d000-000000000021",
      "type": "email.send",
      "state": "discarded",
      "args": ["page2-user@example.com", "welcome", {"locale": "en"}],
      "queue": "email",
      "attempt": 5,
      "max_attempts": 5,
      "discarded_at": "2026-02-12T09:00:00.000Z"
    }
  ],
  "pagination": {
    "total": 45,
    "limit": 10,
    "offset": 20,
    "has_more": true
  }
}
```

---

## 18. Rate Limiting

### 18.1 Rate Limit Headers

Servers that enforce rate limiting MUST include the following headers in every response:

| Header                  | Type    | Description                                              |
|-------------------------|---------|----------------------------------------------------------|
| `X-RateLimit-Limit`     | integer | Maximum requests allowed in the current window.          |
| `X-RateLimit-Remaining` | integer | Requests remaining in the current window.                |
| `X-RateLimit-Reset`     | integer | Unix timestamp (seconds) when the window resets.         |

**Rationale:** These headers follow the widely adopted convention established by GitHub, Twitter, and other major APIs. Providing rate limit information proactively allows clients to implement backoff before hitting the limit, reducing 429 errors.

Servers that do not enforce rate limiting MAY omit these headers.

### 18.2 Rate Limit Exceeded Response

When a client exceeds the rate limit, the server MUST respond with `429 Too Many Requests`:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0028-7000-a000-000000000001
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1739356260
Retry-After: 60

{
  "error": {
    "code": "rate_limited",
    "message": "Rate limit exceeded. Try again in 60 seconds.",
    "retryable": true,
    "details": {
      "limit": 1000,
      "window_seconds": 3600,
      "retry_after_seconds": 60
    },
    "request_id": "req_019414d4-0028-7000-a000-000000000001"
  }
}
```

The server MUST include a `Retry-After` header (in seconds) as specified by RFC 7231.

**Rationale:** The `Retry-After` header is the HTTP-standard mechanism for communicating when a client should retry. Including it alongside the `X-RateLimit-*` headers provides both immediate retry guidance and ongoing rate information.

### 18.3 Example: Normal Response with Rate Limit Headers

```http
HTTP/1.1 201 Created
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0029-7000-a000-000000000001
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 997
X-RateLimit-Reset: 1739356260
Location: /ojs/v1/jobs/019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6

{
  "job": {
    "id": "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6",
    "type": "email.send",
    "state": "available",
    "args": ["user@example.com", "welcome", {"locale": "en"}],
    "queue": "email",
    "created_at": "2026-02-12T10:30:00.000Z",
    "enqueued_at": "2026-02-12T10:30:00.123Z"
  }
}
```

---

## 19. Request ID Tracking

### 19.1 Server-Generated Request IDs

The server MUST generate a unique `X-Request-Id` for every request and include it in the response headers. The request ID MUST also appear in error response bodies as `error.request_id`.

**Rationale:** Request IDs are essential for debugging, support tickets, and log correlation. Generating them server-side ensures every request is trackable, even if the client does not send one.

### 19.2 Client-Provided Request IDs

If the client includes an `X-Request-Id` header in the request, the server SHOULD use the client-provided value instead of generating a new one.

**Rationale:** In microservice architectures, propagating a client-generated request ID enables end-to-end tracing across multiple services.

### 19.3 Request ID Format

Request IDs SHOULD use the format `req_<UUIDv7>`, for example:

```
req_019414d4-0001-7000-a000-000000000001
```

Implementations MAY use a different format, but the value MUST be a non-empty string that is unique within a reasonable time window (at least 24 hours).

### 19.4 Example: Client-Provided Request ID

```bash
curl -s -X POST https://jobs.example.com/ojs/v1/jobs \
  -H "Content-Type: application/openjobspec+json" \
  -H "Accept: application/openjobspec+json" \
  -H "X-Request-Id: req_client-019414d4-ffff-7000-a000-123456789abc" \
  -d '{
    "type": "email.send",
    "args": ["user@example.com", "welcome", {"locale": "en"}]
  }'
```

```http
HTTP/1.1 201 Created
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_client-019414d4-ffff-7000-a000-123456789abc
Location: /ojs/v1/jobs/019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6

{
  "job": {
    "id": "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6",
    "type": "email.send",
    "state": "available",
    "args": ["user@example.com", "welcome", {"locale": "en"}],
    "queue": "default",
    "created_at": "2026-02-12T10:30:00.000Z",
    "enqueued_at": "2026-02-12T10:30:00.123Z"
  }
}
```

---

## 20. CORS Considerations

### 20.1 Browser Access

OJS endpoints are primarily designed for server-to-server communication. However, implementations that serve browser-based dashboards or management UIs SHOULD support CORS.

### 20.2 CORS Headers

Implementations supporting CORS SHOULD respond to preflight requests (`OPTIONS`) with:

| Header                           | Value                                         |
|----------------------------------|-----------------------------------------------|
| `Access-Control-Allow-Origin`    | Configured allowed origins (not `*` in production) |
| `Access-Control-Allow-Methods`   | `GET, POST, DELETE, OPTIONS`                  |
| `Access-Control-Allow-Headers`   | `Content-Type, Accept, Authorization, X-Request-Id, OJS-Version` |
| `Access-Control-Expose-Headers`  | `X-Request-Id, X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset, OJS-Version, Retry-After` |
| `Access-Control-Max-Age`         | `86400` (24 hours)                            |

**Rationale:** Exposing OJS-specific headers (`X-Request-Id`, `OJS-Version`, rate limit headers) through `Access-Control-Expose-Headers` allows browser-based clients to read these values. Without this header, browsers restrict access to a small set of "simple" response headers.

### 20.3 Security Recommendations

Implementations MUST NOT set `Access-Control-Allow-Origin: *` on endpoints that require authentication. Implementations SHOULD use an allowlist of trusted origins.

**Rationale:** Wildcard CORS combined with credentialed requests creates a security vulnerability. All CORS-enabled OJS deployments should explicitly enumerate trusted origins.

---

## 21. Conformance Manifest

### 21.1 Manifest Endpoint

**`GET /ojs/manifest`**

Returns the server's conformance manifest, which describes the implementation's capabilities, supported conformance level, and available protocol bindings.

This endpoint is served at `/ojs/manifest` (without the `/v1` version prefix) so that clients can discover the server's capabilities before making versioned requests.

Implementations MUST serve the manifest endpoint.

**Rationale:** The manifest enables runtime capability discovery. Clients can programmatically determine whether the server supports features like batch operations, cron scheduling, or workflows before attempting to use them. Serving it outside the versioned path ensures it remains accessible even when the server introduces new major versions.

#### Request

```bash
curl -s https://jobs.example.com/ojs/manifest \
  -H "Accept: application/openjobspec+json"
```

#### Response (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/openjobspec+json
OJS-Version: 1.0
X-Request-Id: req_019414d4-0030-7000-a000-000000000001

{
  "ojs_version": "1.0",
  "implementation": {
    "name": "ojs-redis",
    "version": "1.0.0",
    "language": "go",
    "homepage": "https://github.com/openjobspec/ojs-backend-redis"
  },
  "conformance_level": 2,
  "protocols": ["http"],
  "backend": "redis",
  "capabilities": {
    "batch_enqueue": true,
    "cron_jobs": true,
    "dead_letter": true,
    "delayed_jobs": true,
    "job_ttl": true,
    "priority_queues": false,
    "rate_limiting": false,
    "schema_validation": true,
    "unique_jobs": false,
    "workflows": false,
    "pause_resume": false
  },
  "extensions": [],
  "endpoints": {
    "base_url": "https://jobs.example.com/ojs/v1",
    "manifest": "/ojs/manifest",
    "health": "/ojs/v1/health"
  }
}
```

### 21.2 Manifest Fields

| Field                  | Type     | Required | Description                                                  |
|------------------------|----------|----------|--------------------------------------------------------------|
| `ojs_version`          | string   | Yes      | OJS spec version implemented.                                |
| `implementation`       | object   | Yes      | Implementation metadata.                                     |
| `implementation.name`  | string   | Yes      | Name of the implementation (e.g., `ojs-redis`).              |
| `implementation.version`| string  | Yes      | Version of the implementation.                               |
| `implementation.language`| string | Yes      | Primary language of the implementation.                      |
| `implementation.homepage`| string | No       | URL to the implementation's homepage or repository.          |
| `conformance_level`    | integer  | Yes      | Highest conformance level supported (0--4).                  |
| `protocols`            | string[] | Yes      | Supported protocol bindings (MUST include `"http"`).         |
| `backend`              | string   | Yes      | Backend type (e.g., `redis`, `postgres`, `memory`).          |
| `capabilities`         | object   | Yes      | Feature flags for optional capabilities.                     |
| `extensions`           | string[] | No       | List of non-standard extensions supported.                   |
| `endpoints`            | object   | No       | Base URL and key endpoint paths.                             |

The `protocols` array MUST include `"http"` since HTTP is the required baseline binding.

**Rationale:** The `capabilities` object provides granular feature detection beyond the coarse conformance level. A Level 2 implementation might support cron jobs but not delayed jobs if it only implements a subset of Level 2 features. The capabilities object makes this explicit.

---

## Appendix A: Complete Endpoint Reference

| Method   | Path                              | Operation       | Level | Success Status |
|----------|-----------------------------------|-----------------|-------|----------------|
| `GET`    | `/ojs/manifest`                   | Manifest        | 0     | `200`          |
| `GET`    | `/ojs/v1/health`                  | Health          | 0     | `200`          |
| `POST`   | `/ojs/v1/jobs`                    | PUSH            | 0     | `201`          |
| `POST`   | `/ojs/v1/jobs/batch`              | PUSH (batch)    | 4     | `201`          |
| `GET`    | `/ojs/v1/jobs/:id`                | INFO            | 1     | `200`          |
| `DELETE` | `/ojs/v1/jobs/:id`                | CANCEL          | 1     | `200`          |
| `POST`   | `/ojs/v1/jobs/:id/activate`       | ACTIVATE        | 1     | `200`          |
| `POST`   | `/ojs/v1/workers/fetch`           | FETCH           | 0     | `200`          |
| `POST`   | `/ojs/v1/workers/ack`             | ACK             | 0     | `200`          |
| `POST`   | `/ojs/v1/workers/nack`            | FAIL            | 0     | `200`          |
| `POST`   | `/ojs/v1/workers/heartbeat`       | BEAT            | 1     | `200`          |
| `GET`    | `/ojs/v1/queues`                  | List queues     | 0     | `200`          |
| `GET`    | `/ojs/v1/queues/:name/stats`      | Queue stats     | 4     | `200`          |
| `POST`   | `/ojs/v1/queues/:name/pause`      | Pause queue     | 4     | `200`          |
| `POST`   | `/ojs/v1/queues/:name/resume`     | Resume queue    | 4     | `200`          |
| `GET`    | `/ojs/v1/dead-letter`             | List dead letter| 1     | `200`          |
| `POST`   | `/ojs/v1/dead-letter/:id/retry`   | Retry dead      | 1     | `200`          |
| `DELETE` | `/ojs/v1/dead-letter/:id`         | Discard dead    | 1     | `200`          |
| `GET`    | `/ojs/v1/cron`                    | List cron       | 2     | `200`          |
| `POST`   | `/ojs/v1/cron`                    | Register cron   | 2     | `201`          |
| `DELETE` | `/ojs/v1/cron/:name`              | Unregister cron | 2     | `200`          |
| `POST`   | `/ojs/v1/workflows`               | Create workflow | 3     | `201`          |
| `GET`    | `/ojs/v1/workflows/:id`           | Get workflow    | 3     | `200`          |
| `DELETE` | `/ojs/v1/workflows/:id`           | Cancel workflow | 3     | `200`          |
| `GET`    | `/ojs/v1/schemas`                 | List schemas    | 0     | `200`          |
| `POST`   | `/ojs/v1/schemas`                 | Register schema | 0     | `201`          |
| `GET`    | `/ojs/v1/schemas/:uri`            | Get schema      | 0     | `200`          |
| `DELETE` | `/ojs/v1/schemas/:uri`            | Delete schema   | 0     | `200`          |

---

## Appendix B: Standard Error Code Reference

| Code                | HTTP Status | Retryable | Description                                     |
|---------------------|-------------|-----------|--------------------------------------------------|
| `handler_error`     | --          | yes       | Unhandled exception in job handler               |
| `timeout`           | --          | yes       | Job exceeded its execution timeout               |
| `cancelled`         | --          | no        | Job was explicitly cancelled                     |
| `invalid_payload`   | `400`       | no        | Job args failed schema validation                |
| `invalid_request`   | `400`       | no        | Malformed HTTP request                           |
| `not_found`         | `404`       | no        | Requested resource does not exist                |
| `backend_error`     | `500`       | yes       | Backend storage or transport failure             |
| `rate_limited`      | `429`       | yes       | Rate limit exceeded                              |
| `duplicate`         | `409`       | no        | Unique job constraint violated                   |
| `queue_paused`      | `422`       | yes       | Target queue is currently paused                 |
| `schema_validation` | `400`       | no        | Job args do not conform to registered schema     |
| `unsupported`       | `422`       | no        | Feature requires a higher conformance level      |

---

## Appendix C: Example Session

The following demonstrates a complete job lifecycle using curl commands against an OJS HTTP server.

### Step 1: Check Health

```bash
curl -s https://jobs.example.com/ojs/v1/health \
  -H "Accept: application/openjobspec+json" | jq .
```

```json
{
  "status": "ok",
  "version": "1.0",
  "uptime_seconds": 3600,
  "backend": {
    "type": "redis",
    "status": "connected",
    "latency_ms": 1
  }
}
```

### Step 2: Enqueue a Job

```bash
curl -s -X POST https://jobs.example.com/ojs/v1/jobs \
  -H "Content-Type: application/openjobspec+json" \
  -H "Accept: application/openjobspec+json" \
  -d '{
    "type": "email.send",
    "args": ["user@example.com", "welcome", {"locale": "en"}],
    "options": {
      "queue": "email",
      "retry": {
        "max_attempts": 5,
        "initial_interval_ms": 1000,
        "backoff_coefficient": 2.0,
        "max_interval_ms": 300000,
        "jitter": true
      }
    }
  }' | jq .
```

```json
{
  "job": {
    "id": "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6",
    "type": "email.send",
    "state": "available",
    "args": ["user@example.com", "welcome", {"locale": "en"}],
    "queue": "email",
    "priority": 0,
    "attempt": 0,
    "max_attempts": 5,
    "created_at": "2026-02-12T10:30:00.000Z",
    "enqueued_at": "2026-02-12T10:30:00.123Z"
  }
}
```

### Step 3: Fetch the Job (Worker)

```bash
curl -s -X POST https://jobs.example.com/ojs/v1/workers/fetch \
  -H "Content-Type: application/openjobspec+json" \
  -H "Accept: application/openjobspec+json" \
  -d '{
    "queues": ["email"],
    "count": 1,
    "worker_id": "worker_019414d4-aaaa-7000-c000-111111111111"
  }' | jq .
```

```json
{
  "jobs": [
    {
      "id": "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6",
      "type": "email.send",
      "state": "active",
      "args": ["user@example.com", "welcome", {"locale": "en"}],
      "queue": "email",
      "attempt": 1,
      "max_attempts": 5,
      "timeout_ms": 30000,
      "created_at": "2026-02-12T10:30:00.000Z",
      "enqueued_at": "2026-02-12T10:30:00.123Z",
      "started_at": "2026-02-12T10:30:05.000Z"
    }
  ]
}
```

### Step 4: Send Heartbeat (Worker)

```bash
curl -s -X POST https://jobs.example.com/ojs/v1/workers/heartbeat \
  -H "Content-Type: application/openjobspec+json" \
  -H "Accept: application/openjobspec+json" \
  -d '{
    "worker_id": "worker_019414d4-aaaa-7000-c000-111111111111",
    "active_jobs": ["019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6"]
  }' | jq .
```

```json
{
  "state": "running",
  "jobs_extended": [
    "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6"
  ],
  "server_time": "2026-02-12T10:30:15.000Z"
}
```

### Step 5: Acknowledge Completion (Worker)

```bash
curl -s -X POST https://jobs.example.com/ojs/v1/workers/ack \
  -H "Content-Type: application/openjobspec+json" \
  -H "Accept: application/openjobspec+json" \
  -d '{
    "job_id": "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6",
    "result": {
      "message_id": "msg_019414d5-1234-7000-b000-aabbccddeeff",
      "delivered": true
    }
  }' | jq .
```

```json
{
  "acknowledged": true,
  "job_id": "019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6",
  "state": "completed",
  "completed_at": "2026-02-12T10:30:06.789Z"
}
```

### Step 6: Verify Final State

```bash
curl -s https://jobs.example.com/ojs/v1/jobs/019414d4-8b2e-7c3a-b5d1-f0e2a3b4c5d6 \
  -H "Accept: application/openjobspec+json" | jq .state
```

```json
"completed"
```

---

## Appendix D: Changelog

| Version        | Date       | Changes                    |
|----------------|------------|----------------------------|
| 1.0.0-rc.1     | 2026-02-12 | Initial release candidate. |
