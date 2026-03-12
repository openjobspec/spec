# ADR-016: AMQP Backend Architecture

## Status

Accepted

## Context

RabbitMQ is one of the most widely deployed message brokers, supporting AMQP 0-9-1 with durable queues, consumer acknowledgments, and exchange-based routing. Many organizations already run RabbitMQ in production and want to adopt OJS without introducing a new data store.

However, AMQP 0-9-1 is a message transport protocol, not a job state store. It provides message delivery and acknowledgment but lacks: job state tracking across the 8-state lifecycle, rich query capabilities (list jobs by state, queue statistics), scheduled job promotion, cron firing, retry backoff with delay, and workflow orchestration.

The question was how to build a full-conformance OJS backend on top of RabbitMQ while maintaining the simplicity and operational familiarity that RabbitMQ users expect.

### Options Considered

1. **AMQP + PostgreSQL**: RabbitMQ for transport, PostgreSQL for state. Full query capability but adds a database dependency, negating the "just RabbitMQ" appeal.
2. **AMQP + Redis**: RabbitMQ for transport, Redis for state. Performant but adds Redis as a dependency.
3. **AMQP + SQLite**: RabbitMQ for transport, embedded SQLite for state. Zero additional infrastructure — the state store is a local file.
4. **AMQP only (in-memory state)**: Purely in-memory state tracking. Zero persistence but loses state on restart.

## Decision

We chose **Option 3: AMQP + SQLite** as the default, with **Option 4 (in-memory)** available via configuration (`OJS_PERSIST=""`).

SQLite provides:
- Full SQL query capability for job listing, filtering, and statistics
- WAL mode for concurrent read/write without blocking
- Zero infrastructure — no additional services to deploy or manage
- File-based persistence that survives process restarts
- Configurable via `OJS_PERSIST=ojs-amqp.db` (default) or `OJS_PERSIST=""` for pure in-memory

RabbitMQ handles:
- Message delivery to workers via consumer groups
- Message acknowledgment for at-least-once delivery
- Exchange-based routing for queue multiplexing

A background scheduler runs the same periodic tasks as other backends:
- Scheduled job promotion (scheduled → available)
- Retry backoff delay management
- Stalled job reaping (visibility timeout)
- Cron job firing
- Expired job purging

## Consequences

### Positive

- **Zero additional infrastructure**: Users with existing RabbitMQ deployments need nothing else.
- **Full conformance**: The SQLite state store enables all L0–L4 conformance tests to pass.
- **Operational simplicity**: Single binary with embedded state, familiar RabbitMQ operational model.
- **Flexible persistence**: Users can choose between durable (SQLite) and ephemeral (in-memory) modes.

### Negative

- **Single-node state**: SQLite is local to the process, so horizontal scaling requires external coordination or a switch to a shared state store.
- **Not suitable for high-throughput distributed deployments**: For those use cases, the Redis or PostgreSQL backends are recommended.
- **SQLite WAL file management**: The WAL file can grow during heavy write periods and requires periodic checkpointing (handled automatically by SQLite).
