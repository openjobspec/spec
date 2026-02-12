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
| [ojs-core.md](ojs-core.md) | **Core Specification (Layer 1)** -- Abstract data model, required and optional attributes, type system, extension points |

### Wire Formats

| Document | Description |
|----------|-------------|
| [ojs-json-format.md](ojs-json-format.md) | **JSON Wire Format (Layer 2)** -- JSON serialization rules, attribute mapping, batch encoding |

### Protocol Bindings

| Document | Description |
|----------|-------------|
| [ojs-http-binding.md](ojs-http-binding.md) | **HTTP Protocol Binding (Layer 3)** -- HTTP method mapping, headers, status codes |
| [ojs-grpc-binding.md](ojs-grpc-binding.md) | **gRPC Protocol Binding (Layer 3)** -- Protobuf service definition, streaming, error codes |

### Extensions

| Document | Description |
|----------|-------------|
| [ojs-retry.md](ojs-retry.md) | **Retry Policy** -- Backoff strategies, max attempts, dead-letter semantics |
| [ojs-unique-jobs.md](ojs-unique-jobs.md) | **Unique Jobs / Deduplication** -- Uniqueness keys, lock windows, conflict resolution |
| [ojs-workflows.md](ojs-workflows.md) | **Workflow Primitives** -- DAG-based job composition, fan-out/fan-in, callbacks |
| [ojs-cron.md](ojs-cron.md) | **Cron / Periodic Jobs** -- Cron expressions, timezone handling, overlap policies |
| [ojs-events.md](ojs-events.md) | **Event Vocabulary** -- Lifecycle events emitted by brokers and workers |
| [ojs-middleware.md](ojs-middleware.md) | **Middleware Chains** -- Interceptor model for cross-cutting concerns |

### Runtime

| Document | Description |
|----------|-------------|
| [ojs-worker-protocol.md](ojs-worker-protocol.md) | **Worker Lifecycle** -- Registration, heartbeats, graceful shutdown, signal handling |
| [ojs-conformance.md](ojs-conformance.md) | **Conformance Levels** -- Tiered compliance requirements for implementations |

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

See [ojs-conformance.md](ojs-conformance.md) for the full test matrix and certification process.

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
