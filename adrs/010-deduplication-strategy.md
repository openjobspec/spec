# ADR-010: Deduplication Strategy

## Status

Accepted

## Context

Job deduplication is widely considered one of the hardest unsolved problems in background job processing. When the same logical job is enqueued multiple times — due to retries, user double-clicks, or concurrent producers — the system must decide whether to accept or reject the duplicate. Getting this wrong leads to either duplicate work (wasted resources, incorrect side effects) or lost work (legitimate jobs rejected as duplicates).

Existing systems take wildly different approaches. Oban uses multi-dimensional uniqueness keys that can combine job type, queue, arguments, and metadata fields with configurable time windows and state filters. BullMQ uses simple job IDs for deduplication — if a job with the same ID exists, the new one is rejected. Faktory provides a `unique_for` time window during which jobs with matching type and arguments are considered duplicates. Research from the `ojs-unique-jobs.md` analysis revealed that no single approach satisfies all use cases, and the choice between simplicity and expressiveness has significant implications for backend implementors.

The spec needed to choose a deduplication model that covers real-world patterns without requiring all backends to implement complex atomic operations. A simple ID-based approach is easy to implement but cannot express "unique per queue" or "unique only while pending." A rich multi-dimensional approach covers more scenarios but demands sophisticated backend support for atomic check-and-insert across multiple dimensions.

## Decision

We adopt multi-dimensional uniqueness via a UniquePolicy configuration that allows producers to specify which dimensions constitute uniqueness for a given job. The configurable dimensions include job type, queue, args (or a subset of args), and metadata fields. Producers can also specify conflict resolution strategies — reject (return an error), replace (overwrite the existing job), or drop (silently discard the duplicate) — and filter by job state (e.g., "unique only among pending and running jobs, but allow a new enqueue if the previous one completed").

To accommodate the wide range of backend capabilities, we define two guarantee tiers. The "strong" tier requires atomic check-and-insert: the backend verifies uniqueness and inserts the job in a single atomic operation, preventing race conditions between concurrent producers. The "best-effort" tier allows a non-atomic check-then-insert, accepting that rare race conditions may result in duplicates under high concurrency. Backends declare which tier they support in their conformance profile.

This tiered approach lets backends start with best-effort deduplication (sufficient for most workloads) and upgrade to strong guarantees as their implementation matures or their storage backend adds support for atomic operations.

## Consequences

### Easier

- **Real-world coverage**: Multi-dimensional uniqueness covers the vast majority of deduplication patterns seen in production systems
- **Incremental backend adoption**: Backends can start with best-effort guarantees and upgrade to strong guarantees without changing the API surface
- **Flexible conflict resolution**: Producers choose what happens on conflict (reject, replace, drop), enabling different deduplication semantics for different job types
- **State-aware uniqueness**: Filtering by job state prevents completed jobs from blocking new enqueues of the same logical work

### Harder

- **Strong guarantee complexity**: Atomic check-and-insert requires backend-specific operations (database constraints, Lua scripts in Redis, conditional writes) that vary significantly across storage engines
- **Encrypted field deduplication**: When client-side encryption is used (ADR-007), uniqueness checks on encrypted args fields are impossible since identical plaintext produces different ciphertext
- **Key computation overhead**: Computing uniqueness keys across multiple dimensions adds per-enqueue overhead, especially when hashing large argument payloads
- **Cross-queue uniqueness**: Uniqueness checks spanning multiple queues require global coordination, which conflicts with queue-level partitioning strategies
