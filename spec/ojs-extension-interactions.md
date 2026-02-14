# Open Job Spec -- Extension Interactions Specification

| Field        | Value                                                              |
|-------------|----------------------------------------------------------------------|
| **Title**   | OJS Extension Interactions                                           |
| **Version** | 1.0.0-rc.1                                                          |
| **Date**    | 2026-02-15                                                           |
| **Status**  | Release Candidate 1                                                  |
| **Layer**   | Meta (cross-cutting governance)                                      |
| **URI**     | https://openjobspec.org/spec/v1/ojs-extension-interactions           |
| **Requires**| OJS Core Specification (Layer 1), OJS Extension Lifecycle            |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Interaction Matrix](#3-interaction-matrix)
4. [Encryption + Unique Jobs](#4-encryption--unique-jobs)
5. [Encryption + Observability](#5-encryption--observability)
6. [Multi-Tenancy + Rate Limiting](#6-multi-tenancy--rate-limiting)
7. [Multi-Tenancy + Backpressure](#7-multi-tenancy--backpressure)
8. [Multi-Tenancy + Dead Letter Queue](#8-multi-tenancy--dead-letter-queue)
9. [Retry + Rate Limiting](#9-retry--rate-limiting)
10. [Retry + Dead Letter Queue](#10-retry--dead-letter-queue)
11. [Workflows + Graceful Shutdown](#11-workflows--graceful-shutdown)
12. [Workflows + Job Versioning](#12-workflows--job-versioning)
13. [Cron + Unique Jobs](#13-cron--unique-jobs)
14. [Middleware Ordering](#14-middleware-ordering)
15. [Framework Adapters + Encryption](#15-framework-adapters--encryption)
16. [Conformance Requirements](#16-conformance-requirements)
17. [Prior Art](#17-prior-art)

---

## 1. Introduction

The Open Job Spec ecosystem comprises a growing set of extensions, each defining
behavior for a focused concern: retries, encryption, rate limiting, observability,
and so on. Each extension is designed and specified in isolation, which keeps individual
documents manageable. However, production systems rarely activate a single extension.
Real deployments combine five, ten, or more extensions simultaneously.

When *N* extensions are active, there are up to *N × (N − 1) / 2* pairwise
interactions. For the fifteen extensions covered in this document, that yields 105
potential interaction points. Without explicit documentation, implementers are left to
discover these interactions through trial and error -- leading to subtle bugs, data
leaks, and inconsistent behavior across SDKs and backends.

This specification defines the **interaction semantics** between OJS extensions. For
each pair of extensions that interact in a non-trivial way, this document specifies
the expected behavior, the ordering constraints, and the conformance requirements
that implementations MUST satisfy.

### 1.1 Scope

This specification defines:

- A classification matrix for all pairwise extension interactions.
- Detailed interaction semantics for pairs that require coordination or have conflict
  potential.
- The canonical middleware ordering when multiple extensions contribute middleware.
- Conformance requirements for implementations supporting multiple extensions.

This specification does **not** redefine the behavior of any individual extension.
Each extension's own specification remains authoritative for its internal semantics.

### 1.2 Relationship to Other Specifications

This document is a companion to the [Extension Lifecycle](ojs-extension-lifecycle.md)
specification. While the lifecycle document governs how extensions are proposed,
promoted, and deprecated, this document governs how extensions **behave together**
at runtime.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD",
"SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this
document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14)
[[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)]
[[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they
appear in ALL CAPITALS, as shown here.

Every MUST requirement includes a rationale explaining why the requirement is mandatory.

### 2.1 Interaction Classifications

| Symbol | Classification            | Meaning                                                      |
|--------|---------------------------|--------------------------------------------------------------|
| ✅     | **Compatible**            | Extensions work together without special handling.           |
| ⚙️     | **Requires coordination** | Specific ordering or configuration rules apply.              |
| ⚠️     | **Conflict potential**    | Implementers MUST handle edge cases to avoid incorrect behavior. |
| ➖     | **Independent**           | Extensions have no runtime interaction.                      |

---

## 3. Interaction Matrix

The following matrix documents all pairwise interactions between the fifteen OJS
extensions covered by this specification. Each cell is classified using the symbols
defined in [Section 2.1](#21-interaction-classifications). Cells referencing a
detailed section contain a hyperlink to that section.

Abbreviations used in column/row headers:

| Abbr  | Extension          | Abbr  | Extension          |
|-------|--------------------|-------|--------------------|
| RET   | Retry Policy       | BP    | Backpressure       |
| UNQ   | Unique Jobs        | DLQ   | Dead Letter Queue  |
| WF    | Workflows          | GS    | Graceful Shutdown  |
| CRN   | Cron               | ENC   | Encryption         |
| EVT   | Events             | MT    | Multi-Tenancy      |
| MW    | Middleware         | OBS   | Observability      |
| RL    | Rate Limiting      | VER   | Job Versioning     |
| FA    | Framework Adapters |       |                    |

|       | RET | UNQ | WF  | CRN | EVT | MW  | RL  | BP  | DLQ | GS  | ENC | MT  | OBS | VER | FA  |
|-------|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|
| **RET** | ➖ | ✅ | ✅ | ✅ | ✅ | ✅ | [⚙️](#9-retry--rate-limiting) | ✅ | [⚙️](#10-retry--dead-letter-queue) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **UNQ** | ✅ | ➖ | ✅ | [⚠️](#13-cron--unique-jobs) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | [⚠️](#4-encryption--unique-jobs) | ✅ | ✅ | ✅ | ✅ |
| **WF**  | ✅ | ✅ | ➖ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | [⚙️](#11-workflows--graceful-shutdown) | ✅ | ✅ | ✅ | [⚙️](#12-workflows--job-versioning) | ✅ |
| **CRN** | ✅ | [⚠️](#13-cron--unique-jobs) | ✅ | ➖ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **EVT** | ✅ | ✅ | ✅ | ✅ | ➖ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **MW**  | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **RL**  | [⚙️](#9-retry--rate-limiting) | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ | ✅ | ✅ | ✅ | ✅ | [⚙️](#6-multi-tenancy--rate-limiting) | ✅ | ✅ | ✅ |
| **BP**  | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ | ✅ | ✅ | ✅ | [⚙️](#7-multi-tenancy--backpressure) | ✅ | ✅ | ✅ |
| **DLQ** | [⚙️](#10-retry--dead-letter-queue) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ | ✅ | ✅ | [⚠️](#8-multi-tenancy--dead-letter-queue) | ✅ | ✅ | ✅ |
| **GS**  | ✅ | ✅ | [⚙️](#11-workflows--graceful-shutdown) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **ENC** | ✅ | [⚠️](#4-encryption--unique-jobs) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ | ✅ | [⚙️](#5-encryption--observability) | ✅ | [⚙️](#15-framework-adapters--encryption) |
| **MT**  | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | [⚙️](#6-multi-tenancy--rate-limiting) | [⚙️](#7-multi-tenancy--backpressure) | [⚠️](#8-multi-tenancy--dead-letter-queue) | ✅ | ✅ | ➖ | ✅ | ✅ | ✅ |
| **OBS** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | [⚙️](#5-encryption--observability) | ✅ | ➖ | ✅ | ✅ |
| **VER** | ✅ | ✅ | [⚙️](#12-workflows--job-versioning) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ | ✅ |
| **FA**  | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | [⚙️](#15-framework-adapters--encryption) | ✅ | ✅ | ✅ | ➖ |

> **Reading the matrix**: Find the row for extension A and the column for extension B.
> The cell describes the interaction when both A and B are active simultaneously.
> The matrix is symmetric: the interaction between A→B is identical to B→A.

---

## 4. Encryption + Unique Jobs

**Classification**: ⚠️ Conflict potential

### 4.1 Problem

The Unique Jobs extension (see [ojs-unique-jobs.md](ojs-unique-jobs.md)) computes a
deduplication key from the job's `queue`, `job_type`, and `args` fields. The
Encryption extension (see [ojs-encryption.md](ojs-encryption.md)) encrypts `args`
using authenticated encryption with random nonces (e.g., AES-256-GCM).

Because each encryption operation produces different ciphertext for the same plaintext
-- a fundamental property of secure encryption -- computing the unique key **after**
encryption yields a different key every time, even for semantically identical jobs.
Deduplication breaks silently.

### 4.2 Solution

**Unique key computation MUST happen BEFORE encryption in the middleware chain.**

SDKs and implementations MUST enforce the following ordering during enqueue:

1. Compute the unique job key from the **plaintext** `args`.
2. Apply encryption to `args`.
3. Enqueue the job with both the unique key and the encrypted payload.

**Rationale**: Reversing this order makes deduplication non-functional. Since the
unique key is a hash (not the args themselves), storing it in plaintext alongside
encrypted args does not leak sensitive data -- the hash is irreversible.

### 4.3 Implementation Notes

- The unique key SHOULD be stored in the job envelope's `meta` field or a dedicated
  `unique_key` field, NOT derived on-the-fly from encrypted args.
- Implementations that derive unique keys at the backend MUST receive the precomputed
  key from the SDK rather than recomputing from the (now encrypted) args.

---

## 5. Encryption + Observability

**Classification**: ⚙️ Requires coordination

### 5.1 Problem

The Observability extension (see [ojs-observability.md](ojs-observability.md)) emits
traces, metrics, and logs for job processing. When encryption is active, `args` and
potentially `meta` fields contain ciphertext. Logging or including encrypted payloads
in span attributes serves no diagnostic purpose and may violate the principle of least
exposure.

Dashboard UIs need to display job arguments for debugging, but they receive only
encrypted data from the backend.

### 5.2 Solution

**Span attributes MUST NOT include raw encrypted `args` values.**

Implementations MUST follow these rules:

1. Trace spans SHOULD include structural metadata (`job_type`, `queue`, `job_id`,
   `attempt`) but MUST NOT include `args` when encryption is active.
2. Log entries produced by the observability middleware MUST NOT include encrypted
   payloads. A placeholder such as `"[encrypted]"` SHOULD be used.
3. Dashboard access to plaintext args MUST use the **Codec Server** mechanism defined
   in [ojs-encryption.md](ojs-encryption.md). The Codec Server provides authorized,
   on-demand decryption with authentication and audit logging.

**Rationale**: Including ciphertext in logs creates large, useless log entries that
increase storage costs. The Codec Server pattern centralizes decryption authorization,
providing an auditable access path.

---

## 6. Multi-Tenancy + Rate Limiting

**Classification**: ⚙️ Requires coordination

### 6.1 Problem

The Rate Limiting extension (see [ojs-rate-limiting.md](ojs-rate-limiting.md)) enforces
concurrency and throughput limits using a `rate_limit_key`. The Multi-Tenancy extension
(see [ojs-multi-tenancy.md](ojs-multi-tenancy.md)) isolates tenants by `tenant_id`.

Without coordination, rate limits apply globally across all tenants. A single tenant
producing a burst of jobs can exhaust the rate limit, starving other tenants. Conversely,
some deployments need a global rate limit that protects a shared external API regardless
of which tenant originates the request.

### 6.2 Solution

**Rate limit scope MUST support tenant-aware partitioning when multi-tenancy is active.**

Implementations MUST provide:

1. **Per-tenant rate limits**: When multi-tenancy is active, the `rate_limit_key`
   SHOULD include the `tenant_id` by default, producing per-tenant counters.
   Example: `rate_limit_key = "api:stripe:" + tenant_id`.
2. **Global rate limits**: Implementations MUST also support rate limits that span
   all tenants, for shared resources with absolute capacity constraints.
   Example: `rate_limit_key = "global:stripe_api"`.
3. **Configuration**: The rate limit policy SHOULD accept a `scope` field with values
   `"tenant"` (default when multi-tenancy is active) or `"global"`.

**Rationale**: Tenant fairness is a fundamental property of multi-tenant systems. Without
per-tenant rate limits, noisy-neighbor effects are unavoidable.

---

## 7. Multi-Tenancy + Backpressure

**Classification**: ⚙️ Requires coordination

### 7.1 Problem

The Backpressure extension (see [ojs-backpressure.md](ojs-backpressure.md)) defines
queue depth thresholds that trigger producer slowdown or rejection. In a multi-tenant
system, one tenant enqueueing a large batch can fill the queue, triggering backpressure
that blocks all tenants.

### 7.2 Solution

**Backpressure bounds SHOULD be configurable per-tenant.**

1. Implementations SHOULD support per-tenant queue depth thresholds. When tenant A
   exceeds its allocation, backpressure applies only to tenant A's producers.
2. **Sharded queues** (one queue per tenant) provide natural isolation and are the
   RECOMMENDED approach for deployments with strict tenant SLAs.
3. When shared queues are used, implementations SHOULD track per-tenant depth as a
   virtual counter and enforce tenant-level thresholds independently.

**Rationale**: Shared queue backpressure without tenant awareness creates a denial-of-service
vector where one tenant can prevent others from enqueueing work.

---

## 8. Multi-Tenancy + Dead Letter Queue

**Classification**: ⚠️ Conflict potential

### 8.1 Problem

The Dead Letter Queue extension (see [ojs-dead-letter.md](ojs-dead-letter.md)) stores
failed jobs for inspection and reprocessing. In a multi-tenant system, DLQ inspection
endpoints could expose tenant A's failed jobs (including args, errors, and stack traces)
to tenant B.

### 8.2 Solution

**DLQ queries MUST be filtered by `tenant_id`.**

1. All DLQ query APIs (list, get, replay, purge) MUST include `tenant_id` filtering.
   A request without `tenant_id` MUST return only jobs belonging to the authenticated
   tenant.
2. The Admin API (see [ojs-admin-api.md](ojs-admin-api.md)) MUST enforce tenant
   isolation for all DLQ operations. Cross-tenant DLQ access MUST require explicit
   super-admin authorization.
3. DLQ event emissions (`job.dead_lettered`) MUST include `tenant_id` so that
   event consumers can route notifications to the correct tenant.

**Rationale**: DLQ entries often contain sensitive error details, stack traces, and
the original job arguments. Cross-tenant access constitutes a data leak.

---

## 9. Retry + Rate Limiting

**Classification**: ⚙️ Requires coordination

### 9.1 Problem

The Retry extension (see [ojs-retry.md](ojs-retry.md)) re-enqueues failed jobs for
subsequent attempts. The Rate Limiting extension enforces throughput constraints. When
both are active, retried jobs compete with new jobs for the same rate limit slots.

In high-throughput systems, a burst of failures can generate a wave of retries that
fills the rate limit window, preventing new jobs from executing. Conversely, prioritizing
new jobs indefinitely can starve retried jobs that may carry time-sensitive data.

### 9.2 Solution

**Implementations SHOULD provide configurable priority between retried and new jobs
within rate limit windows.**

1. The default behavior SHOULD treat retried jobs and new jobs equally (FIFO within
   the rate limit window).
2. Implementations SHOULD support a `retry_priority` configuration with values:
   - `"equal"` (default): Retried and new jobs are treated identically.
   - `"prefer_retry"`: Retried jobs are dequeued before new jobs within the same
     rate limit window.
   - `"prefer_new"`: New jobs are dequeued before retried jobs.
3. Rate limit counters MUST count retried jobs. A retried job consumes a rate limit
   slot just like a new job.

**Rationale**: The correct priority depends on the use case. Billing jobs may need
`prefer_retry` to avoid revenue loss; notification jobs may need `prefer_new` to
prioritize freshness.

---

## 10. Retry + Dead Letter Queue

**Classification**: ⚙️ Requires coordination

### 10.1 Problem

The Retry and Dead Letter Queue extensions form a natural pipeline: jobs that exhaust
all retry attempts are moved to the DLQ. This interaction is partially defined in
the individual specifications but warrants explicit cross-reference.

### 10.2 Solution

**A job MUST be moved to the DLQ only after all retry attempts are exhausted.**

1. The retry policy's `max_retries` field defines the total number of attempts. After
   the final attempt fails, the job transitions to the `dead` state and is inserted
   into the DLQ.
2. The DLQ entry MUST preserve the full retry history, including the error from each
   attempt, as defined in [ojs-dead-letter.md](ojs-dead-letter.md).
3. When a DLQ job is replayed, it MUST reset its attempt counter to zero and follow
   the retry policy from the beginning.
4. Events: The `job.retry_exhausted` event (Retry extension) and the `job.dead_lettered`
   event (DLQ extension) MUST both be emitted, in that order.

**Rationale**: Without explicit ordering of events and state transitions, implementations
may emit events inconsistently or lose retry history during DLQ insertion.

---

## 11. Workflows + Graceful Shutdown

**Classification**: ⚙️ Requires coordination

### 11.1 Problem

The Workflows extension (see [ojs-workflows.md](ojs-workflows.md)) defines multi-step
job chains where the completion of one step triggers the next. The Graceful Shutdown
extension (see [ojs-graceful-shutdown.md](ojs-graceful-shutdown.md)) defines how
workers drain in-flight jobs during shutdown.

When a shutdown signal arrives while a workflow chain is mid-execution, individual
steps may complete while subsequent steps have not yet been enqueued.

### 11.2 Solution

**Individual jobs within a workflow MUST follow standard graceful shutdown semantics.
The workflow engine MUST resume from the last completed step upon restart.**

1. Each job in a workflow is an independent unit for shutdown purposes. If a job is
   in-flight when shutdown begins, it receives the standard drain period to complete.
2. The workflow engine MUST persist the workflow's progress (i.e., which steps have
   completed) durably. Upon worker restart, the engine MUST resume by enqueueing the
   next uncompleted step.
3. Implementations MUST NOT attempt to execute the entire remaining workflow chain
   within the drain period. Only the currently executing step is subject to the drain
   timeout.

**Rationale**: Treating the entire workflow as an atomic unit for shutdown would require
unbounded drain periods, defeating the purpose of graceful shutdown.

---

## 12. Workflows + Job Versioning

**Classification**: ⚙️ Requires coordination

### 12.1 Problem

The Job Versioning extension (see [ojs-job-versioning.md](ojs-job-versioning.md))
allows job schemas to evolve over time. A workflow chain may span multiple steps where
some steps were enqueued under schema version 1 and later steps run under schema
version 2.

Data passed between workflow steps (via `result` or shared context) may have different
shapes across versions.

### 12.2 Solution

**Each job in a workflow MUST carry its own version. Data passing between steps MUST
handle version transformation.**

1. The `version` field on each job in a workflow is independent. Step A (v1) may
   produce output consumed by step B (v2).
2. When a version mismatch is detected between a step's output and the next step's
   expected input, implementations MUST apply the version transformation defined in
   the Job Versioning extension.
3. Workflow definitions SHOULD declare the expected version for each step. If omitted,
   the latest version is assumed.

**Rationale**: Long-running workflows (e.g., multi-day approval chains) are particularly
susceptible to version drift. Explicit per-step versioning prevents silent data
corruption.

---

## 13. Cron + Unique Jobs

**Classification**: ⚠️ Conflict potential

### 13.1 Problem

The Cron extension (see [ojs-cron.md](ojs-cron.md)) creates jobs on a periodic
schedule. If the previous cron-triggered job has not completed when the next tick
fires, a duplicate job is enqueued. The Unique Jobs extension prevents duplicates, but
the interaction between Cron's `overlap_policy` and Unique Jobs' `on_conflict` policy
creates ambiguous behavior if not explicitly coordinated.

### 13.2 Solution

**The overlap policy and unique policy MUST be evaluated together.**

1. Cron's `overlap_policy` is evaluated first:
   - `"skip"`: If the previous job is still running, the new job is not enqueued.
     The unique check is never reached.
   - `"queue"`: The new job is enqueued. The unique check then applies.
   - `"replace"`: The previous job is cancelled and the new job takes its place.
     The unique check is bypassed.
2. When `overlap_policy` is `"queue"` and unique jobs is active:
   - `on_conflict: "reject"`: The new job is rejected if a matching job exists.
   - `on_conflict: "replace"`: The existing job is replaced.
3. The combination `overlap: "skip"` + `unique: on_conflict: "reject"` provides the
   **strongest deduplication guarantee** and is RECOMMENDED for most cron jobs.

**Rationale**: Without explicit evaluation ordering, an implementation might apply
unique checks before the overlap policy, leading to unexpected rejections of jobs that
the overlap policy would have allowed.

---

## 14. Middleware Ordering

When multiple extensions contribute middleware to the enqueue or execution chain, the
ordering of middleware determines correctness. This section defines the **canonical
middleware execution order** for the enqueue chain.

### 14.1 Canonical Enqueue Middleware Order

Implementations MUST execute enqueue middleware in the following order:

| Order | Middleware               | Extension         | Rationale                                                      |
|-------|--------------------------|-------------------|----------------------------------------------------------------|
| 1     | Trace context injection  | Observability     | Establishes the trace span that encompasses all subsequent middleware. |
| 2     | Authentication / Authorization | Multi-Tenancy | Tenant identity must be resolved before any tenant-scoped logic. |
| 3     | Input validation         | Middleware (core)  | Reject malformed jobs before any processing or state mutation.  |
| 4     | Unique job check         | Unique Jobs       | Deduplication must use plaintext args (before encryption).      |
| 5     | Rate limiting            | Rate Limiting     | Apply throughput constraints before committing the job.         |
| 6     | Payload encryption       | Encryption        | Encrypt args after all middleware that reads plaintext.         |
| 7     | Enqueue to backend       | Core              | Final step: persist the job to the queue backend.              |

### 14.2 Rules

1. Observability middleware MUST be first so that the trace context covers the entire
   enqueue pipeline, including any rejections by downstream middleware.
2. Unique job checks MUST precede encryption, as specified in [Section 4](#4-encryption--unique-jobs).
3. Encryption MUST be the last transformation before enqueue, ensuring no subsequent
   middleware can access plaintext args.
4. Implementations MAY insert custom middleware at any point, but MUST NOT reorder
   the canonical middleware listed above.

### 14.3 Canonical Execution Middleware Order

For the worker-side execution chain, the RECOMMENDED order is:

| Order | Middleware               | Extension         | Rationale                                                      |
|-------|--------------------------|-------------------|----------------------------------------------------------------|
| 1     | Trace context extraction | Observability     | Restores the trace context from the job envelope.              |
| 2     | Payload decryption       | Encryption        | Decrypt args before any middleware that reads them.            |
| 3     | Tenant context binding   | Multi-Tenancy     | Establishes tenant scope for the handler and downstream services. |
| 4     | Rate limit slot acquisition | Rate Limiting  | Acquires a concurrency slot before handler execution.          |
| 5     | Retry wrapper            | Retry Policy      | Catches handler exceptions and determines retry behavior.      |
| 6     | Job handler invocation   | Core              | Executes the application-defined handler.                      |

---

## 15. Framework Adapters + Encryption

**Classification**: ⚙️ Requires coordination

### 15.1 Problem

The Framework Adapters extension (see [ojs-framework-adapters.md](ojs-framework-adapters.md))
defines patterns for transactional enqueue, where jobs are written to an **outbox table**
within the same database transaction as application state changes. The question arises:
should jobs be encrypted before or after insertion into the outbox?

If encrypted before, the outbox contains ciphertext -- protecting data at rest. If
encrypted after (by the outbox relay), the outbox contains plaintext -- creating a
window of exposure.

### 15.2 Solution

**Encryption SHOULD be applied before outbox insertion.**

1. The enqueue middleware chain (including encryption) MUST execute before the job
   is written to the outbox table. This ensures the outbox never contains plaintext
   sensitive data.
2. The outbox relay process, which reads from the outbox and publishes to the queue
   backend, MUST NOT re-encrypt the payload. The job is already encrypted.
3. If the outbox relay needs to inspect job metadata (e.g., queue name, priority),
   those fields MUST remain unencrypted. Only `args` and designated `meta` fields
   are encrypted, as defined in [ojs-encryption.md](ojs-encryption.md).

**Rationale**: The outbox table is typically stored in the application's primary
database. If the database is compromised, unencrypted job args in the outbox table
expose sensitive data. Encrypting before insertion maintains the end-to-end encryption
guarantee.

---

## 16. Conformance Requirements

### 16.1 Required Capabilities

An implementation declaring support for multiple extensions MUST satisfy the following
interaction requirements:

| ID     | Requirement                                                                                              | Section |
|--------|----------------------------------------------------------------------------------------------------------|---------|
| EI-001 | Unique key computation MUST occur before encryption in the enqueue pipeline.                             | [4](#4-encryption--unique-jobs) |
| EI-002 | Observability span attributes MUST NOT include encrypted `args` values.                                 | [5](#5-encryption--observability) |
| EI-003 | Rate limit scope MUST support tenant-aware partitioning when multi-tenancy is active.                   | [6](#6-multi-tenancy--rate-limiting) |
| EI-004 | DLQ queries MUST be filtered by `tenant_id` when multi-tenancy is active.                               | [8](#8-multi-tenancy--dead-letter-queue) |
| EI-005 | DLQ Admin API MUST enforce tenant isolation for all DLQ operations.                                     | [8](#8-multi-tenancy--dead-letter-queue) |
| EI-006 | Rate limit counters MUST count retried jobs.                                                            | [9](#9-retry--rate-limiting) |
| EI-007 | Jobs MUST be moved to the DLQ only after all retry attempts are exhausted.                              | [10](#10-retry--dead-letter-queue) |
| EI-008 | `job.retry_exhausted` and `job.dead_lettered` events MUST be emitted in that order.                     | [10](#10-retry--dead-letter-queue) |
| EI-009 | Workflow engine MUST resume from the last completed step after graceful shutdown.                        | [11](#11-workflows--graceful-shutdown) |
| EI-010 | Each job in a workflow MUST carry its own version field.                                                 | [12](#12-workflows--job-versioning) |
| EI-011 | Cron overlap policy MUST be evaluated before unique job conflict policy.                                 | [13](#13-cron--unique-jobs) |
| EI-012 | Enqueue middleware MUST follow the canonical ordering defined in Section 14.                             | [14](#14-middleware-ordering) |
| EI-013 | Encryption MUST be applied before outbox insertion in transactional enqueue.                             | [15](#15-framework-adapters--encryption) |

### 16.2 Recommended Capabilities

| ID       | Requirement                                                                                            | Section |
|----------|--------------------------------------------------------------------------------------------------------|---------|
| EI-R001  | Backpressure bounds SHOULD be configurable per-tenant.                                                 | [7](#7-multi-tenancy--backpressure) |
| EI-R002  | Implementations SHOULD provide configurable priority between retried and new jobs.                      | [9](#9-retry--rate-limiting) |
| EI-R003  | DLQ replay SHOULD reset the attempt counter to zero.                                                   | [10](#10-retry--dead-letter-queue) |
| EI-R004  | The combination `overlap: "skip"` + `unique: "reject"` SHOULD be the default for cron jobs.            | [13](#13-cron--unique-jobs) |
| EI-R005  | Observability logs SHOULD use `"[encrypted]"` as a placeholder for encrypted payloads.                 | [5](#5-encryption--observability) |
| EI-R006  | Rate limit policy SHOULD accept a `scope` field with values `"tenant"` or `"global"`.                  | [6](#6-multi-tenancy--rate-limiting) |

---

## 17. Prior Art

This specification draws on interaction patterns observed in mature systems:

### 17.1 OpenTelemetry Semantic Convention Interactions

OpenTelemetry defines semantic conventions for HTTP, database, messaging, and RPC
instrumentation. When multiple conventions apply to a single span (e.g., an HTTP
request that triggers a database query), the conventions define explicit attribute
precedence and nesting rules. OJS's interaction matrix follows the same principle:
documenting pairwise behavior prevents conflicting attribute sets and ambiguous
semantics.

### 17.2 Kubernetes Admission Webhook Ordering

Kubernetes supports **mutating** and **validating** admission webhooks that intercept
API requests. Multiple webhooks execute in a defined order, and Kubernetes documents
the interaction semantics (e.g., mutating webhooks run before validating webhooks).
OJS's canonical middleware ordering in [Section 14](#14-middleware-ordering) follows
this established pattern.

### 17.3 Middleware Pipeline Patterns

Web frameworks (Rack, Express, ASP.NET Core, Django) define middleware pipelines
where ordering determines correctness. Authentication middleware must run before
authorization; compression must run after response generation. OJS's enqueue and
execution middleware chains apply the same principle to job processing.

### 17.4 Temporal Codec Server

Temporal's approach to encryption and observability interaction -- where a Codec
Server provides authorized decryption for the Web UI -- directly informs the
Encryption + Observability interaction defined in [Section 5](#5-encryption--observability).

---

*End of specification.*
