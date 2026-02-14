# ADR-011: OpenTelemetry-Native Observability

## Status

Accepted

## Context

Job processing systems require robust observability to diagnose failures, monitor throughput, and trace work across distributed components. When a job is enqueued by a web request handler and processed by a worker on a different machine minutes later, operators need to correlate these events into a single trace to understand end-to-end latency and failure modes.

The spec faced a choice: define its own observability model (custom span names, metric definitions, and context propagation format) or adopt an existing industry standard. A custom model would give us full control over naming and semantics, but it would require every monitoring tool to add OJS-specific support. Adopting an existing standard means compromising on some naming conventions but gaining immediate compatibility with the entire ecosystem of observability tools.

OpenTelemetry (OTel) has emerged as the industry standard for distributed tracing, metrics, and logging. It provides semantic conventions for messaging systems that map naturally to job processing concepts (producers, consumers, message queues). Major observability platforms — Jaeger, Zipkin, Datadog, Grafana, New Relic — all support OTel natively. The CNCF backing and broad adoption make it a safe long-term choice.

## Decision

We adopt OpenTelemetry as the native observability framework for OJS. Implementations SHOULD use OTel semantic conventions for messaging systems (`messaging.*` attributes) to describe job operations, ensuring that existing OTel-compatible tools can display OJS traces without custom configuration.

OJS defines specific span conventions for the two primary operations: enqueue creates a PRODUCER span (representing the creation of a message) and process creates a CONSUMER span (representing the consumption and processing of a message). These spans carry OJS-specific attributes (`ojs.job.type`, `ojs.job.id`, `ojs.queue.name`) alongside standard messaging attributes. The PRODUCER span links to the CONSUMER span via W3C Trace Context propagated through job metadata, enabling end-to-end trace correlation even when jobs are processed hours after enqueue.

W3C Trace Context (the `traceparent` and `tracestate` headers) is the required propagation format, carried in job metadata fields. This ensures interoperability across different OTel SDK implementations and languages. Implementations that do not use OTel internally MUST still propagate trace context through metadata to avoid breaking trace chains.

## Consequences

### Easier

- **Ecosystem compatibility**: OJS traces appear natively in Jaeger, Zipkin, Datadog, Grafana Tempo, and any OTel-compatible backend without custom plugins
- **No reinventing the wheel**: OTel's semantic conventions for messaging provide well-tested naming patterns and attribute definitions
- **Familiar to operators**: Teams already using OTel for HTTP and database tracing can extend the same tooling to job processing
- **Cross-language correlation**: W3C Trace Context propagation works across all OTel SDK implementations regardless of language

### Harder

- **OTel dependency**: Full observability conformance requires OTel SDK integration, adding a dependency that some minimal implementations may resist
- **Evolving semantic conventions**: OTel messaging semantic conventions are still stabilizing, meaning attribute names may change in future OTel releases
- **Cardinality management**: High-throughput job systems can produce enormous volumes of spans and metrics, requiring careful sampling and aggregation strategies to avoid overwhelming observability backends
