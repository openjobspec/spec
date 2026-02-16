# ADR-013: NATS JetStream Backend Architecture

## Status

Accepted

## Context

OJS requires backend implementations to support the full job lifecycle, including ordered delivery, visibility timeouts, retries, and state tracking. NATS with JetStream provides a distributed messaging system with persistence, but unlike Redis or PostgreSQL, it does not natively offer the job-queue semantics (priority, scheduled execution, state machine) that OJS requires.

The challenge was determining how to map OJS operations onto NATS primitives while preserving conformance across all 5 levels.

### Key NATS Constraints

1. JetStream provides at-least-once delivery with explicit ack, but no built-in priority or delayed delivery
2. NATS KV (backed by JetStream) provides key-value storage but lacks query/filter capabilities
3. Pull consumers provide backpressure-friendly consumption but no server-side filtering by job state
4. No native scheduled message delivery or visibility timeout mechanism

## Decision

Use a **dual-subsystem architecture**: JetStream streams for message transport and NATS KV buckets for job state management.

### Transport Layer (JetStream)

- One JetStream stream `OJS` with subject hierarchy `ojs.queue.{name}.jobs`
- Job enqueue publishes to the queue's subject
- Job fetch uses pull consumers with explicit ack policy
- Each queue gets its own durable pull consumer for isolation

### State Layer (NATS KV)

- KV bucket stores full job state (metadata, attempt count, retry policy, timestamps)
- Job ack acknowledges the JetStream message and updates KV state
- Job nack acknowledges the message (preventing redelivery) and writes retry metadata to KV; a scheduler goroutine re-publishes when the backoff period elapses
- Visibility timeout tracked in KV with a reaper goroutine that re-enqueues timed-out jobs

### Scheduling and Priorities

- Scheduled jobs are stored in KV with a `run_at` timestamp; a promoter goroutine polls and publishes when due
- Priority is stored in KV metadata and applied at fetch time by the server, not by NATS
- Cron jobs managed entirely in KV with a scheduler that publishes at cron intervals

## Consequences

**Positive:**
- Full Level 0–4 conformance achieved
- NATS clustering provides built-in high availability
- Subject-based routing enables clean queue isolation
- Pull consumers provide natural backpressure

**Negative:**
- Dual-subsystem adds complexity compared to single-store backends (Redis, PostgreSQL)
- Scheduled delivery requires server-side goroutines rather than database-native mechanisms
- Priority ordering is approximate when multiple consumers compete
- KV operations are not transactional across keys, requiring careful ordering of state updates

**Trade-offs:**
- Chose explicit ack + KV-tracked retry over JetStream's built-in retry (NAK with delay) to maintain control over backoff strategies and attempt counting
- Chose server-side priority sorting over multiple streams per priority to keep the NATS resource footprint bounded
