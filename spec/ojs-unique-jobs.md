# Open Job Spec: Unique Jobs / Deduplication

**Version:** 1.0.0-rc.1
**Date:** 2026-02-12
**Status:** Release Candidate
**Maturity:** Beta
**Layer:** 1 (Core Specification)
**Conformance Level:** 4 (Advanced)

---

## Abstract

This document defines the semantics of unique jobs (deduplication) in Open Job Spec (OJS). Deduplication prevents duplicate work from being enqueued, a capability that every production job system eventually needs but that no two systems implement alike. The specification defines a `UniquePolicy` structure, a key computation algorithm, configurable conflict resolution strategies, state filtering, and a two-tier conformance model that acknowledges the fundamental tension between correctness and portability.

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt).

---

## 1. Problem Statement

Deduplication is, by wide consensus among job system implementers, the hardest unsolved problem in background job processing.

The difficulty stems from a fundamental tension: checking whether a duplicate exists and inserting a new job must happen atomically to be correct, but achieving atomicity depends entirely on the capabilities of the underlying storage backend. A PostgreSQL backend can use a unique index or constraint; a Redis backend can use `SET NX`; an in-memory backend can use a simple map with a mutex. Each mechanism offers different guarantees, different failure modes, and different performance characteristics.

Prior art confirms this:

- **Oban** (Elixir) provides the richest deduplication model in the ecosystem -- multi-dimensional uniqueness across type, queue, args, period, and states -- but its open-source version uses a query-then-insert approach with a race window. Only Oban Pro's constraint-based approach provides strong guarantees.
- **River** (Go) evolved from advisory-lock-based uniqueness to index-based uniqueness across multiple releases, demonstrating how difficult it is to get this right even with a single storage backend.
- **Graphile Worker** (Node.js) uses an explicit `job_key` string with three conflict modes (`replace`, `preserve_run_at`, `unsafe_dedupe`), trading flexibility for simplicity.
- **BullMQ** (Node.js) offers both custom job ID deduplication and a newer explicit deduplication API with throttle and debounce modes.
- **Asynq** (Go) provides dual mechanisms: a deterministic `TaskID` that provides guaranteed uniqueness via storage-level constraints, and TTL-based `Unique` locks that are explicitly documented as best-effort.
- **Faktory** (polyglot) gates unique jobs to its Enterprise tier, using a jobtype+args hash with a `unique_for` TTL window.

A universal spec cannot mandate a single implementation strategy. Instead, OJS defines the **semantics** of deduplication -- what dimensions define uniqueness, how conflicts are resolved, which job states participate -- and requires implementations to declare the **strength** of their guarantee. This allows a PostgreSQL backend with constraint-based uniqueness and a Redis backend with TTL-based locks to both conform to OJS, while giving users the information they need to choose the right backend for their correctness requirements.

---

## 2. UniquePolicy Structure

A `UniquePolicy` is an optional object attached to a job at enqueue time. When present, it instructs the backend to check for an existing job that matches the specified dimensions before inserting.

```json
{
  "unique": {
    "keys": ["type", "queue", "args"],
    "args_keys": ["user_id"],
    "meta_keys": [],
    "period": "PT1H",
    "states": ["available", "active", "scheduled", "retryable", "pending"],
    "on_conflict": "reject"
  }
}
```

### 2.1 Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `keys` | `string[]` | No | `["type"]` | Dimensions that define the uniqueness fingerprint. Valid values: `"type"`, `"queue"`, `"args"`, `"meta"`. |
| `args_keys` | `string[]` | No | `null` (all args) | When `"args"` is included in `keys`, specifies which top-level keys within `args` to include. If `null` or omitted, all of `args` is included. |
| `meta_keys` | `string[]` | No | `null` (no meta) | When `"meta"` is included in `keys`, specifies which top-level keys within `meta` to include. MUST be provided when `"meta"` is in `keys`. |
| `period` | `string` (ISO 8601 duration) | No | `null` (no expiry) | Duration for which the uniqueness constraint is active. After this period elapses from the original job's `created_at` timestamp, a new job with the same fingerprint is permitted. |
| `states` | `string[]` | No | `["available", "active", "scheduled", "retryable", "pending"]` | Job states to check against when determining if a duplicate exists. Only jobs in one of these states are considered duplicates. |
| `on_conflict` | `string` | No | `"reject"` | Strategy for handling a detected duplicate. One of: `"reject"`, `"replace"`, `"replace_except_schedule"`, `"ignore"`. |

### 2.2 Normative Requirements

Implementations MUST validate the `UniquePolicy` structure at enqueue time and reject invalid policies with an `invalid_request` error.

**Rationale:** Failing fast on invalid policies prevents silent misconfiguration. A developer who typos `"argz"` in the `keys` array should learn about it immediately, not discover days later that deduplication was silently ignored.

Implementations MUST include `"type"` in the computed uniqueness fingerprint, regardless of whether it appears in the `keys` array.

**Rationale:** Without `type`, jobs of different types with identical arguments would collide. An `email.send` job and a `sms.send` job with the same `user_id` argument are fundamentally different work items. Omitting `type` from the fingerprint would produce nonsensical deduplication behavior. Silently including `type` is preferred over requiring it in `keys` because it eliminates a class of misconfiguration.

Implementations MUST reject a `UniquePolicy` where `keys` contains `"meta"` but `meta_keys` is `null` or empty.

**Rationale:** Unlike `args`, which has a natural "use all of it" default, metadata is an extensible grab bag of cross-cutting concerns (trace IDs, locale, timestamps). Including all metadata in the fingerprint by default would cause virtually every job to be unique, defeating the purpose. Requiring explicit `meta_keys` forces the developer to be intentional.

Implementations MUST reject a `UniquePolicy` where `args_keys` references keys that do not exist in the job's `args`.

**Rationale:** A uniqueness policy that references nonexistent keys would silently produce fingerprints based on `null` values, causing unintended collisions between jobs that merely share the absence of a field.

Implementations MUST treat `keys` values as case-sensitive.

**Rationale:** Consistency with JSON field names, which are case-sensitive per RFC 8259.

---

## 3. Uniqueness Dimensions

The uniqueness fingerprint is composed from one or more **dimensions**. Each dimension contributes data to the hash that identifies a logically unique unit of work.

### 3.1 `type` -- Job Type

The job's `type` field (e.g., `"email.send"`, `"report.generate"`).

This dimension is **always included** in the fingerprint, whether or not it appears in `keys`. See Section 2.2 for rationale.

### 3.2 `queue` -- Target Queue

The job's target `queue` field (e.g., `"default"`, `"email"`, `"critical"`).

When included, the same job type with the same arguments enqueued to different queues is treated as distinct work. This is useful when the same logical operation has different processing characteristics per queue (e.g., a `notification.send` job on the `"high-priority"` queue vs. the `"batch"` queue).

When omitted, uniqueness is global across all queues for the given type.

### 3.3 `args` -- Job Arguments

The job's `args` field, either in its entirety or filtered to specific top-level keys via `args_keys`.

**Full args (default when `args_keys` is omitted):**

All of `args` is canonicalized and included. Two jobs are duplicates only if their entire argument payloads are semantically identical.

**Selective args (when `args_keys` is provided):**

Only the specified top-level keys are extracted from `args`, canonicalized, and included. This enables deduplication on a subset of the arguments, which is the common case.

Example: For a job with `args: {"user_id": 42, "template": "welcome", "locale": "en-US"}` and `args_keys: ["user_id"]`, only the value `42` for key `"user_id"` participates in the fingerprint. Two jobs with the same `user_id` but different `template` or `locale` values are considered duplicates.

### 3.4 `meta` -- Metadata Keys

Selected keys from the job's `meta` object, specified via `meta_keys`.

Unlike `args`, `meta` has no "include all" default because metadata typically contains system-generated values (trace IDs, timestamps, worker hints) that are unique per enqueue call. Including all metadata would make every job unique, which is never the intent.

Example: For a job with `meta: {"tenant_id": "acme", "trace_id": "abc123", "source": "api"}` and `meta_keys: ["tenant_id"]`, only the value `"acme"` for key `"tenant_id"` participates in the fingerprint.

---

## 4. Uniqueness Key Computation

The uniqueness key is a deterministic hash derived from the selected dimensions. Two jobs that produce the same uniqueness key are considered duplicates.

### 4.1 Algorithm

The computation proceeds in the following steps:

1. **Collect dimension values.** For each dimension in the effective set (always including `type`, plus any dimensions listed in `keys`), extract the relevant value:
   - `type`: the string value of the `type` field.
   - `queue`: the string value of the `queue` field.
   - `args`: if `args_keys` is provided, construct an object containing only the specified keys and their values from `args`, preserving original types. If `args_keys` is not provided, use the entire `args` value.
   - `meta`: construct an object containing only the keys listed in `meta_keys` and their values from `meta`, preserving original types.

2. **Canonicalize.** Serialize the collected dimensions into a canonical form:
   - Construct a JSON object where each key is the dimension name (`"type"`, `"queue"`, `"args"`, `"meta"`) and each value is the extracted value from step 1.
   - Sort object keys lexicographically at every level of nesting.
   - Serialize to a JSON string with no whitespace (compact form).
   - Use the serialization rules from [RFC 8785 (JSON Canonicalization Scheme)](https://www.rfc-editor.org/rfc/rfc8785) for deterministic number and string representation.

3. **Hash.** Compute a cryptographic hash of the canonical JSON string.

4. **Encode.** Encode the hash as a lowercase hexadecimal string.

### 4.2 Normative Requirements

Implementations MUST use a deterministic hash function for uniqueness key computation.

**Rationale:** A non-deterministic hash would cause identical jobs to produce different keys across enqueue calls, completely defeating deduplication.

Implementations SHOULD use SHA-256 as the hash function.

**Rationale:** SHA-256 provides a good balance of collision resistance, performance, and universal availability across programming languages. It is not chosen for cryptographic security (there is no adversarial threat model here) but for its determinism, uniform distribution, and ubiquitous library support. Implementations MAY use other deterministic hash functions (e.g., xxHash, BLAKE3) if they document the choice, but SHA-256 is the recommended default for interoperability.

Implementations MUST sort object keys lexicographically at every level of nesting when canonicalizing.

**Rationale:** JSON object key ordering is not guaranteed by RFC 8259. Without deterministic ordering, `{"a":1,"b":2}` and `{"b":2,"a":1}` would produce different hashes despite representing identical data. Lexicographic sorting is the simplest unambiguous ordering.

Implementations MUST normalize Unicode strings to NFC form before hashing.

**Rationale:** The same logical string can have multiple Unicode representations (e.g., "e" followed by combining acute accent vs. precomposed "e-acute"). Without normalization, semantically identical arguments would produce different fingerprints.

### 4.3 Example Computation

Given a job:

```json
{
  "type": "email.send",
  "queue": "notifications",
  "args": {
    "user_id": 42,
    "template": "welcome",
    "locale": "en-US"
  },
  "meta": {
    "tenant_id": "acme",
    "trace_id": "abc123"
  }
}
```

With a `UniquePolicy`:

```json
{
  "keys": ["type", "queue", "args"],
  "args_keys": ["user_id"]
}
```

**Step 1 -- Collect dimension values:**

- `type`: `"email.send"`
- `queue`: `"notifications"`
- `args`: `{"user_id": 42}` (filtered to `args_keys`)

**Step 2 -- Canonicalize:**

Construct the canonical object (keys sorted lexicographically):

```json
{"args":{"user_id":42},"queue":"notifications","type":"email.send"}
```

**Step 3 -- Hash (SHA-256):**

```
SHA-256("{"args":{"user_id":42},"queue":"notifications","type":"email.send"}")
= "b89a6e7c3f2d1e4a5b8c9d0e1f2a3b4c5d6e7f8091a2b3c4d5e6f7081929a3b"
```

(Illustrative; actual hash value will differ.)

**Step 4 -- Encode:**

The uniqueness key is the lowercase hex string: `"b89a6e7c3f2d1e4a5b8c9d0e1f2a3b4c5d6e7f8091a2b3c4d5e6f7081929a3b"`.

---

## 5. Conflict Resolution Strategies

When a job is enqueued with a `UniquePolicy` and a duplicate is detected (an existing job in a matching state produces the same uniqueness key), the `on_conflict` strategy determines what happens.

### 5.1 `reject`

Return an error to the caller. The new job is NOT enqueued.

Implementations MUST return an HTTP `409 Conflict` status (for the HTTP protocol binding) with the standard `duplicate` error code.

**Rationale:** `reject` is the safest default. It makes duplicates visible to the caller, who can then decide how to proceed. Silent discard (`ignore`) can mask bugs; `replace` can cause data loss if the existing job has accumulated state (retries, partial progress). Explicit rejection forces the caller to handle the duplicate case.

The error response SHOULD include the existing job's `id` to aid debugging.

**Response example (HTTP binding):**

```json
{
  "error": {
    "code": "duplicate",
    "message": "A job matching the uniqueness key already exists",
    "retryable": false,
    "details": {
      "existing_job_id": "019078a3-b5c7-7def-8a12-3456789abcde",
      "existing_job_state": "active",
      "uniqueness_key": "b89a6e7c..."
    }
  }
}
```

### 5.2 `replace`

Remove the existing job and enqueue the new one in its place.

The existing job MUST be transitioned to the `cancelled` state before the new job is inserted.

**Rationale:** Cancelling rather than hard-deleting preserves audit trail and allows event emission. The `job.cancelled` event provides observability into replaced jobs.

Implementations MUST NOT replace a job that is in the `active` state unless the implementation supports strong uniqueness (see Section 8). For best-effort implementations, replacing an active job risks data corruption if the worker is mid-execution.

**Rationale:** An active job may have side effects in progress (HTTP requests sent, database rows written). Replacing it without the worker's knowledge creates an inconsistency: the worker thinks it is executing job A, but job A no longer exists in the system. Strong implementations that use database constraints can handle this atomically; best-effort implementations cannot.

If the existing job is `active` and the implementation does not support strong uniqueness, the implementation MUST fall back to `reject` behavior and return an error indicating that the active job cannot be replaced.

**Use case:** A user updates their profile picture. The latest `resize.avatar` job should always win; any previously enqueued-but-not-yet-started job for the same user is obsolete.

**Example:**

```json
{
  "type": "resize.avatar",
  "args": { "user_id": 42, "image_url": "https://cdn.example.com/new-photo.jpg" },
  "unique": {
    "keys": ["type", "args"],
    "args_keys": ["user_id"],
    "on_conflict": "replace"
  }
}
```

### 5.3 `replace_except_schedule`

Replace the existing job's arguments and metadata with the new job's values, but preserve the original job's `scheduled_at` timestamp.

This strategy is only meaningful for jobs in the `scheduled` state. For non-scheduled jobs, it behaves identically to `replace`.

**Rationale:** This strategy addresses the pattern where a scheduled job's data needs updating but its execution time should remain as originally planned. For example, a `daily.report` job scheduled for 9:00 AM should retain its schedule even if the report parameters change.

**Use case:** A scheduled notification job is updated with new content, but should still fire at its originally scheduled time.

**Example:**

```json
{
  "type": "notification.send",
  "args": { "user_id": 42, "message": "Updated message content" },
  "options": {
    "scheduled_at": "2026-02-12T15:00:00Z",
    "unique": {
      "keys": ["type", "args"],
      "args_keys": ["user_id"],
      "on_conflict": "replace_except_schedule"
    }
  }
}
```

If a `notification.send` job for `user_id: 42` already exists and is scheduled for `2026-02-12T14:00:00Z`, the job's arguments are updated to the new message content, but the `scheduled_at` remains `2026-02-12T14:00:00Z`.

### 5.4 `ignore`

Silently discard the new job without enqueueing it. Return a successful response containing the existing job's `id`.

Implementations MUST return an HTTP `200 OK` status (not `201 Created`) to distinguish from a newly created job.

**Rationale:** The `200` vs. `201` distinction allows callers to detect that their job was deduplicated, even in the `ignore` case. Callers who need the existing job's ID (e.g., to poll for completion) receive it in the response.

The response MUST include the existing job's `id` and SHOULD include its current `state`.

**Response example (HTTP binding):**

```json
{
  "job": {
    "id": "019078a3-b5c7-7def-8a12-3456789abcde",
    "type": "email.send",
    "state": "available"
  },
  "deduplicated": true
}
```

**Use case:** Multiple microservices may attempt to enqueue the same `invoice.generate` job for the same order. The first one wins; subsequent attempts are harmless no-ops.

---

## 6. State Filtering

The `states` field in `UniquePolicy` controls which existing job states are considered when checking for duplicates. A job in a state not listed in `states` is invisible to the uniqueness check.

### 6.1 Default States

When `states` is omitted, the default set is:

```json
["available", "active", "scheduled", "retryable", "pending"]
```

This means a new job is considered a duplicate only if an existing job with the same uniqueness key is in one of these five transitive (non-terminal) states.

**Rationale:** Terminal states (`completed`, `cancelled`, `discarded`) are excluded by default because a completed job represents finished work. Enqueueing a new instance of the same job after the previous one has completed is normal and expected behavior. If terminal states were included by default, a job could never be re-enqueued after completion, which would break common patterns like periodic report generation.

### 6.2 Configurable States

Callers MAY override the default by providing an explicit `states` array. The valid state values are the eight OJS lifecycle states:

- `scheduled`
- `available`
- `pending`
- `active`
- `completed`
- `retryable`
- `cancelled`
- `discarded`

Implementations MUST reject `states` arrays containing invalid state names.

**Rationale:** Accepting unknown state names silently would allow typos to disable deduplication against specific states without any indication to the developer.

### 6.3 Including Terminal States

Including `completed` or `discarded` in `states` creates a stronger deduplication window that persists even after a job finishes.

**Example:** Prevent re-sending a welcome email even after the first one completes:

```json
{
  "type": "email.send_welcome",
  "args": { "user_id": 42 },
  "unique": {
    "keys": ["type", "args"],
    "args_keys": ["user_id"],
    "states": ["available", "active", "scheduled", "retryable", "pending", "completed"],
    "period": "P7D",
    "on_conflict": "ignore"
  }
}
```

This policy ensures that a welcome email for `user_id: 42` is sent at most once in any 7-day window, even if the job completes successfully.

### 6.4 Narrow State Filtering

Callers MAY use narrow state filters for specific patterns:

**Only check against scheduled jobs:**

```json
{
  "states": ["scheduled"]
}
```

This allows a new job to be enqueued even if an identical job is currently active, but prevents scheduling a duplicate when one is already waiting to run.

---

## 7. TTL / Period Semantics

The `period` field defines a time window during which the uniqueness constraint is active. It uses [ISO 8601 duration](https://en.wikipedia.org/wiki/ISO_8601#Durations) format.

### 7.1 Behavior

When `period` is set:

- The uniqueness constraint begins at the existing job's `created_at` timestamp.
- The constraint expires at `created_at + period`.
- After expiry, a new job with the same fingerprint is permitted regardless of the existing job's state.

When `period` is `null` or omitted:

- The uniqueness constraint has no time limit.
- The constraint remains active as long as the existing job is in one of the checked `states`.
- Once the existing job transitions to a state not in `states`, the constraint is released.

### 7.2 Normative Requirements

Implementations MUST evaluate the period relative to the existing job's `created_at` timestamp, not the current enqueue attempt's timestamp.

**Rationale:** Using the existing job's `created_at` provides a predictable, anchored window. If the period were relative to the new enqueue attempt, the effective uniqueness window would shift with each rejected attempt, creating confusing behavior.

Implementations MUST use [ISO 8601 duration format](https://en.wikipedia.org/wiki/ISO_8601#Durations) for the `period` field.

**Rationale:** ISO 8601 durations are unambiguous, language-agnostic, and well-supported by standard libraries. Using milliseconds (as some systems do) is more compact but less readable and more error-prone for longer durations (e.g., `"P30D"` vs. `2592000000`).

### 7.3 Common Periods

| Duration | ISO 8601 | Use Case |
|----------|----------|----------|
| 5 minutes | `PT5M` | Debounce rapid-fire events |
| 1 hour | `PT1H` | Prevent duplicate notifications |
| 24 hours | `P1D` | Daily report generation |
| 7 days | `P7D` | Weekly digest deduplication |
| 30 days | `P30D` | Monthly billing job protection |

### 7.4 Interaction with State Transitions

The `period` and `states` constraints work together with AND semantics:

A new job is considered a duplicate **if and only if**:

1. An existing job with the same uniqueness key exists, **AND**
2. The existing job is in one of the listed `states`, **AND**
3. The existing job's `created_at + period` has not yet elapsed (or `period` is null).

If any of these conditions is false, the new job is not a duplicate and is enqueued normally.

---

## 8. Strength Levels and Conformance

OJS acknowledges that uniqueness guarantees vary based on backend capabilities. Rather than mandating a specific implementation strategy, the spec defines two strength levels and requires implementations to declare which they provide.

### 8.1 Strong Uniqueness

A **strong** uniqueness implementation guarantees that no two jobs with the same uniqueness key can coexist in the checked states, even under concurrent enqueue attempts.

Strong implementations typically use one of:

- **Database unique constraint or index** (e.g., a partial unique index on the uniqueness key column, scoped to non-terminal states). This is the approach used by Oban Pro and later versions of River.
- **Atomic compare-and-set** (e.g., Redis `SET NX` with the uniqueness key, or an RDBMS `INSERT ... ON CONFLICT`). This is the approach used by Asynq's deterministic `TaskID`.
- **Serializable transactions** that encompass both the duplicate check and the insert.

Strong uniqueness MUST guarantee: if two concurrent enqueue calls arrive with the same uniqueness fingerprint, exactly one succeeds and the other observes the conflict (receiving the appropriate `on_conflict` behavior).

### 8.2 Best-Effort Uniqueness

A **best-effort** uniqueness implementation minimizes duplicates but does not guarantee prevention under all concurrent conditions.

Best-effort implementations typically use one of:

- **Query-then-insert** with a possible race window between the existence check and the insert. This is the approach used by Oban's open-source version.
- **Advisory locks** that serialize uniqueness checks but may have edge cases during lock contention or network partitions.
- **TTL-based locks** (e.g., a Redis key with an expiry) where the lock may expire prematurely under clock skew or slow operations.

Best-effort uniqueness acknowledges: under high concurrency, it is possible (though unlikely in practice) for two jobs with the same uniqueness fingerprint to coexist briefly. The implementation takes reasonable steps to prevent this (e.g., using transactions, narrow race windows) but does not provide an absolute guarantee.

### 8.3 Conformance Declaration

Implementations MUST declare their uniqueness strength level in the OJS conformance manifest.

**Rationale:** Users cannot make informed decisions about their deduplication strategy without knowing the strength of the guarantee. A payment processing system that requires exactly-once job creation needs strong uniqueness; a notification system where occasional duplicates are tolerable can accept best-effort.

The manifest declaration:

```json
{
  "ojs_version": "1.0.0-rc.1",
  "implementation": {
    "name": "ojs-backend-redis",
    "version": "1.0.0",
    "language": "go"
  },
  "conformance_level": 4,
  "capabilities": {
    "unique_jobs": {
      "strength": "strong",
      "mechanism": "Redis SET NX with Lua script atomicity"
    }
  }
}
```

The `strength` field MUST be one of: `"strong"` or `"best-effort"`.

Implementations SHOULD include a `mechanism` field (free-form string) describing the underlying technique, to aid users in understanding the trade-offs.

### 8.4 Conformance Requirements by Strength Level

Both strength levels MUST:

- Support all four `on_conflict` strategies (`reject`, `replace`, `replace_except_schedule`, `ignore`).
- Support all uniqueness dimensions (`type`, `queue`, `args`, `meta`).
- Support `args_keys` and `meta_keys` for selective dimension filtering.
- Support `period` (ISO 8601 duration) for time-windowed uniqueness.
- Support configurable `states` for state-scoped uniqueness.
- Compute uniqueness keys using the algorithm defined in Section 4.
- Validate `UniquePolicy` at enqueue time and reject invalid policies.

Strong implementations MUST additionally:

- Guarantee that concurrent enqueue calls with the same uniqueness key never both succeed (when `on_conflict` is `reject`).
- Guarantee that `replace` atomically cancels the existing job and inserts the new one, with no window where neither or both exist.

Best-effort implementations MUST additionally:

- Document the known race conditions and their likelihood.
- Provide guidance on how users can mitigate duplicate risk (e.g., idempotent handlers).

---

## 9. Interaction with Retry

Retrying jobs interact with uniqueness in ways that require careful definition.

### 9.1 Does a Retrying Job Count as a Duplicate?

A job in the `retryable` state is included in the default `states` set. This means that, by default, a new job with the same uniqueness fingerprint will be treated as a duplicate if an existing job with that fingerprint is awaiting retry.

**Rationale:** A retrying job is still "in-flight" -- it has not succeeded and has not been permanently discarded. Allowing a duplicate to be enqueued while the original is retrying would result in two instances of the same logical work being processed, potentially concurrently if the retry fires while the duplicate is executing.

### 9.2 Retry Does Not Re-check Uniqueness

When a job transitions from `retryable` back to `available` (i.e., the retry fires), the implementation MUST NOT re-evaluate the uniqueness constraint.

**Rationale:** The job has already been admitted to the system. Re-checking uniqueness on retry would create a situation where a job that was accepted could later be silently discarded -- a confusing and dangerous behavior. Uniqueness is an enqueue-time check only.

### 9.3 Exhausted Retries and Uniqueness Release

When a job exhausts its retries and transitions to the `discarded` state, the uniqueness constraint is released (assuming `discarded` is not in the `states` set, which it is not by default).

This means a new job with the same fingerprint can be enqueued after the original has been permanently discarded.

**Example flow:**

1. Job A (`email.send`, `user_id: 42`) is enqueued. Uniqueness key is claimed.
2. Job A fails and enters `retryable`. Uniqueness key remains claimed (retryable is in default states).
3. New enqueue attempt for `email.send`, `user_id: 42` is rejected as a duplicate.
4. Job A exhausts retries, transitions to `discarded`. Uniqueness key is released.
5. New enqueue attempt for `email.send`, `user_id: 42` succeeds.

---

## 10. Complete Examples

### 10.1 Simple Type-Level Deduplication

Prevent duplicate `report.daily` jobs regardless of arguments:

```json
{
  "type": "report.daily",
  "args": { "date": "2026-02-12", "format": "pdf" },
  "options": {
    "unique": {
      "keys": ["type"],
      "on_conflict": "ignore"
    }
  }
}
```

The uniqueness key is computed from `type` alone. Only one `report.daily` job can exist in non-terminal states at any time. Subsequent enqueue attempts return the existing job's ID without error.

### 10.2 Args-Based Deduplication

Prevent duplicate `email.send_welcome` jobs for the same user, but allow different users:

```json
{
  "type": "email.send_welcome",
  "args": { "user_id": 42, "locale": "en-US" },
  "options": {
    "unique": {
      "keys": ["type", "args"],
      "args_keys": ["user_id"],
      "on_conflict": "reject"
    }
  }
}
```

The uniqueness key includes `type` and the `user_id` value from `args`. A second `email.send_welcome` for `user_id: 42` is rejected with `409 Conflict`. An `email.send_welcome` for `user_id: 99` is allowed.

### 10.3 Time-Windowed Deduplication

Allow the same notification job to be enqueued at most once per hour:

```json
{
  "type": "notification.push",
  "args": { "user_id": 42, "event": "new_comment" },
  "options": {
    "unique": {
      "keys": ["type", "args"],
      "args_keys": ["user_id", "event"],
      "period": "PT1H",
      "on_conflict": "ignore"
    }
  }
}
```

If a `notification.push` job for `user_id: 42` and `event: "new_comment"` was created within the last hour, the new attempt is silently discarded. After one hour from the existing job's `created_at`, the constraint expires and a new job is permitted.

### 10.4 Queue-Scoped Deduplication

Deduplicate within a specific queue but allow the same job on different queues:

```json
{
  "type": "image.resize",
  "queue": "thumbnails",
  "args": { "image_id": "img_abc123", "size": "256x256" },
  "options": {
    "unique": {
      "keys": ["type", "queue", "args"],
      "args_keys": ["image_id"],
      "on_conflict": "replace"
    }
  }
}
```

An `image.resize` for `image_id: "img_abc123"` on the `"thumbnails"` queue replaces any existing job for the same image on that queue. The same image on a different queue (e.g., `"full-size"`) is treated as distinct work.

### 10.5 Deduplication with Terminal State Awareness

Prevent re-processing of successfully completed work within a window:

```json
{
  "type": "invoice.generate",
  "args": { "order_id": "order_12345" },
  "options": {
    "unique": {
      "keys": ["type", "args"],
      "args_keys": ["order_id"],
      "states": ["available", "active", "scheduled", "retryable", "pending", "completed"],
      "period": "P1D",
      "on_conflict": "ignore"
    }
  }
}
```

This prevents generating duplicate invoices for the same order within 24 hours, even after the first invoice job completes successfully.

### 10.6 Replace-Except-Schedule for Scheduled Jobs

Update a scheduled job's arguments without changing its execution time:

```json
{
  "type": "digest.send",
  "args": { "user_id": 42, "items": ["item_1", "item_2", "item_3"] },
  "options": {
    "scheduled_at": "2026-02-12T18:00:00Z",
    "unique": {
      "keys": ["type", "args"],
      "args_keys": ["user_id"],
      "on_conflict": "replace_except_schedule"
    }
  }
}
```

If a `digest.send` for `user_id: 42` is already scheduled for `2026-02-12T17:00:00Z`, the job's `items` are updated to include the new items, but the execution time remains `17:00:00Z` rather than being changed to `18:00:00Z`.

### 10.7 Metadata-Based Deduplication

Deduplicate by tenant in a multi-tenant system:

```json
{
  "type": "cache.warm",
  "args": { "resource": "products" },
  "meta": { "tenant_id": "acme", "region": "us-east-1" },
  "options": {
    "unique": {
      "keys": ["type", "args", "meta"],
      "meta_keys": ["tenant_id"],
      "on_conflict": "ignore"
    }
  }
}
```

This allows one `cache.warm` for `products` per tenant. Tenant `"acme"` and tenant `"globex"` can each have their own cache warming job, but duplicate warming jobs within the same tenant are suppressed.

---

## 11. Prior Art

This specification draws directly from the design choices and hard-won lessons of existing job processing systems.

### 11.1 Oban (Elixir)

Oban provides the richest uniqueness model in the ecosystem, with multi-dimensional uniqueness spanning `worker`, `queue`, `args`, `period`, and `states`. Oban also supports `keys` for selecting specific argument fields. The OJS `UniquePolicy` structure is modeled closely on Oban's approach.

However, Oban's open-source implementation checks for existing jobs with a `SELECT` query and then inserts, creating a race window under concurrent enqueue calls. Oban Pro closes this gap with a database constraint-based approach. This dual-implementation reality directly inspired OJS's two-tier strength model (Section 8).

**Adopted:** Multi-dimensional uniqueness, args key selection, state filtering, period-based TTL.
**Adapted:** OJS adds `meta_keys`, defines explicit canonicalization, and formalizes strength levels.

### 11.2 River (Go)

River's evolution from advisory-lock-based uniqueness to index-based uniqueness across its release history demonstrates the difficulty of getting deduplication right. River's unique jobs support scoping by `args`, `period`, `queue`, and `state`, and offers both `ByArgs` and `ByPeriod` scoping options.

**Adopted:** The lesson that uniqueness implementation will evolve; spec should allow for both approaches.
**Adapted:** OJS formalizes the strength distinction that River discovered empirically.

### 11.3 Graphile Worker (Node.js)

Graphile Worker takes a different approach: an explicit `job_key` string (user-provided, not computed) with three conflict modes: `replace` (update the job), `preserve_run_at` (update but keep schedule), and `unsafe_dedupe` (skip if exists).

**Adopted:** The `replace_except_schedule` conflict mode (Graphile's `preserve_run_at`). The concept that users may want to preserve scheduling even when updating job data.

### 11.4 BullMQ (Node.js)

BullMQ offers two deduplication mechanisms: custom `jobId` (where the user controls the ID, making it inherently unique) and an explicit deduplication API with throttle and debounce modes. BullMQ's `jobId` approach is simple and effective but pushes the burden of key computation to the user.

**Adopted:** The recognition that simple ID-based deduplication (user-provided keys) is a valid pattern. OJS supports this implicitly: a user can set `keys: ["type", "args"]` with carefully chosen `args_keys` to achieve the same effect.

### 11.5 Asynq (Go)

Asynq provides the clearest example of the strong-vs-best-effort distinction. Its deterministic `TaskID` provides guaranteed uniqueness (the ID is the deduplication key, enforced by Redis's data structures). Its `Unique` option provides best-effort uniqueness via TTL-based locks that may expire under adverse conditions. Asynq documents both mechanisms with clear trade-off descriptions.

**Adopted:** The explicit strong-vs-best-effort distinction and the requirement to declare which level is provided (Section 8).

### 11.6 Faktory (Polyglot)

Faktory uses a hash of `jobtype` + `args` with a `unique_for` TTL (in seconds). It is simple and effective but limited: no selective args filtering, no state scoping, no conflict resolution options beyond rejection. Faktory gates unique jobs to its Enterprise tier.

**Adopted:** The jobtype+args hash as the foundation of key computation.
**Extended:** OJS adds selective args, queue scoping, meta scoping, state filtering, multiple conflict strategies, and ISO 8601 durations instead of integer seconds.

---

## 12. Security Considerations

The uniqueness key is derived from job arguments, which may contain sensitive data. Implementations SHOULD ensure that uniqueness keys (which are hashes of argument data) are stored with the same access controls as the job data itself. The use of a cryptographic hash function (SHA-256) ensures that the original argument values cannot be recovered from the uniqueness key alone.

Implementations MUST NOT log uniqueness keys at a verbosity level higher than DEBUG, as the keys are derived from potentially sensitive job arguments.

---

## 13. JSON Schema

The normative JSON Schema for the `UniquePolicy` object:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://openjobspec.org/schemas/v1/unique-policy.json",
  "title": "OJS UniquePolicy",
  "description": "Defines the deduplication policy for a job at enqueue time.",
  "type": "object",
  "properties": {
    "keys": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": ["type", "queue", "args", "meta"]
      },
      "uniqueItems": true,
      "default": ["type"],
      "description": "Dimensions that define the uniqueness fingerprint."
    },
    "args_keys": {
      "type": "array",
      "items": { "type": "string" },
      "uniqueItems": true,
      "description": "Top-level keys within args to include in the fingerprint. If omitted, all of args is included."
    },
    "meta_keys": {
      "type": "array",
      "items": { "type": "string" },
      "uniqueItems": true,
      "minItems": 1,
      "description": "Top-level keys within meta to include in the fingerprint. Required when 'meta' is in keys."
    },
    "period": {
      "type": "string",
      "pattern": "^P(?:\\d+Y)?(?:\\d+M)?(?:\\d+W)?(?:\\d+D)?(?:T(?:\\d+H)?(?:\\d+M)?(?:\\d+(?:\\.\\d+)?S)?)?$",
      "description": "ISO 8601 duration for the uniqueness window."
    },
    "states": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": ["scheduled", "available", "pending", "active", "completed", "retryable", "cancelled", "discarded"]
      },
      "uniqueItems": true,
      "default": ["available", "active", "scheduled", "retryable", "pending"],
      "description": "Job states to check against when detecting duplicates."
    },
    "on_conflict": {
      "type": "string",
      "enum": ["reject", "replace", "replace_except_schedule", "ignore"],
      "default": "reject",
      "description": "Strategy for handling a detected duplicate."
    }
  },
  "additionalProperties": false,
  "if": {
    "properties": {
      "keys": {
        "contains": { "const": "meta" }
      }
    }
  },
  "then": {
    "required": ["meta_keys"]
  }
}
```

---

## 14. Conformance Test Requirements

Conformance tests for unique jobs are part of the Level 4 (Advanced) test suite. The following scenarios MUST be tested:

1. **Basic deduplication:** Enqueue two identical jobs with `on_conflict: "reject"`. The second MUST be rejected with `409 Conflict`.
2. **Args-key filtering:** Enqueue two jobs with the same `args_keys` values but different non-key args. The second MUST be treated as a duplicate.
3. **Period expiry:** Enqueue a job with a short `period`. After the period elapses, enqueue the same job again. The second MUST succeed.
4. **State filtering:** Enqueue a job, transition it to `completed`. Enqueue the same job again with default `states`. The second MUST succeed (completed is not in default states).
5. **State filtering with terminal states:** Enqueue a job with `states` including `"completed"`. Complete the job. Enqueue again. The second MUST be treated as a duplicate.
6. **Replace strategy:** Enqueue a job with `on_conflict: "replace"`. Enqueue a duplicate. The original MUST be cancelled and the new job MUST be enqueued.
7. **Ignore strategy:** Enqueue a job with `on_conflict: "ignore"`. Enqueue a duplicate. The response MUST return `200 OK` with the original job's ID and `"deduplicated": true`.
8. **Queue scoping:** Enqueue a job with `keys: ["type", "queue"]` on queue `"a"`. Enqueue the same type on queue `"b"`. The second MUST succeed (different queue).
9. **Invalid policy rejection:** Enqueue a job with `keys: ["meta"]` but no `meta_keys`. The request MUST be rejected with `400 Bad Request`.
10. **Retry interaction:** Enqueue a job. Let it fail and enter `retryable`. Enqueue a duplicate. The second MUST be treated as a duplicate.

For strong implementations, additional concurrency tests:

11. **Concurrent enqueue:** Send N concurrent enqueue requests for the same uniqueness key with `on_conflict: "reject"`. Exactly one MUST succeed; all others MUST receive `409 Conflict`.

---

## Appendix A: Design Decisions and Alternatives Considered

### A.1 Why Not User-Provided Uniqueness Keys?

Some systems (Graphile Worker's `job_key`, BullMQ's `jobId`) let users provide an arbitrary string as the uniqueness key. This is simpler but error-prone: users must ensure key generation is deterministic and collision-free. OJS computes the key from declared dimensions, which is more structured and less susceptible to accidental collisions from key formatting differences.

Implementations MAY additionally support user-provided uniqueness keys as an extension, but the canonical OJS mechanism is dimension-based computation.

### A.2 Why SHA-256 Instead of a Faster Hash?

SHA-256 is slower than non-cryptographic alternatives (xxHash, FNV) but provides stronger collision resistance and is available in every standard library across every major programming language. Since uniqueness key computation happens once per enqueue (not on a hot path), the performance difference is negligible. The interoperability benefit of a universally available hash function outweighs the microsecond-level performance gain of a faster alternative.

### A.3 Why ISO 8601 Durations Instead of Milliseconds?

Integer milliseconds are compact and unambiguous, but ISO 8601 durations are human-readable and self-documenting. `"PT1H"` is immediately understandable as "one hour"; `3600000` requires mental conversion. Since the `period` field is authored by humans in configuration and job definitions, readability is prioritized. Implementations MUST parse ISO 8601 durations and MAY additionally accept integer seconds or milliseconds as a convenience extension.

### A.4 Why `type` Is Always Included

Early drafts allowed `keys: ["args"]` without `type`, which would make all jobs with the same arguments collide regardless of type. This was identified as a footgun with no legitimate use case. Including `type` implicitly eliminates an entire class of misconfiguration.

---

*Open Job Spec v1.0.0-rc.1 -- Unique Jobs / Deduplication -- 2026-02-12*
*https://openjobspec.org*
