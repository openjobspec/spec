# Open Job Spec — Glossary

| Field       | Value                                                  |
|-------------|--------------------------------------------------------|
| **Title**   | OJS Glossary                                           |
| **Version** | 1.0.0-rc.1                                             |
| **Date**    | 2026-02-15                                             |
| **Status**  | Release Candidate 1                                    |
| **URI**     | `urn:ojs:spec:glossary`                                |

---

## Table of Contents

- [1. Introduction](#1-introduction)
- [2. Notational Conventions](#2-notational-conventions)
- [3. Core Concepts](#3-core-concepts)
- [4. Lifecycle & State](#4-lifecycle--state)
- [5. Reliability](#5-reliability)
- [6. Scheduling & Shutdown](#6-scheduling--shutdown)
- [7. Observability](#7-observability)
- [8. Rate Limiting & Backpressure](#8-rate-limiting--backpressure)
- [9. Worker Protocol](#9-worker-protocol)
- [10. Multi-Tenancy](#10-multi-tenancy)
- [11. Encryption & Codecs](#11-encryption--codecs)
- [12. Framework Integration](#12-framework-integration)
- [13. Versioning](#13-versioning)
- [14. Testing](#14-testing)
- [15. Middleware](#15-middleware)
- [16. Admin & Operations](#16-admin--operations)
- [17. Extension System](#17-extension-system)
- [18. Workflow](#18-workflow)
- [19. Wire Format & Protocol](#19-wire-format--protocol)

---

## 1. Introduction

This document is the **canonical glossary** for the Open Job Spec (OJS). It
serves as the single source of truth for all terminology used across the 24 OJS
specification documents. Individual spec documents MAY define terms inline for
convenience, but such definitions MUST be consistent with this glossary. In the
event of a conflict, this glossary takes precedence.

Terms are organized alphabetically within thematic categories. Each entry
provides the term, a concise definition, and a reference to the specification
document and section where the term is authoritatively defined.

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD",
"SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be
interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

---

## 3. Core Concepts

- **Backend** — The persistent storage layer (e.g., PostgreSQL, Redis) that
  durably stores job envelopes, state, and queue metadata.
  *(Defined in: ojs-core.md, Section 3)*
- **Client** — A component that creates and enqueues jobs into a queue by
  constructing job envelopes and submitting them to a backend.
  *(Defined in: ojs-core.md, Section 3)*
- **Handler** — A user-defined function that performs the actual work for a job.
  Each job type is associated with exactly one handler.
  *(Defined in: ojs-core.md, Section 3)*
- **Job** — A discrete unit of work described by a job envelope, carrying a type
  identifier, arguments, and metadata.
  *(Defined in: ojs-core.md, Section 3)*
- **Job Envelope** — The complete data structure representing a job, including
  required attributes (type, arguments, state) and optional attributes
  (priority, queue, tags, metadata).
  *(Defined in: ojs-core.md, Section 5)*
- **Middleware** — A composable component that wraps handler execution or job
  enqueueing to add cross-cutting behavior such as logging or telemetry.
  *(Defined in: ojs-middleware.md, Section 1.3)*
- **Queue** — A named, logical channel through which jobs flow from clients to
  workers, providing ordering guarantees and isolation.
  *(Defined in: ojs-core.md, Section 3)*
- **Spec Version** — The OJS specification version to which a job envelope or
  implementation conforms.
  *(Defined in: ojs-core.md, Section 1)*
- **State Transition** — A change from one lifecycle state to another. State
  transitions MUST be atomic and follow the valid transition graph.
  *(Defined in: ojs-core.md, Section 3)*
- **Terminal State** — A lifecycle state from which no further transitions are
  permitted: `completed`, `cancelled`, or `discarded`.
  *(Defined in: ojs-core.md, Section 3)*
- **Worker** — A process that polls queues, claims available jobs, and
  dispatches them to the appropriate handler for execution.
  *(Defined in: ojs-core.md, Section 3)*

---

## 4. Lifecycle & State

OJS defines eight lifecycle states, listed here in typical progression order:

- **scheduled** — The job has a future execution time and is not yet eligible
  for processing. Transitions to `available` when its scheduled time arrives.
  *(Defined in: ojs-core.md, Section 6.1)*
- **available** — The job is eligible to be claimed by a worker and resides in
  the queue awaiting pickup.
  *(Defined in: ojs-core.md, Section 6.1)*
- **pending** — The job is accepted but awaits preconditions (e.g., dependency
  resolution) before becoming available.
  *(Defined in: ojs-core.md, Section 6.1)*
- **active** — The job has been claimed by a worker and is currently being
  executed.
  *(Defined in: ojs-core.md, Section 6.1)*
- **completed** — The handler finished successfully. Terminal state.
  *(Defined in: ojs-core.md, Section 6.1)*
- **retryable** — The job failed but is eligible for automatic retry. It will
  transition back to `available` or `scheduled` after the backoff elapses.
  *(Defined in: ojs-core.md, Section 6.1)*
- **cancelled** — The job was explicitly cancelled before completion. Terminal
  state.
  *(Defined in: ojs-core.md, Section 6.1)*
- **discarded** — The job has exhausted all retries or been permanently
  rejected. Terminal state. MAY be moved to a dead letter queue.
  *(Defined in: ojs-core.md, Section 6.1)*

---

## 5. Reliability

- **Automatic Replay** — Programmatic re-enqueuing of dead-lettered jobs in
  response to a fix or configuration change, without manual per-job action.
  *(Defined in: ojs-retry.md, Section 1.2)*
- **Dead Letter Job** — A job moved to a dead letter queue after exhausting all
  retry attempts or being explicitly discarded.
  *(Defined in: ojs-dead-letter.md, Section 3)*
- **Dead Letter Queue (DLQ)** — A special-purpose queue that receives
  permanently failed jobs for inspection, debugging, and potential
  re-processing.
  *(Defined in: ojs-dead-letter.md, Section 3)*
- **Manual Retry** — An operator-initiated action that re-enqueues a specific
  failed or dead-lettered job, typically via an admin API.
  *(Defined in: ojs-retry.md, Section 1.2)*
- **Pruning** — Removing expired or obsolete jobs from a DLQ or backend storage
  based on retention policy rules (age or count thresholds).
  *(Defined in: ojs-dead-letter.md, Section 8)*
- **Retention Policy** — Configuration governing how long dead-lettered or
  completed jobs are preserved before becoming eligible for pruning.
  *(Defined in: ojs-dead-letter.md, Section 3)*
- **Retry Policy** — Rules determining how and when a failed job is retried,
  including max attempts, backoff strategy, and jitter.
  *(Defined in: ojs-retry.md, Section 1.2)*

---

## 6. Scheduling & Shutdown

- **Cron Expression** — A string defining a recurring schedule using standard
  cron syntax, used to create periodic jobs enqueued at specified intervals.
  *(Defined in: ojs-cron.md, Section 1.2)*
- **Drain Phase** — The second shutdown phase where the worker stops accepting
  new jobs and waits for active jobs to complete within the grace period.
  *(Defined in: ojs-graceful-shutdown.md, Section 5)*
- **Force-Stop** — The action taken when the grace period expires: the worker
  terminates remaining work and releases held jobs back to the queue.
  *(Defined in: ojs-graceful-shutdown.md, Section 5.3)*
- **Grace Period** — Maximum duration a worker waits during shutdown for active
  jobs to complete before force-stopping.
  *(Defined in: ojs-graceful-shutdown.md, Section 3)*
- **Graceful Shutdown** — A controlled process where a worker stops accepting
  new work and allows in-flight jobs to complete before terminating.
  *(Defined in: ojs-graceful-shutdown.md, Section 3)*
- **Overlap Policy** — A rule governing behavior when a cron-scheduled job is
  due while a previous instance is still active (e.g., skip, enqueue,
  cancel-previous).
  *(Defined in: ojs-cron.md, Section 6.1)*
- **PID 1 Problem** — A container deployment concern where the worker runs as
  PID 1 and may not receive POSIX signals correctly, interfering with graceful
  shutdown.
  *(Defined in: ojs-graceful-shutdown.md, Section 3)*
- **Quiet Phase** — The first shutdown phase where the worker signals it will
  stop polling but continues executing already-claimed work.
  *(Defined in: ojs-graceful-shutdown.md, Section 5)*

---

## 7. Observability

- **Cardinality** — The number of distinct values a metric label or span
  attribute can take. High cardinality SHOULD be avoided.
  *(Defined in: ojs-observability.md, Section 3)*
- **Semantic Conventions** — Standardized attribute names and values for spans
  and metrics, aligned with OpenTelemetry, ensuring interoperable telemetry.
  *(Defined in: ojs-observability.md, Section 3)*
- **Span** — A named, timed operation within a trace representing a unit of work
  (e.g., enqueue, handler execution, retry attempt).
  *(Defined in: ojs-observability.md, Section 3)*
- **Span Link** — An association between causally related spans that lack a
  direct parent-child relationship, such as linking execution to enqueue.
  *(Defined in: ojs-observability.md, Section 3)*
- **Trace Context** — Propagated metadata (trace ID, span ID, trace flags)
  connecting distributed spans into a logical trace. Implementations SHOULD
  propagate W3C Trace Context through job metadata.
  *(Defined in: ojs-observability.md, Section 3)*

---

## 8. Rate Limiting & Backpressure

- **Backpressure** — A flow-control mechanism where downstream components signal
  upstream to slow down when queues approach their configured bounds.
  *(Defined in: ojs-backpressure.md, Section 3)*
- **Backpressure Action** — The behavior taken when a queue reaches its bound
  (e.g., reject, block, or drop lowest-priority jobs).
  *(Defined in: ojs-backpressure.md, Section 3)*
- **Bounded Queue** — A queue with a configured maximum capacity that applies
  its backpressure action when the bound is reached.
  *(Defined in: ojs-backpressure.md, Section 3)*
- **Concurrency Limit** — Maximum number of jobs executing simultaneously,
  scoped to a queue, worker, or global level.
  *(Defined in: ojs-rate-limiting.md, Section 3)*
- **Headroom** — Remaining capacity in a bounded queue (bound minus current
  depth), used to determine when backpressure applies.
  *(Defined in: ojs-backpressure.md, Section 3)*
- **Partition** — A logical subdivision within a rate limit scope enabling
  independent rate tracking (e.g., per-customer limits in a shared queue).
  *(Defined in: ojs-rate-limiting.md, Section 3)*
- **Queue Bound** — The configured maximum number of jobs a bounded queue may
  hold before triggering backpressure.
  *(Defined in: ojs-backpressure.md, Section 3)*
- **Queue Depth** — The current number of jobs in a queue across all non-terminal
  states, used as the primary backpressure metric.
  *(Defined in: ojs-backpressure.md, Section 3)*
- **Rate Limit** — A constraint on jobs processed or enqueued within a time
  window, expressed as count per window duration.
  *(Defined in: ojs-rate-limiting.md, Section 3)*
- **Rate Limit Key** — A string identifier grouping jobs that share the same
  rate limit counter.
  *(Defined in: ojs-rate-limiting.md, Section 3)*
- **Scope** — The boundary within which a rate or concurrency limit applies
  (e.g., per-queue, per-worker, per-key, global).
  *(Defined in: ojs-rate-limiting.md, Section 3)*
- **Throttle** — Deliberately slowing job processing to stay within a rate
  limit; throttled jobs are delayed rather than rejected.
  *(Defined in: ojs-rate-limiting.md, Section 3)*
- **Window** — A fixed or sliding time interval used to measure rate limit
  consumption (e.g., 100 jobs per 60-second window).
  *(Defined in: ojs-rate-limiting.md, Section 3)*

---

## 9. Worker Protocol

- **Heartbeat** — A periodic signal from a worker to the backend indicating it
  is alive and processing a claimed job. Missed heartbeats may trigger
  visibility timeout expiration.
  *(Defined in: ojs-worker-protocol.md, Section 1.3)*
- **Reservation** — The act of claiming a job from a queue for exclusive
  processing, granting the worker a visibility timeout window.
  *(Defined in: ojs-worker-protocol.md, Section 1.3)*
- **Visibility Timeout** — Maximum duration a job may remain `active` without
  heartbeat renewal before the backend makes it available for re-processing.
  *(Defined in: ojs-worker-protocol.md, Section 1.3)*

---

## 10. Multi-Tenancy

- **Fairness** — A scheduling property ensuring each tenant receives equitable
  processing capacity, preventing monopolization.
  *(Defined in: ojs-multi-tenancy.md, Section 3)*
- **Namespace** — A logical grouping that isolates jobs, queues, and
  configuration for different tenants or environments within a shared backend.
  *(Defined in: ojs-multi-tenancy.md, Section 3)*
- **Noisy Neighbor** — A condition where one tenant's workload degrades
  performance for others due to shared resource contention.
  *(Defined in: ojs-multi-tenancy.md, Section 3)*
- **Sharded Queue** — A queue distributing jobs across multiple physical
  partitions to improve throughput and enable tenant-level isolation.
  *(Defined in: ojs-multi-tenancy.md, Section 3)*
- **Starvation** — A condition where a tenant's jobs are perpetually delayed
  because other tenants consume all available worker capacity.
  *(Defined in: ojs-multi-tenancy.md, Section 3)*
- **Tenant** — An organizational entity (e.g., customer, team) that owns jobs
  and queues within a shared OJS deployment.
  *(Defined in: ojs-multi-tenancy.md, Section 3)*
- **Tenant ID** — A unique identifier for a tenant, propagated through job
  metadata for routing, rate limiting, and access control.
  *(Defined in: ojs-multi-tenancy.md, Section 3)*

---

## 11. Encryption & Codecs

- **Ciphertext** — The encrypted form of job payload data, opaque to the backend
  and decodable only by a codec with the appropriate key.
  *(Defined in: ojs-encryption.md, Section 3)*
- **Codec** — A component that encodes and decodes job payloads, performing
  serialization, compression, encryption, or other transformations.
  *(Defined in: ojs-encryption.md, Section 3)*
- **Codec Chain** — An ordered sequence of codecs applied during encoding (and
  reversed during decoding), e.g., JSON → gzip → AES-256.
  *(Defined in: ojs-encryption.md, Section 3)*
- **Codec Server** — A standalone service performing codec operations on behalf
  of clients or workers, enabling centralized key management.
  *(Defined in: ojs-encryption.md, Section 3)*
- **Compression Codec** — A codec that reduces payload size (e.g., gzip, zstd),
  typically applied before encryption in a codec chain.
  *(Defined in: ojs-encryption.md, Section 3)*
- **Encryption Codec** — A codec that encrypts job payloads to protect data at
  rest and in transit. MUST support key rotation and SHOULD use authenticated
  encryption.
  *(Defined in: ojs-encryption.md, Section 3)*
- **Payload Codec** — The primary codec for serializing and deserializing job
  arguments between in-memory and stored byte formats.
  *(Defined in: ojs-encryption.md, Section 3)*
- **Plaintext** — The unencrypted, human-readable form of job payload data.
  *(Defined in: ojs-encryption.md, Section 3)*

---

## 12. Framework Integration

- **Framework Adapter** — A library-specific integration layer bridging an OJS
  backend with a host framework (e.g., Rails, Django, Spring), handling
  lifecycle hooks and idiomatic APIs.
  *(Defined in: ojs-framework-adapters.md, Section 3)*
- **Outbox Pattern** — A reliability pattern where jobs are written to an outbox
  table in the same transaction as the business operation, then relayed to the
  queue asynchronously.
  *(Defined in: ojs-framework-adapters.md, Section 3)*
- **Request Context** — The ambient context (e.g., HTTP request, current user)
  available at enqueue time. Adapters MAY capture and propagate it into job
  metadata.
  *(Defined in: ojs-framework-adapters.md, Section 3)*
- **Transactional Enqueue** — Enqueuing a job within the same database
  transaction as a business operation, ensuring the job exists if and only if
  the transaction commits.
  *(Defined in: ojs-framework-adapters.md, Section 3)*

---

## 13. Versioning

- **Canary Deployment** — A strategy where a new worker version is rolled out to
  a small subset first, allowing validation before full rollout.
  *(Defined in: ojs-job-versioning.md, Section 10)*
- **Compatible Worker** — A worker that declares support for a specific job
  version or version range and can correctly process those jobs.
  *(Defined in: ojs-job-versioning.md, Section 3)*
- **Job Version** — A numeric or semantic identifier indicating the schema and
  behavior contract of a job type's arguments and handler.
  *(Defined in: ojs-job-versioning.md, Section 3)*
- **Rolling Deployment** — A strategy where new worker versions are gradually
  introduced while old versions continue processing, enabling zero-downtime
  upgrades.
  *(Defined in: ojs-job-versioning.md, Section 9)*
- **Schema Evolution** — Changing a job's argument structure over time while
  maintaining compatibility with existing jobs and workers.
  *(Defined in: ojs-job-versioning.md, Section 3)*
- **Schema Version** — A version identifier for a job's argument structure,
  distinct from the job version, enabling independent payload evolution.
  *(Defined in: ojs-job-versioning.md, Section 3)*
- **Version Range** — A semver-compatible expression declaring which job versions
  a worker accepts, used for routing jobs to compatible workers.
  *(Defined in: ojs-job-versioning.md, Section 3)*

---

## 14. Testing

- **Assertion Helper** — A test utility that simplifies verification of job
  enqueueing, execution results, and state transitions.
  *(Defined in: ojs-testing.md, Section 3)*
- **Drain (testing)** — A test operation that synchronously processes all
  enqueued jobs until the queue is empty, ensuring deterministic execution.
  *(Defined in: ojs-testing.md, Section 3)*
- **Fake Mode** — A testing mode that captures enqueued jobs in memory without
  executing them, useful for verifying enqueue behavior.
  *(Defined in: ojs-testing.md, Section 3)*
- **Inline Mode** — A testing mode that executes handlers synchronously at the
  point of enqueue, providing immediate feedback.
  *(Defined in: ojs-testing.md, Section 3)*
- **Real Mode** — A testing mode using actual backend infrastructure for full
  end-to-end integration testing.
  *(Defined in: ojs-testing.md, Section 3)*
- **Test Context** — An isolated testing environment with its own queue, backend
  state, and configuration to prevent cross-test pollution.
  *(Defined in: ojs-testing.md, Section 3)*

---

## 15. Middleware

- **Chain Management** — The API and rules for registering, ordering, inserting,
  and removing middleware within a chain (prepend, append, insert-before,
  insert-after).
  *(Defined in: ojs-middleware.md, Section 5)*
- **Enqueue Middleware** — Middleware executing during the enqueue path before
  persistence, used for validation, enrichment, or deduplication.
  *(Defined in: ojs-middleware.md, Section 3.1)*
- **Execution Middleware** — Middleware wrapping handler execution for concerns
  such as error handling, logging, and transaction management.
  *(Defined in: ojs-middleware.md, Section 4.1)*
- **Middleware Chain** — An ordered list of middleware components forming a
  pipeline through which a job passes during enqueue or execution.
  *(Defined in: ojs-middleware.md, Section 1.3)*
- **Yield/Next** — The mechanism by which middleware delegates to the next
  component in the chain. Middleware MUST call yield/next exactly once to
  continue, or skip it to short-circuit.
  *(Defined in: ojs-middleware.md, Section 1.3)*

---

## 16. Admin & Operations

- **Admin Endpoint** — An HTTP or gRPC endpoint exposing administrative
  operations such as queue inspection, job cancellation, and worker management.
  *(Defined in: ojs-admin-api.md, Section 3)*
- **Bulk Operation** — An administrative action applied to multiple jobs or
  queues simultaneously (e.g., bulk cancel, bulk retry, bulk discard).
  *(Defined in: ojs-admin-api.md, Section 3)*
- **Control Plane** — APIs and interfaces for managing and configuring the job
  processing system, distinct from the data plane.
  *(Defined in: ojs-admin-api.md, Section 3)*
- **Data Plane** — The runtime path through which jobs are enqueued, dispatched,
  and executed, prioritizing throughput and low latency.
  *(Defined in: ojs-admin-api.md, Section 3)*
- **Queue Configuration** — Parameters defining queue behavior: concurrency
  limits, rate limits, priority, retry policy, and backpressure settings.
  *(Defined in: ojs-admin-api.md, Section 3)*
- **Stale Worker** — An unresponsive worker whose claimed jobs have not been
  released. Stale worker detection enables job recovery.
  *(Defined in: ojs-admin-api.md, Section 3)*

---

## 17. Extension System

- **Capability Negotiation** — The process by which a client or worker discovers
  extensions supported by a backend, enabling graceful degradation.
  *(Defined in: ojs-extension-lifecycle.md, Section 3)*
- **Conformance Level** — A classification indicating how fully an
  implementation satisfies a specification tier (e.g., "Core-conformant").
  *(Defined in: ojs-extension-lifecycle.md, Section 3)*
- **Deprecation** — Formally marking an extension as obsolete. Deprecated
  extensions remain functional for a defined period but SHOULD NOT be used in
  new implementations.
  *(Defined in: ojs-extension-lifecycle.md, Section 3)*
- **Extension** — A self-contained, optional specification module adding
  functionality beyond the core OJS spec, following a defined lifecycle.
  *(Defined in: ojs-extension-lifecycle.md, Section 3)*
- **Extension Identifier** — A unique URI or URN identifying an extension
  (e.g., `urn:ojs:spec:retry`), used in capability negotiation and conformance
  declarations.
  *(Defined in: ojs-extension-lifecycle.md, Section 3)*
- **Promotion** — Advancing an extension from one tier to a higher tier (e.g.,
  experimental → stable) based on maturity and community consensus.
  *(Defined in: ojs-extension-lifecycle.md, Section 3)*
- **Tier** — A classification level indicating extension maturity and stability
  (e.g., Core, Stable, Experimental, Deprecated).
  *(Defined in: ojs-extension-lifecycle.md, Section 3)*

---

## 18. Workflow

- **Batch (workflow)** — A pattern that enqueues independent jobs as a named
  group, enabling collective monitoring and completion callbacks.
  *(Defined in: ojs-workflows.md, Section 2)*
- **Callback** — A job or function invoked when a workflow step or group reaches
  a specified state, triggering downstream processing.
  *(Defined in: ojs-workflows.md, Section 2)*
- **Chain (workflow)** — A pattern where jobs execute sequentially, each starting
  only after its predecessor completes. Failures halt the chain unless an error
  strategy is defined.
  *(Defined in: ojs-workflows.md, Section 2)*
- **Fan-in** — A synchronization point where multiple parallel jobs must
  complete before a single downstream job begins.
  *(Defined in: ojs-workflows.md, Section 2)*
- **Fan-out** — A pattern spawning multiple parallel jobs from a single parent;
  results may be aggregated at a fan-in point.
  *(Defined in: ojs-workflows.md, Section 2)*
- **Group (workflow)** — A pattern executing multiple jobs in parallel,
  optionally with a concurrency limit, completing when all members reach a
  terminal state.
  *(Defined in: ojs-workflows.md, Section 2)*

---

## 19. Wire Format & Protocol

- **Batch Encoding** — A wire format convention for encoding multiple job
  envelopes in a single message, enabling efficient bulk submission.
  *(Defined in: ojs-json-format.md, Section 10)*
- **Content Type** — A media type (e.g., `application/json`) declaring the
  serialization format of a job envelope on the wire.
  *(Defined in: ojs-json-format.md, Section 2)*
- **Protocol Binding** — A specification mapping OJS operations onto a transport
  protocol (HTTP or gRPC), defining endpoints, methods, headers, and error
  codes.
  *(Defined in: ojs-http-binding.md, Section 2; ojs-grpc-binding.md, Section 2)*
- **Wire Format** — The byte-level representation of a job envelope during
  transmission. OJS defines a canonical JSON format and permits alternatives
  via content type negotiation.
  *(Defined in: ojs-json-format.md, Section 2)*
