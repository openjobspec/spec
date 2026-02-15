# Open Job Spec -- Conformance Levels and Requirements

**OJS Conformance Specification**

| Field        | Value                              |
|--------------|------------------------------------|
| **Version**  | 1.0.0-rc.1                         |
| **Date**     | 2025-06-01                         |
| **Status**   | Release Candidate                  |
| **Layer**    | Cross-cutting (applies to all layers) |
| **Requires** | OJS Core Specification (Layer 1)   |
| **License**  | Apache 2.0                         |

---

## 1. Introduction

This document defines the **conformance levels**, **conformance tiers**, **testing methodology**, and **badge program** for Open Job Spec (OJS) implementations. It specifies the requirements an implementation MUST satisfy to claim conformance at a given level and tier, and it defines the language-agnostic test suite format used to verify those claims.

### 1.1 Why Conformance Testing Matters

Interoperability is the core promise of any open standard. A specification without a conformance program is a suggestion; a specification with a conformance program is a contract. When an implementation declares "OJS Conformant Level 2, Runtime Tier," operators and integrators can rely on a specific, testable set of behaviors.

The history of open standards teaches this lesson repeatedly:

- **OpenAPI** never shipped a formal conformance test suite. The result: tools claiming OpenAPI 3.0 support interpret edge cases differently, producing subtly incompatible outputs. Developers cannot trust that two "OpenAPI-compliant" tools will agree on the same document.
- **GraphQL** published a precise specification with formal grammar, yet did not ship a language-agnostic conformance test suite alongside it. The community built ad hoc test suites years later, but fragmentation had already taken root. Server libraries still disagree on nullable field coercion, subscription transport, and error formatting.
- **OpenTelemetry** defined extensive semantic conventions and wire protocols, but conformance testing lagged behind specification work. The result: instrumentation libraries that pass their own unit tests but produce traces that confuse backends expecting stricter adherence.

All three communities have publicly acknowledged that shipping conformance tests alongside the specification -- not as an afterthought -- would have prevented years of interoperability friction. OJS treats conformance testing as a first-class deliverable, not a future aspiration.

### 1.2 Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt) and [RFC 8174](https://www.ietf.org/rfc/rfc8174.txt).

Every MUST requirement in this document includes a rationale explaining why the requirement is mandatory rather than optional. Requirements without sufficient justification for MUST are expressed as SHOULD or MAY.

### 1.3 Scope

This document covers:

1. **Conformance levels** (Levels 0 through 4): what capabilities an implementation supports.
2. **Conformance tiers** (Parser, Runtime, Full): what depth of implementation is provided.
3. **Conformance manifest**: the machine-readable declaration of an implementation's conformance claims.
4. **Test suite format**: the language-agnostic JSON test case structure.
5. **Badge program**: how implementations advertise their conformance status.
6. **Test suite versioning**: how the test suite evolves alongside the specification.

This document does not define the OJS job envelope, lifecycle, operations, or wire formats. Those are defined in the Core Specification (Layer 1), Wire Format Encodings (Layer 2), and Protocol Bindings (Layer 3). This document defines how to verify that an implementation correctly implements those specifications.

---

## 2. Conformance Levels

OJS defines five conformance levels, numbered 0 through 4. Each level builds on the previous: **an implementation declaring Level N MUST support all capabilities of Levels 0 through N**.

**Rationale**: Layered conformance allows the ecosystem to include both simple, lightweight implementations (an in-memory queue that supports Level 0) and full-featured production systems (a Redis-backed implementation supporting Level 4). Without layered conformance, the specification would either set the bar too low (making the "conformant" label meaningless) or too high (excluding simple implementations that serve valid use cases).

| Level | Name              | Description                                                                                  |
|-------|-------------------|----------------------------------------------------------------------------------------------|
| 0     | **Core**          | Enqueue, dequeue, execute, succeed/fail. The absolute minimum viable job processing system.  |
| 1     | **Reliable**      | At-least-once delivery, retries with backoff, dead letter queue, heartbeat, visibility timeout. |
| 2     | **Scheduled**     | Delayed jobs, cron/recurring jobs, job expiration (TTL).                                     |
| 3     | **Orchestration** | Workflow primitives: chain, group, batch.                                                    |
| 4     | **Advanced**      | Priority queues, rate limiting, unique jobs (deduplication), batch operations, pause/resume.  |

### 2.1 Level 0: Core

Level 0 defines the absolute minimum a system MUST implement to be called an OJS implementation. A Level 0 implementation can enqueue jobs, assign them to workers, execute them, and report success or failure.

#### 2.1.1 Job Envelope (L0-ENV)

**L0-ENV-001**: Implementations MUST support the OJS job envelope with the five required attributes: `specversion`, `id`, `type`, `queue`, and `args`.

**Rationale**: These five fields are the irreducible minimum for cross-system interoperability. Without `specversion`, parsers cannot determine which version of the specification governs the envelope. Without `id`, there is no way to correlate, deduplicate, or query a job. Without `type`, workers cannot route the job to the correct handler. Without `queue`, the job has no destination. Without `args`, the handler has no input data. Removing any one of these fields makes the envelope ambiguous or unusable.

**L0-ENV-002**: Implementations MUST generate a UUIDv7 identifier for the `id` field when the client does not provide one.

**Rationale**: UUIDv7 provides time-ordered, globally unique identifiers without coordination. Time-ordering enables efficient database indexing and natural chronological sorting. Global uniqueness without a central authority is essential for distributed systems where multiple producers enqueue jobs concurrently.

**L0-ENV-003**: Implementations MUST validate that `type` is a non-empty, dot-namespaced string matching the pattern `^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)*$`.

**Rationale**: The type field is the routing key for job dispatch. An empty or malformed type cannot be routed. The dot-namespace pattern prevents naming collisions across teams and organizations (e.g., `billing.invoice.generate` vs. `reports.invoice.generate`).

**L0-ENV-004**: Implementations MUST validate that `queue` matches the pattern `^[a-z0-9][a-z0-9\-\.]*$`.

**Rationale**: Restricting queue names to lowercase alphanumeric with hyphens and dots prevents case-sensitivity bugs across systems (Redis treats `Default` and `default` as different keys) and ensures queue names are safe for use in URLs, file paths, and metric labels without escaping.

**L0-ENV-005**: Implementations MUST validate that `args` is a JSON array containing only JSON-native types (string, number, boolean, null, array, object).

**Rationale**: This constraint is the foundation of cross-language interoperability. Allowing language-specific serialization formats (Python pickle, Ruby Marshal, Java ObjectInputStream) in arguments couples the job to a specific runtime and introduces remote code execution vulnerabilities during deserialization.

**L0-ENV-006**: Implementations MUST accept and preserve unknown fields in the job envelope without error.

**Rationale**: Forward compatibility requires that implementations built against an earlier version of the specification can process envelopes containing fields defined in a later version. Rejecting unknown fields would make every specification update a breaking change.

#### 2.1.2 Operations (L0-OPS)

**L0-OPS-001**: Implementations MUST support the PUSH operation (enqueue a job).

**Rationale**: Enqueuing is the fundamental producer operation. Without PUSH, no jobs enter the system.

**L0-OPS-002**: Implementations MUST support the FETCH operation (dequeue a job for execution).

**Rationale**: Fetching is the fundamental consumer operation. Without FETCH, no jobs leave the queue for processing.

**L0-OPS-003**: Implementations MUST support the ACK operation (acknowledge successful completion).

**Rationale**: Without explicit acknowledgment, the system cannot distinguish between "completed successfully" and "worker crashed mid-execution." ACK is the signal that moves a job to its terminal success state.

**L0-OPS-004**: Implementations MUST support the FAIL operation (report job failure with structured error data).

**Rationale**: Structured failure reporting is essential for debugging, retry decisions, and dead letter queue analysis. A FAIL operation that accepts only a boolean provides no actionable information; structured error data (error type, message, and optional backtrace) enables cross-language debugging.

#### 2.1.3 Job Lifecycle (L0-LC)

**L0-LC-001**: Implementations MUST implement the 8-state lifecycle: `scheduled`, `available`, `pending`, `active`, `completed`, `retryable`, `cancelled`, `discarded`.

**Rationale**: The 8-state model captures every meaningful phase of a job's existence, distilled from analysis of 12 production job processing systems. Fewer states (e.g., omitting `retryable` or `pending`) would conflate distinct operational conditions, making monitoring and debugging ambiguous. The two terminal success/failure states (`completed` and `discarded`) keep the model clean and predictable.

**L0-LC-002**: Implementations MUST enforce valid state transitions. Only the following transitions are permitted:

| From State    | To State(s)                                  |
|---------------|----------------------------------------------|
| `scheduled`   | `available`, `cancelled`                     |
| `available`   | `active`, `cancelled`                        |
| `pending`     | `available`, `cancelled`                     |
| `active`      | `completed`, `retryable`, `cancelled`, `discarded` |
| `retryable`   | `available`, `cancelled`, `discarded`        |
| `completed`   | (terminal -- no transitions out)             |
| `cancelled`   | (terminal -- no transitions out)             |
| `discarded`   | (terminal -- no transitions out)             |

**Rationale**: Unrestricted state transitions allow nonsensical operations (completing a job that was never started, retrying a job that already succeeded) that corrupt the system's invariants. Strict state transition enforcement is a precondition for reliable job processing.

**L0-LC-003**: Implementations MUST reject any state transition not listed in L0-LC-002 and MUST return a structured error indicating the current state and the attempted invalid transition.

**Rationale**: Silent acceptance of invalid transitions masks bugs. Explicit rejection with diagnostic information enables rapid debugging.

#### 2.1.4 Events (L0-EVT)

**L0-EVT-001**: Implementations MUST emit the following core lifecycle events: `job.enqueued`, `job.started`, `job.completed`, `job.failed`.

**Rationale**: Lifecycle events are the foundation of observability. Without standardized events, monitoring tools, dashboards, and alerting systems must be custom-built for each implementation. The four core events capture the minimum information needed to answer "what happened to this job?"

**L0-EVT-002**: Each event MUST include at minimum the `job_id`, `type`, `queue`, `state`, and `timestamp` fields.

**Rationale**: These fields provide enough context to correlate events to jobs, filter by type or queue, and reconstruct timelines. Omitting any of these fields makes the event insufficient for basic operational monitoring.

#### 2.1.5 Queue (L0-Q)

**L0-Q-001**: Implementations MUST support a queue named `default`.

**Rationale**: A universally agreed default queue name eliminates configuration for the simplest use cases and provides a known starting point for tutorials, documentation, and getting-started guides. Every major job processing system (Sidekiq, BullMQ, Celery, Faktory, Oban, River) uses `default` as the default queue name.

#### 2.1.6 Wire Format (L0-WF)

**L0-WF-001**: Implementations MUST support JSON as a wire format for job envelopes, conforming to the OJS JSON Wire Format Encoding specification (Layer 2).

**Rationale**: JSON is the universal interchange format. Every programming language has a JSON parser. Mandating JSON as the baseline ensures that any OJS implementation can communicate with any other, regardless of what additional wire formats they may support.

#### 2.1.7 Middleware (L0-MW)

**L0-MW-001**: Implementations MUST support enqueue middleware chains (middleware that runs before job insertion).

**Rationale**: Enqueue middleware enables cross-cutting concerns (trace context propagation, tenant isolation, argument validation) to be composed without modifying producer code. This pattern, pioneered by Sidekiq's client middleware and adopted by every major system, is essential for production use.

**L0-MW-002**: Implementations MUST support execution middleware chains (middleware that wraps job execution).

**Rationale**: Execution middleware enables cross-cutting concerns (logging, metrics, error handling, timeout enforcement) to be composed without modifying handler code. Without middleware, every handler would independently implement these concerns, leading to inconsistency and duplication.

---

### 2.2 Level 1: Reliable

Level 1 adds the reliability features necessary for production use in environments where job loss is unacceptable. A Level 1 implementation provides at-least-once delivery guarantees.

**Prerequisite**: All Level 0 requirements.

#### 2.2.1 Retry Policy (L1-RET)

**L1-RET-001**: Implementations MUST support retry policies with configurable backoff, conforming to the structured retry policy format defined in the OJS Core Specification.

**Rationale**: Retry with backoff is the fundamental reliability mechanism for transient failures. Without standardized retry configuration, every implementation invents its own format, making retry policies non-portable across implementations.

**L1-RET-002**: Implementations MUST support the following retry policy fields: `max_attempts`, `initial_interval`, `backoff_coefficient`, `max_interval`, and `jitter`.

**Rationale**: These five fields, adopted from Temporal's retry policy, represent the minimum set of knobs required for production retry strategies. Fewer fields (e.g., omitting `max_interval`) allow runaway exponential backoff. Omitting `jitter` enables thundering herd problems.

**L1-RET-003**: Implementations MUST support `non_retryable_errors` -- a list of error type strings that bypass retry and move the job directly to the `discarded` state.

**Rationale**: Not all failures are transient. A validation error or "not found" error will never succeed on retry. Without non-retryable error classification, the system wastes resources retrying jobs that can never succeed and delays their arrival in the dead letter queue.

#### 2.2.2 Dead Letter Queue (L1-DLQ)

**L1-DLQ-001**: Implementations MUST move jobs that exhaust all retry attempts to the `discarded` state (dead letter queue).

**Rationale**: Jobs that fail permanently must be preserved for inspection, debugging, and manual retry. Silently dropping failed jobs violates the at-least-once delivery guarantee and destroys diagnostic information.

**L1-DLQ-002**: Implementations MUST support listing and inspecting discarded jobs.

**Rationale**: A dead letter queue that cannot be inspected provides no value. Operators must be able to view failed jobs, examine their errors, and decide whether to retry or delete them.

#### 2.2.3 Heartbeat (L1-HB)

**L1-HB-001**: Implementations MUST support the BEAT operation (worker heartbeat).

**Rationale**: Heartbeats enable the system to detect crashed workers and requeue their in-progress jobs. Without heartbeats, a worker crash results in jobs stuck in the `active` state indefinitely, violating at-least-once delivery.

**L1-HB-002**: Implementations MUST support server-initiated state changes via heartbeat responses (at minimum: `quiet` and `terminate` signals).

**Rationale**: Graceful shutdown requires the server to signal workers to stop fetching new jobs (`quiet`) or to terminate entirely (`terminate`). Without server-initiated signals, deployments must use operating system signals (SIGTERM, SIGQUIT), which do not propagate through all runtime environments and cannot carry application-level metadata.

#### 2.2.4 Visibility Timeout (L1-VT)

**L1-VT-001**: Implementations MUST support visibility timeout (reservation period) for active jobs.

**Rationale**: The visibility timeout is the mechanism that implements at-least-once delivery. When a worker fetches a job, the job becomes invisible to other workers for a configurable period. If the worker does not ACK or FAIL within this period, the job becomes available again. Without visibility timeout, a worker crash during execution causes permanent job loss.

**L1-VT-002**: Implementations MUST automatically requeue jobs whose visibility timeout expires without an ACK or FAIL.

**Rationale**: Automatic requeue on timeout expiry is what makes the system self-healing. Manual intervention to recover from worker crashes is not acceptable in production systems.

#### 2.2.5 Cancellation (L1-CAN)

**L1-CAN-001**: Implementations MUST support the CANCEL operation, which moves a job to the `cancelled` state.

**Rationale**: Cancellation is an operational necessity. Jobs enqueued in error, jobs for deleted resources, and jobs superseded by newer requests must be removable from the queue. Without cancellation, operators must wait for jobs to execute and fail, wasting resources and potentially causing side effects.

**L1-CAN-002**: Implementations MUST support cancellation of jobs in the `scheduled`, `available`, `pending`, and `retryable` states.

**Rationale**: Cancellation is meaningful for any non-terminal, non-active state. Restricting cancellation to a subset of these states would leave operators unable to cancel jobs in certain phases of their lifecycle.

#### 2.2.6 Job Info (L1-INFO)

**L1-INFO-001**: Implementations MUST support the INFO operation, which retrieves the full current state of a job by its ID.

**Rationale**: Job inspection is essential for debugging, monitoring dashboards, and programmatic status checking. Without INFO, the only way to determine a job's state is to observe lifecycle events, which requires a persistent event consumer and does not support point-in-time queries.

#### 2.2.7 Events (L1-EVT)

**L1-EVT-001**: Implementations MUST emit `job.retrying` events when a failed job enters the `retryable` state.

**Rationale**: Retry events are critical for alerting on flaky jobs. A job that retries 24 times before succeeding indicates an underlying problem even though it eventually completes.

**L1-EVT-002**: Implementations MUST emit `job.cancelled` events when a job is cancelled.

**Rationale**: Cancellation events are necessary for audit trails and for downstream systems that may need to react to a job being cancelled (e.g., releasing reserved resources).

---

### 2.3 Level 2: Scheduled

Level 2 adds time-based scheduling capabilities: delayed execution, recurring jobs, and job expiration.

**Prerequisite**: All Level 0 and Level 1 requirements.

#### 2.3.1 Delayed Jobs (L2-DEL)

**L2-DEL-001**: Implementations MUST support the `scheduled_at` attribute, which specifies the earliest time a job may begin execution.

**Rationale**: Delayed execution is one of the most common job processing patterns (send a reminder email in 24 hours, retry a payment in 1 hour, generate a report at end of business day). Without delayed execution, producers must build their own scheduling layer on top of the job system.

**L2-DEL-002**: Implementations MUST NOT execute a job before its `scheduled_at` time.

**Rationale**: Premature execution of a scheduled job violates the producer's explicit intent. The `scheduled_at` field is a contract, not a hint.

**L2-DEL-003**: Implementations SHOULD execute a scheduled job within 1 second of its `scheduled_at` time under normal load conditions.

**Rationale**: While exact-time execution is not achievable in distributed systems (clock skew, polling intervals, queue depth), excessive delay degrades the usefulness of scheduling. A 1-second target balances precision with implementation feasibility.

#### 2.3.2 Cron / Periodic Jobs (L2-CRON)

**L2-CRON-001**: Implementations MUST support cron-based periodic job scheduling using standard 5-field cron expressions (minute, hour, day-of-month, month, day-of-week).

**Rationale**: Cron expressions are the universal language for periodic scheduling, understood by developers across all platforms and languages. Inventing a new scheduling syntax would impose a learning curve with no compensating benefit.

**L2-CRON-002**: Implementations MUST support IANA timezone names (e.g., `America/New_York`, `Europe/London`) for cron schedule evaluation.

**Rationale**: Cron schedules that ignore timezones produce incorrect results across daylight saving time transitions. A report scheduled for "09:00 America/New_York" must run at 09:00 Eastern regardless of whether EST or EDT is in effect. UTC-only cron evaluation shifts the timezone math to every producer, which is error-prone and defeats the purpose of the scheduling system.

**L2-CRON-003**: Implementations MUST prevent overlapping executions of the same cron job by default.

**Rationale**: A cron job that takes longer than its interval to execute must not spawn overlapping instances. Overlapping execution causes resource contention, duplicate side effects, and data corruption. Preventing overlap by default protects users who do not anticipate this scenario.

#### 2.3.3 Job Expiration (L2-TTL)

**L2-TTL-001**: Implementations MUST support the `expires_at` attribute, which specifies the deadline after which a job MUST NOT begin execution.

**Rationale**: Jobs have a window of relevance. A "send flash sale notification" job is worthless after the sale ends. Without expiration, stale jobs consume worker capacity and may produce confusing side effects (sending a notification about a sale that ended hours ago).

**L2-TTL-002**: Implementations MUST move expired jobs to the `discarded` state without executing them.

**Rationale**: Expired jobs must not be silently dropped -- they must be trackable in the dead letter queue for auditing and debugging. Moving them to `discarded` preserves the diagnostic trail.

#### 2.3.4 Timezone Handling (L2-TZ)

**L2-TZ-001**: Implementations MUST handle timezone-aware scheduling using IANA timezone names from the IANA Time Zone Database (commonly known as the tz database or Olson database).

**Rationale**: IANA timezone names are the only timezone representation that correctly handles historical and future changes to timezone rules, including daylight saving time transitions, government-mandated timezone changes, and leap seconds. Numeric UTC offsets (e.g., `+05:30`) are insufficient because they do not encode DST transition rules.

---

### 2.4 Level 3: Orchestration

Level 3 adds workflow composition primitives that enable multi-step job pipelines.

**Prerequisite**: All Level 0, Level 1, and Level 2 requirements.

#### 2.4.1 Chain (L3-CHAIN)

**L3-CHAIN-001**: Implementations MUST support the chain workflow primitive: a sequence of jobs executed one after another, where each job begins only after the previous job completes successfully.

**Rationale**: Sequential job pipelines are the most common workflow pattern (extract -> transform -> load, generate report -> format -> email). Without chain support, producers must implement their own sequencing logic using completion callbacks or polling, which is error-prone and non-portable.

**L3-CHAIN-002**: Implementations MUST pass the result of each completed job in a chain as input to the next job in the sequence.

**Rationale**: Data flow between pipeline stages is the primary purpose of chaining. A chain that cannot pass data between stages forces producers to use external storage for intermediate results, adding complexity and failure modes.

**L3-CHAIN-003**: Implementations MUST halt chain execution when any job in the chain fails (after exhausting retries), and MUST move the entire chain to a failed state.

**Rationale**: Continuing a chain after a step fails produces undefined behavior, since subsequent steps depend on the output of the failed step. Halting on failure and recording the failure point enables debugging and manual retry from the point of failure.

#### 2.4.2 Group (L3-GROUP)

**L3-GROUP-001**: Implementations MUST support the group workflow primitive: a set of independent jobs executed concurrently, with no ordering guarantees between them.

**Rationale**: Parallel fan-out is the second most common workflow pattern (resize an image to 5 sizes simultaneously, send notifications to multiple channels in parallel). Without group support, producers must enqueue jobs individually and build their own fan-in synchronization.

**L3-GROUP-002**: Implementations MUST track the completion status of all jobs in a group and MUST report when all jobs have reached a terminal state.

**Rationale**: Without group completion tracking, there is no way for downstream logic to know when all parallel work is done. This is the essential primitive that enables fan-in patterns.

#### 2.4.3 Batch (L3-BATCH)

**L3-BATCH-001**: Implementations MUST support the batch workflow primitive: a group of jobs with configurable callbacks that fire when all jobs succeed, when any job fails, or when all jobs reach a terminal state (regardless of outcome).

**Rationale**: Batch is group plus callbacks -- the "chord" pattern from Celery. The three callback types (on_success, on_failure, on_complete) cover the most common use cases: send a summary email when all imports succeed, alert an operator when any import fails, clean up temporary resources when all imports finish regardless of outcome.

**L3-BATCH-002**: Implementations MUST support at minimum these callback triggers: `on_complete` (all jobs terminal), `on_success` (all jobs completed successfully), and `on_failure` (at least one job failed/discarded).

**Rationale**: These three triggers cover the essential fan-in patterns. Fewer triggers (e.g., only `on_complete`) would force producers to inspect individual job statuses in every callback, duplicating logic that the system should handle.

#### 2.4.4 Data Passing (L3-DATA)

**L3-DATA-001**: Implementations MUST support passing data between workflow steps via the `result` field of completed jobs.

**Rationale**: Workflow steps that cannot share data are not a workflow -- they are just independent jobs with ordering constraints. The `result` field is the standard mechanism for a job to produce output that downstream steps can consume.

#### 2.4.5 Workflow Events (L3-WF-EVT)

**L3-WF-EVT-001**: Implementations MUST emit workflow lifecycle events: `workflow.started`, `workflow.completed`, `workflow.failed`.

**Rationale**: Workflow-level events provide aggregate observability. Without them, monitoring a multi-step pipeline requires correlating individual job events, which is error-prone and does not scale.

---

### 2.5 Level 4: Advanced

Level 4 adds advanced features that production systems commonly need but that are not universally required.

**Prerequisite**: All Level 0, Level 1, Level 2, and Level 3 requirements.

#### 2.5.1 Priority Queues (L4-PRI)

**L4-PRI-001**: Implementations MUST support job prioritization within a queue, with at minimum three named priority levels: `HIGH`, `NORMAL`, and `LOW`.

**Rationale**: Not all jobs are equally urgent. A password reset email is more time-sensitive than a weekly digest. Without priority support, operators must create separate queues for each priority level and manage worker allocation manually.

**L4-PRI-002**: Implementations MUST support numeric priority values in addition to named levels, where higher numbers indicate higher priority.

**Rationale**: Three named levels are insufficient for systems with fine-grained prioritization needs. Numeric priorities enable arbitrary ordering. The "higher is more important" convention matches human intuition and avoids the confusion caused by systems where 0 is highest priority (BullMQ) or 1 is highest (some UNIX nice-inspired systems).

**L4-PRI-003**: Implementations MUST map named priority levels to numeric values: `HIGH` = 3, `NORMAL` = 2, `LOW` = 1.

**Rationale**: Fixed numeric mappings for named levels ensure that implementations agree on the relative ordering of named priorities. Without fixed mappings, one implementation might treat `HIGH` as 10 and another as 100, causing surprising behavior when switching implementations.

#### 2.5.2 Unique Jobs / Deduplication (L4-UNIQ)

**L4-UNIQ-001**: Implementations MUST support unique job constraints based on configurable dimensions: job `type`, `queue`, and selectable fields within `args`.

**Rationale**: Deduplication prevents wasted work and duplicate side effects. A "send welcome email to user X" job should not execute twice because two requests arrived simultaneously. Configurable dimensions allow producers to define uniqueness precisely (unique per user, unique per queue, unique per type+args combination).

**L4-UNIQ-002**: Implementations MUST support at least the `reject` conflict resolution strategy (refuse to enqueue a duplicate job).

**Rationale**: `reject` is the safest default -- it prevents duplicates without modifying existing jobs. More sophisticated strategies (`replace`, `ignore`) are useful but not universally needed.

**L4-UNIQ-003**: Implementations MUST document the strength of their uniqueness guarantee: `strong` (constraint-based, no race conditions) or `best_effort` (query-based, may have race windows).

**Rationale**: Unique jobs are the hardest unsolved problem in job processing. Implementations backed by databases with constraint support can provide strong guarantees; implementations backed by Redis typically provide best-effort guarantees. Operators must know which guarantee they are getting to make informed architectural decisions.

#### 2.5.3 Batch Enqueue (L4-BULK)

**L4-BULK-001**: Implementations MUST support batch enqueue operations (enqueueing multiple jobs in a single request).

**Rationale**: Batch enqueue reduces network round trips and enables atomic insertion of related jobs. Enqueueing 1,000 jobs individually requires 1,000 round trips; batch enqueue requires one.

**L4-BULK-002**: Implementations MUST support batches of at least 1,000 jobs per request.

**Rationale**: A minimum batch size ensures that implementations advertising batch support can handle realistic workloads. A batch limit of 10 would negate most of the performance benefit.

#### 2.5.4 Queue Pause/Resume (L4-PAUSE)

**L4-PAUSE-001**: Implementations MUST support pausing a queue (stopping job delivery from that queue while allowing new jobs to be enqueued).

**Rationale**: Queue pause is an operational necessity for deployments, incident response, and debugging. When a handler has a bug, operators must be able to stop job delivery immediately without losing enqueued jobs. Pausing the queue provides this capability without the data loss risk of draining or deleting the queue.

**L4-PAUSE-002**: Implementations MUST support resuming a paused queue (restoring normal job delivery).

**Rationale**: Pause without resume is useless. Resume must restore normal delivery without manual intervention beyond the resume command itself.

#### 2.5.5 Queue Statistics (L4-STATS)

**L4-STATS-001**: Implementations MUST support retrieving queue statistics including at minimum: total jobs, jobs by state (available, active, scheduled, retryable, completed, discarded), and throughput metrics (jobs completed per time period).

**Rationale**: Queue statistics are the foundation of operational dashboards and capacity planning. Without standardized statistics, every monitoring integration must be custom-built for each implementation.

#### 2.5.6 Rate Limiting (L4-RATE)

**L4-RATE-001**: Implementations SHOULD support rate limiting on a per-queue or per-job-type basis, with at minimum a maximum concurrency limit (maximum number of simultaneously active jobs).

**Rationale**: Rate limiting is expressed as SHOULD rather than MUST because the design space is vast (concurrency limits, sliding window, token bucket, leaky bucket) and implementation complexity varies significantly by backend. However, maximum concurrency is the most commonly needed form of rate limiting and is feasible to implement on all backends.

---

## 3. Conformance Tiers

Conformance levels define *what* capabilities an implementation supports. Conformance tiers define *how deeply* those capabilities are implemented. An implementation declares both a level and a tier.

| Tier        | Name        | Description                                                                                      |
|-------------|-------------|--------------------------------------------------------------------------------------------------|
| 1           | **Parser**  | Can validate OJS job envelopes and API payloads against the specification. The minimum bar.       |
| 2           | **Runtime** | Can execute jobs per specification (full lifecycle, state machine, retry). What most implementations target. |
| 3           | **Full**    | Supports all optional features, all protocol bindings, and passes the complete test suite.        |

### 3.1 Parser Tier

A Parser tier implementation can validate OJS documents but does not execute jobs. Parser implementations are typically libraries, linters, or schema validators.

**Parser tier requirements**:

- MUST validate job envelopes against the OJS JSON Schema.
- MUST detect and report missing required fields.
- MUST detect and report invalid field types.
- MUST detect and report invalid field values (e.g., malformed UUIDv7, invalid queue name pattern, invalid timestamp format).
- MUST detect and report invalid state transitions when validating sequences of operations.
- MAY validate protocol-specific payloads (HTTP request/response bodies, gRPC messages).

**Rationale**: Parser tier exists because validation libraries are valuable even without runtime capability. A CI/CD pipeline might validate job definitions at build time without running a job queue. A linter might check that job arguments conform to a registered schema. These tools deserve a conformance designation.

### 3.2 Runtime Tier

A Runtime tier implementation can execute jobs through their full lifecycle. This is the tier that most OJS implementations target.

**Runtime tier requirements**:

- All Parser tier requirements.
- MUST implement the complete job lifecycle state machine.
- MUST execute jobs by dispatching to registered handlers.
- MUST support at least one protocol binding (HTTP or gRPC).
- MUST support the JSON wire format.
- MUST pass all test cases for the declared conformance level.

**Rationale**: Runtime tier is the standard bar for a job processing system. An implementation that can validate envelopes but not execute jobs is a parser, not a job system.

### 3.3 Full Tier

A Full tier implementation supports every feature defined in the specification, including all optional features and all protocol bindings.

**Full tier requirements**:

- All Runtime tier requirements.
- MUST support both HTTP and gRPC protocol bindings.
- MUST support all OPTIONAL features defined at the declared conformance level.
- MUST pass the complete test suite, including optional test cases.
- SHOULD support additional wire formats beyond JSON (e.g., Protocol Buffers).

**Rationale**: Full tier is aspirational. It recognizes implementations that go beyond the minimum and provide complete specification coverage. Full tier implementations serve as reference points for the ecosystem.

---

## 4. Conformance Manifest

Every OJS-conforming implementation MUST expose a machine-readable conformance manifest. This manifest declares the implementation's conformance level, tier, supported protocols, and other capabilities.

### 4.1 Manifest Format

The conformance manifest MUST be a JSON object with the following structure:

```json
{
  "specversion": "1.0",
  "implementation": {
    "name": "ojs-redis",
    "version": "1.0.0",
    "language": "go",
    "repository": "https://github.com/openjobspec/ojs-redis"
  },
  "conformance_level": 2,
  "conformance_tier": "runtime",
  "protocols": ["http", "grpc"],
  "backend": "redis",
  "extensions": {
    "official": [
      {
        "name": "rate-limiting",
        "uri": "urn:ojs:ext:rate-limiting",
        "version": "1.0.0"
      },
      {
        "name": "admin-api",
        "uri": "urn:ojs:ext:admin-api",
        "version": "1.0.0"
      }
    ],
    "experimental": [
      {
        "name": "job-versioning",
        "uri": "urn:ojs:ext:experimental:job-versioning",
        "version": "0.1.0"
      }
    ]
  },
  "schema_validation": true,
  "unique_job_strength": "strong",
  "test_suite_version": "1.0.0",
  "test_suite_passed_at": "2025-06-01T10:00:00Z"
}
```

### 4.2 Manifest Fields

| Field                  | Type             | Required | Description                                                               |
|------------------------|------------------|----------|---------------------------------------------------------------------------|
| `specversion`          | string           | Yes      | OJS specification version (major.minor only, e.g., `"1.0"`).             |
| `implementation`       | object           | Yes      | Implementation metadata.                                                  |
| `implementation.name`  | string           | Yes      | Implementation name (e.g., `"ojs-redis"`, `"ojs-postgres"`).             |
| `implementation.version` | string         | Yes      | Implementation version (SemVer).                                          |
| `implementation.language` | string        | Yes      | Primary implementation language (e.g., `"go"`, `"typescript"`, `"python"`). |
| `implementation.repository` | string     | No       | URL of the source code repository.                                        |
| `conformance_level`    | integer          | Yes      | Highest conformance level supported (0-4).                                |
| `conformance_tier`     | string           | Yes      | One of: `"parser"`, `"runtime"`, `"full"`.                                |
| `protocols`            | array of string  | Yes      | Supported protocol bindings (e.g., `["http"]`, `["http", "grpc"]`).       |
| `backend`              | string           | Yes      | Backend type (e.g., `"redis"`, `"postgres"`, `"memory"`, `"kafka"`).      |
| `extensions`           | object or array  | No       | Extensions supported by this implementation (see Section 4.2.1).          |
| `schema_validation`    | boolean          | No       | Whether the implementation validates job envelopes against JSON Schema.   |
| `unique_job_strength`  | string           | No       | `"strong"` or `"best_effort"`. Required if `conformance_level` >= 4.      |
| `test_suite_version`   | string           | No       | Version of the OJS conformance test suite that was passed.                |
| `test_suite_passed_at` | string           | No       | RFC 3339 timestamp of when the test suite was last passed.                |

#### 4.2.1 Extensions Field

The `extensions` field declares which OJS extensions the implementation supports, organized by tier as defined in the [Extension Lifecycle Specification](./ojs-extension-lifecycle.md).

**Structured format (RECOMMENDED)**:

When using the structured format, `extensions` is an object with two optional keys:

| Field                         | Type    | Description                                                                |
|-------------------------------|---------|----------------------------------------------------------------------------|
| `extensions.official`         | array   | Official extensions supported. Each entry has `name`, `uri`, and `version`. |
| `extensions.experimental`     | array   | Experimental extensions supported. Each entry has `name`, `uri`, and `version`. |

Each extension entry MUST contain:

| Field     | Type   | Required | Description                                                    |
|-----------|--------|----------|----------------------------------------------------------------|
| `name`    | string | Yes      | Extension name (e.g., `"rate-limiting"`).                      |
| `uri`     | string | Yes      | Full extension URI (e.g., `"urn:ojs:ext:rate-limiting"`).      |
| `version` | string | Yes      | SemVer version of the extension specification implemented.     |

**Legacy format (backward compatible)**:

For backward compatibility, `extensions` MAY also be a flat array of strings. Consumers MUST handle both formats. When the flat array format is encountered, all entries SHOULD be treated as custom (non-standard) extensions.

```json
{
  "extensions": ["bulk_purge", "queue_migration"]
}
```

**Rationale**: The structured format enables clients to discover extension support with version information, which is critical for feature negotiation (see ojs-extension-lifecycle.md Section 8). The legacy format is preserved to avoid breaking existing implementations during migration.

### 4.3 Manifest Endpoint

Runtime and Full tier implementations MUST expose the conformance manifest at a well-known endpoint:

- **HTTP**: `GET /ojs/manifest` returning `application/json`.
- **gRPC**: `Manifest()` RPC on the OJS service.

Parser tier implementations SHOULD include the manifest as a static JSON file in their distribution.

**Rationale**: A machine-readable manifest at a well-known endpoint enables automated discovery and compatibility checking. A client library can query the manifest to determine whether the server supports the features it needs before attempting to use them.

---

## 5. Test Suite Format and Methodology

The OJS conformance test suite is distributed as a collection of **language-agnostic JSON test case files**. Each test case describes an operation or sequence of operations, the expected behavior, and the assertions to verify.

### 5.1 Design Principles

The test suite follows these design principles:

1. **Language-agnostic**: Test cases are data, not code. Any implementation in any language can read the JSON test files and execute the described scenarios.

2. **Deterministic where possible**: Tests that can be verified deterministically (schema validation, state transitions, error codes) MUST produce identical results across implementations. Tests that involve timing (backoff delays, scheduling precision) MUST use tolerance ranges.

3. **Self-describing**: Each test case contains its own description, setup requirements, and assertions. No external documentation is needed to understand what a test verifies.

4. **Organized by level**: Test cases are grouped by conformance level, enabling implementations to run only the tests for their declared level.

### 5.2 Test Case Structure

Each test case is a JSON file with the following structure:

```json
{
  "test_id": "L0-001",
  "level": 0,
  "name": "enqueue_simple_job",
  "description": "Enqueue a job and verify it receives an ID and enters available state",
  "tags": ["core", "enqueue", "lifecycle"],
  "requires": [],
  "steps": [
    {
      "action": "POST /ojs/v1/jobs",
      "body": {
        "type": "test.echo",
        "args": ["hello"]
      },
      "expect": {
        "status": 201,
        "body": {
          "job.id": "string:nonempty",
          "job.type": "test.echo",
          "job.state": "available"
        }
      }
    }
  ]
}
```

### 5.3 Test Case Fields

| Field         | Type             | Required | Description                                                    |
|---------------|------------------|----------|----------------------------------------------------------------|
| `test_id`     | string           | Yes      | Unique identifier in the format `L{level}-{number}`.           |
| `level`       | integer          | Yes      | Conformance level this test belongs to (0-4).                  |
| `name`        | string           | Yes      | Human-readable test name using snake_case.                     |
| `description` | string           | Yes      | What this test verifies and why.                               |
| `tags`        | array of string  | No       | Categories for filtering (e.g., `"lifecycle"`, `"retry"`, `"scheduling"`). |
| `requires`    | array of string  | No       | Test IDs that must pass before this test can run.              |
| `setup`       | object           | No       | Pre-conditions and test fixtures (see Section 5.4).            |
| `input`       | object           | No       | Job definition or operation input for non-HTTP tests.          |
| `steps`       | array of object  | No       | Ordered sequence of HTTP/protocol operations (see Section 5.5). |
| `assertions`  | array of object  | No       | Expected outcomes for multi-step or timing-sensitive tests.    |
| `teardown`    | object           | No       | Cleanup operations to run after the test.                      |

### 5.4 Setup Block

The `setup` block defines pre-conditions and test fixtures:

```json
{
  "setup": {
    "handler": "test.fail_twice",
    "behavior": "fail first 2 attempts, succeed on 3rd",
    "queues": ["test-queue"],
    "cron": [],
    "jobs": []
  }
}
```

The `handler` and `behavior` fields describe a test handler that the test harness must provide. Conformance test harnesses MUST implement a standard set of test handlers:

| Handler Name         | Behavior                                           |
|----------------------|----------------------------------------------------|
| `test.echo`          | Returns its arguments as the result.               |
| `test.fail_once`     | Fails on the first attempt, succeeds on the second.|
| `test.fail_twice`    | Fails on the first two attempts, succeeds on the third. |
| `test.fail_always`   | Always fails with a retryable error.               |
| `test.slow`          | Sleeps for a configurable duration, then succeeds. |
| `test.timeout`       | Runs longer than any configured timeout.           |
| `test.panic`         | Crashes the handler (simulates worker crash).      |
| `test.produce`       | Returns a configurable result value.               |
| `test.noop`          | Succeeds immediately with no result.               |

### 5.5 Steps Block (Protocol-Level Tests)

The `steps` block defines a sequence of protocol-level operations:

```json
{
  "steps": [
    {
      "action": "POST /ojs/v1/jobs",
      "headers": {
        "Content-Type": "application/openjobspec+json"
      },
      "body": {
        "type": "test.echo",
        "args": ["hello"]
      },
      "expect": {
        "status": 201,
        "headers": {
          "Content-Type": "application/openjobspec+json"
        },
        "body": {
          "job.id": "string:nonempty",
          "job.type": "test.echo",
          "job.state": "available"
        }
      },
      "capture": {
        "job_id": "body.job.id"
      }
    },
    {
      "action": "GET /ojs/v1/jobs/{job_id}",
      "expect": {
        "status": 200,
        "body": {
          "job.state": "available"
        }
      }
    }
  ]
}
```

Step fields:

| Field     | Type    | Required | Description                                                    |
|-----------|---------|----------|----------------------------------------------------------------|
| `action`  | string  | Yes      | HTTP method and path, or abstract operation name.              |
| `headers` | object  | No       | HTTP headers to include in the request.                        |
| `body`    | any     | No       | Request body (JSON).                                           |
| `expect`  | object  | Yes      | Expected response (status, headers, body assertions).          |
| `capture` | object  | No       | Values to extract from the response for use in subsequent steps.|
| `wait`    | string  | No       | ISO 8601 duration to wait before executing this step.          |

### 5.6 Assertions Block (Behavioral Tests)

The `assertions` block is used for behavioral tests that verify sequences of state changes, timing, and side effects:

```json
{
  "assertions": [
    { "attempt": 1, "state_after": "retryable" },
    { "attempt": 2, "delay_after_failure": "~1s", "state_after": "retryable" },
    { "attempt": 3, "delay_after_failure": "~2s", "state_after": "completed" }
  ]
}
```

Timing assertions use the `~` prefix to indicate approximate values. The test harness MUST allow a tolerance of +/- 50% for timing assertions, unless a more specific tolerance is given.

**Rationale**: Exact timing assertions are impossible in distributed systems due to scheduling jitter, clock skew, and OS scheduling. The 50% default tolerance is generous enough to pass on slow CI systems while still catching gross violations (e.g., a 1-second delay that actually takes 10 seconds).

### 5.7 Assertion Value Matchers

Test assertions support the following value matchers:

| Matcher               | Description                                      | Example                        |
|-----------------------|--------------------------------------------------|--------------------------------|
| Literal value         | Exact match.                                     | `"test.echo"`                  |
| `"string:nonempty"`   | Any non-empty string.                            | `"job.id": "string:nonempty"`  |
| `"string:uuid"`       | Valid UUID (any version).                         | `"job.id": "string:uuid"`      |
| `"string:uuidv7"`     | Valid UUIDv7.                                    | `"job.id": "string:uuidv7"`    |
| `"string:datetime"`   | Valid RFC 3339 timestamp.                        | `"created_at": "string:datetime"` |
| `"number:positive"`   | Positive number.                                 | `"attempt": "number:positive"` |
| `"number:range(a,b)"` | Number in range [a, b] inclusive.                | `"priority": "number:range(1,10)"` |
| `"any"`               | Any value (field must exist but value is unconstrained). | `"result": "any"` |
| `"absent"`            | Field must not be present.                       | `"errors": "absent"`           |
| `"array:length(n)"`   | Array with exactly n elements.                   | `"args": "array:length(2)"`    |
| `"array:nonempty"`    | Array with at least one element.                 | `"errors": "array:nonempty"`   |

---

## 6. Example Test Cases

This section provides representative test cases for each conformance level. The full test suite contains many more cases.

### 6.1 Level 0: Core

#### L0-001: Enqueue Simple Job

```json
{
  "test_id": "L0-001",
  "level": 0,
  "name": "enqueue_simple_job",
  "description": "Enqueue a job and verify it receives an ID and enters available state",
  "tags": ["core", "enqueue", "lifecycle"],
  "steps": [
    {
      "action": "POST /ojs/v1/jobs",
      "body": {
        "type": "test.echo",
        "args": ["hello"]
      },
      "expect": {
        "status": 201,
        "body": {
          "job.id": "string:uuidv7",
          "job.type": "test.echo",
          "job.queue": "default",
          "job.state": "available",
          "job.args": ["hello"],
          "job.created_at": "string:datetime",
          "job.enqueued_at": "string:datetime"
        }
      }
    }
  ]
}
```

#### L0-002: Reject Invalid Envelope (Missing Type)

```json
{
  "test_id": "L0-002",
  "level": 0,
  "name": "reject_missing_type",
  "description": "Reject a job envelope that is missing the required 'type' field",
  "tags": ["core", "validation", "error"],
  "steps": [
    {
      "action": "POST /ojs/v1/jobs",
      "body": {
        "args": ["hello"]
      },
      "expect": {
        "status": 400,
        "body": {
          "error.code": "invalid_payload",
          "error.retryable": false
        }
      }
    }
  ]
}
```

#### L0-003: Enforce Valid State Transitions

```json
{
  "test_id": "L0-003",
  "level": 0,
  "name": "reject_invalid_state_transition",
  "description": "Reject an attempt to complete a job that is not in the active state",
  "tags": ["core", "lifecycle", "state-machine"],
  "requires": ["L0-001"],
  "steps": [
    {
      "action": "POST /ojs/v1/jobs",
      "body": {
        "type": "test.noop",
        "args": []
      },
      "expect": {
        "status": 201
      },
      "capture": {
        "job_id": "body.job.id"
      }
    },
    {
      "action": "POST /ojs/v1/jobs/{job_id}/ack",
      "expect": {
        "status": 409,
        "body": {
          "error.code": "invalid_state_transition"
        }
      }
    }
  ]
}
```

#### L0-004: Execute Job and Verify Completion

```json
{
  "test_id": "L0-004",
  "level": 0,
  "name": "execute_job_to_completion",
  "description": "Enqueue a job, let a worker execute it, and verify it reaches completed state",
  "tags": ["core", "lifecycle", "execution"],
  "setup": {
    "handler": "test.echo",
    "behavior": "returns its arguments as the result"
  },
  "steps": [
    {
      "action": "POST /ojs/v1/jobs",
      "body": {
        "type": "test.echo",
        "args": ["hello", "world"]
      },
      "expect": {
        "status": 201
      },
      "capture": {
        "job_id": "body.job.id"
      }
    },
    {
      "wait": "PT5S",
      "action": "GET /ojs/v1/jobs/{job_id}",
      "expect": {
        "status": 200,
        "body": {
          "job.state": "completed",
          "job.result": ["hello", "world"],
          "job.completed_at": "string:datetime"
        }
      }
    }
  ]
}
```

### 6.2 Level 1: Reliable

#### L1-001: Retry on Failure

```json
{
  "test_id": "L1-001",
  "level": 1,
  "name": "retry_on_failure",
  "description": "A job that fails on the first attempt is retried and succeeds on the second",
  "tags": ["reliable", "retry", "lifecycle"],
  "setup": {
    "handler": "test.fail_once",
    "behavior": "fail first attempt, succeed on second"
  },
  "input": {
    "type": "test.fail_once",
    "args": [],
    "options": {
      "retry": {
        "max_attempts": 3,
        "initial_interval": "PT1S"
      }
    }
  },
  "assertions": [
    { "attempt": 1, "state_after": "retryable" },
    { "attempt": 2, "state_after": "completed" }
  ]
}
```

#### L1-005: Retry with Exponential Backoff

```json
{
  "test_id": "L1-005",
  "level": 1,
  "name": "retry_with_exponential_backoff",
  "description": "Job that fails is retried with exponential backoff",
  "tags": ["reliable", "retry", "backoff"],
  "setup": {
    "handler": "test.fail_twice",
    "behavior": "fail first 2 attempts, succeed on 3rd"
  },
  "input": {
    "type": "test.fail_twice",
    "args": [],
    "options": {
      "retry": {
        "max_attempts": 3,
        "initial_interval": "PT1S",
        "backoff_coefficient": 2.0
      }
    }
  },
  "assertions": [
    { "attempt": 1, "state_after": "retryable" },
    { "attempt": 2, "delay_after_failure": "~1s", "state_after": "retryable" },
    { "attempt": 3, "delay_after_failure": "~2s", "state_after": "completed" }
  ]
}
```

#### L1-006: Dead Letter Queue on Exhausted Retries

```json
{
  "test_id": "L1-006",
  "level": 1,
  "name": "dead_letter_on_exhausted_retries",
  "description": "A job that exhausts all retry attempts moves to the discarded state",
  "tags": ["reliable", "retry", "dead-letter"],
  "setup": {
    "handler": "test.fail_always",
    "behavior": "always fails with a retryable error"
  },
  "input": {
    "type": "test.fail_always",
    "args": [],
    "options": {
      "retry": {
        "max_attempts": 2,
        "initial_interval": "PT0.5S"
      }
    }
  },
  "assertions": [
    { "attempt": 1, "state_after": "retryable" },
    { "attempt": 2, "state_after": "discarded" }
  ]
}
```

#### L1-007: Visibility Timeout Requeue

```json
{
  "test_id": "L1-007",
  "level": 1,
  "name": "visibility_timeout_requeue",
  "description": "A job whose visibility timeout expires is automatically requeued",
  "tags": ["reliable", "visibility-timeout", "requeue"],
  "setup": {
    "handler": "test.timeout",
    "behavior": "runs longer than any configured timeout"
  },
  "input": {
    "type": "test.timeout",
    "args": [],
    "options": {
      "visibility_timeout": 2
    }
  },
  "assertions": [
    { "attempt": 1, "active_for": "~2s", "state_after": "available" }
  ]
}
```

### 6.3 Level 2: Scheduled

#### L2-001: Delayed Job Execution

```json
{
  "test_id": "L2-001",
  "level": 2,
  "name": "delayed_job_execution",
  "description": "A job with scheduled_at is not executed before the scheduled time",
  "tags": ["scheduled", "delayed", "lifecycle"],
  "setup": {
    "handler": "test.echo",
    "behavior": "returns its arguments as the result"
  },
  "steps": [
    {
      "action": "POST /ojs/v1/jobs",
      "body": {
        "type": "test.echo",
        "args": ["delayed"],
        "scheduled_at": "{now+5s}"
      },
      "expect": {
        "status": 201,
        "body": {
          "job.state": "scheduled"
        }
      },
      "capture": {
        "job_id": "body.job.id"
      }
    },
    {
      "wait": "PT2S",
      "action": "GET /ojs/v1/jobs/{job_id}",
      "expect": {
        "status": 200,
        "body": {
          "job.state": "scheduled"
        }
      }
    },
    {
      "wait": "PT5S",
      "action": "GET /ojs/v1/jobs/{job_id}",
      "expect": {
        "status": 200,
        "body": {
          "job.state": "completed"
        }
      }
    }
  ]
}
```

#### L2-002: Job Expiration

```json
{
  "test_id": "L2-002",
  "level": 2,
  "name": "job_expiration",
  "description": "A job with expires_at that is not executed before the deadline is discarded",
  "tags": ["scheduled", "expiration", "ttl"],
  "steps": [
    {
      "action": "POST /ojs/v1/jobs",
      "body": {
        "type": "test.echo",
        "args": ["expiring"],
        "scheduled_at": "{now+10s}",
        "expires_at": "{now+5s}"
      },
      "expect": {
        "status": 201,
        "body": {
          "job.state": "scheduled"
        }
      },
      "capture": {
        "job_id": "body.job.id"
      }
    },
    {
      "wait": "PT7S",
      "action": "GET /ojs/v1/jobs/{job_id}",
      "expect": {
        "status": 200,
        "body": {
          "job.state": "discarded"
        }
      }
    }
  ]
}
```

### 6.4 Level 3: Orchestration

#### L3-001: Chain Workflow

```json
{
  "test_id": "L3-001",
  "level": 3,
  "name": "chain_workflow_execution",
  "description": "A chain of three jobs executes sequentially, passing results between steps",
  "tags": ["orchestration", "chain", "workflow"],
  "setup": {
    "handler": "test.produce",
    "behavior": "returns a configurable result value"
  },
  "steps": [
    {
      "action": "POST /ojs/v1/workflows",
      "body": {
        "type": "chain",
        "jobs": [
          { "type": "test.produce", "args": ["step1_output"] },
          { "type": "test.echo", "args": [] },
          { "type": "test.echo", "args": [] }
        ]
      },
      "expect": {
        "status": 201,
        "body": {
          "workflow.id": "string:nonempty",
          "workflow.type": "chain",
          "workflow.state": "active"
        }
      },
      "capture": {
        "workflow_id": "body.workflow.id"
      }
    },
    {
      "wait": "PT10S",
      "action": "GET /ojs/v1/workflows/{workflow_id}",
      "expect": {
        "status": 200,
        "body": {
          "workflow.state": "completed"
        }
      }
    }
  ]
}
```

#### L3-002: Group Workflow

```json
{
  "test_id": "L3-002",
  "level": 3,
  "name": "group_workflow_execution",
  "description": "A group of three independent jobs executes concurrently and all complete",
  "tags": ["orchestration", "group", "workflow"],
  "setup": {
    "handler": "test.echo",
    "behavior": "returns its arguments as the result"
  },
  "steps": [
    {
      "action": "POST /ojs/v1/workflows",
      "body": {
        "type": "group",
        "jobs": [
          { "type": "test.echo", "args": ["a"] },
          { "type": "test.echo", "args": ["b"] },
          { "type": "test.echo", "args": ["c"] }
        ]
      },
      "expect": {
        "status": 201,
        "body": {
          "workflow.id": "string:nonempty",
          "workflow.type": "group",
          "workflow.state": "active"
        }
      },
      "capture": {
        "workflow_id": "body.workflow.id"
      }
    },
    {
      "wait": "PT10S",
      "action": "GET /ojs/v1/workflows/{workflow_id}",
      "expect": {
        "status": 200,
        "body": {
          "workflow.state": "completed"
        }
      }
    }
  ]
}
```

### 6.5 Level 4: Advanced

#### L4-001: Priority Ordering

```json
{
  "test_id": "L4-001",
  "level": 4,
  "name": "priority_ordering",
  "description": "Jobs with higher priority are dequeued before jobs with lower priority",
  "tags": ["advanced", "priority", "ordering"],
  "setup": {
    "handler": "test.echo",
    "behavior": "returns its arguments as the result"
  },
  "steps": [
    {
      "action": "POST /ojs/v1/queues/test-priority/pause",
      "expect": { "status": 200 }
    },
    {
      "action": "POST /ojs/v1/jobs",
      "body": {
        "type": "test.echo",
        "args": ["low"],
        "queue": "test-priority",
        "priority": 1
      },
      "expect": { "status": 201 },
      "capture": { "low_id": "body.job.id" }
    },
    {
      "action": "POST /ojs/v1/jobs",
      "body": {
        "type": "test.echo",
        "args": ["high"],
        "queue": "test-priority",
        "priority": 3
      },
      "expect": { "status": 201 },
      "capture": { "high_id": "body.job.id" }
    },
    {
      "action": "POST /ojs/v1/queues/test-priority/resume",
      "expect": { "status": 200 }
    },
    {
      "wait": "PT5S",
      "action": "GET /ojs/v1/jobs/{high_id}",
      "expect": {
        "status": 200,
        "body": {
          "job.state": "completed"
        }
      }
    }
  ]
}
```

#### L4-002: Unique Job Deduplication

```json
{
  "test_id": "L4-002",
  "level": 4,
  "name": "unique_job_rejection",
  "description": "A duplicate job is rejected when a matching unique job exists",
  "tags": ["advanced", "unique", "deduplication"],
  "steps": [
    {
      "action": "POST /ojs/v1/jobs",
      "body": {
        "type": "test.slow",
        "args": [5],
        "unique": {
          "key": [],
          "period": "PT1M",
          "on_conflict": "reject",
          "states": ["available", "active"]
        }
      },
      "expect": { "status": 201 },
      "capture": { "first_id": "body.job.id" }
    },
    {
      "action": "POST /ojs/v1/jobs",
      "body": {
        "type": "test.slow",
        "args": [5],
        "unique": {
          "key": [],
          "period": "PT1M",
          "on_conflict": "reject",
          "states": ["available", "active"]
        }
      },
      "expect": {
        "status": 409,
        "body": {
          "error.code": "duplicate"
        }
      }
    }
  ]
}
```

---

## 7. Badge Program

Implementations that pass the OJS conformance test suite earn an "OJS Conformant" badge. The badge communicates the conformance level and tier at a glance.

### 7.1 Badge Format

Badges follow the format:

```
OJS Conformant Level {N} ({Tier})
```

Examples:

- **OJS Conformant Level 0 (Parser)**
- **OJS Conformant Level 1 (Runtime)**
- **OJS Conformant Level 2 (Runtime)**
- **OJS Conformant Level 4 (Full)**

### 7.2 Badge Assets

The OJS project provides badge assets in the following formats:

- SVG badges for use in README files and documentation.
- JSON badge definitions compatible with [shields.io](https://shields.io).
- Markdown snippets for quick embedding.

Example Markdown:

```markdown
[![OJS Conformant Level 2 (Runtime)](https://img.shields.io/badge/OJS-Level%202%20Runtime-blue)](https://openjobspec.org/conformance)
```

### 7.3 Badge Requirements

To display an OJS Conformant badge, an implementation MUST:

1. Pass the complete test suite for the declared conformance level.
2. Include a conformance manifest (see Section 4) in the implementation's distribution or at its well-known endpoint.
3. Reference the specific test suite version that was passed.

Implementations SHOULD include the conformance test run in their CI/CD pipeline so that the badge reflects the current state of the codebase.

### 7.4 Badge Revocation

An OJS Conformant badge becomes invalid when:

- A new version of the test suite is released and the implementation has not been re-tested against it within 90 days.
- The implementation introduces changes that cause previously passing tests to fail.
- The implementation misrepresents its conformance level or tier.

The OJS project does not actively police badge usage but reserves the right to request removal of badges that misrepresent conformance status.

---

## 8. Running the Conformance Test Suite

### 8.1 Test Suite Distribution

The conformance test suite is distributed as a directory of JSON files in the `ojs-conformance` repository:

```
ojs-conformance/
  README.md
  LICENSE
  manifest.json            # Test suite metadata (version, test count, etc.)
  handlers/
    handlers.json           # Standard test handler definitions
  tests/
    level-0/
      L0-001.json
      L0-002.json
      L0-003.json
      L0-004.json
      ...
    level-1/
      L1-001.json
      L1-005.json
      L1-006.json
      L1-007.json
      ...
    level-2/
      L2-001.json
      L2-002.json
      ...
    level-3/
      L3-001.json
      L3-002.json
      ...
    level-4/
      L4-001.json
      L4-002.json
      ...
```

### 8.2 Test Harness Requirements

A conformance test harness is a language-specific program that:

1. Reads the JSON test case files.
2. Sets up the required test handlers (see Section 5.4).
3. Executes the described operations against the implementation under test.
4. Evaluates the assertions.
5. Produces a conformance report.

Implementations MAY provide their own test harness or use a community-provided harness. The OJS project provides reference test harnesses in Go and TypeScript.

### 8.3 Running Tests

To run the conformance test suite for a specific level:

```bash
# Run Level 0 tests only
ojs-conformance-runner --level 0 --target http://localhost:8080

# Run Level 0 and Level 1 tests
ojs-conformance-runner --level 1 --target http://localhost:8080

# Run all tests up to Level 4
ojs-conformance-runner --level 4 --target http://localhost:8080

# Run specific test by ID
ojs-conformance-runner --test L1-005 --target http://localhost:8080
```

### 8.4 Conformance Report

The test runner produces a JSON conformance report:

```json
{
  "test_suite_version": "1.0.0",
  "target": "http://localhost:8080",
  "run_at": "2025-06-01T10:00:00Z",
  "duration_ms": 45000,
  "requested_level": 2,
  "results": {
    "total": 87,
    "passed": 85,
    "failed": 1,
    "skipped": 1,
    "level_0": { "total": 25, "passed": 25, "failed": 0, "skipped": 0 },
    "level_1": { "total": 35, "passed": 34, "failed": 1, "skipped": 0 },
    "level_2": { "total": 27, "passed": 26, "failed": 0, "skipped": 1 }
  },
  "conformant": false,
  "conformant_level": 0,
  "failures": [
    {
      "test_id": "L1-005",
      "name": "retry_with_exponential_backoff",
      "reason": "Expected delay_after_failure ~2s for attempt 3, actual was 5.2s (outside tolerance)"
    }
  ],
  "skipped": [
    {
      "test_id": "L2-003",
      "name": "cron_timezone_dst_transition",
      "reason": "Test requires system clock manipulation not supported by this harness"
    }
  ]
}
```

The `conformant_level` field indicates the highest level for which ALL tests passed. In the example above, all Level 0 tests passed but a Level 1 test failed, so the conformant level is 0.

---

## 9. Test Suite Versioning

### 9.1 Version Scheme

The conformance test suite uses [Semantic Versioning 2.0.0](https://semver.org/):

- **MAJOR**: Incremented when tests are changed in a way that a previously conformant implementation might fail (new mandatory tests, stricter assertions).
- **MINOR**: Incremented when new tests are added without changing existing tests (new optional tests, tests for new specification features).
- **PATCH**: Incremented for bug fixes in test cases (correcting an incorrect assertion, fixing a typo in a test description).

### 9.2 Compatibility Policy

- A MAJOR version bump of the test suite indicates that implementations MUST re-run the suite to maintain their conformance claim.
- A MINOR version bump indicates that implementations SHOULD re-run the suite to verify they pass new tests, but their existing conformance claim remains valid.
- A PATCH version bump does not affect conformance claims.

### 9.3 Relationship to Specification Version

The test suite version tracks independently from the OJS specification version. However, each test suite release documents which specification version it targets.

| Test Suite Version | Specification Version | Notes                          |
|--------------------|-----------------------|--------------------------------|
| 1.0.0              | 1.0.0-rc.1            | Initial release.               |

### 9.4 Deprecation of Test Cases

Test cases MAY be deprecated when the specification evolves. Deprecated tests:

- MUST be marked with a `"deprecated": true` field.
- MUST include a `"deprecated_reason"` field explaining why.
- MUST remain in the test suite for at least one MAJOR version after deprecation.
- MUST NOT count toward conformance pass/fail evaluation after the deprecation grace period.

---

## 10. Prior Art and Lessons Learned

This section documents the lessons from existing standards that shaped OJS's conformance approach.

### 10.1 OpenAPI: The Cost of No Conformance Tests

OpenAPI (formerly Swagger) is the most widely adopted API specification standard, yet it never shipped a formal conformance test suite. The consequences:

- **Validator disagreement**: Tools claiming OpenAPI 3.0 compliance disagree on edge cases. A document that passes validation in one tool may fail in another. The community maintains a [comparison matrix](https://github.com/OAI/OpenAPI-Specification) documenting inconsistencies.
- **Generator drift**: Code generators produce subtly different client and server code for the same OpenAPI document, because each generator interprets ambiguous specification language differently.
- **Specification ambiguity persists**: Without conformance tests to force precise specification language, ambiguities survive from version to version. The specification committee debates semantics in prose rather than expressing them as executable tests.

**Lesson for OJS**: Every MUST requirement in the specification MUST have at least one corresponding conformance test. Tests force precision in specification language: if a test case is ambiguous, the specification text is ambiguous.

### 10.2 GraphQL: Spec Precision Without Test Distribution

GraphQL published one of the most precise specifications in the API standards space, with formal grammar, explicit algorithms, and detailed execution semantics. Yet it did not ship a language-agnostic test suite alongside the specification.

The consequences:

- **Community-built test suites lag**: The community eventually built test suites (graphql-js's test suite became a de facto reference), but they are tied to a specific language (JavaScript) and a specific implementation.
- **Edge case divergence**: Server implementations in different languages occasionally disagree on coercion rules, error formatting, and subscription behavior -- precisely the areas where a cross-language test suite would catch differences.
- **Specification evolution slowed**: New features (input unions, the `@defer`/`@stream` directives) stalled partly because there was no conformance test infrastructure to validate implementations of draft features.

**Lesson for OJS**: The test suite MUST be language-agnostic (JSON data files, not code). The test suite MUST ship alongside the first release candidate, not as a follow-up.

### 10.3 OpenTelemetry: Complexity Without Conformance Guardrails

OpenTelemetry defined extensive specifications covering traces, metrics, logs, semantic conventions, and multiple wire protocols (OTLP, Zipkin, Jaeger). Conformance testing was deprioritized in favor of shipping SDKs.

The consequences:

- **Semantic convention drift**: Instrumentation libraries in different languages use slightly different attribute names, span structures, and metric conventions -- defeating the purpose of "semantic conventions."
- **Protocol conformance gaps**: OTLP implementations in different languages occasionally produce payloads that cause parsing errors in receivers built against a different interpretation of the spec.
- **Adoption friction**: Organizations adopting OpenTelemetry report spending significant effort on "making traces look the same" across services written in different languages -- work that a conformance test suite would have prevented.

**Lesson for OJS**: Conformance testing MUST cover semantic behavior (state transitions, retry timing, event content), not just structural validation (envelope shape, field types). Structural correctness is necessary but not sufficient for interoperability.

### 10.4 Summary of Prior Art Lessons

| Lesson                                         | OJS Response                                              |
|------------------------------------------------|-----------------------------------------------------------|
| Ship tests alongside the spec, not later.      | Test suite is a first-class deliverable of v1.0.0-rc.1.  |
| Tests must be language-agnostic.               | JSON test case files, no language-specific code.          |
| Tests must cover behavior, not just structure.  | Behavioral assertions for state transitions, timing, workflows. |
| Every MUST must have a test.                   | Coverage requirement: each MUST requirement maps to at least one test ID. |
| Precision in spec language comes from tests.   | Ambiguous spec text is treated as a bug; tests resolve ambiguity. |
| Conformance levels prevent all-or-nothing.     | Five levels (0-4) allow incremental conformance claims.   |

---

## Appendix A: Requirement Traceability Matrix

Every MUST requirement in this document maps to one or more conformance test cases. The following table provides the mapping (representative, not exhaustive):

| Requirement ID | Description                        | Test Case(s)                     |
|----------------|------------------------------------|----------------------------------|
| L0-ENV-001     | Required envelope attributes       | L0-001, L0-002                   |
| L0-ENV-002     | UUIDv7 generation                  | L0-001                           |
| L0-ENV-003     | Type validation                    | L0-002, L0-005                   |
| L0-ENV-004     | Queue name validation              | L0-006                           |
| L0-ENV-005     | Args JSON-native types             | L0-007, L0-008                   |
| L0-ENV-006     | Unknown field preservation         | L0-009                           |
| L0-OPS-001     | PUSH operation                     | L0-001, L0-004                   |
| L0-OPS-002     | FETCH operation                    | L0-010                           |
| L0-OPS-003     | ACK operation                      | L0-004                           |
| L0-OPS-004     | FAIL operation                     | L0-011                           |
| L0-LC-001      | 8-state lifecycle                  | L0-003, L0-004                   |
| L0-LC-002      | Valid state transitions            | L0-003, L0-012                   |
| L0-EVT-001     | Core lifecycle events              | L0-013, L0-014                   |
| L0-Q-001       | Default queue support              | L0-001                           |
| L0-WF-001      | JSON wire format                   | L0-001, L0-002                   |
| L0-MW-001      | Enqueue middleware                 | L0-015                           |
| L0-MW-002      | Execution middleware               | L0-016                           |
| L1-RET-001     | Retry with backoff                 | L1-001, L1-005                   |
| L1-RET-002     | Retry policy fields                | L1-005                           |
| L1-RET-003     | Non-retryable errors               | L1-008                           |
| L1-DLQ-001     | Dead letter queue                  | L1-006                           |
| L1-HB-001      | BEAT operation                     | L1-009                           |
| L1-VT-001      | Visibility timeout                 | L1-007                           |
| L1-CAN-001     | CANCEL operation                   | L1-010                           |
| L1-INFO-001    | INFO operation                     | L1-011                           |
| L2-DEL-001     | Delayed jobs                       | L2-001                           |
| L2-CRON-001    | Cron scheduling                    | L2-003                           |
| L2-TTL-001     | Job expiration                     | L2-002                           |
| L3-CHAIN-001   | Chain workflow                     | L3-001                           |
| L3-GROUP-001   | Group workflow                     | L3-002                           |
| L3-BATCH-001   | Batch workflow                     | L3-003                           |
| L4-PRI-001     | Priority queues                    | L4-001                           |
| L4-UNIQ-001    | Unique jobs                        | L4-002                           |
| L4-BULK-001    | Batch enqueue                      | L4-003                           |
| L4-PAUSE-001   | Queue pause                        | L4-001, L4-004                   |
| L4-STATS-001   | Queue statistics                   | L4-005                           |

---

## Appendix B: Changelog

### 1.0.0-rc.1 (2025-06-01)

- Initial release candidate.
- Defined five conformance levels (Core, Reliable, Scheduled, Orchestration, Advanced).
- Defined three conformance tiers (Parser, Runtime, Full).
- Defined conformance manifest format.
- Defined language-agnostic JSON test case format.
- Defined badge program.
- Defined test suite versioning policy.
- Documented prior art lessons from OpenAPI, GraphQL, and OpenTelemetry.
- Every MUST requirement includes explicit rationale per RFC 2119 usage policy.

---

*Open Job Spec v1.0.0-rc.1 -- Conformance Levels and Requirements*
*https://openjobspec.org*
