# ADR-014: Kafka Hybrid Backend Architecture

## Status

Accepted

## Context

Apache Kafka excels at high-throughput, ordered log-based messaging but lacks native job-queue primitives such as visibility timeouts, per-job state tracking, priority ordering, and scheduled delivery. OJS requires all of these for full conformance.

The question was whether to build all OJS semantics purely on Kafka primitives (topics, consumer groups, compacted topics) or introduce a complementary state store.

### Options Considered

1. **Kafka-only**: Use Kafka topics for queues, compacted topics for state, consumer group rebalancing for assignment. Feasible for Level 0–1 but extremely complex for workflows, cron, and unique jobs.
2. **Kafka + Redis hybrid**: Use Kafka for message transport (high throughput, ordering) and Redis for job state (fast lookups, TTL, Lua scripting). Simpler to implement, leverages each system's strengths.
3. **Kafka + PostgreSQL hybrid**: Similar to option 2 but with stronger durability guarantees. Higher latency for state queries.

## Decision

Use **Kafka + Redis hybrid architecture** (Option 2).

### Transport Layer (Kafka)

- One Kafka topic per OJS queue, using KRaft mode (no ZooKeeper dependency)
- Job enqueue produces to the queue's topic
- Job fetch consumes from the topic via consumer groups with manual offset commit
- Partition assignment provides natural parallelism

### State Layer (Redis)

- Redis stores full job state, indexed by job ID
- Job ack commits the Kafka offset and updates Redis state
- Visibility timeout tracked in Redis with TTL-based expiration
- Retry scheduling uses Redis sorted sets with score = next attempt timestamp
- Workflow DAG state, cron definitions, and unique job constraints all in Redis
- Lua scripts ensure atomic multi-key state transitions

### Why Not Kafka-Only?

- Kafka consumer groups don't support visibility timeouts (a consumed message is committed or not)
- Job-level state queries (get by ID, filter by state) require a secondary index that Kafka doesn't provide
- Scheduled delivery and priority ordering require out-of-band mechanisms regardless

## Consequences

**Positive:**
- Full Level 0–4 conformance achieved
- Kafka provides 50K+ jobs/second throughput for high-volume workloads
- Redis provides sub-millisecond state queries
- KRaft mode eliminates ZooKeeper operational complexity
- Clean separation: Kafka handles durability and ordering, Redis handles state and scheduling

**Negative:**
- Two infrastructure dependencies (Kafka + Redis) increase operational complexity
- State consistency between Kafka offsets and Redis requires careful error handling
- Redis failure impacts state queries even if Kafka is healthy

**Trade-offs:**
- Chose Redis over PostgreSQL for the state store to minimize latency on hot paths (fetch, ack, heartbeat)
- Chose one-topic-per-queue over a single topic with headers to simplify consumer group management and enable per-queue throughput tuning
