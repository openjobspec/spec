# Open Job Spec (OJS)

**A universal, language-agnostic standard for background job processing.**

<!--
[![Spec Version](https://img.shields.io/badge/spec-v1.0.0--rc.1-blue)](https://openjobspec.org)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](../LICENSE)
[![Conformance](https://img.shields.io/badge/conformance-passing-brightgreen)](spec/ojs-conformance.md)
-->

## Overview

Open Job Spec (OJS) defines a vendor-neutral, protocol-agnostic envelope format for describing background jobs. Today every job framework -- Sidekiq, BullMQ, Celery, Faktory -- invents its own wire format, its own retry semantics, and its own lifecycle model. OJS replaces that fragmentation with a single, well-specified standard so that producers, brokers, and workers can be mixed and matched across languages, backends, and deployment topologies.

## Architecture

OJS follows a layered architecture inspired by [CloudEvents](https://cloudevents.io):

```
+-------------------------------------------------+
|           Layer 3: Protocol Bindings             |
|         (HTTP, gRPC, AMQP, custom)              |
+-------------------------------------------------+
|           Layer 2: Wire Formats                  |
|            (JSON, Protobuf, ...)                 |
+-------------------------------------------------+
|           Layer 1: Core Specification            |
|     (Logical model, required attributes,         |
|      type system, extension framework)           |
+-------------------------------------------------+
```

- **Layer 1 -- Core** defines the abstract data model: what attributes a job envelope carries, which are required, how types work, and how extensions plug in.
- **Layer 2 -- Wire Formats** map that abstract model to concrete serialization (JSON today, Protobuf planned).
- **Layer 3 -- Protocol Bindings** define how a serialized job is transmitted over a specific transport (HTTP, gRPC, and others).

This separation means you can add a new transport without touching the core model, or add a new serialization without changing any binding.

## Specification Documents

### Core

| Document | Description |
|----------|-------------|
| [ojs-core.md](spec/ojs-core.md) | **Core Specification (Layer 1)** -- Abstract data model, required and optional attributes, type system, extension points |

### Wire Formats

| Document | Description |
|----------|-------------|
| [ojs-json-format.md](spec/ojs-json-format.md) | **JSON Wire Format (Layer 2)** -- JSON serialization rules, attribute mapping, batch encoding |
| [ojs-protobuf-format.md](spec/ojs-protobuf-format.md) | **Protobuf Wire Format (Layer 2)** -- Binary serialization, Protobuf schema design, type mapping, batch encoding |

### Protocol Bindings

| Document | Description |
|----------|-------------|
| [ojs-http-binding.md](spec/ojs-http-binding.md) | **HTTP Protocol Binding (Layer 3)** -- HTTP method mapping, headers, status codes |
| [ojs-grpc-binding.md](spec/ojs-grpc-binding.md) | **gRPC Protocol Binding (Layer 3)** -- Protobuf service definition, streaming, error codes |
| [ojs-amqp-binding.md](spec/ojs-amqp-binding.md) | **AMQP Protocol Binding (Layer 3)** -- RabbitMQ/AMQP 0-9-1 queue mapping, exchange topology, retry via DLX |

### Extensions

| Document | Description |
|----------|-------------|
| [ojs-retry.md](spec/ojs-retry.md) | **Retry Policy** -- Backoff strategies, max attempts, dead-letter semantics |
| [ojs-unique-jobs.md](spec/ojs-unique-jobs.md) | **Unique Jobs / Deduplication** -- Uniqueness keys, lock windows, conflict resolution |
| [ojs-workflows.md](spec/ojs-workflows.md) | **Workflow Primitives** -- Chain, group, and batch composition, fan-out/fan-in |
| [ojs-cron.md](spec/ojs-cron.md) | **Cron / Periodic Jobs** -- Cron expressions, timezone handling, overlap policies |
| [ojs-events.md](spec/ojs-events.md) | **Event Vocabulary** -- Lifecycle events emitted by brokers and workers |
| [ojs-middleware.md](spec/ojs-middleware.md) | **Middleware Chains** -- Interceptor model for cross-cutting concerns |

### Runtime

| Document | Description |
|----------|-------------|
| [ojs-worker-protocol.md](spec/ojs-worker-protocol.md) | **Worker Lifecycle** -- Registration, heartbeats, graceful shutdown, signal handling |
| [ojs-conformance.md](spec/ojs-conformance.md) | **Conformance Levels** -- Tiered compliance requirements for implementations |

### Official Extensions

| Document | Description |
|----------|-------------|
| [ojs-admin-api.md](spec/ojs-admin-api.md) | **Admin and Operator API** -- Queue management, job inspection, bulk operations, worker management |
| [ojs-observability.md](spec/ojs-observability.md) | **Observability** -- OpenTelemetry trace context, span conventions, metrics |
| [ojs-priority.md](spec/ojs-priority.md) | **Job Priority** -- Integer priority levels, strict/weighted queue consumption, dynamic adjustment |
| [ojs-fair-scheduling.md](spec/ojs-fair-scheduling.md) | **Fair Scheduling** -- Competing consumers, worker pools, weighted fair queuing, starvation prevention |
| [ojs-bulk-operations.md](spec/ojs-bulk-operations.md) | **Bulk Operations** -- Batch enqueue/cancel/retry/delete, atomicity modes, partial failure semantics |
| [ojs-progress.md](spec/ojs-progress.md) | **Job Progress** -- Numeric and structured progress reporting, checkpoint resumption, SSE streaming |
| [ojs-backpressure.md](spec/ojs-backpressure.md) | **Backpressure** -- Reject, block, and drop-oldest strategies for queue bounds |
| [ojs-dead-letter.md](spec/ojs-dead-letter.md) | **Dead Letter Queue** -- Retention, manual retry, automatic replay, pruning |
| [ojs-graceful-shutdown.md](spec/ojs-graceful-shutdown.md) | **Graceful Shutdown** -- Signal handling, drain semantics, container integration |
| [ojs-rate-limiting.md](spec/ojs-rate-limiting.md) | **Rate Limiting** -- Concurrency limits, window-based limiting, throttling |
| [ojs-testing.md](spec/ojs-testing.md) | **Testing** -- Fake, inline, and real modes, assertion helpers, test utilities |
| [ojs-extension-lifecycle.md](spec/ojs-extension-lifecycle.md) | **Extension Lifecycle** -- Core, official, and experimental tier system, promotion criteria |
| [ojs-security.md](spec/ojs-security.md) | **Security Considerations** -- Threat model, transport security, authentication, authorization, input validation |
| [ojs-delivery-guarantees.md](spec/ojs-delivery-guarantees.md) | **Delivery Guarantees** -- At-least-once, exactly-once semantics, CAP theorem, idempotency patterns |
| [ojs-payload-limits.md](spec/ojs-payload-limits.md) | **Payload Limits** -- Size constraints, external payload references, chunking, compression |
| [ojs-disaster-recovery.md](spec/ojs-disaster-recovery.md) | **Disaster Recovery & HA** -- Durability guarantees, replication, failover, backup/restore |
| [ojs-extension-interactions.md](spec/ojs-extension-interactions.md) | **Extension Interactions** -- Pairwise interaction matrix, middleware ordering, conflict resolution |
| [ojs-cloudevents-interop.md](spec/ojs-cloudevents-interop.md) | **CloudEvents Interoperability** -- Bidirectional conversion, event bridge, job triggers |
| [ojs-errors.md](spec/ojs-errors.md) | **Error Catalog** -- Canonical error codes, structured error format, HTTP/gRPC/AMQP mapping |
| [ojs-timeouts.md](spec/ojs-timeouts.md) | **Job Timeouts** -- Execution, total, and enqueue TTL timeouts, grace periods, heartbeat-based stall detection |
| [ojs-results.md](spec/ojs-results.md) | **Job Results** -- Result storage, retention, size limits, retrieval patterns, external result references |
| [ojs-webhooks.md](spec/ojs-webhooks.md) | **Webhook Delivery** -- Push-based event delivery, subscription management, HMAC signing, retry policies |
| [ojs-logging.md](spec/ojs-logging.md) | **Structured Logging** -- JSON log format, severity levels, job correlation, sampling, sensitive data handling |
| [ojs-queue-config.md](spec/ojs-queue-config.md) | **Queue Configuration** -- Queue lifecycle, capacity limits, DLQ routing, retention policies, default policies |

### Experimental Extensions

> ⚠️ **Note**: Experimental extensions (v0.1.0) may change in breaking ways. See [ojs-extension-lifecycle.md](spec/ojs-extension-lifecycle.md) for stability guarantees.

| Document | Description |
|----------|-------------|
| [ojs-encryption.md](spec/ojs-encryption.md) | **Encryption and Codecs** -- Payload encryption, compression, codec chaining |
| [ojs-framework-adapters.md](spec/ojs-framework-adapters.md) | **Framework Adapters** -- Transactional enqueue, outbox pattern |
| [ojs-job-versioning.md](spec/ojs-job-versioning.md) | **Job Versioning** -- Schema evolution, version routing, canary deployments |
| [ojs-multi-tenancy.md](spec/ojs-multi-tenancy.md) | **Multi-Tenancy** -- Tenant isolation, fairness scheduling, resource limits |

### Guides & Reference

| Document | Description |
|----------|-------------|
| [ojs-glossary.md](spec/ojs-glossary.md) | **Unified Glossary** -- Canonical definitions for all terms used across the specification |
| [ojs-sdk-guidelines.md](spec/ojs-sdk-guidelines.md) | **SDK Design Guidelines** -- Naming conventions, async patterns, error handling, language-specific guidance |
| [ojs-migration.md](spec/ojs-migration.md) | **Migration Guide** -- Attribute mapping and migration paths from Sidekiq, BullMQ, Celery, Faktory, Temporal, River |

### Machine-Readable Schemas

The specification is accompanied by machine-readable schema definitions maintained in sibling repositories:

| Repository | Description |
|------------|-------------|
| **[ojs-json-schema](../ojs-json-schema)** | JSON Schema definitions for job envelopes, policies, and all extension data structures |
| **[ojs-proto](../ojs-proto)** | Protocol Buffers definitions for the gRPC binding and binary wire format |

These repositories ensure naming consistency across protocols and provide the foundation for code generation, validation tooling, and IDE autocomplete in any language.

## Hello World

A minimal OJS job envelope:

```json
{
  "specversion": "1.0",
  "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "type": "email.send",
  "queue": "default",
  "args": ["user@example.com", "welcome"]
}
```

That is a complete, valid OJS job. A producer creates it; a broker routes it by `queue`; a worker matches on `type` and receives `args`. Everything else -- retries, scheduling, uniqueness, workflows -- layers on top through well-defined extensions.

## Design Principles

1. **Backend-agnostic.** OJS does not assume Redis, PostgreSQL, RabbitMQ, or any specific broker. The core model works with any storage or transport layer.

2. **Language-agnostic.** The specification is defined in terms of an abstract type system. Implementations exist (or can exist) in any programming language.

3. **Protocol-extensible.** New transports are added by writing a protocol binding document and a conformance test suite -- no changes to the core specification are required.

4. **Developer-first.** The simplest possible job (type + args) should require no boilerplate. Advanced features are opt-in through extensions, never mandatory.

## Conformance Levels

Implementations declare which conformance level they support. Each level is a strict superset of the previous one:

| Level | Name | Requirements |
|-------|------|--------------|
| **Level 0** | **Core** | Produce and consume valid job envelopes. Validate required attributes. |
| **Level 1** | **Retry** | Level 0 + retry policies, dead-letter handling, backoff strategies. |
| **Level 2** | **Scheduling** | Level 1 + delayed execution, cron/periodic jobs, timezone support. |
| **Level 3** | **Orchestration** | Level 2 + unique jobs, workflow primitives (DAGs, fan-out/fan-in). |
| **Level 4** | **Full** | Level 3 + event vocabulary, middleware chains, worker lifecycle protocol. |

See [ojs-conformance.md](spec/ojs-conformance.md) for the full test matrix and certification process.

## Reference Implementations

The OJS ecosystem includes reference implementations across multiple languages and backends:

| Repository | Description | Conformance |
|------------|-------------|-------------|
| **ojs-redis** | Redis-backed broker (Lua scripts, Streams) | Level 3 |
| **ojs-postgres** | PostgreSQL-backed broker (advisory locks, SKIP LOCKED) | Level 3 |
| **ojs-client-js** | JavaScript/TypeScript client SDK | Level 4 |
| **ojs-client-go** | Go client SDK | Level 4 |
| **ojs-client-python** | Python client SDK | Level 2 |
| **ojs-client-java** | Java client SDK | Level 2 |
| **ojs-conformance** | Language-agnostic conformance test suite | -- |

## Prior Art

OJS builds on lessons from years of production job processing systems:

- **[Sidekiq](https://sidekiq.org/)** -- Proved that Redis + simple JSON payloads scale to millions of jobs. OJS adopts the simplicity of its job format while generalizing beyond Ruby and Redis.
- **[BullMQ](https://docs.bullmq.io/)** -- Pioneered flow-based job composition in Node.js. OJS formalizes similar workflow primitives as a spec extension.
- **[Celery](https://docs.celeryq.dev/)** -- Demonstrated multi-broker, multi-language task processing. OJS embraces the same backend-agnostic philosophy at the specification level.
- **[Faktory](https://contribsys.com/faktory/)** -- Introduced a language-agnostic job server with a wire protocol. OJS takes this further by standardizing the envelope format itself.
- **[Temporal](https://temporal.io/)** -- Showed that durable execution and workflow orchestration need first-class primitives. OJS includes workflow extensions for simpler DAG-based use cases.
- **[CloudEvents](https://cloudevents.io/)** -- Provided the layered architecture model (core / format / binding) that OJS directly adopts.

## Contributing

We welcome contributions from everyone. Whether you are filing a bug, proposing an RFC, or implementing the spec in a new language, please read our **[Contributing Guide](CONTRIBUTING.md)** first.

## License

Open Job Spec is licensed under the [Apache License, Version 2.0](../LICENSE).

---

**[openjobspec.org](https://openjobspec.org)**



