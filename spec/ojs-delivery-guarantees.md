# Open Job Spec: Delivery Guarantees

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Delivery Guarantees Specification          |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-19                                     |
| **Status**  | Release Candidate 1                            |
| **Maturity** | Experimental                                   |
| **Tier**    | Core Specification                             |
| **URI**     | `urn:ojs:spec:delivery-guarantees`             |
| **Requires**| OJS Core Specification, OJS Worker Protocol    |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Delivery Guarantee Levels](#4-delivery-guarantee-levels)
5. [CAP Theorem Implications](#5-cap-theorem-implications)
6. [At-Least-Once Delivery Mechanism](#6-at-least-once-delivery-mechanism)
7. [Achieving Effectively Exactly-Once](#7-achieving-effectively-exactly-once)
8. [Duplicate Execution Scenarios](#8-duplicate-execution-scenarios)
9. [Ordering Guarantees](#9-ordering-guarantees)
10. [Consistency Model](#10-consistency-model)
11. [Conformance Requirements](#11-conformance-requirements)
12. [Prior Art](#12-prior-art)
13. [Examples](#13-examples)

---

## 1. Introduction

Every distributed job processing system must answer a deceptively simple question: will this job be executed exactly once? The answer, rooted in decades of distributed systems research, is that true exactly-once delivery is impossible in the presence of network partitions and process failures. What systems can provide -- and what this specification formalizes -- is a set of guarantees about how jobs behave under failure conditions, and a framework for achieving *effectively* exactly-once semantics through the combination of infrastructure guarantees and application-level idempotency.

Delivery guarantees matter because real-world job processing carries real-world consequences. A payment processed twice charges a customer twice. An email never sent loses a customer. A report generated out of order produces incorrect results. The choice of delivery guarantee directly determines the failure modes an application must handle.

This specification defines three delivery guarantee levels, establishes at-least-once as the OJS baseline, and provides a formal framework for achieving effectively exactly-once semantics. It addresses the CAP theorem tradeoffs inherent in distributed job processing, catalogs duplicate execution scenarios and their mitigations, and defines the consistency model that OJS implementations MUST provide.

### 1.1 Scope

This specification defines:

- The three delivery guarantee levels and their semantics.
- How OJS achieves at-least-once delivery through durable enqueue, visibility timeout, and job reaping.
- The shared-responsibility model for effectively exactly-once semantics.
- Duplicate execution scenarios, their causes, and mitigations.
- Ordering guarantees (or the deliberate lack thereof).
- The consistency model for enqueue, dequeue, and acknowledgment operations.

This specification does NOT define:

- Transport-level reliability (see OJS HTTP Binding, OJS gRPC Binding).
- Retry strategies and backoff algorithms (see OJS Retry Specification).
- Enqueue-time deduplication (see OJS Unique Jobs Specification).

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term                  | Definition                                                                                                       |
|-----------------------|------------------------------------------------------------------------------------------------------------------|
| **At-most-once**      | A delivery guarantee where a job is delivered zero or one times. The job may be lost but is never duplicated.     |
| **At-least-once**     | A delivery guarantee where a job is delivered one or more times. The job is never lost but may be duplicated.     |
| **Exactly-once**      | An idealized delivery guarantee where a job is delivered precisely one time. Impossible to achieve in the general case in distributed systems. |
| **Effectively exactly-once** | The practical approximation of exactly-once semantics achieved by combining at-least-once delivery with idempotent processing. |
| **Idempotency**       | The property of an operation such that applying it multiple times produces the same result as applying it once.   |
| **Idempotency key**   | A unique identifier used to detect and suppress duplicate executions of the same logical operation.              |
| **Deduplication window** | The time period during which a backend or application tracks idempotency keys to detect duplicates.            |
| **Visibility timeout** | The duration after a job is fetched during which it is invisible to other workers. If the worker does not acknowledge the job within this window, the job becomes available for redelivery. |
| **Redelivery**        | The act of making a previously fetched but unacknowledged job available for processing again.                    |
| **Phantom job**       | A job that has been processed to completion by a worker but whose acknowledgment was lost, causing it to be redelivered and potentially processed again. |
| **Duplicate execution** | The condition where the side effects of a job are applied more than once due to redelivery of a phantom job.   |

---

## 4. Delivery Guarantee Levels

OJS recognizes three delivery guarantee levels. Each level represents a different tradeoff between reliability, performance, and complexity.

### 4.1 At-Most-Once

**Guarantee**: A job is delivered zero or one times.

At-most-once delivery is the simplest guarantee. The backend enqueues the job and a worker fetches it. If the worker crashes, the network fails, or the backend restarts, the job is lost. No retry is attempted.

- Jobs are **never duplicated**.
- Jobs **may be lost** on failure.
- No visibility timeout, no redelivery, no reaper.
- Fastest and lowest overhead of all guarantee levels.

At-most-once is appropriate for fire-and-forget workloads where occasional loss is acceptable: analytics events, cache warming, non-critical notifications.

An OJS implementation MAY support at-most-once delivery as an opt-in mode.

### 4.2 At-Least-Once

**Guarantee**: A job is delivered one or more times.

At-least-once delivery ensures that every successfully enqueued job will eventually be processed, even in the presence of worker crashes, network partitions, and backend failovers. The tradeoff is that a job may be delivered more than once.

- Jobs are **never lost** after successful enqueue.
- Jobs **may be duplicated** on failure.
- Achieved through durable enqueue, visibility timeout, and dead worker reaping.
- The OJS default and baseline guarantee.

An OJS-conformant implementation MUST provide at-least-once delivery as the default guarantee level. This is non-negotiable: if a producer receives a successful PUSH response, that job MUST eventually be delivered to a worker or enter a terminal state (completed, discarded, or cancelled).

### 4.3 Effectively Exactly-Once

**Guarantee**: A job's side effects are applied precisely once, even if the job is delivered multiple times.

True exactly-once delivery is impossible in distributed systems (see [Section 5](#5-cap-theorem-implications)). Effectively exactly-once is not a delivery guarantee provided by the infrastructure alone -- it is a **shared responsibility** between the OJS backend (which provides at-least-once delivery) and the application (which provides idempotent processing).

- At-least-once delivery + idempotent handler = effectively exactly-once semantics.
- The backend guarantees delivery; the application guarantees idempotency.
- Requires application-level design: idempotency keys, deduplication checks, transactional processing.

An OJS implementation SHOULD provide mechanisms that facilitate effectively exactly-once semantics, such as exposing the job `id` as a natural idempotency key and supporting transactional acknowledgment patterns.

---

## 5. CAP Theorem Implications

### 5.1 CAP and Job Processing

The CAP theorem states that a distributed system can provide at most two of three properties simultaneously: **Consistency**, **Availability**, and **Partition tolerance**. Since network partitions are inevitable in production systems, the practical choice is between consistency and availability during a partition.

Job processing systems are distributed systems. A producer enqueues a job on one node; a worker processes it on another. The backend may be replicated across data centers. CAP applies directly.

### 5.2 Why True Exactly-Once Is Impossible

The Fischer-Lynch-Paterson (FLP) impossibility result proves that no deterministic protocol can guarantee consensus in an asynchronous system where even one process may crash. Applied to job processing:

1. A worker fetches a job and processes it.
2. The worker sends an ACK to the backend.
3. The network drops the ACK.
4. The backend cannot distinguish "worker crashed before processing" from "worker processed but ACK was lost."
5. The backend MUST either redeliver (risking duplication) or not redeliver (risking loss).

There is no third option. This is not a limitation of any particular implementation -- it is a fundamental property of distributed systems.

### 5.3 Consistency vs. Availability Tradeoffs

| Tradeoff   | Behavior During Partition                                                    | Consequence                                   |
|------------|------------------------------------------------------------------------------|-----------------------------------------------|
| **CP**     | Backend rejects enqueue/fetch until partition heals.                         | No duplicates, no loss, but reduced availability. |
| **AP**     | Backend continues accepting enqueue/fetch, reconciles after partition heals. | Higher availability, but risk of duplicates.    |

OJS specifies **AP behavior** for job processing: availability is prioritized. During a network partition, the system continues processing jobs with the understanding that duplicates may occur. This aligns with the at-least-once baseline.

### 5.4 Network Partition Scenarios

**Scenario 1: Partition between producer and backend.** The producer cannot enqueue. The producer SHOULD retry with exponential backoff. If the enqueue eventually succeeds, at-least-once is preserved.

**Scenario 2: Partition between worker and backend.** The worker has fetched a job but cannot send ACK. The visibility timeout expires. The backend redelivers the job to another worker. Duplicate execution occurs unless the handler is idempotent.

**Scenario 3: Partition within a replicated backend.** A job enqueued on one replica may not be visible on another. After the partition heals, the job becomes visible. OJS does not specify replication semantics -- this is backend-specific.

---

## 6. At-Least-Once Delivery Mechanism

OJS achieves at-least-once delivery through three interlocking mechanisms: durable enqueue (PUSH), visibility timeout, and dead worker reaping.

### 6.1 Durable Enqueue (PUSH)

When a producer calls PUSH and receives a successful response, the job MUST be durably stored. "Durably stored" means the job survives backend process restarts. The specific durability mechanism (fsync, WAL, replication) is backend-specific, but the guarantee is not: a successful PUSH response means the job will not be lost.

### 6.2 Visibility Timeout

When a worker calls FETCH and receives a job, the backend sets a **visibility timeout** on that job. During this window:

- The job is in the `active` state.
- The job is invisible to other workers (it will not be returned by another FETCH).
- The job is **reserved** exclusively for the fetching worker.

If the worker completes processing and sends ACK before the timeout expires, the job transitions to a terminal state. If the timeout expires without ACK, the job becomes available for redelivery.

### 6.3 Heartbeat Extension

A worker that is still actively processing a job SHOULD send periodic heartbeat signals to extend the visibility timeout. Each heartbeat resets the timeout, preventing premature redelivery of long-running jobs.

If a worker stops sending heartbeats (due to crash, deadlock, or network failure), the timeout eventually expires and the job is redelivered. Heartbeat is the mechanism by which the system distinguishes "still processing" from "dead."

### 6.4 Dead Worker Reaper

The backend MUST run a periodic reaper process that scans for jobs whose visibility timeout has expired. These jobs are transitioned back to the `available` state (or to `retryable` if retry policy applies) and become eligible for FETCH by another worker.

The reaper is the safety net that closes the loop on at-least-once delivery. Without it, jobs reserved by crashed workers would be stuck indefinitely.

### 6.5 The Redelivery Scenario

The canonical failure scenario that at-least-once delivery addresses:

1. Worker W1 calls FETCH and receives Job J.
2. W1 begins processing J.
3. W1 crashes (process kill, OOM, hardware failure).
4. W1 never sends ACK for J.
5. The visibility timeout for J expires.
6. The reaper detects J's expired timeout.
7. J is moved back to `available`.
8. Worker W2 calls FETCH and receives J.
9. W2 processes J and sends ACK.
10. J transitions to `completed`.

Job J was delivered twice (to W1 and W2) but only successfully processed once. This is at-least-once delivery working as designed.

### 6.6 Failure Modes

| Failure                        | Recovery Mechanism            | Job Outcome                          |
|--------------------------------|-------------------------------|--------------------------------------|
| Worker crash before processing | Visibility timeout + reaper   | Redelivered to another worker        |
| Worker crash after processing  | Visibility timeout + reaper   | Redelivered (duplicate execution)    |
| Backend crash after PUSH       | Durable storage               | Job survives restart                 |
| Network partition (worker↔backend) | Visibility timeout         | Redelivered after timeout            |

---

## 7. Achieving Effectively Exactly-Once

Effectively exactly-once is not a property of the delivery system -- it is a property of the **end-to-end system** comprising the OJS backend and the application handler. This section defines the patterns and mechanisms that make it achievable.

### 7.1 Idempotent Handler Design

An idempotent handler produces the same observable result whether it is invoked once or multiple times with the same input. Designing for idempotency requires:

1. **Check before act**: Before performing a side effect, check whether it has already been performed.
2. **Use natural idempotency keys**: Many operations have natural keys (order ID, payment ID, user ID + action).
3. **Make side effects unconditional**: Use upserts instead of inserts. Use "set to X" instead of "increment by 1."

### 7.2 The Job ID as Idempotency Key

Every OJS job has a unique `id` assigned at enqueue time. This `id` is a natural idempotency key: if a job is redelivered, the redelivered copy carries the same `id`. Handlers SHOULD use the job `id` to detect and suppress duplicate executions.

An OJS implementation MUST guarantee that a redelivered job retains its original `id`. The `id` MUST NOT change across redeliveries.

### 7.3 Application-Layer Deduplication

The application maintains a record of processed job IDs (or idempotency keys derived from job arguments). Before executing a job's side effects, the handler checks this record:

- If the key exists: skip execution, return success.
- If the key does not exist: execute, record the key, return success.

The deduplication record SHOULD be stored in the same transactional scope as the job's side effects to avoid race conditions.

### 7.4 Transactional Processing Pattern

The strongest exactly-once guarantee combines job processing and acknowledgment in a single atomic transaction:

1. Begin database transaction.
2. Check deduplication record for job ID.
3. If duplicate: rollback, ACK the job.
4. If not duplicate: perform side effects, insert deduplication record, commit.
5. ACK the job.

This pattern requires the application's database and the deduplication record to share a transactional boundary. See the [OJS Framework Adapters Specification](ojs-framework-adapters.md) for language-specific transactional patterns.

### 7.5 Enqueue-Time Deduplication

Deduplication at enqueue time prevents the same logical job from being enqueued multiple times. This is complementary to execution-time deduplication and is defined in the [OJS Unique Jobs Specification](ojs-unique-jobs.md). Enqueue deduplication reduces unnecessary work but does not eliminate the need for idempotent handlers, because redelivery can still cause duplicate execution.

---

## 8. Duplicate Execution Scenarios

The following table catalogs scenarios that cause duplicate execution, their root causes, and recommended mitigations.

| Scenario | Description | Root Cause | Mitigation |
|----------|-------------|------------|------------|
| **Worker crash after processing** | Worker completes job side effects but crashes before sending ACK. Backend redelivers the job. | The gap between "side effects applied" and "ACK sent" is not atomic. | Idempotent handler with deduplication check on job `id`. |
| **Network partition (worker↔backend)** | Worker processes job and sends ACK, but ACK is lost due to network partition. Backend redelivers after visibility timeout. | Network unreliability between worker and backend. | Idempotent handler. Heartbeat extends timeout to reduce the window. |
| **Visibility timeout during slow execution** | Worker is still processing when visibility timeout expires. Backend redelivers to another worker. Both workers execute concurrently. | Processing time exceeds visibility timeout and worker fails to heartbeat. | Heartbeat to extend timeout. Set visibility timeout conservatively. Monitor processing duration. |
| **Backend failover during processing** | Primary backend fails over to replica. Replica may not have received the ACK. Job is redelivered from replica state. | Replication lag between primary and replica. | Idempotent handler. Backend SHOULD use synchronous replication for job state. |
| **Retry after transient ACK failure** | Worker processes job, ACK fails transiently, worker retries ACK but backend has already redelivered. | Race between ACK retry and visibility timeout expiration. | Idempotent handler. Backend SHOULD accept late ACKs for recently redelivered jobs. |

---

## 9. Ordering Guarantees

### 9.1 Default: No Ordering Guarantee

OJS provides **no ordering guarantee** by default. Jobs enqueued in sequence A, B, C may be processed in any order: B, A, C or C, A, B or any other permutation. This is a deliberate design choice that enables:

- Parallel processing across multiple workers.
- Priority-based scheduling.
- Efficient backend implementations that do not require sequential access.

### 9.2 FIFO Ordering

FIFO (first-in, first-out) ordering is an OPTIONAL backend capability. A backend that supports FIFO ordering MUST process jobs within a given queue in enqueue order when operating with a single worker. With multiple workers, FIFO ordering requires additional coordination (e.g., partition keys, sequential dispatch).

An OJS backend MAY advertise FIFO support through capability discovery. Applications that require strict ordering SHOULD verify backend FIFO support at startup.

### 9.3 Priority and Ordering

When priority scheduling is enabled, higher-priority jobs are processed before lower-priority jobs regardless of enqueue order. Priority explicitly overrides FIFO ordering. A priority-1 job enqueued after a priority-10 job will be processed first.

### 9.4 Retry Reordering

When a job fails and is scheduled for retry, it re-enters the queue at a future time determined by the retry policy's backoff algorithm. This means a retried job will typically be processed after jobs that were enqueued later than the original attempt. Retry reordering is inherent to any system with retry backoff and is not a violation of FIFO semantics.

---

## 10. Consistency Model

OJS defines consistency guarantees for the three core operations: enqueue, dequeue, and acknowledgment.

### 10.1 Enqueue Consistency

After a successful PUSH response, the job is guaranteed to exist in the backend's durable store. The job MUST be eventually visible to FETCH operations. The backend MUST NOT silently drop a job after returning a successful PUSH response.

### 10.2 Dequeue Consistency

After a successful FETCH response, the job is exclusively reserved for the fetching worker. No other FETCH operation SHALL return the same job while the visibility timeout is active. This is an exclusive-ownership guarantee.

### 10.3 Acknowledgment Consistency

After a successful ACK response, the job's state transition is permanent and irreversible. A completed job MUST NOT be redelivered. A discarded job MUST NOT be redelivered. Terminal states are final.

### 10.4 Read-Your-Writes

A producer that successfully enqueues a job SHOULD be able to immediately query that job by ID and receive a consistent result. This read-your-writes guarantee is RECOMMENDED but not REQUIRED, as some eventually consistent backends may not support it without additional configuration.

---

## 11. Conformance Requirements

An OJS-conformant implementation MUST satisfy the following requirements:

| ID      | Level    | Requirement                                                                                                    |
|---------|----------|----------------------------------------------------------------------------------------------------------------|
| DG-001  | MUST     | Provide at-least-once delivery as the default guarantee level.                                                 |
| DG-002  | MUST     | Durably store a job after returning a successful PUSH response.                                                |
| DG-003  | MUST     | Implement visibility timeout for fetched jobs.                                                                 |
| DG-004  | MUST     | Implement a reaper process that detects expired visibility timeouts and redelivers jobs.                       |
| DG-005  | MUST     | Preserve the original job `id` across redeliveries.                                                            |
| DG-006  | MUST     | Guarantee exclusive ownership of a job during its visibility timeout (no double-FETCH).                        |
| DG-007  | MUST     | Guarantee that ACK transitions are permanent and irreversible for terminal states.                             |
| DG-008  | MUST     | Never silently drop a job after a successful PUSH response.                                                    |
| DG-009  | SHOULD   | Support heartbeat-based visibility timeout extension.                                                          |
| DG-010  | SHOULD   | Expose the job `id` as a natural idempotency key for application-level deduplication.                          |
| DG-011  | SHOULD   | Provide read-your-writes consistency for job queries immediately after enqueue.                                |
| DG-012  | SHOULD   | Accept late ACKs for jobs that have been recently redelivered.                                                 |
| DG-013  | MAY      | Support at-most-once delivery as an opt-in mode.                                                               |
| DG-014  | MAY      | Support FIFO ordering as an optional backend capability.                                                       |
| DG-015  | MAY      | Advertise delivery guarantee capabilities through capability discovery.                                        |

---

## 12. Prior Art

| System                | Delivery Guarantee Approach                                                                                                     |
|-----------------------|---------------------------------------------------------------------------------------------------------------------------------|
| **Apache Kafka**      | Exactly-once semantics (EOS) via idempotent producers and transactional consumers. Assigns sequence numbers to detect duplicates at the broker. Requires `enable.idempotence=true` and transactional API for end-to-end EOS. |
| **AWS SQS**           | Standard queues: at-least-once with best-effort ordering. FIFO queues: exactly-once processing via message deduplication IDs with a 5-minute deduplication window. Content-based deduplication as an alternative. |
| **RabbitMQ**          | At-most-once by default. Publisher confirms upgrade to at-least-once on the publish side. Consumer acknowledgments provide at-least-once on the consume side. No built-in exactly-once; applications must implement idempotency. |
| **Temporal**          | Durable execution model. Activities have built-in retry with at-least-once delivery. Workflows are deterministically replayed, providing effectively exactly-once workflow execution. Activity idempotency is the developer's responsibility. |
| **Apache Flink**      | Exactly-once state consistency via distributed snapshots (Chandy-Lamport algorithm). Checkpoint barriers flow through the dataflow graph. End-to-end exactly-once requires idempotent or transactional sinks. |
| **Sidekiq**           | At-least-once via Redis `BRPOPLPUSH` (fetch) and explicit acknowledgment (delete from processing set). Reliability requires Sidekiq Pro's `super_fetch`. No exactly-once guarantees. |
| **Oban**              | At-least-once via PostgreSQL row locking (`FOR UPDATE SKIP LOCKED`). Advisory locks for uniqueness. No built-in exactly-once; idempotency is the developer's responsibility. |

Kafka's idempotent producer and SQS FIFO's deduplication ID are the closest prior art to OJS's approach of using the job `id` as a natural idempotency key. Temporal's durable execution model represents a higher-level abstraction that achieves effectively exactly-once through deterministic replay rather than idempotent processing.

---

## 13. Examples

### 13.1 Idempotent Payment Handler (Pseudocode)

The following pseudocode demonstrates an idempotent handler that safely processes a payment job even if it is delivered multiple times:

```
function handle_payment_job(job):
    payment_id = job.args["payment_id"]
    amount     = job.args["amount"]
    recipient  = job.args["recipient"]

    // Begin a database transaction
    tx = db.begin_transaction()

    try:
        // Check if this job has already been processed
        existing = tx.query(
            "SELECT status FROM processed_jobs WHERE job_id = ?",
            job.id
        )

        if existing is not null:
            // Already processed -- skip execution, commit is a no-op
            tx.rollback()
            return SUCCESS

        // Perform the payment (the actual side effect)
        payment_result = payment_gateway.charge(payment_id, amount, recipient)

        // Record that this job has been processed
        tx.execute(
            "INSERT INTO processed_jobs (job_id, status, processed_at) VALUES (?, ?, NOW())",
            job.id, payment_result.status
        )

        // Commit the side effect and the deduplication record atomically
        tx.commit()

        return SUCCESS

    catch error:
        tx.rollback()
        raise error  // Let OJS retry mechanism handle the failure
```

**Key properties of this handler:**

1. **Check before act**: The handler queries `processed_jobs` before performing the payment.
2. **Atomic record**: The payment and the deduplication record are committed in a single transaction.
3. **Safe on redelivery**: If the job is delivered again, the check finds the existing record and skips execution.
4. **Uses job `id`**: The OJS-assigned `id` serves as the natural idempotency key.

### 13.2 Non-Idempotent Handler (Anti-Pattern)

```
// WARNING: This handler is NOT idempotent.
// Duplicate delivery will charge the customer twice.
function handle_payment_job_UNSAFE(job):
    payment_id = job.args["payment_id"]
    amount     = job.args["amount"]

    // No deduplication check -- every delivery triggers a charge
    payment_gateway.charge(payment_id, amount)

    return SUCCESS
```

This handler will cause duplicate charges if the job is redelivered after a worker crash or visibility timeout expiration. Every OJS handler that performs non-idempotent side effects SHOULD implement the pattern shown in Section 13.1.

---

## Appendix A: Changelog

| Date       | Change                        |
|------------|-------------------------------|
| 2026-02-15 | Initial release candidate.    |
