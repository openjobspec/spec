# ADR-009: Transactional Enqueue Pattern

## Status

Accepted

## Context

Applications frequently need to persist business data and enqueue a job as a single atomic operation. For example, when a user places an order, the application must save the order to the database and enqueue a fulfillment job. If these operations are not atomic, the system can end up in inconsistent states: the order is saved but the job is never enqueued (lost work), or the job is enqueued but the order save fails (phantom job processing nonexistent data).

This problem is well-known in distributed systems as the "dual write" problem. Two broad solutions exist. For database-backed job backends (like Oban on PostgreSQL or Solid Queue on MySQL), the application can insert the job row in the same database transaction as the business data — true atomicity with no additional infrastructure. For external backends (like Redis-backed Sidekiq or cloud queue services), the application cannot span a transaction across two systems, so an outbox pattern is used: the job is written to an outbox table in the application's database within the same transaction, and a separate relay process reads the outbox and enqueues jobs to the external backend.

Both patterns are proven in production, but they have different operational characteristics. In-transaction enqueue is simpler and has no additional latency, but it requires the job backend to use the same database as the application. The outbox pattern works with any backend but introduces a relay process, polling latency, and an outbox table that must be maintained.

## Decision

We support both transactional enqueue patterns through a Framework Adapter interface. The adapter provides a unified API for atomic job enqueue — from the application's perspective, the call is the same regardless of the underlying strategy.

For database-backed backends, the adapter participates in the application's existing database transaction, inserting the job row alongside business data. When the transaction commits, the job is atomically visible to workers. For external backends, the adapter writes to an outbox table within the application's transaction. A relay process (provided by the adapter or the backend implementation) polls the outbox and enqueues jobs to the external system, deleting outbox entries after successful enqueue.

The Framework Adapter interface is the same for both strategies — implementations choose the appropriate strategy based on their backend type. This means application code does not need to change when switching between a database-backed backend and an external backend; only the adapter configuration changes.

## Consequences

### Easier

- **Consistency guarantees**: Applications get atomic enqueue semantics regardless of backend type, eliminating dual-write bugs
- **Clean abstraction**: The Framework Adapter hides the complexity of the chosen strategy behind a unified interface
- **Framework integration**: Web frameworks (Rails, Django, Spring) can integrate the adapter into their transaction lifecycle naturally
- **Backend portability**: Applications can switch between database-backed and external backends without changing enqueue code

### Harder

- **Outbox relay operations**: The outbox pattern introduces a relay process that must be deployed, monitored, and scaled independently
- **Polling latency**: Outbox-based enqueue adds latency between transaction commit and job visibility, which may be unacceptable for time-sensitive jobs
- **Outbox table maintenance**: The outbox table accumulates rows and requires periodic cleanup to prevent unbounded growth
- **Relay failure modes**: If the relay process crashes or falls behind, jobs queue up in the outbox, requiring alerting and recovery procedures
