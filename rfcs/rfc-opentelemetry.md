# RFC-0002: OpenTelemetry Distributed Tracing

- **Stage**: 1 (Proposal)
- **Champion**: TBD
- **Created**: 2025-07-25
- **Last Updated**: 2025-07-25
- **Target Spec Version**: 0.2.0

## Summary

This RFC proposes a standardized OpenTelemetry integration for all OJS backends and SDKs. It defines trace context propagation via the job `meta` object, span naming conventions, metric names, and baggage semantics so that any OJS-compliant implementation produces consistent, interoperable telemetry.

## Motivation

Distributed tracing is essential for debugging production job processing systems. Today, the OJS core spec reserves `trace_id` and `span_id` as well-known `meta` keys but does not specify:

1. **How trace context propagates** between producers and consumers. A Go producer enqueuing a job and a Python worker executing it have no standard way to link their spans into a single trace.

2. **What spans to emit**. Each SDK and backend can choose its own span names, attributes, and boundaries, making cross-implementation dashboards impossible.

3. **What metrics to export**. Without a common metric vocabulary, operators cannot build a single monitoring dashboard for heterogeneous OJS deployments (e.g., Redis backend + Postgres backend behind a load balancer).

4. **How baggage travels with jobs**. OpenTelemetry Baggage allows key-value pairs to propagate across service boundaries, but there is no convention for carrying baggage through the job queue.

The v0.2 roadmap explicitly calls for "OpenTelemetry distributed tracing to all backends." This RFC formalizes the requirements so that all implementations converge on a single telemetry model.

### Use Cases

1. **End-to-end request tracing**: A web request handler enqueues a `report.generate` job. The operator sees the enqueue span, the queue wait time, and the worker execution span in a single Jaeger trace.

2. **Cross-SDK debugging**: A Go service enqueues a job. A TypeScript worker processes it and enqueues a follow-up. A Python worker completes the chain. All three spans appear in one trace.

3. **SLO monitoring**: An SRE defines an SLO on job processing latency. Standardized metrics (`ojs.job.duration`, `ojs.queue.depth`) feed into the SLO dashboard regardless of which backend is in use.

## Prior Art

### Sidekiq (Ruby)

Sidekiq does not natively integrate with OpenTelemetry. Third-party gems (`opentelemetry-instrumentation-sidekiq`) instrument enqueue and perform operations. Trace context is propagated by injecting W3C Trace Context headers into the job's argument hash. Span names follow the pattern `{queue} send` and `{queue} process`.

**Lesson**: Injecting trace context into the job payload works but pollutes application data. OJS should use the `meta` object instead.

### Celery (Python)

The `opentelemetry-instrumentation-celery` package instruments `apply_async` (producer) and task execution (consumer). It uses Celery's `headers` dictionary for trace context propagation. Span names follow `{task_name} apply_async` and `{task_name} run`.

**Lesson**: Using a dedicated metadata channel (headers) keeps trace context separate from task arguments. This aligns with OJS's `meta` object approach.

### Temporal (Go/TypeScript)

Temporal has first-class OpenTelemetry support via interceptors. Trace context is propagated through workflow headers. Spans cover workflow start, activity execution, and signal handling. Temporal defines semantic conventions specific to its workflow model.

**Lesson**: First-class interceptor/middleware integration makes adoption frictionless. OJS middleware chains are the natural integration point.

### OpenTelemetry Semantic Conventions for Messaging

The OpenTelemetry project defines [semantic conventions for messaging systems](https://opentelemetry.io/docs/specs/semconv/messaging/) with standardized attribute names (`messaging.system`, `messaging.destination.name`, `messaging.operation`). These conventions apply to systems like Kafka, RabbitMQ, and SQS.

**Lesson**: OJS should align with these conventions where applicable and extend them for job-specific semantics (lifecycle states, retry counts, workflow membership).

## Detailed Design

### 1. Trace Context Propagation

Trace context MUST be propagated through the job's `meta` object using W3C Trace Context format. *Rationale: The `meta` object is the spec-designated extensibility mechanism, and W3C Trace Context is the industry standard supported by all OpenTelemetry SDKs.*

#### Required Meta Attributes

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `ojs.otel.traceparent` | string | SHOULD | W3C `traceparent` header value (version-trace_id-parent_id-trace_flags) |
| `ojs.otel.tracestate` | string | MAY | W3C `tracestate` header value for vendor-specific context |
| `ojs.otel.baggage` | string | MAY | W3C Baggage header value (key-value pairs) |

#### Propagation Flow

```
Producer SDK                  Backend                    Consumer SDK
    │                            │                            │
    ├─ Create enqueue span       │                            │
    ├─ Inject traceparent ──────►│                            │
    │  into meta                 ├─ Store meta with job       │
    ├─ Finish enqueue span       │                            │
    │                            │                            │
    │                            ├─ Return job to worker ────►│
    │                            │                            ├─ Extract traceparent
    │                            │                            │  from meta
    │                            │                            ├─ Create process span
    │                            │                            │  (child of producer)
    │                            │                            ├─ Execute handler
    │                            │                            ├─ Finish process span
```

Backends MUST preserve `meta` attributes with the `ojs.otel.` prefix without modification. *Rationale: Backends that strip or modify trace context would break trace continuity.*

### 2. Span Naming Conventions

All OJS implementations MUST use the following span naming pattern, aligned with OpenTelemetry messaging semantic conventions:

```
{job_type} {operation}
```

Where `operation` is one of the standard messaging operations:

| Operation | Span Name Example | Description |
|-----------|-------------------|-------------|
| `publish` | `email.send publish` | Producer enqueues a job |
| `receive` | `email.send receive` | Consumer fetches a job from the queue |
| `process` | `email.send process` | Consumer executes the job handler |

#### Span Attributes

All spans MUST include the following attributes:

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `messaging.system` | string | MUST | Always `"ojs"` |
| `messaging.operation` | string | MUST | `"publish"`, `"receive"`, or `"process"` |
| `messaging.destination.name` | string | MUST | Queue name (e.g., `"default"`, `"email"`) |
| `messaging.message.id` | string | MUST | Job ID (UUIDv7) |
| `ojs.job.type` | string | MUST | Job type (e.g., `"email.send"`) |
| `ojs.job.attempt` | int | SHOULD | Current attempt number |
| `ojs.job.state` | string | SHOULD | Job state after the operation |
| `ojs.job.priority` | int | MAY | Job priority |

#### Additional Attributes for Specific Operations

**Publish spans:**

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `ojs.job.scheduled_at` | string | MAY | RFC 3339 timestamp if job is scheduled for future execution |
| `ojs.job.unique_key` | string | MAY | Unique job key if uniqueness is configured |

**Process spans:**

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `ojs.job.duration_ms` | double | SHOULD | Handler execution time in milliseconds |
| `ojs.job.outcome` | string | MUST | `"completed"`, `"failed"`, or `"cancelled"` |
| `ojs.job.error.type` | string | MAY | Error class/type if the job failed |
| `ojs.job.error.message` | string | MAY | Error message if the job failed |

### 3. Backend Spans

Backends SHOULD emit spans for internal operations to provide visibility into queue internals:

| Span Name | Description |
|-----------|-------------|
| `ojs.backend.enqueue` | Time to persist the job to storage |
| `ojs.backend.dequeue` | Time to fetch and lock a job |
| `ojs.backend.ack` | Time to acknowledge completion |
| `ojs.backend.nack` | Time to return a failed job to the queue |
| `ojs.backend.heartbeat` | Time to extend a job's active lease |

Backend spans MUST be children of the SDK operation span when trace context is available. *Rationale: Linking backend spans to SDK spans enables end-to-end latency analysis.*

### 4. Workflow Spans

Workflow operations introduce additional span boundaries:

```
workflow.create publish                      (root span for workflow)
├── step[0]: email.send publish              (chain step 1)
│   └── email.send process
├── step[1]: notification.push publish       (chain step 2)
│   └── notification.push process
└── group[0]                                 (parallel group)
    ├── report.pdf publish
    │   └── report.pdf process
    └── report.csv publish
        └── report.csv process
```

| Span Name | Description |
|-----------|-------------|
| `{workflow_type} publish` | Workflow enqueue |
| `{workflow_type} step[{index}]` | Sequential step in a chain |
| `{workflow_type} group[{index}]` | Parallel group fan-out |
| `{workflow_type} complete` | Workflow completion (all steps done) |

Workflow spans MUST use [span links](https://opentelemetry.io/docs/concepts/signals/traces/#span-links) to connect individual job spans to the parent workflow span. *Rationale: Span links preserve the logical relationship without imposing a strict parent-child hierarchy, which would be inaccurate for parallel groups.*

### 5. Metric Definitions

All OJS implementations SHOULD export the following metrics using OpenTelemetry Metrics API:

#### Counters

| Metric Name | Unit | Description | Attributes |
|-------------|------|-------------|------------|
| `ojs.job.enqueued` | `{job}` | Total jobs enqueued | `ojs.job.type`, `messaging.destination.name` |
| `ojs.job.completed` | `{job}` | Total jobs completed successfully | `ojs.job.type`, `messaging.destination.name` |
| `ojs.job.failed` | `{job}` | Total job failures (per attempt) | `ojs.job.type`, `messaging.destination.name` |
| `ojs.job.discarded` | `{job}` | Total jobs discarded (retries exhausted) | `ojs.job.type`, `messaging.destination.name` |
| `ojs.job.cancelled` | `{job}` | Total jobs cancelled | `ojs.job.type`, `messaging.destination.name` |
| `ojs.job.retried` | `{job}` | Total retry attempts | `ojs.job.type`, `messaging.destination.name` |

#### Histograms

| Metric Name | Unit | Description | Attributes |
|-------------|------|-------------|------------|
| `ojs.job.duration` | `ms` | Job handler execution time | `ojs.job.type`, `messaging.destination.name`, `ojs.job.outcome` |
| `ojs.job.queue_time` | `ms` | Time from enqueue to worker pickup | `ojs.job.type`, `messaging.destination.name` |

#### Gauges

| Metric Name | Unit | Description | Attributes |
|-------------|------|-------------|------------|
| `ojs.queue.depth` | `{job}` | Current number of jobs in queue | `messaging.destination.name`, `ojs.job.state` |
| `ojs.worker.active_jobs` | `{job}` | Currently executing jobs | `ojs.worker.id` |

### 6. Baggage Propagation

OpenTelemetry Baggage carried in the `ojs.otel.baggage` meta attribute MUST be restored in the consumer context before the handler executes. *Rationale: Baggage enables cross-cutting concerns (tenant ID, feature flags) to propagate through job chains without requiring application-level plumbing.*

Implementations MUST NOT automatically add entries to baggage. Only entries explicitly set by the application SHOULD be propagated. *Rationale: Unbounded baggage growth is a known performance concern in distributed systems.*

### 7. SDK Integration Points

Each SDK MUST provide OpenTelemetry integration through the existing middleware mechanism:

```go
// Go SDK — middleware-based integration
worker := ojs.NewWorker(ojs.WorkerConfig{
    Middleware: []ojs.Middleware{
        otelMiddleware.New(otelMiddleware.Config{
            TracerProvider: tp,
            MeterProvider:  mp,
            Propagator:     propagation.TraceContext{},
        }),
    },
})
```

```typescript
// TypeScript SDK — middleware-based integration
const worker = new Worker({
  middleware: [
    otelMiddleware({
      tracerProvider: tp,
      meterProvider: mp,
    }),
  ],
});
```

```python
# Python SDK — middleware-based integration
worker = Worker(
    middleware=[
        OtelMiddleware(
            tracer_provider=tp,
            meter_provider=mp,
        ),
    ],
)
```

The middleware MUST:
1. Extract trace context from `meta` on the consumer side
2. Inject trace context into `meta` on the producer side
3. Create spans with the naming conventions defined above
4. Record metrics for each operation
5. Propagate baggage to the handler context

## Examples

### Complete Enqueue + Process Trace

**Producer (Go):**

```json
{
  "type": "email.send",
  "queue": "email",
  "args": ["user@example.com", "Welcome!"],
  "meta": {
    "ojs.otel.traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
    "ojs.otel.tracestate": "ojs=t61rcWkgMzE",
    "ojs.otel.baggage": "tenant_id=acme-corp,environment=production"
  }
}
```

**Resulting Spans (Jaeger/Zipkin view):**

```
Trace: 4bf92f3577b34da6a3ce929d0e0e4736
│
├─ email.send publish  [12ms]
│   messaging.system: ojs
│   messaging.operation: publish
│   messaging.destination.name: email
│   messaging.message.id: 01912e4a-7b3c-7def-8a12-abcdef123456
│   ojs.job.type: email.send
│
├─ email.send receive  [2ms]
│   messaging.system: ojs
│   messaging.operation: receive
│   messaging.destination.name: email
│   messaging.message.id: 01912e4a-7b3c-7def-8a12-abcdef123456
│   ojs.job.type: email.send
│   ojs.job.attempt: 1
│
└─ email.send process  [145ms]
    messaging.system: ojs
    messaging.operation: process
    messaging.destination.name: email
    messaging.message.id: 01912e4a-7b3c-7def-8a12-abcdef123456
    ojs.job.type: email.send
    ojs.job.attempt: 1
    ojs.job.outcome: completed
    ojs.job.duration_ms: 143.2
```

### Workflow Trace

```
Trace: 8a3c5f1e2b4d6e7f9a0b1c2d3e4f5a6b
│
├─ order.fulfill publish  [8ms]
│   ojs.job.type: order.fulfill
│
├─ order.fulfill step[0]
│   ├─ payment.charge publish  [5ms]
│   └─ payment.charge process  [320ms]
│       ojs.job.outcome: completed
│
├─ order.fulfill group[1]
│   ├─ inventory.reserve publish  [4ms]
│   │   └─ inventory.reserve process  [85ms]
│   │       ojs.job.outcome: completed
│   └─ shipping.label publish  [3ms]
│       └─ shipping.label process  [210ms]
│           ojs.job.outcome: completed
│
└─ order.fulfill complete  [1ms]
```

## Conformance Impact

OpenTelemetry integration is an OPTIONAL extension. It does not affect conformance levels 0–4.

New requirements introduced:

- **MUST**: Backends MUST preserve `ojs.otel.*` meta attributes without modification. *Rationale: Modifying trace context would break trace continuity across service boundaries.*
- **MUST**: SDKs that implement OpenTelemetry support MUST use the span naming conventions defined in this RFC. *Rationale: Consistent naming enables cross-implementation dashboards and alerting.*
- **MUST**: SDKs that implement OpenTelemetry support MUST use W3C Trace Context format for propagation. *Rationale: W3C Trace Context is the only vendor-neutral propagation format with universal SDK support.*
- **SHOULD**: SDKs SHOULD provide OpenTelemetry integration via middleware. *Rationale: Middleware integration is opt-in and does not impose a dependency on users who do not need tracing.*
- **SHOULD**: Backends SHOULD emit backend-level spans for storage operations. *Rationale: Backend spans reveal queue internals that are invisible at the SDK level.*
- **MAY**: Implementations MAY export the standardized metrics defined in this RFC. *Rationale: Metrics are valuable but require an OpenTelemetry Metrics SDK dependency.*

## Backward Compatibility

This proposal is fully backward compatible. All telemetry attributes use the `ojs.otel.` prefix in the `meta` object. Existing implementations that do not support OpenTelemetry will pass these attributes through as opaque metadata. SDKs that add OpenTelemetry middleware will continue to work with backends that do not emit backend-level spans.

No changes to the core job envelope, lifecycle states, or existing API endpoints are required.

## Implementation Requirements

Per the OJS RFC process, proposals at Stage 2+ MUST include working prototypes in at least two languages:

- [ ] Go: OpenTelemetry middleware in `ojs-go-sdk/middleware/otel/`
- [ ] TypeScript: OpenTelemetry middleware in `ojs-js-sdk/src/middleware/otel/`

## Alternatives Considered

### Custom Trace Propagation Format

A custom propagation format specific to OJS was considered. This was rejected because:

- It would require every tracing vendor to add OJS-specific support
- W3C Trace Context is universally supported by all OpenTelemetry SDKs
- A custom format would create an adoption barrier for no practical benefit

### Embedding Trace Context in Job Args

Embedding trace context directly in the `args` array was considered. This was rejected because:

- It pollutes the application payload with infrastructure concerns
- It requires application code to be aware of trace context positioning
- The `meta` object exists precisely for this class of cross-cutting metadata

### Backend-Side Trace Context Injection

Having the backend inject trace context (creating a new trace for each job) was considered. This was rejected because:

- It breaks the producer-consumer trace link, which is the primary value of distributed tracing for job systems
- The backend cannot know the producer's trace context unless the SDK provides it
- Producer-side injection is how all existing messaging system instrumentations work

### Mandatory OpenTelemetry Dependency

Making OpenTelemetry a required dependency for all SDKs was considered. This was rejected because:

- It would increase bundle size for users who don't need tracing
- The OJS design philosophy favors zero required dependencies
- Middleware-based integration makes the dependency opt-in

## Open Questions

1. **Metric bucket boundaries**: What histogram bucket boundaries should be recommended for `ojs.job.duration` and `ojs.job.queue_time`? The OpenTelemetry default buckets may not be optimal for job processing latencies.

2. **Trace sampling**: Should the RFC recommend a default sampling strategy? For high-throughput job systems, head-based sampling at 1% may be insufficient for debugging, while 100% sampling creates storage pressure.

3. **Multi-backend correlation**: When a deployment uses multiple backends (e.g., Redis for fast jobs, Postgres for durable jobs), should there be a standard way to correlate metrics across backends?

4. **Log correlation**: Should the RFC define conventions for correlating structured logs with traces (e.g., injecting `trace_id` and `span_id` into log entries)?

5. **Span status mapping**: How should OJS job outcomes map to OpenTelemetry span status? Proposed: `completed` → `OK`, `failed`/`discarded` → `ERROR`, `cancelled` → `OK` (cancellation is expected behavior, not an error).
