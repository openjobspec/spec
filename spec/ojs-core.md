# Open Job Spec -- Core Specification

| Field        | Value                          |
|-------------|--------------------------------|
| **Title**   | OJS Core Specification         |
| **Version** | 1.0.0-rc.1                     |
| **Status**  | Release Candidate              |
| **Date**    | 2026-02-12                     |
| **Layer**   | 1 -- Core (protocol-agnostic)  |
| **URI**     | https://openjobspec.org/spec/v1/ojs-core |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Design Principles](#4-design-principles)
5. [Job Envelope](#5-job-envelope)
   - 5.1 [Required Attributes](#51-required-attributes)
   - 5.2 [Optional Attributes](#52-optional-attributes)
   - 5.3 [System-Managed Attributes](#53-system-managed-attributes)
   - 5.4 [Attribute Summary Table](#54-attribute-summary-table)
   - 5.5 [Constraints on Attribute Values](#55-constraints-on-attribute-values)
6. [Job Lifecycle State Machine](#6-job-lifecycle-state-machine)
   - 6.1 [States](#61-states)
   - 6.2 [State Diagram](#62-state-diagram)
   - 6.3 [Valid State Transitions](#63-valid-state-transitions)
   - 6.4 [Transition Semantics](#64-transition-semantics)
7. [Logical Operations](#7-logical-operations)
   - 7.1 [PUSH](#71-push)
   - 7.2 [FETCH](#72-fetch)
   - 7.3 [ACK](#73-ack)
   - 7.4 [FAIL](#74-fail)
   - 7.5 [BEAT](#75-beat)
   - 7.6 [CANCEL](#76-cancel)
   - 7.7 [INFO](#77-info)
8. [Error Reporting](#8-error-reporting)
9. [Middleware](#9-middleware)
10. [Worker Lifecycle](#10-worker-lifecycle)
11. [Extension Points](#11-extension-points)
12. [Prior Art](#12-prior-art)
13. [Examples](#13-examples)
14. [Security Considerations](#14-security-considerations)
15. [Acknowledgments](#15-acknowledgments)

---

## 1. Introduction

The Open Job Spec (OJS) is an open, language-agnostic, backend-agnostic standard for background job processing. It defines the structure, lifecycle, and operational semantics of background jobs in a way that is independent of any particular programming language, transport protocol, or storage engine.

This document is the **Layer 1 Core Specification**. It defines *what* a job IS -- its attributes, lifecycle states, operations, and semantics. It is intentionally protocol-agnostic and wire-format-agnostic. How jobs are serialized (Layer 2 -- Wire Format Encodings) and how they are transmitted (Layer 3 -- Protocol Bindings) are defined in companion specifications.

The three-tier architecture is inspired by [CloudEvents](https://cloudevents.io/), which proved that separating the core event model from wire formats and protocol bindings enables broad interoperability across diverse ecosystems.

### 1.1 Goals

- Define a **universal job envelope** that can represent any background job.
- Define a **complete lifecycle state machine** that covers scheduling, execution, retry, cancellation, and failure.
- Define **abstract logical operations** that protocol bindings map to concrete wire interactions.
- Enable **backend portability**: the same job definitions and handler logic work across Redis, PostgreSQL, Kafka, SQS, in-memory, or any conforming backend.
- Enable **language interoperability**: a job enqueued by a Python application can be processed by a Go worker, or vice versa.
- Be **implementable in a weekend**: the core specification is small enough that a developer can build a conforming implementation quickly.

### 1.2 Scope

This specification defines:

- The job envelope (required, optional, and system-managed attributes).
- The job lifecycle state machine (states and valid transitions).
- Logical operations (PUSH, FETCH, ACK, FAIL, BEAT, CANCEL, INFO).
- Structured error reporting format.
- Extension points for optional features (retry, uniqueness, middleware, workflows).

This specification does **not** define:

- Wire format encoding (see [ojs-json-format.md](./ojs-json-format.md)).
- Protocol bindings (see [ojs-http-binding.md](./ojs-http-binding.md), [ojs-grpc-binding.md](./ojs-grpc-binding.md)).
- Retry policy details (see [ojs-retry.md](./ojs-retry.md)).
- Unique job semantics (see [ojs-unique-jobs.md](./ojs-unique-jobs.md)).
- Workflow primitives (see [ojs-workflows.md](./ojs-workflows.md)).
- Deployment topology, authentication, or auto-scaling.

### 1.3 Companion Specifications

| Document | Layer | Description |
|----------|-------|-------------|
| **ojs-core.md** (this document) | 1 -- Core | Job envelope, lifecycle, operations |
| **ojs-json-format.md** | 2 -- Wire Format | JSON serialization rules |
| **ojs-http-binding.md** | 3 -- Protocol Binding | HTTP/REST mapping |
| **ojs-grpc-binding.md** | 3 -- Protocol Binding | gRPC mapping |
| **ojs-retry.md** | Extension | Retry policy specification |
| **ojs-unique-jobs.md** | Extension | Job deduplication |
| **ojs-workflows.md** | Extension | Chain, group, batch primitives |
| **ojs-cron.md** | Extension | Periodic/cron job scheduling |
| **ojs-events.md** | Extension | Standard lifecycle event vocabulary |
| **ojs-middleware.md** | Extension | Enqueue and execution middleware chains |
| **ojs-worker-protocol.md** | Extension | Worker lifecycle and coordination |
| **ojs-conformance.md** | Meta | Conformance levels and requirements |
| **ojs-extension-lifecycle.md** | Meta | Extension tiers, promotion, and governance |
| **ojs-rate-limiting.md** | Official Extension | Rate limiting and concurrency control |
| **ojs-admin-api.md** | Official Extension | Admin/operator control-plane API |
| **ojs-testing.md** | Official Extension | Testing modes and assertion helpers |
| **ojs-observability.md** | Official Extension | OpenTelemetry conventions and metrics |
| **ojs-backpressure.md** | Official Extension | Bounded queues and enqueue-side pressure |
| **ojs-graceful-shutdown.md** | Official Extension | Signal handling, drain, K8s integration |
| **ojs-dead-letter.md** | Official Extension | Dead letter queue management |
| **ojs-job-versioning.md** | Experimental Extension | Job versioning and schema evolution |
| **ojs-multi-tenancy.md** | Experimental Extension | Multi-tenancy and fairness |
| **ojs-encryption.md** | Experimental Extension | Client-side encryption and codec |
| **ojs-framework-adapters.md** | Experimental Extension | Transactional enqueue and framework integration |

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

When these words are used in lowercase, they carry their ordinary English meaning and do not imply specification requirements.

Throughout this document, requirements are annotated with a *Rationale* explaining why the requirement exists. This aids implementers in understanding the design intent and making informed decisions when the specification is ambiguous.

---

## 3. Terminology

**Job**
: The fundamental unit of work in OJS. A job is a serializable data structure that describes a task to be executed asynchronously. A job consists of an envelope (attributes defined by this specification) and arguments (user-provided data).

**Job Envelope**
: The set of attributes that describe a job's identity, type, configuration, and lifecycle state. The envelope is defined by this specification. User-provided data is carried in the `args` and `meta` attributes.

**Queue**
: A named, ordered collection of jobs awaiting execution. Queues are logical constructs; the physical implementation is backend-specific.

**Worker**
: A process that fetches jobs from one or more queues and executes the corresponding handler for each job. A single worker process MAY execute multiple jobs concurrently.

**Handler**
: User-defined logic that processes a job of a given type. Handlers are registered with a worker and invoked when a matching job is fetched.

**Backend**
: The storage and transport layer that manages job persistence, state transitions, ordering, and delivery. Also referred to as a "broker" in some systems. The specification defines the behavioral contract a backend MUST implement, not how it works internally.

**Client**
: A process that creates and enqueues jobs. Clients interact with the backend to submit jobs for asynchronous processing.

**State Transition**
: A change in a job's lifecycle state. Transitions MUST be atomic and MUST only follow the valid transitions defined in this specification.

**Terminal State**
: A lifecycle state from which no further automatic transitions occur. The terminal states are `completed` and `discarded`.

**Middleware**
: A composable function that wraps job enqueueing or execution, enabling cross-cutting concerns such as logging, metrics, error handling, and context propagation. See [ojs-middleware.md](./ojs-middleware.md).

**Spec Version**
: The version of this specification that a job envelope conforms to. Expressed as a [Semantic Versioning 2.0.0](https://semver.org/) string.

---

## 4. Design Principles

These principles guide the specification and SHOULD guide implementation decisions:

1. **Backend-agnostic.** The specification defines the behavioral contract. Redis, PostgreSQL, Kafka, SQS, in-memory -- all are valid backends as long as they conform. An implementation MUST NOT require a specific storage engine.

2. **Language-agnostic.** Any programming language can implement a conforming client or worker. A JavaScript application and a Go application SHOULD be able to share the same job definitions and interoperate through a common backend.

3. **Protocol-extensible.** This core specification is protocol-agnostic. Protocol bindings (HTTP, gRPC, AMQP, etc.) are defined in separate companion specifications. An implementation MAY support one or many protocol bindings.

4. **Simple JSON-only arguments.** Job arguments MUST use JSON-native types only (string, number, boolean, null, array, object). This constraint, proven by Sidekiq over a decade of production use, forces clean separation between job definition and application state, prevents stale object references, and enables cross-language inspection.

5. **Convention over configuration.** The specification defines sensible defaults for every configurable parameter. An implementation SHOULD work correctly with zero configuration.

6. **Server-side intelligence, client simplicity.** Retry logic, scheduling, state management, and coordination live in the backend. Clients need only implement PUSH, FETCH, ACK, FAIL, and BEAT. This architectural pattern, borrowed from Faktory, keeps clients thin and easy to implement in new languages.

7. **Observable by default.** Every conforming implementation MUST support structured error reporting and SHOULD emit lifecycle events as defined in [ojs-events.md](./ojs-events.md).

---

## 5. Job Envelope

The job envelope is the core data structure of the Open Job Spec. It contains all attributes necessary to identify, configure, route, execute, and track a background job.

Attributes are organized into three categories:

- **Required attributes**: MUST be present on every valid job envelope.
- **Optional attributes**: MAY be provided by the client at enqueue time.
- **System-managed attributes**: Set and maintained by the implementation. Clients MUST NOT set these directly; implementations MUST ignore client-provided values for system-managed attributes.

### 5.1 Required Attributes

#### `specversion`

- **Type**: `string`
- **Description**: The version of the OJS Core Specification that the job envelope conforms to.
- **Constraints**: MUST be a valid [Semantic Versioning 2.0.0](https://semver.org/) string. For this version of the specification, the value MUST be `"1.0.0-rc.1"`.
- **Rationale**: Including the spec version in every job envelope enables backward-compatible evolution of the specification. Implementations can use this field to determine which attributes and semantics apply. This pattern is borrowed from CloudEvents, where `specversion` is one of only four required attributes.

#### `id`

- **Type**: `string`
- **Description**: A globally unique identifier for the job.
- **Constraints**: MUST be a [UUIDv7](https://www.rfc-editor.org/rfc/rfc9562#section-5.7) formatted as a lowercase hexadecimal string with hyphens (e.g., `"019461a8-1a2b-7c3d-8e4f-5a6b7c8d9e0f"`). The standard 8-4-4-4-12 format MUST be used.
- **Rationale**: UUIDv7 is time-ordered and sortable, which enables efficient database indexing, chronological job listing, and distributed generation without coordination. Sidekiq uses random hex bytes; Faktory uses random base64url. UUIDv7 provides the sortability advantages of ULIDs with the standardization and tooling support of UUIDs. The choice of UUIDv7 over UUIDv4 is driven by the need for time-based ordering in job tables and sorted sets -- random UUIDs cause index fragmentation and prevent efficient range queries.

#### `type`

- **Type**: `string`
- **Description**: The job type, used to route the job to the appropriate handler.
- **Constraints**: MUST be a non-empty string. MUST use a dot-separated namespace convention (e.g., `"email.send"`, `"report.generate"`, `"data.etl.transform"`). Each segment MUST match the pattern `[a-z][a-z0-9_]*` (lowercase alphanumeric with underscores, starting with a letter). The minimum length is 1 character; there is no maximum length, but implementations SHOULD support types up to 255 characters.
- **Rationale**: Dot-separated namespacing prevents type collisions across teams and applications (e.g., `billing.invoice.generate` vs. `reporting.invoice.generate`). Celery uses Python module paths (`myapp.tasks.add`); Faktory uses flat strings. The dot convention provides natural grouping without coupling to any language's module system. Lowercase is required to prevent case-sensitivity issues across languages and file systems.

#### `queue`

- **Type**: `string`
- **Description**: The target queue for the job.
- **Constraints**: MUST be a non-empty string matching the pattern `[a-z0-9][a-z0-9\-\.]*` (lowercase alphanumeric, hyphens, and dots; must start with alphanumeric). Maximum length: 128 characters. If not provided by the client, the implementation MUST default to `"default"`.
- **Default**: `"default"`
- **Rationale**: Queue names are lowercase to prevent case-sensitivity issues. The character set is deliberately restrictive to ensure queue names are safe for use as Redis keys, PostgreSQL identifiers, file paths, and environment variable components. The `"default"` queue name is universal across all surveyed systems (Sidekiq, BullMQ, Celery, Faktory, Oban, River). Every implementation MUST support at least the `"default"` queue.

#### `args`

- **Type**: `array`
- **Description**: Positional arguments for the job handler. This is the user-provided input data.
- **Constraints**: MUST be a JSON array. Each element MUST be a JSON-native type: `string`, `number`, `boolean`, `null`, `array`, or `object`. Implementations MUST NOT require or support language-specific serialization formats (e.g., Python pickle, Ruby Marshal, Java serialization). The array MAY be empty (`[]`). There is no defined maximum size, but implementations SHOULD document their size limits.
- **Rationale**: Sidekiq's decade of production experience proved that restricting arguments to simple JSON types is the single most important design decision for a job system. It forces developers to pass identifiers rather than serialized objects, preventing stale data bugs. It enables cross-language interoperability (a job enqueued by Ruby can be processed by Go). It makes job arguments inspectable in dashboards and logs. The choice of `args` (array) over `payload` (object) follows Sidekiq's model: positional arguments are simpler to validate, version, and document. An object payload encourages dumping entire model instances into jobs, which is an anti-pattern.

### 5.2 Optional Attributes

Optional attributes MAY be provided by the client at enqueue time. If not provided, implementations MUST use the documented default value.

#### `meta`

- **Type**: `object`
- **Description**: Extensible key-value metadata for cross-cutting concerns. Intended for information that is not part of the job's business logic but is useful for infrastructure, observability, or routing.
- **Constraints**: MUST be a JSON object. Keys MUST be strings. Values MUST be JSON-native types. Implementations MUST preserve all key-value pairs through the job lifecycle without modification. Implementations MUST NOT require specific keys.
- **Default**: `{}` (empty object)
- **Rationale**: Faktory's `custom` hash demonstrated the power of extensible metadata -- it enables trace context propagation, locale, user identity, tenant ID, and other cross-cutting concerns without protocol changes. Taskiq's `labels` serve the same purpose. By separating metadata from arguments, the specification keeps the `args` array focused on handler input while allowing infrastructure concerns to travel with the job. This separation is essential for middleware (see [ojs-middleware.md](./ojs-middleware.md)): enqueue middleware can inject metadata (e.g., trace IDs) without modifying handler arguments.

**Well-known meta keys** (RECOMMENDED but not required):

| Key | Type | Description |
|-----|------|-------------|
| `trace_id` | string | Distributed tracing correlation ID (W3C Trace Context recommended) |
| `span_id` | string | Current span ID for tracing |
| `locale` | string | Locale/language for the job (e.g., `"en-US"`) |
| `user_id` | string | ID of the user who initiated the job |
| `tenant_id` | string | Multi-tenant identifier |
| `correlation_id` | string | Business-level correlation identifier |
| `tags` | array of strings | Tags for filtering and observability |

#### `priority`

- **Type**: `integer`
- **Description**: Job priority within a queue. Higher numbers indicate higher priority.
- **Constraints**: MUST be a signed integer. There is no defined range, but implementations MUST support at least the range -100 to 100. Within a queue, jobs with higher priority values MUST be fetched before jobs with lower priority values. Jobs with equal priority MUST be fetched in FIFO (first-in, first-out) order.
- **Default**: `0`
- **Rationale**: Higher-number-means-higher-priority is the most intuitive convention and aligns with common usage (priority 10 is "more important" than priority 1). BullMQ's convention of 0-is-highest is counterintuitive and causes confusion. Three named priority levels are defined as a convenience, but numeric values allow fine-grained control.

**Named priority levels** (RECOMMENDED):

| Name | Value | Description |
|------|-------|-------------|
| HIGH | 10 | High priority -- processed before normal jobs |
| NORMAL | 0 | Default priority |
| LOW | -10 | Low priority -- processed after normal jobs |

Implementations MUST support numeric priorities. Implementations MAY additionally support named priority levels as aliases for the numeric values.

#### `timeout`

- **Type**: `integer`
- **Description**: Maximum execution time for the job, in seconds.
- **Constraints**: MUST be a positive integer. If a job's execution exceeds this duration, the implementation MUST treat it as a failure with error type `"timeout"`. A value of `0` means no timeout (the implementation's default timeout applies).
- **Default**: Implementation-defined. Implementations SHOULD default to 1800 seconds (30 minutes).
- **Rationale**: Timeouts prevent runaway jobs from consuming worker capacity indefinitely. Faktory defaults to 1800 seconds (30 minutes); Sidekiq does not enforce server-side timeouts by default. Expressing the timeout in seconds (rather than milliseconds) is chosen for readability -- job timeouts are typically measured in seconds or minutes, not milliseconds.

#### `scheduled_at`

- **Type**: `string`
- **Description**: The earliest time at which the job should be executed.
- **Constraints**: MUST be an [ISO 8601](https://en.wikipedia.org/wiki/ISO_8601) / [RFC 3339](https://www.rfc-editor.org/rfc/rfc3339) timestamp with timezone designator (e.g., `"2026-03-15T09:30:00Z"` or `"2026-03-15T09:30:00+02:00"`). If set to a future time, the job MUST enter the `scheduled` state instead of `available`. The implementation MUST transition the job to `available` when the scheduled time arrives (within implementation-defined polling tolerance).
- **Default**: Not set (job is immediately available).
- **Rationale**: Delayed execution is universally supported across all surveyed systems. ISO 8601 with timezone is mandated because: (a) Sidekiq 8.0's migration from floating-point epoch seconds to integer milliseconds demonstrated that numeric timestamps cause precision issues in JSON and JavaScript; (b) human-readable timestamps dramatically improve debuggability in logs and dashboards; (c) timezone is required to prevent ambiguity in distributed systems spanning multiple time zones.

#### `expires_at`

- **Type**: `string`
- **Description**: The deadline after which the job should be discarded if it has not yet started execution.
- **Constraints**: MUST be an ISO 8601 / RFC 3339 timestamp with timezone. If the current time is past `expires_at` when the job would be fetched, the implementation MUST transition the job to `discarded` and MUST NOT execute it.
- **Default**: Not set (job does not expire).
- **Rationale**: Expiration prevents stale jobs from executing after their results would be meaningless (e.g., a "send verification code" job that expires after 10 minutes). This is a TTL (time-to-live) expressed as an absolute deadline rather than a relative duration, which avoids ambiguity about when the TTL starts.

#### `retry`

- **Type**: `object`
- **Description**: Retry policy for the job, controlling behavior when execution fails.
- **Constraints**: See [ojs-retry.md](./ojs-retry.md) for the complete retry policy specification.
- **Default**: Implementation-defined. Implementations SHOULD default to a retry policy with `max_attempts: 3`, exponential backoff, and jitter enabled.
- **Rationale**: Retry is a first-class concept in every production job system. Separating the retry policy into a dedicated object (rather than overloading a single field like Faktory's `retry: 25` / `retry: 0` / `retry: -1`) makes the semantics explicit and extensible.

#### `unique`

- **Type**: `object`
- **Description**: Uniqueness policy for deduplication, preventing duplicate jobs.
- **Constraints**: See [ojs-unique-jobs.md](./ojs-unique-jobs.md) for the complete uniqueness specification.
- **Default**: Not set (no deduplication).
- **Rationale**: Unique jobs are one of the most requested features in job systems. Oban, River, BullMQ, Asynq, and Faktory all provide deduplication with varying degrees of sophistication. The specification defers the details to a companion document because the design space is large and the implementation trade-offs are significant.

#### `schema`

- **Type**: `string`
- **Description**: URI referencing a schema that the `args` array conforms to, enabling validation.
- **Constraints**: MUST be a valid URI. The recommended format is `urn:ojs:schema:{job_type}:v{version}` (e.g., `"urn:ojs:schema:email.send:v1"`). Implementations that support schema validation MUST validate `args` against the referenced schema before enqueueing. Implementations that do not support schema validation MUST preserve the field without rejecting it.
- **Default**: Not set (no schema validation).
- **Rationale**: Optional schema validation enables teams to enforce contracts on job arguments, catching errors at enqueue time rather than execution time. The field is a URI reference rather than an inline schema to support both local registries and remote schema repositories.

### 5.3 System-Managed Attributes

System-managed attributes are set and maintained by the implementation. Clients MUST NOT set these attributes when enqueuing a job. If a client includes system-managed attributes in a PUSH operation, the implementation MUST ignore the client-provided values and use its own.

> **Rationale**: Separating client-provided attributes from system-managed attributes prevents clients from forging state (e.g., claiming a job is `completed` when it has not been executed) and ensures the implementation maintains authoritative control over lifecycle state and timing.

#### `state`

- **Type**: `string`
- **Description**: The current lifecycle state of the job.
- **Constraints**: MUST be one of the eight defined states: `"scheduled"`, `"available"`, `"pending"`, `"active"`, `"completed"`, `"retryable"`, `"cancelled"`, `"discarded"`. See [Section 6](#6-job-lifecycle-state-machine) for the complete state machine definition.
- **Set by**: Implementation, on every state transition.

#### `attempt`

- **Type**: `integer`
- **Description**: The current attempt number for the job. Incremented each time the job transitions to `active`.
- **Constraints**: MUST be a non-negative integer. The first execution is attempt `1`. A job that has never been executed has attempt `0`.
- **Set by**: Implementation, when the job transitions to `active`.
- **Rationale**: 1-indexed attempts (rather than 0-indexed) align with human intuition: "this is the 3rd attempt" means `attempt = 3`. This convention matches Sidekiq, Oban, and Faktory.

#### `created_at`

- **Type**: `string`
- **Description**: The timestamp when the job was created (received by the backend).
- **Constraints**: MUST be an ISO 8601 / RFC 3339 timestamp with timezone.
- **Set by**: Implementation, when the job is received via PUSH.

#### `enqueued_at`

- **Type**: `string`
- **Description**: The timestamp when the job entered the `available` state (became ready for execution).
- **Constraints**: MUST be an ISO 8601 / RFC 3339 timestamp with timezone. For immediately available jobs, this equals `created_at`. For scheduled jobs, this is set when the job transitions from `scheduled` to `available`.
- **Set by**: Implementation, when the job transitions to `available`.

#### `started_at`

- **Type**: `string`
- **Description**: The timestamp when the job most recently entered the `active` state.
- **Constraints**: MUST be an ISO 8601 / RFC 3339 timestamp with timezone. Updated on each attempt.
- **Set by**: Implementation, when the job transitions to `active`.

#### `completed_at`

- **Type**: `string`
- **Description**: The timestamp when the job reached a terminal state (`completed` or `discarded`).
- **Constraints**: MUST be an ISO 8601 / RFC 3339 timestamp with timezone.
- **Set by**: Implementation, when the job transitions to `completed` or `discarded`.

#### `error`

- **Type**: `object`
- **Description**: Information about the most recent error. See [Section 8](#8-error-reporting) for the structure.
- **Constraints**: MUST conform to the error object structure defined in Section 8. This attribute is set when a job fails (transitions to `retryable` or `discarded`) and cleared when the job succeeds.
- **Set by**: Implementation, based on the error data provided in a FAIL operation.

#### `result`

- **Type**: `any`
- **Description**: The return value of the job handler upon successful completion.
- **Constraints**: MUST be a JSON-native value (string, number, boolean, null, array, or object). Implementations MAY impose size limits on stored results and SHOULD document those limits.
- **Set by**: Implementation, based on the result data provided in an ACK operation.
- **Rationale**: Faktory is fire-and-forget with no result mechanism. BullMQ, Celery, Temporal, and Inngest all support return values. Result storage enables workflows where downstream jobs depend on upstream results, and enables clients to poll for job outcomes.

### 5.4 Attribute Summary Table

| Attribute | Type | Category | Required | Default | Description |
|-----------|------|----------|----------|---------|-------------|
| `specversion` | string | Required | Yes | -- | OJS spec version (`"1.0.0-rc.1"`) |
| `id` | string | Required | Yes | -- | UUIDv7 job identifier |
| `type` | string | Required | Yes | -- | Dot-namespaced job type |
| `queue` | string | Required | Yes | `"default"` | Target queue name |
| `args` | array | Required | Yes | -- | Positional arguments (JSON-native types) |
| `meta` | object | Optional | No | `{}` | Extensible key-value metadata |
| `priority` | integer | Optional | No | `0` | Job priority (higher = higher priority) |
| `timeout` | integer | Optional | No | impl-defined | Max execution time in seconds |
| `scheduled_at` | string | Optional | No | -- | ISO 8601 future execution time |
| `expires_at` | string | Optional | No | -- | ISO 8601 expiration deadline |
| `retry` | object | Optional | No | impl-defined | Retry policy (see ojs-retry.md) |
| `unique` | object | Optional | No | -- | Uniqueness policy (see ojs-unique-jobs.md) |
| `schema` | string | Optional | No | -- | URI referencing args schema |
| `state` | string | System | -- | -- | Current lifecycle state |
| `attempt` | integer | System | -- | `0` | Current attempt number (1-indexed) |
| `created_at` | string | System | -- | -- | ISO 8601 creation timestamp |
| `enqueued_at` | string | System | -- | -- | ISO 8601 enqueue timestamp |
| `started_at` | string | System | -- | -- | ISO 8601 execution start timestamp |
| `completed_at` | string | System | -- | -- | ISO 8601 terminal state timestamp |
| `error` | object | System | -- | -- | Last error information |
| `result` | any | System | -- | -- | Job result value |

### 5.5 Constraints on Attribute Values

1. **JSON-native types only.** All attribute values MUST be representable as JSON without loss of information. Implementations MUST NOT introduce language-specific types.

   > *Rationale*: JSON is the universal interchange format. Language-specific serialization (Python pickle, Ruby Marshal) is a security risk and prevents cross-language interoperability. Celery's support for pickle serialization is universally regarded as a security anti-pattern.

2. **Timestamps MUST include timezone.** All timestamp values MUST be ISO 8601 / RFC 3339 strings with an explicit timezone designator. UTC with the `Z` suffix is RECOMMENDED (e.g., `"2026-02-12T10:30:00Z"`). Timestamps without timezone designators MUST be rejected.

   > *Rationale*: Timestamps without timezone information are ambiguous in distributed systems. A job scheduled at "2026-03-15T09:00:00" could mean different times in different data centers. Requiring the timezone eliminates this class of bugs entirely.

3. **Job IDs MUST be unique.** Two distinct jobs MUST NOT have the same `id` value. UUIDv7 generation ensures this with extremely high probability without requiring coordination between distributed clients.

   > *Rationale*: Job ID uniqueness is the foundation of job tracking, deduplication, and idempotent processing. UUIDv7's time-ordered structure additionally enables efficient range queries and chronological ordering.

4. **Unknown attributes MUST be preserved.** Implementations MUST preserve any attributes not defined by this specification when storing and returning job data. Implementations MUST NOT reject a job envelope because it contains unknown attributes.

   > *Rationale*: Forward compatibility requires that older implementations can handle jobs created by newer clients that may include attributes from a future spec version or from extension specifications.

---

## 6. Job Lifecycle State Machine

Every job progresses through a well-defined set of lifecycle states. The state machine captures all valid states and the transitions between them.

Implementations MUST enforce the state machine. An attempt to perform an invalid state transition MUST be rejected with an error.

> *Rationale*: An explicit, enforced state machine prevents impossible job states (e.g., a job that is simultaneously active and completed), enables reliable monitoring and alerting, and provides a common language for discussing job behavior across implementations. The state machine is informed by Oban's seven-state model (the most mature in production), with River's `pending` state added for staged job activation.

### 6.1 States

The lifecycle defines exactly **eight** states:

| State | Description | Terminal? |
|-------|-------------|-----------|
| `scheduled` | The job has a future `scheduled_at` time and is waiting for that time to arrive. The implementation is responsible for transitioning the job to `available` when the time arrives. | No |
| `available` | The job is ready for pickup by a worker. It is in a queue and can be fetched. | No |
| `pending` | The job is staged and awaiting external activation. It will not be made available to workers until explicitly activated. This state supports patterns where jobs must be confirmed or approved before execution. | No |
| `active` | The job has been claimed by a worker and is currently being executed. | No |
| `completed` | The job handler executed successfully. This is a **terminal state**. | **Yes** |
| `retryable` | The job handler failed, but the job has remaining retry attempts and will be retried after a backoff delay. | No |
| `cancelled` | The job was intentionally stopped via a CANCEL operation. This is a **terminal state** in v1.0. | **Yes** |
| `discarded` | The job permanently failed (retry attempts exhausted) or was manually discarded. The job is in the dead letter queue. This is a **terminal state**. | **Yes** |

> *Rationale for exactly eight states*: Fewer states (like Sidekiq's five) conflate important distinctions -- there is no way to distinguish "failed and will retry" from "failed permanently." More states add complexity without clear benefit. The eight-state model is the synthesis of Oban's seven states plus River's `pending` state, covering all real-world job lifecycle scenarios observed across 12 production systems.

> *Rationale for three terminal states*: `completed` and `discarded` are the "natural" terminal states (success and permanent failure). `cancelled` is the "intentional" terminal state. In v1.0, cancelled jobs cannot be recovered; future versions MAY define a transition from `cancelled` to `available` for recovery scenarios.

### 6.2 State Diagram

```
                                    ┌─────────────────────┐
                                    │       PUSH          │
                                    │   (enqueue a job)   │
                                    └──────────┬──────────┘
                                               │
                         ┌─────────────────────┼─────────────────────┐
                         │                     │                     │
                         ▼                     ▼                     ▼
                  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
                  │  scheduled  │      │  available  │      │   pending   │
                  │             │      │             │      │             │
                  │ (future     │      │ (ready for  │      │ (staged,    │
                  │  execution) │      │  pickup)    │      │  awaiting   │
                  │             │      │             │      │  activation)│
                  └──────┬──────┘      └──────┬──────┘      └──────┬──────┘
                         │                    │                     │
                         │  time arrives      │                     │ external
                         └───────────────────►│◄────────────────────┘ activation
                                              │
                                              │ worker claims
                                              ▼
                                       ┌─────────────┐
                                       │   active    │
                                       │             │
                                       │ (executing) │
                                       └──────┬──────┘
                                              │
                        ┌────────────┬────────┼────────┬─────────────┐
                        │            │        │        │             │
                        ▼            ▼        │        ▼             ▼
                 ┌───────────┐ ┌──────────┐   │  ┌──────────┐ ┌───────────┐
                 │ completed │ │retryable │   │  │cancelled │ │ discarded │
                 │           │ │          │   │  │          │ │           │
                 │ (success, │ │ (failed, │   │  │(stopped, │ │ (dead     │
                 │  terminal)│ │ will     │   │  │ terminal)│ │  letter,  │
                 └───────────┘ │ retry)   │   │  └──────────┘ │  terminal)│
                               └────┬─────┘   │               └─────┬─────┘
                                    │         │                     │
                                    │ backoff │                     │ manual
                                    │ delay   │                     │ retry
                                    │ expires │                     │ (MAY)
                                    │         │                     │
                                    │         ▼                     │
                                    │   ┌─────────────┐            │
                                    └──►│  available  │◄───────────┘
                                        └─────────────┘
```

### 6.3 Formal State Transition Table

The following table defines every valid state transition. Any transition not listed in this table is invalid and MUST be rejected by the backend. *Rationale: A closed transition set prevents undefined behavior and ensures all implementations agree on valid state flows.*

| From State | Event/Operation | To State | Side Effects | Condition |
|-----------|----------------|----------|-------------|-----------|
| *(initial)* | PUSH | `scheduled` | Set `created_at`, `enqueued_at` | `scheduled_at` is in the future |
| *(initial)* | PUSH | `available` | Set `created_at`, `enqueued_at` | `scheduled_at` is absent or in the past |
| *(initial)* | PUSH | `pending` | Set `created_at`, `enqueued_at` | `pending` flag is set |
| `scheduled` | Timer | `available` | Clear scheduling metadata | `scheduled_at` <= current time |
| `pending` | ACTIVATE | `available` | Record activation timestamp | External activation received |
| `available` | FETCH | `active` | Set `started_at`, increment `attempt`, start visibility timeout | Worker claims job |
| `active` | ACK | `completed` | Set `completed_at`, store `result` | Handler returned success |
| `active` | FAIL | `retryable` | Record error in `errors[]`, calculate next retry time | `attempt` < `retry_policy.max_attempts` AND error is retryable |
| `active` | FAIL | `discarded` | Record error in `errors[]`, set `discarded_at` | `attempt` >= `retry_policy.max_attempts` OR error is non-retryable |
| `active` | CANCEL | `cancelled` | Set `cancelled_at` | CANCEL operation received |
| `active` | Timeout | `available` | Clear `started_at`, record timeout error | Visibility timeout expired without ACK/FAIL |
| `retryable` | Timer | `available` | — | Backoff delay has elapsed |
| `scheduled` | CANCEL | `cancelled` | Set `cancelled_at` | CANCEL before execution |
| `available` | CANCEL | `cancelled` | Set `cancelled_at` | CANCEL before claim |
| `pending` | CANCEL | `cancelled` | Set `cancelled_at` | CANCEL before activation |
| `retryable` | CANCEL | `cancelled` | Set `cancelled_at` | CANCEL during retry wait |
| `discarded` | RETRY (manual) | `available` | Reset `attempt` to 0, clear errors | Operator-initiated manual retry (MAY support) |

> **Invariants:**
> 1. All state transitions MUST be atomic. *Rationale: Partial state changes can cause duplicate processing or lost jobs.*
> 2. Terminal states (`completed`, `cancelled`, `discarded`) MUST NOT have outgoing transitions except the optional `discarded` → `available` manual retry.
> 3. A job MUST be in exactly one state at any given time.
> 4. The `attempt` counter MUST be monotonically increasing for a given job.

### 6.4 Valid State Transitions

The following table defines every valid state transition. Any transition not listed here is **invalid** and MUST be rejected.

| From State | To State | Trigger | Description |
|------------|----------|---------|-------------|
| *(initial)* | `scheduled` | PUSH with `scheduled_at` in the future | Job is created with a future execution time. |
| *(initial)* | `available` | PUSH without `scheduled_at` (or `scheduled_at` in the past) | Job is immediately available for execution. |
| *(initial)* | `pending` | PUSH with pending flag | Job is staged, awaiting external activation. |
| `scheduled` | `available` | Scheduled time arrives | The implementation's scheduler transitions the job when `scheduled_at` <= now. |
| `available` | `active` | FETCH (worker claims job) | A worker successfully claims the job for execution. |
| `pending` | `available` | External activation | An external process or API call activates the pending job. |
| `active` | `completed` | ACK (handler succeeded) | The handler returned successfully. |
| `active` | `retryable` | FAIL (handler failed, retries remain) | The handler failed and the retry policy permits another attempt. |
| `active` | `cancelled` | CANCEL (while executing) | The job was cancelled during execution. |
| `active` | `discarded` | FAIL (handler failed, no retries remain) | The handler failed and the retry policy is exhausted. The job moves to the dead letter queue. |
| `retryable` | `available` | Backoff delay expires | The retry backoff period has elapsed. The job is returned to the queue. |
| `discarded` | `available` | Manual retry from dead letter | An operator manually retries a discarded job. Implementation MAY support this transition. |

#### Invalid Transitions (examples)

The following transitions are explicitly **invalid** and MUST be rejected:

- `available` -> `completed` (a job cannot complete without being executed)
- `completed` -> any state (terminal states have no outgoing transitions)
- `discarded` -> `active` (a discarded job cannot be directly executed; it must go through `available` first)
- `cancelled` -> any state (in v1.0, cancellation is terminal)
- `scheduled` -> `active` (a scheduled job must pass through `available`)
- `retryable` -> `active` (a retryable job must pass through `available`)

### 6.5 Transition Semantics

1. **State transitions MUST be atomic.** An implementation MUST ensure that a state transition either fully completes or does not occur at all. Partial transitions (where the state changes but associated data updates fail) MUST NOT be possible.

   > *Rationale*: Atomicity prevents split-brain scenarios where a job's state is inconsistent with its data. BullMQ achieves atomicity through Redis Lua scripts; Oban and River achieve it through PostgreSQL transactions with `SELECT FOR UPDATE SKIP LOCKED`. Both approaches are valid as long as atomicity is guaranteed.

2. **Only one worker MUST claim a job.** When a job transitions from `available` to `active`, the implementation MUST ensure that exactly one worker successfully claims the job. Concurrent claim attempts by multiple workers MUST result in exactly one success and all others failing gracefully.

   > *Rationale*: This is the fundamental at-most-once-delivery guarantee for job execution. Without exclusive claiming, jobs may be executed multiple times, causing data corruption or duplicate side effects.

3. **Terminal states are permanent.** Once a job reaches `completed` or `discarded`, no further automatic transitions MUST occur. The only exception is the optional `discarded` -> `available` transition for manual retry from the dead letter queue, which implementations MAY support.

   > *Rationale*: Permanent terminal states provide a clear contract for clients polling for job status: once a job is `completed`, it will never change state again. This simplifies client logic and prevents race conditions.

4. **The `cancelled` state is terminal in v1.0.** A cancelled job MUST NOT transition to any other state. Future versions of this specification MAY define recovery transitions from `cancelled`.

   > *Rationale*: Keeping cancellation terminal in v1.0 simplifies the state machine and avoids complex questions about what happens to a partially-executed cancelled job. Implementations that need cancellation recovery can propose an RFC for v1.1.

5. **Visibility timeout.** When a job transitions to `active`, the implementation SHOULD associate a visibility timeout (reservation period). If the worker does not ACK or FAIL the job within this period, the implementation SHOULD transition the job back to `available` (via a reaper process). This prevents job loss when workers crash.

   > *Rationale*: Faktory defaults to 1800 seconds; SQS defaults to 30 seconds. The specific duration is implementation-defined, but the mechanism is critical for reliability. Without visibility timeouts, a crashed worker causes jobs to be lost forever.

---

## 7. Logical Operations

This section defines the abstract operations that implementations MUST support. These operations are protocol-agnostic -- they define *what* can be done, not *how*. Protocol bindings (HTTP, gRPC, etc.) define how each operation maps to concrete wire interactions.

### 7.1 PUSH

**Purpose**: Enqueue one or more jobs for asynchronous processing.

**Preconditions**: The job envelope MUST contain all required attributes (`specversion`, `id`, `type`, `queue`, `args`). The `id` MUST be unique.

**Behavior**:

1. The implementation MUST validate the job envelope against the constraints defined in Section 5.
2. If `scheduled_at` is set and is in the future, the job MUST enter the `scheduled` state.
3. If `scheduled_at` is not set (or is in the past), the job MUST enter the `available` state.
4. If the pending flag is set (mechanism defined by protocol bindings), the job MUST enter the `pending` state.
5. The implementation MUST set all system-managed attributes (`state`, `attempt`, `created_at`, `enqueued_at`).
6. If a `unique` policy is provided, the implementation MUST enforce uniqueness as defined in [ojs-unique-jobs.md](./ojs-unique-jobs.md).
7. If a `schema` is provided and the implementation supports schema validation, the implementation MUST validate `args` against the referenced schema.
8. Enqueue middleware (see [ojs-middleware.md](./ojs-middleware.md)) MUST be executed before the job is persisted.
9. The implementation MUST return the complete job envelope including all system-managed attributes.

**Batch variant**: Implementations SHOULD support a batch PUSH operation that enqueues multiple jobs atomically. If batch PUSH is supported, either all jobs in the batch MUST be enqueued or none.

> *Rationale*: PUSH is the most common operation and must be fast and reliable. Validation at enqueue time (rather than execution time) catches errors early, when the caller can still handle them. Faktory's `PUSH` command and Sidekiq's `push` method are the models for this operation.

### 7.2 FETCH

**Purpose**: Dequeue one or more jobs for processing by a worker.

**Preconditions**: The worker MUST specify one or more queue names from which to fetch jobs.

**Behavior**:

1. The implementation MUST select the highest-priority available job from the specified queues. If multiple queues are specified, the implementation MUST check queues in the order provided (left-to-right priority).
2. The selected job MUST transition from `available` to `active` atomically. The claim MUST be exclusive -- no other worker can claim the same job.
3. The implementation MUST set `started_at` to the current time and increment `attempt` by 1.
4. The implementation SHOULD associate a visibility timeout with the claimed job.
5. If no jobs are available, the implementation MAY block for a short period (RECOMMENDED: up to 2 seconds) before returning an empty result. This reduces polling overhead.
6. The implementation MUST return the complete job envelope for each fetched job.

**Multi-fetch**: Implementations MAY support fetching multiple jobs in a single operation by accepting a `count` parameter.

> *Rationale*: FETCH must be atomic to prevent duplicate execution. The short blocking behavior on empty queues is borrowed from Faktory, which blocks for 2 seconds -- a smart optimization that reduces polling overhead while remaining responsive. Queue ordering (left-to-right priority) follows BullMQ's convention and allows workers to express queue preference.

### 7.3 ACK

**Purpose**: Acknowledge successful completion of a job.

**Preconditions**: The job MUST be in the `active` state. The caller MUST be the worker that claimed the job.

**Behavior**:

1. The job MUST transition from `active` to `completed`.
2. The implementation MUST set `completed_at` to the current time.
3. If a result value is provided, the implementation MUST store it in the `result` attribute.
4. The implementation SHOULD clear the `error` attribute if it was set from a previous failed attempt.
5. The transition MUST be atomic.

> *Rationale*: ACK is the happy path. Keeping it simple (job ID + optional result) minimizes overhead. The pattern is universal across Faktory (`ACK`), BullMQ (`moveToCompleted`), SQS (`DeleteMessage`), and every other surveyed system.

### 7.4 FAIL

**Purpose**: Report that a job execution failed.

**Preconditions**: The job MUST be in the `active` state.

**Behavior**:

1. The caller MUST provide a structured error object (see [Section 8](#8-error-reporting)).
2. The implementation MUST store the error in the job's `error` attribute.
3. The implementation MUST evaluate the job's retry policy:
   - If retries remain and the error is retryable, the job MUST transition to `retryable`.
   - If retries are exhausted or the error is non-retryable, the job MUST transition to `discarded`.
4. If the job transitions to `retryable`, the implementation MUST calculate the next retry time based on the retry policy (see [ojs-retry.md](./ojs-retry.md)) and transition the job to `available` when the backoff delay expires.
5. If the job transitions to `discarded`, the job enters the dead letter queue.
6. The transition MUST be atomic.

> *Rationale*: Structured error reporting (rather than a simple error string) enables debugging across language boundaries. Faktory's `FAIL` command with `{jid, errtype, message, backtrace}` is the model. The implementation decides the next state based on the retry policy, keeping the decision server-side (per Design Principle 6).

### 7.5 BEAT

**Purpose**: Worker heartbeat -- the worker reports that it is alive and receives directives from the server.

**Preconditions**: The worker MUST be registered with the backend.

**Behavior**:

1. The worker MUST send a heartbeat at regular intervals (RECOMMENDED: every 15 seconds).
2. The implementation MUST update the worker's last-seen timestamp.
3. The implementation MAY respond with a directive to change the worker's lifecycle state:
   - `"running"` -- continue normal operation.
   - `"quiet"` -- stop fetching new jobs, but finish currently active jobs.
   - `"terminate"` -- stop fetching new jobs and shut down after active jobs complete (or after a grace period).
4. If a worker misses heartbeats for a configurable period (RECOMMENDED: 3 missed heartbeats), the implementation SHOULD consider the worker dead and requeue its active jobs.

See [ojs-worker-protocol.md](./ojs-worker-protocol.md) for the complete worker lifecycle specification.

> *Rationale*: The heartbeat mechanism is borrowed from Faktory and Sidekiq. Server-initiated state changes via heartbeat responses enable graceful deployment (send `quiet` before deploying new code, then `terminate` after the new version is ready). Without heartbeats, crashed workers leave jobs in `active` state permanently, requiring manual intervention.

### 7.6 CANCEL

**Purpose**: Cancel a job that has not yet completed.

**Preconditions**: The job MUST be in a non-terminal state.

**Behavior**:

1. If the job is in `scheduled`, `available`, or `pending` state, the implementation MUST transition it to `cancelled`.
2. If the job is in `active` state, the implementation MUST transition it to `cancelled`. The implementation SHOULD notify the executing worker that the job has been cancelled (via the next BEAT response or an out-of-band mechanism). The worker SHOULD stop executing the job.
3. If the job is in `retryable` state, the implementation MUST transition it to `cancelled`.
4. If the job is already in a terminal state (`completed`, `discarded`, `cancelled`), the operation MUST be idempotent -- cancelling an already-cancelled job MUST succeed without error.

> *Rationale*: Cancellation is an operational necessity for runaway jobs, incorrect job submissions, and deployment scenarios. The idempotency requirement prevents race conditions where multiple cancellation requests arrive for the same job.

### 7.7 INFO

**Purpose**: Retrieve the current state and full envelope of a job.

**Preconditions**: A valid job ID MUST be provided.

**Behavior**:

1. The implementation MUST return the complete job envelope including all system-managed attributes.
2. If the job does not exist, the implementation MUST indicate that the job was not found.
3. The INFO operation MUST NOT modify the job's state.

> *Rationale*: INFO enables monitoring, dashboards, and client-side polling for job completion. It is a read-only operation with no side effects.

---

## 8. Error Reporting

When a job fails, the error MUST be reported as a structured object. This enables debugging across language boundaries, automated classification of failures, and meaningful error display in dashboards.

### 8.1 Error Object Structure

```
{
  "type":      string,   // REQUIRED. Error type/class name.
  "message":   string,   // REQUIRED. Human-readable error description.
  "backtrace": [string]  // OPTIONAL. Stack trace as an array of frame strings.
}
```

#### `type`

- **Type**: `string`
- **Description**: The error type or class name. This SHOULD be the language-specific exception class name (e.g., `"RuntimeError"`, `"NullPointerException"`, `"TypeError"`) or a domain-specific error code (e.g., `"SmtpConnectionRefused"`).
- **Rationale**: Structured error types enable pattern matching on errors (e.g., "retry on `ConnectionError`, discard on `ValidationError`") without parsing error messages.

#### `message`

- **Type**: `string`
- **Description**: A human-readable description of the error. This SHOULD be the exception message or a descriptive string.

#### `backtrace`

- **Type**: `array` of `string`
- **Description**: The stack trace at the point of failure, represented as an array of frame strings. Each string represents one stack frame. The format is language-specific but SHOULD be human-readable.
- **Constraints**: Implementations SHOULD limit the backtrace to a reasonable size (RECOMMENDED: at most 50 frames, at most 10,000 total characters). Implementations MAY truncate the backtrace if it exceeds size limits.
- **Rationale**: Stack traces are essential for debugging. Limiting the size prevents a single failing job from consuming excessive storage. The array-of-strings format (borrowed from Faktory) is more structured than a single multiline string, enabling display truncation and filtering by frame.

### 8.2 Error Example

```json
{
  "type": "SmtpConnectionError",
  "message": "Connection refused to smtp.example.com:587 after 30s timeout",
  "backtrace": [
    "at SmtpClient.connect (smtp.js:42:15)",
    "at EmailSender.send (email_sender.js:18:22)",
    "at handler (handlers/email.send.js:7:10)"
  ]
}
```

### 8.3 Error Conventions

1. Implementations MUST accept the error object on FAIL operations.
2. Implementations MUST store the error object in the job's `error` attribute.
3. Implementations SHOULD preserve error history (all errors across attempts), but the `error` attribute on the job envelope contains only the most recent error. Implementations MAY provide access to error history through an extension mechanism.
4. Error types listed in the retry policy's `non_retryable_errors` (see [ojs-retry.md](./ojs-retry.md)) MUST cause the job to transition directly to `discarded`, bypassing retry.

---

## 9. Middleware

Middleware is a first-class concept in OJS. The specification defines two middleware chains:

- **Enqueue middleware**: Runs before a job is persisted during a PUSH operation. Can modify the job envelope, inject metadata, validate arguments, or prevent enqueueing entirely.
- **Execution middleware**: Wraps job execution on the worker side. Enables logging, metrics, error handling, context propagation, and other cross-cutting concerns.

Middleware chains are ordered and composable. Each middleware function receives the job context and a `next` function that invokes the next middleware in the chain (or the terminal operation).

The middleware interface, chain management (add, remove, insert_before, insert_after), and detailed semantics are defined in [ojs-middleware.md](./ojs-middleware.md).

> *Rationale*: Sidekiq's client/server middleware chains -- inspired by Rack middleware -- are arguably its best design decision and have been adopted by every major job system in some form. Making middleware a first-class specification concept (rather than an implementation detail) ensures that cross-cutting concerns like distributed tracing propagation work consistently across all OJS implementations.

---

## 10. Worker Lifecycle

Workers have three lifecycle states:

| State | Description |
|-------|-------------|
| `running` | Normal operation. The worker fetches and executes jobs. |
| `quiet` | The worker stops fetching new jobs but continues executing jobs already claimed. This state is used during graceful deployment: new code is deployed while existing jobs finish. |
| `terminate` | The worker stops fetching new jobs and shuts down after currently active jobs complete, or after a configurable grace period (whichever comes first). Jobs that do not complete within the grace period are returned to the queue (via visibility timeout). |

Worker lifecycle state changes are communicated via the BEAT operation: the server responds to a heartbeat with a directive indicating the desired worker state.

The complete worker lifecycle specification, including registration, deregistration, heartbeat intervals, and crash recovery, is defined in [ojs-worker-protocol.md](./ojs-worker-protocol.md).

> *Rationale*: The three-state worker lifecycle model (Running -> Quiet -> Terminate) is borrowed from Faktory and Sidekiq. It is the minimum viable model for zero-downtime deployments: send `quiet` to all workers before deploying, deploy new code, start new workers, then `terminate` old workers. Without this model, deployments either drop jobs or require complex coordination.

---

## 11. Extension Points

The OJS Core Specification is intentionally minimal. The following areas are defined as extension points, with companion specifications providing the details:

### 11.1 Retry Policies

The `retry` attribute on the job envelope references a retry policy object. The structure, backoff algorithms (exponential, linear, polynomial, custom), jitter, and non-retryable error classification are defined in [ojs-retry.md](./ojs-retry.md).

### 11.2 Unique Jobs / Deduplication

The `unique` attribute on the job envelope references a uniqueness policy. Uniqueness dimensions (type, queue, args, period, states), key selection within args, and conflict resolution strategies (reject, replace, ignore) are defined in [ojs-unique-jobs.md](./ojs-unique-jobs.md).

### 11.3 Workflows

Workflow primitives (chain, group, batch) for composing jobs into sequential, parallel, and fan-out/fan-in patterns are defined in [ojs-workflows.md](./ojs-workflows.md). Full DAG support is deferred to a future version.

### 11.4 Cron / Periodic Jobs

Registration and management of recurring jobs using cron expressions, timezone handling, and overlap prevention are defined in [ojs-cron.md](./ojs-cron.md).

### 11.5 Lifecycle Events

The standard event vocabulary for job lifecycle events (enqueued, started, completed, failed, retrying, discarded, cancelled) and the event envelope format are defined in [ojs-events.md](./ojs-events.md).

### 11.6 Custom Attributes via `meta`

The `meta` object on the job envelope is the primary extension mechanism for user-defined attributes. Implementations MUST preserve all keys in `meta` without modification. This enables:

- Trace context propagation (W3C Trace Context headers stored in `meta`)
- Multi-tenant routing (`tenant_id` in `meta`)
- Locale-aware processing (`locale` in `meta`)
- Business-level correlation (`correlation_id` in `meta`)
- Arbitrary user-defined metadata

### 11.7 Rate Limiting and Concurrency Control

Server-side rate limiting, concurrency limits, and throttling are defined in [ojs-rate-limiting.md](./ojs-rate-limiting.md). This is an official extension (see Section 11.9) that implementations MAY opt into.

### 11.8 Admin / Operator API

The control-plane API for queue management, job inspection, bulk operations, worker management, and system-level operations is defined in [ojs-admin-api.md](./ojs-admin-api.md). This is an official extension that implementations MAY opt into.

### 11.9 Extension Lifecycle

OJS uses a three-tier extension model (core, official, experimental) that governs how features are categorized, how implementations declare support, and how features progress from community proposals to stable requirements. The full model, promotion criteria, and manifest declaration format are defined in [ojs-extension-lifecycle.md](./ojs-extension-lifecycle.md). Additional official and experimental extensions include:

**Official extensions** (opt-in, stable):

- **Testing**: Fake, inline, and real testing modes with standard assertion helpers ([ojs-testing.md](./ojs-testing.md)).
- **Observability**: OpenTelemetry semantic conventions, span names, metrics, and trace context propagation ([ojs-observability.md](./ojs-observability.md)).
- **Backpressure**: Bounded queue semantics and enqueue-side pressure control ([ojs-backpressure.md](./ojs-backpressure.md)).
- **Graceful shutdown**: Signal handling, drain semantics, and container orchestrator integration ([ojs-graceful-shutdown.md](./ojs-graceful-shutdown.md)).
- **Dead letter**: DLQ retention, pruning, manual retry, and automatic replay ([ojs-dead-letter.md](./ojs-dead-letter.md)).

**Experimental extensions** (opt-in, may change):

- **Job versioning**: Schema evolution, version routing, and canary deployments ([ojs-job-versioning.md](./ojs-job-versioning.md)).
- **Multi-tenancy**: Tenant isolation, fairness scheduling, and per-tenant resource limits ([ojs-multi-tenancy.md](./ojs-multi-tenancy.md)).
- **Encryption**: Client-side encryption via codec architecture and Codec Server ([ojs-encryption.md](./ojs-encryption.md)).
- **Framework adapters**: Transactional enqueue and the outbox pattern for framework integration ([ojs-framework-adapters.md](./ojs-framework-adapters.md)).

### 11.10 Backend-Specific Extensions

Implementations MAY define backend-specific attributes and behaviors beyond what this specification requires, provided they:

1. Do not conflict with any attribute defined in this specification.
2. Use a namespaced prefix for any additional attributes (e.g., `x_redis_stream_id`, `x_pg_advisory_lock`).
3. Document all extensions clearly.
4. Ensure that a job created without extensions can still be processed by a conforming implementation.

---

## 12. Prior Art

This specification synthesizes design decisions from the following systems. Where a specific design choice was borrowed, the source is noted.

| System | Language | Key Ideas Incorporated into OJS |
|--------|----------|---------------------------------|
| **Sidekiq** | Ruby | `args` as array of simple JSON types (Section 5.1). Middleware chains as first-class concept (Section 9). Default queue named `"default"` (Section 5.1). Convention of 1-indexed attempt numbers. Sensible defaults philosophy. |
| **Faktory** | Polyglot | Language-agnostic worker protocol with PUSH/FETCH/ACK/FAIL/BEAT operations (Section 7). Structured error format with `{errtype, message, backtrace}` (Section 8). Server-side intelligence / client simplicity principle. Worker heartbeat with server-initiated state changes. Visibility timeout / reservation. |
| **Oban** | Elixir | Seven-state lifecycle model (Section 6). Unique job dimensions (ojs-unique-jobs.md). Structured pruning / job retention. The concept that only `completed` and `discarded` are true terminal states. |
| **River** | Go | `pending` state for staged job activation (Section 6.1). PostgreSQL `SELECT FOR UPDATE SKIP LOCKED` pattern. Clean API design with explicit state transitions. |
| **BullMQ** | JavaScript | Queue priority ordering (left-to-right in FETCH). Flow/dependency support patterns. Real-time event streaming. Non-blocking dequeue patterns. |
| **Celery** | Python | Task routing concepts. Workflow primitives (chain, group, chord). Backoff and jitter for retries. |
| **Temporal** | Polyglot | Structured retry policy format (`max_attempts`, `initial_interval`, `backoff_coefficient`, `max_interval`, `non_retryable_errors`). See ojs-retry.md. |
| **Taskiq** | Python | Extensible metadata (`labels` / `meta`). Clean broker/result backend separation. Explicit middleware pipeline with named hooks. |
| **Asynq** | Go | Dual uniqueness mechanisms (deterministic ID + TTL lock). ServeMux-style middleware. |
| **CloudEvents** | Spec | Three-tier architecture (core spec / wire formats / protocol bindings). `specversion` as a required attribute. Minimal required attribute set. Forward-compatible attribute preservation. |
| **OpenTelemetry** | Spec | Vendor-neutral observability patterns. Trace context propagation via metadata. Layered architecture. |

---

## 13. Examples

The following examples demonstrate complete, valid job envelopes. All examples conform to this specification and are intended to be copy-pasteable.

### 13.1 Minimal Job

The simplest possible valid job envelope, with only required attributes:

```json
{
  "specversion": "1.0.0-rc.1",
  "id": "019461a8-1a2b-7c3d-8e4f-5a6b7c8d9e0f",
  "type": "email.send",
  "queue": "default",
  "args": ["user@example.com", "welcome"]
}
```

After enqueueing, the implementation returns the full envelope with system-managed attributes:

```json
{
  "specversion": "1.0.0-rc.1",
  "id": "019461a8-1a2b-7c3d-8e4f-5a6b7c8d9e0f",
  "type": "email.send",
  "queue": "default",
  "args": ["user@example.com", "welcome"],
  "meta": {},
  "priority": 0,
  "state": "available",
  "attempt": 0,
  "created_at": "2026-02-12T10:30:00.000Z",
  "enqueued_at": "2026-02-12T10:30:00.000Z"
}
```

### 13.2 Full Job with All Optional Attributes

A job that uses every optional attribute:

```json
{
  "specversion": "1.0.0-rc.1",
  "id": "019461a8-2b3c-7d4e-9f50-6a7b8c9d0e1f",
  "type": "report.generate",
  "queue": "reports",
  "args": [42, "quarterly", {"include_charts": true}],
  "meta": {
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "span_id": "00f067aa0ba902b7",
    "user_id": "usr_12345",
    "tenant_id": "tenant_acme",
    "locale": "en-US",
    "correlation_id": "corr_report_q4_2026",
    "tags": ["quarterly", "finance", "high-priority"]
  },
  "priority": 10,
  "timeout": 300,
  "scheduled_at": "2026-03-01T09:00:00Z",
  "expires_at": "2026-03-01T18:00:00Z",
  "retry": {
    "max_attempts": 5,
    "initial_interval": "1s",
    "backoff_coefficient": 2.0,
    "max_interval": "300s",
    "jitter": true,
    "non_retryable_errors": ["ValidationError", "AuthenticationError"]
  },
  "unique": {
    "key": ["report_id"],
    "period": "3600s",
    "on_conflict": "reject"
  },
  "schema": "urn:ojs:schema:report.generate:v2"
}
```

After enqueueing (note: `scheduled_at` is in the future, so state is `scheduled`):

```json
{
  "specversion": "1.0.0-rc.1",
  "id": "019461a8-2b3c-7d4e-9f50-6a7b8c9d0e1f",
  "type": "report.generate",
  "queue": "reports",
  "args": [42, "quarterly", {"include_charts": true}],
  "meta": {
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "span_id": "00f067aa0ba902b7",
    "user_id": "usr_12345",
    "tenant_id": "tenant_acme",
    "locale": "en-US",
    "correlation_id": "corr_report_q4_2026",
    "tags": ["quarterly", "finance", "high-priority"]
  },
  "priority": 10,
  "timeout": 300,
  "scheduled_at": "2026-03-01T09:00:00Z",
  "expires_at": "2026-03-01T18:00:00Z",
  "retry": {
    "max_attempts": 5,
    "initial_interval": "1s",
    "backoff_coefficient": 2.0,
    "max_interval": "300s",
    "jitter": true,
    "non_retryable_errors": ["ValidationError", "AuthenticationError"]
  },
  "unique": {
    "key": ["report_id"],
    "period": "3600s",
    "on_conflict": "reject"
  },
  "schema": "urn:ojs:schema:report.generate:v2",
  "state": "scheduled",
  "attempt": 0,
  "created_at": "2026-02-12T10:30:00.000Z"
}
```

### 13.3 Job After Successful Completion

A job that has been executed and completed:

```json
{
  "specversion": "1.0.0-rc.1",
  "id": "019461a8-3c4d-7e5f-a061-7b8c9d0e1f2a",
  "type": "email.send",
  "queue": "email",
  "args": ["user@example.com", "welcome"],
  "meta": {
    "trace_id": "abc123def456",
    "user_id": "usr_67890"
  },
  "priority": 0,
  "timeout": 30,
  "state": "completed",
  "attempt": 1,
  "created_at": "2026-02-12T10:30:00.000Z",
  "enqueued_at": "2026-02-12T10:30:00.000Z",
  "started_at": "2026-02-12T10:30:01.456Z",
  "completed_at": "2026-02-12T10:30:02.789Z",
  "result": {
    "message_id": "msg_abc123",
    "delivered": true
  }
}
```

### 13.4 Job After Failure (Retryable)

A job that failed on its second attempt and is waiting to retry:

```json
{
  "specversion": "1.0.0-rc.1",
  "id": "019461a8-4d5e-7f60-b172-8c9d0e1f2a3b",
  "type": "data.sync",
  "queue": "default",
  "args": ["source_db", "target_db", {"table": "users"}],
  "meta": {},
  "priority": 0,
  "timeout": 600,
  "retry": {
    "max_attempts": 5,
    "initial_interval": "1s",
    "backoff_coefficient": 2.0,
    "max_interval": "300s",
    "jitter": true
  },
  "state": "retryable",
  "attempt": 2,
  "created_at": "2026-02-12T10:00:00.000Z",
  "enqueued_at": "2026-02-12T10:00:00.000Z",
  "started_at": "2026-02-12T10:01:00.000Z",
  "error": {
    "type": "ConnectionError",
    "message": "Connection to target_db timed out after 60s",
    "backtrace": [
      "at DbClient.connect (db_client.go:142)",
      "at SyncHandler.Execute (handlers/data_sync.go:38)",
      "at Worker.executeJob (worker.go:201)"
    ]
  }
}
```

### 13.5 Job in the Dead Letter Queue (Discarded)

A job that exhausted all retry attempts:

```json
{
  "specversion": "1.0.0-rc.1",
  "id": "019461a8-5e6f-7071-c283-9d0e1f2a3b4c",
  "type": "payment.process",
  "queue": "payments",
  "args": [{"order_id": "ord_98765", "amount": 49.99, "currency": "USD"}],
  "meta": {
    "user_id": "usr_11111",
    "correlation_id": "checkout_sess_xyz"
  },
  "priority": 10,
  "timeout": 60,
  "retry": {
    "max_attempts": 3
  },
  "state": "discarded",
  "attempt": 3,
  "created_at": "2026-02-12T08:00:00.000Z",
  "enqueued_at": "2026-02-12T08:00:00.000Z",
  "started_at": "2026-02-12T08:05:12.000Z",
  "completed_at": "2026-02-12T08:05:13.500Z",
  "error": {
    "type": "PaymentGatewayError",
    "message": "Payment gateway returned HTTP 503: Service Unavailable",
    "backtrace": [
      "at PaymentClient.charge (payment_client.py:89)",
      "at process_payment (handlers/payment.py:23)",
      "at Worker.run_handler (worker.py:156)"
    ]
  }
}
```

### 13.6 Scheduled Job

A job set to execute at a future time:

```json
{
  "specversion": "1.0.0-rc.1",
  "id": "019461a8-6f70-7182-d394-0e1f2a3b4c5d",
  "type": "notification.send_digest",
  "queue": "notifications",
  "args": ["usr_22222", "weekly"],
  "meta": {
    "locale": "fr-FR"
  },
  "priority": -10,
  "scheduled_at": "2026-02-17T08:00:00+01:00"
}
```

After enqueueing:

```json
{
  "specversion": "1.0.0-rc.1",
  "id": "019461a8-6f70-7182-d394-0e1f2a3b4c5d",
  "type": "notification.send_digest",
  "queue": "notifications",
  "args": ["usr_22222", "weekly"],
  "meta": {
    "locale": "fr-FR"
  },
  "priority": -10,
  "scheduled_at": "2026-02-17T08:00:00+01:00",
  "state": "scheduled",
  "attempt": 0,
  "created_at": "2026-02-12T10:30:00.000Z"
}
```

### 13.7 FAIL Operation Example

When a worker reports a failure:

```
FAIL {
  job_id: "019461a8-4d5e-7f60-b172-8c9d0e1f2a3b",
  error: {
    "type": "SmtpConnectionError",
    "message": "Connection refused to smtp.example.com:587 after 30s timeout",
    "backtrace": [
      "at SmtpClient.connect (smtp.js:42:15)",
      "at EmailSender.send (email_sender.js:18:22)",
      "at handler (handlers/email.send.js:7:10)"
    ]
  }
}
```

The implementation evaluates the retry policy and transitions the job to either `retryable` (if attempts remain) or `discarded` (if exhausted).

---

## 14. Security Considerations

1. **Argument sanitization.** Implementations MUST NOT execute job arguments as code. Arguments are data, not instructions. Language-specific serialization formats (Python pickle, Ruby Marshal, Java serialization) MUST NOT be used for job arguments, as they enable remote code execution attacks.

2. **Backtrace exposure.** Stack traces in error objects may contain sensitive information (file paths, internal service names, database connection strings). Implementations SHOULD provide a configuration option to redact or omit backtraces in production environments.

3. **Meta field injection.** The `meta` object is writable by clients. Implementations MUST NOT trust `meta` values for authorization or access control decisions without independent validation.

4. **Job size limits.** Implementations SHOULD enforce maximum job envelope size to prevent denial-of-service through excessively large arguments or metadata. A RECOMMENDED maximum is 1 MiB per job envelope.

5. **Authentication and authorization.** This specification does not define authentication or authorization mechanisms. These concerns are addressed at the protocol binding layer (see [ojs-http-binding.md](./ojs-http-binding.md)) and are implementation-specific.

---

## 15. Acknowledgments

The Open Job Spec is informed by the design, documentation, and operational experience of the following open-source projects and their communities: Sidekiq (Mike Perham), Faktory (Mike Perham), Oban (Parker Selbert), River (Brandur Leach), BullMQ (Manast), Celery (Ask Solem), Temporal (Maxim Fateev, Samar Abbas), Taskiq, Asynq, Graphile Worker, Inngest, and Machinery.

The three-tier specification architecture is directly inspired by the CloudEvents specification (CNCF).

---

*Open Job Spec v1.0.0-rc.1 -- Release Candidate -- February 2026*
*https://openjobspec.org*
*Licensed under Apache 2.0*
