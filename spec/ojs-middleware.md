# Open Job Spec -- Middleware Chain Specification

**OJS Middleware: Enqueue and Execution Chains**

| Field        | Value                                    |
|--------------|------------------------------------------|
| **Version**  | 1.0.0-rc.1                               |
| **Date**     | 2026-02-19                               |
| **Status**   | Release Candidate                        |
| **Maturity** | Beta                                     |
| **Layer**    | 1 (Core Specification)                   |
| **Requires** | OJS Core Specification (Layer 1)         |
| **License**  | Apache 2.0                               |

---

## 1. Introduction

This document defines the **middleware chain pattern** as a first-class concept in Open
Job Spec (OJS). Middleware chains provide a standardized mechanism for intercepting,
modifying, and augmenting job processing at two critical points: **enqueue time**
(client-side) and **execution time** (worker-side).

Conformant OJS implementations MUST support both middleware chains as defined in this
specification.

**Rationale**: Sidekiq's client/server middleware chains -- inspired by Rack middleware --
are arguably its most underrated contribution to the job processing ecosystem. Every major
system has adopted some variant: Taskiq provides an explicit pipeline with named hooks,
Asynq matches `net/http` middleware patterns, and Celery implements implicit middleware
through signals and task base classes. The middleware pattern is the single most effective
mechanism for separating cross-cutting concerns (logging, metrics, error handling, trace
context propagation) from job handler logic.

By elevating middleware to a MUST requirement, OJS ensures that every conformant
implementation provides a composable, ordered, language-idiomatic interception mechanism.
Without standardized middleware, each implementation invents its own hook system,
fragmenting the ecosystem and preventing portable middleware libraries.

### 1.1 Relationship to Other Specifications

This specification extends the OJS Core Specification (Layer 1). Middleware chains operate
on the job envelope as defined in the Core Specification and the JSON Wire Format Encoding
(Layer 2). Middleware executes within the context of protocol bindings (Layer 3) but is
not specific to any protocol.

Middleware chains interact with:

- **Job Envelope** (Core Specification): Middleware receives and may modify the job envelope.
- **Job Lifecycle** (Core Specification): Enqueue middleware runs during the transition from
  client submission to the `available` state. Execution middleware wraps the transition from
  `active` through handler invocation to `completed`, `retryable`, or `discarded`.
- **Retry Policy** (OJS Retry Specification): Execution middleware may implement retry-aware
  behavior such as conditional logic based on `attempt` count.
- **Worker Protocol** (OJS Worker Protocol Specification): Execution middleware integrates
  with the worker's job processing pipeline.

### 1.2 Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD",
"SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this
document are to be interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt)
and [RFC 8174](https://www.ietf.org/rfc/rfc8174.txt).

### 1.3 Terminology

| Term                     | Definition                                                                   |
|--------------------------|------------------------------------------------------------------------------|
| **Middleware**           | A composable unit of logic that intercepts a job at a defined point in its lifecycle. |
| **Middleware Chain**     | An ordered sequence of middleware that processes a job in series.             |
| **Enqueue Middleware**   | Middleware that runs on the client side before a job is inserted into a queue. |
| **Execution Middleware** | Middleware that runs on the worker side, wrapping the invocation of a job handler. |
| **Chain Management**     | The API for adding, removing, and reordering middleware within a chain.       |
| **Yield / Next**         | The mechanism by which a middleware delegates to the next middleware in the chain or to the final operation (enqueue or handler execution). |

---

## 2. Overview and Rationale

### 2.1 Why Middleware is a MUST Requirement

Middleware chains MUST be supported by all conformant OJS implementations.

**Rationale**: Cross-cutting concerns -- logging, metrics, error reporting, distributed
trace propagation, locale injection, validation, rate limiting, timeout enforcement --
arise in every production job processing system. Without a standardized middleware
mechanism, these concerns are addressed through ad-hoc patterns:

1. **Inheritance hierarchies** (Celery's base task classes): Fragile, language-specific,
   and incompatible across implementations.
2. **Event listeners** (BullMQ's event emitters): Can observe but cannot intercept or
   modify job processing.
3. **Decorator patterns** (Taskiq's pre/post hooks): Effective but non-standard, making
   middleware non-portable across implementations.
4. **Monkey-patching** (common in Ruby/Python ecosystems): Brittle, order-dependent,
   and invisible to tooling.

Sidekiq's middleware chains solved this definitively over a decade ago. The pattern is
proven, well-understood, and universally applicable. Making middleware a MUST requirement
ensures that:

- Cross-cutting concerns are cleanly separated from handler logic.
- Middleware is composable and reorderable without modifying handler code.
- The community can build portable middleware libraries that work across OJS implementations.
- Observability is consistent: every implementation provides the same interception points.

### 2.2 Two Chains, Two Purposes

OJS defines exactly two middleware chains:

| Chain                  | Execution Context | Purpose                                           |
|------------------------|-------------------|---------------------------------------------------|
| **Enqueue Middleware** | Client-side       | Intercept and transform jobs before queue insertion |
| **Execution Middleware** | Worker-side     | Wrap job handler invocation with cross-cutting concerns |

**Rationale**: Sidekiq's two-chain model (client middleware + server middleware) has been
validated by over a decade of production use. The separation is necessary because:

- **Enqueue and execution happen in different processes**, often in different languages.
  A Ruby web application may enqueue jobs that a Go worker processes. Each side needs its
  own interception point.
- **The concerns differ**: Enqueue middleware deals with job creation (validation,
  deduplication checks, metadata injection). Execution middleware deals with job processing
  (timing, error handling, transaction management).
- **The invocation model differs**: Enqueue middleware is linear (pass-through or reject).
  Execution middleware is nested (wrap-around, like Rack/Ring/Express middleware).

---

## 3. Enqueue Middleware Specification

### 3.1 Definition

Enqueue middleware runs on the **client side**, before a job envelope is submitted to the
backend for insertion into a queue. Each middleware in the enqueue chain receives the job
envelope and can pass it through (possibly modified), prevent it from being enqueued, or
abort the operation with an error.

### 3.2 Invocation Order

Enqueue middleware MUST execute in **insertion order** -- the order in which middleware
was added to the chain.

```
Client calls enqueue(job)
  |
  v
middleware_1.call(job, next)
  |
  v
middleware_2.call(job, next)
  |
  v
middleware_3.call(job, next)
  |
  v
Actual enqueue operation (job inserted into queue)
```

**Rationale**: Linear, predictable ordering is essential for middleware that has
dependencies. For example, a validation middleware MUST run before a deduplication
middleware (there is no point checking for duplicates if the job is invalid). Insertion
order provides the simplest mental model and matches Sidekiq's proven approach.

### 3.3 Abstract Interface

The enqueue middleware interface is defined abstractly below. Implementations MUST provide
a language-idiomatic equivalent.

```
EnqueueMiddleware {
  call(job: Job, next: Function) -> Job | null
}
```

**Contract**:

- **Return a `Job` object**: The job (possibly modified) is passed to the next middleware
  in the chain. When the last middleware returns a job, the actual enqueue operation
  executes.
- **Return `null` (or the language-equivalent of "no value")**: The job is silently
  dropped. The enqueue operation does not execute. The client receives an indication that
  the job was not enqueued.
- **Throw an exception / return an error**: The enqueue operation is aborted. The error
  propagates to the caller. No subsequent middleware in the chain executes.

**Rationale**: The three outcomes (pass, drop, error) cover all real-world enqueue
interception needs. Sidekiq's `yield`-based model achieves the same semantics. The explicit
`null` return for silent rejection (as opposed to throwing) supports use cases like
deduplication where dropping a duplicate is not an error condition.

### 3.4 Job Envelope Visibility

Enqueue middleware MUST receive the complete job envelope as defined in the OJS Core
Specification, including all REQUIRED fields (`specversion`, `id`, `type`, `queue`, `args`)
and any OPTIONAL fields (`meta`, `priority`, `timeout`, `scheduled_at`, `expires_at`,
`retry`, `unique`, `visibility_timeout`) that were set by the client.

**Rationale**: Middleware MUST have full visibility into the job to make informed decisions.
A rate-limiting middleware needs to see the `type` and `queue`. A validation middleware
needs to inspect `args`. A metadata-injection middleware needs to modify `meta`.

### 3.5 Job Envelope Modification

Enqueue middleware MAY modify any field of the job envelope before passing it to the next
middleware in the chain.

Implementations MUST ensure that modifications made by one middleware are visible to all
subsequent middleware in the chain and to the final enqueue operation.

Enqueue middleware MUST NOT modify the `id` field of a job envelope.

**Rationale**: The `id` is the stable identifier used for deduplication, correlation, and
status tracking. Allowing middleware to change it would break these guarantees. All other
fields are safe to modify: middleware that sets `meta.trace_id`, adjusts `priority`, or
rewrites `queue` are common, legitimate use cases.

### 3.6 Use Cases

The following table lists common enqueue middleware use cases. These are illustrative, not
exhaustive.

| Middleware              | Purpose                                                    | Modifies Job? |
|-------------------------|------------------------------------------------------------|---------------|
| **Logging**             | Log job enqueue events with type, queue, and ID            | No            |
| **TraceContext**        | Inject distributed trace ID into `meta`                    | Yes (`meta`)  |
| **Locale**              | Propagate current locale/timezone into `meta`              | Yes (`meta`)  |
| **Validation**          | Validate `args` against a schema; reject invalid jobs      | No            |
| **RateLimiting**        | Check rate limits; drop or reject jobs that exceed limits  | No            |
| **Deduplication**       | Check for existing duplicate jobs; drop duplicates         | No            |
| **DefaultMetadata**     | Set default `meta` values (e.g., `enqueued_by`, `source`) | Yes (`meta`)  |
| **QueueRouting**        | Override `queue` based on job type or priority             | Yes (`queue`) |
| **Encryption**          | Encrypt sensitive `args` before storage                    | Yes (`args`)  |

### 3.7 Example: Enqueue Middleware Chain

The following pseudocode demonstrates a three-middleware enqueue chain:

```
// Middleware 1: Inject trace context
TraceContextMiddleware.call(job, next):
  job.meta["trace_id"] = current_trace_id()
  job.meta["span_id"] = current_span_id()
  return next(job)

// Middleware 2: Validate arguments
ValidationMiddleware.call(job, next):
  schema = lookup_schema(job.type)
  if schema is not null:
    errors = validate(job.args, schema)
    if errors is not empty:
      throw ValidationError("Invalid args for #{job.type}: #{errors}")
  return next(job)

// Middleware 3: Log enqueue events
LoggingMiddleware.call(job, next):
  log.info("Enqueueing job", type=job.type, id=job.id, queue=job.queue)
  result = next(job)
  if result is not null:
    log.info("Enqueued job", type=job.type, id=job.id)
  else:
    log.info("Job dropped by downstream middleware", type=job.type, id=job.id)
  return result

// Chain execution for enqueue("email.send", ["user@example.com", "welcome"]):
//
// 1. TraceContextMiddleware adds trace_id and span_id to meta
// 2. ValidationMiddleware checks args against email.send schema
// 3. LoggingMiddleware logs the enqueue event
// 4. Actual enqueue operation inserts job into queue
```

---

## 4. Execution Middleware Specification

### 4.1 Definition

Execution middleware runs on the **worker side**, wrapping the invocation of a job handler.
Each middleware in the execution chain wraps the next, forming a nested call stack. This
is the same pattern used by Rack (Ruby), Ring (Clojure), Express (Node.js), and `net/http`
(Go) middleware.

### 4.2 Invocation Order

Execution middleware MUST execute as **nested wrappers** -- the first middleware added is
the outermost wrapper, and the last middleware added is the innermost wrapper closest to
the handler.

```
Worker receives job "email.send"
  |
  v
middleware_1.call(job, ctx, next)        <-- outermost
  |
  v
  middleware_2.call(job, ctx, next)
    |
    v
    middleware_3.call(job, ctx, next)     <-- innermost
      |
      v
      Handler.execute(job, ctx)          <-- actual job handler
      |
      v
    middleware_3 resumes after next()
    |
    v
  middleware_2 resumes after next()
  |
  v
middleware_1 resumes after next()        <-- outermost resumes last
```

**Rationale**: The nested wrapper model (also called "onion model") is the proven pattern
for execution middleware. It enables each middleware to:

1. Execute logic **before** the handler runs (setup).
2. Execute logic **after** the handler runs (teardown).
3. **Wrap** the handler invocation in a try/catch or timing block.
4. **Short-circuit** execution by not calling `next()`.

Sidekiq's `yield`-based server middleware, Asynq's `net/http`-style middleware, and
Rack's `call(env)` pattern all implement this model. Linear pre/post hooks (as in
Taskiq's `pre_execute`/`post_execute`) are strictly less powerful because they cannot
wrap the handler invocation.

### 4.3 Abstract Interface

The execution middleware interface is defined abstractly below. Implementations MUST
provide a language-idiomatic equivalent.

```
ExecutionMiddleware {
  call(job: Job, context: JobContext, next: Function) -> Result
}
```

**Contract**:

- **Call `next()`**: Invokes the next middleware in the chain, or the job handler if this
  is the innermost middleware. The middleware MUST call `next()` exactly once to continue
  the chain. Calling `next()` zero times short-circuits execution (the handler never runs).
  Calling `next()` more than once results in undefined behavior and implementations
  SHOULD guard against it.
- **Return a `Result`**: The result of the handler execution (or of the middleware's own
  logic if it short-circuits). The result propagates back through the middleware chain.
- **Throw an exception / return an error**: The error propagates outward through the
  middleware chain. Each outer middleware has the opportunity to catch and handle the error.

**Rationale**: The `next()` function is the key abstraction. It gives each middleware
complete control over whether and how the handler executes. A timeout middleware calls
`next()` with a deadline. A metrics middleware measures the duration around `next()`. An
error-handling middleware wraps `next()` in a try/catch. This is strictly more powerful
than pre/post hooks because the middleware maintains its stack frame across the handler's
execution.

### 4.4 JobContext

Execution middleware receives a `JobContext` in addition to the job envelope. The
`JobContext` provides execution-scoped state and capabilities.

Implementations MUST provide a `JobContext` that includes at minimum:

| Field / Method  | Type     | Description                                              |
|-----------------|----------|----------------------------------------------------------|
| `job`           | Job      | The full job envelope                                    |
| `attempt`       | integer  | Current attempt number (1-indexed)                       |
| `queue`         | string   | The queue from which the job was fetched                  |

Implementations SHOULD provide additional context capabilities:

| Field / Method    | Type     | Description                                            |
|-------------------|----------|--------------------------------------------------------|
| `log(level, msg)` | function | Structured logging bound to the current job            |
| `heartbeat()`     | function | Extend the job's visibility timeout                    |
| `set_result(val)` | function | Set the job's return value                             |
| `metadata`        | object   | Mutable key-value store scoped to this execution       |

**Rationale**: Middleware frequently needs access to execution context beyond the job
envelope itself. The `attempt` number enables conditional logic (e.g., more verbose
logging on retries). The `metadata` store enables middleware-to-middleware communication
within a single execution (e.g., a trace middleware sets a span ID that a logging
middleware reads).

### 4.5 Use Cases

The following table lists common execution middleware use cases:

| Middleware              | Purpose                                                        | Wraps next()? |
|-------------------------|----------------------------------------------------------------|---------------|
| **Logging**             | Log job start/complete/fail events with duration               | Yes           |
| **Metrics**             | Record execution duration, success/failure counters            | Yes           |
| **Timeout**             | Enforce `job.timeout` by wrapping `next()` with a deadline     | Yes           |
| **ErrorReporting**      | Capture exceptions from `next()` and report to error service   | Yes           |
| **TraceContext**        | Restore distributed trace context from `job.meta` before `next()` | Yes        |
| **TransactionManagement** | Wrap `next()` in a database transaction                     | Yes           |
| **ContextPropagation**  | Set locale, timezone, user context from `job.meta`             | Yes           |
| **CircuitBreaker**      | Skip `next()` if the downstream service is unhealthy           | Conditional   |
| **Retry Logging**       | Log additional context on retry attempts (`attempt > 1`)       | Yes           |
| **Concurrency Limiting**| Acquire a semaphore before `next()`, release after             | Yes           |

### 4.6 Example: Execution Middleware Chain

The following pseudocode demonstrates the nested execution model:

```
// Request comes in for job "email.send"

LoggingMiddleware.call(job, ctx, next):
  log.info("Starting job", type=job.type, id=job.id, attempt=ctx.attempt)
  start_time = now()
  try:
    result = next()
    log.info("Completed job", type=job.type, id=job.id,
             duration_ms=elapsed(start_time))
    return result
  catch error:
    log.error("Failed job", type=job.type, id=job.id,
              duration_ms=elapsed(start_time), error=error.message)
    throw error

MetricsMiddleware.call(job, ctx, next):
  start_time = now()
  try:
    result = next()
    metrics.increment("ojs.jobs.completed", tags={type: job.type, queue: job.queue})
    metrics.histogram("ojs.jobs.duration_ms", elapsed(start_time),
                      tags={type: job.type, queue: job.queue})
    return result
  catch error:
    metrics.increment("ojs.jobs.failed", tags={type: job.type, queue: job.queue})
    throw error

TimeoutMiddleware.call(job, ctx, next):
  timeout_seconds = job.timeout or DEFAULT_TIMEOUT
  try:
    result = with_timeout(timeout_seconds, next)
    return result
  catch TimeoutError:
    throw JobTimeoutError("Job #{job.id} exceeded #{timeout_seconds}s timeout")

// Complete execution flow:
//
// LoggingMiddleware.call(job, ctx, next)
//   -> log "Starting job email.send"
//   -> MetricsMiddleware.call(job, ctx, next)
//     -> start timer
//     -> TimeoutMiddleware.call(job, ctx, next)
//       -> set timeout to 30s
//       -> Handler.execute(job, ctx)    <-- actual job handler
//       -> timeout not exceeded
//     -> stop timer, record duration = 245ms
//     -> increment ojs.jobs.completed
//   -> log "Completed job email.send in 245ms"
```

---

## 5. Chain Management Operations

### 5.1 Required Operations

Implementations MUST provide the following chain management operations for both enqueue
and execution middleware chains:

| Operation                             | Description                                         |
|---------------------------------------|-----------------------------------------------------|
| `add(middleware)`                      | Append `middleware` to the end of the chain          |
| `prepend(middleware)`                  | Insert `middleware` at the beginning of the chain    |
| `insert_before(existing, middleware)`  | Insert `middleware` immediately before `existing`    |
| `insert_after(existing, middleware)`   | Insert `middleware` immediately after `existing`     |
| `remove(middleware)`                   | Remove `middleware` from the chain                   |

**Rationale**: The five operations cover all real-world chain manipulation needs:

- `add` is the default -- most middleware is simply appended.
- `prepend` enables middleware that must run first (e.g., a security check before any other middleware).
- `insert_before` and `insert_after` enable precise positioning relative to existing middleware, which is essential when middleware has ordering dependencies (e.g., metrics must wrap timeout, so metrics is inserted before timeout).
- `remove` enables testing (remove production middleware in test suites), conditional configuration (remove verbose logging in production), and middleware replacement.

Sidekiq provides exactly these five operations for its middleware chains. They have proven
sufficient for over a decade of production use across thousands of organizations.

### 5.2 Middleware Identity

Implementations MUST provide a mechanism to identify middleware for the purposes of
`insert_before`, `insert_after`, and `remove` operations.

Implementations MAY use any of the following identification mechanisms:

- **Class / type identity**: The middleware class or type serves as the identifier
  (Sidekiq's approach).
- **String name**: Each middleware has a unique string name.
- **Instance identity**: The specific middleware instance serves as the identifier.

The identification mechanism MUST be documented by the implementation.

**Rationale**: The choice of identification mechanism is language-dependent. In Ruby,
class identity is idiomatic (Sidekiq uses `Sidekiq.configure_server { |config|
config.server_middleware { |chain| chain.remove MyMiddleware } }`). In Go, a string
identifier is more natural. In JavaScript, either class identity or string names work.
Mandating a specific mechanism would conflict with language idioms.

### 5.3 Chain Immutability During Execution

Implementations MUST NOT allow modification of a middleware chain while jobs are being
processed through that chain.

Implementations SHOULD require that middleware chains are configured during application
startup and frozen before job processing begins.

**Rationale**: Modifying a middleware chain while jobs are in flight would create race
conditions and unpredictable behavior. A job that begins processing with chain
`[A, B, C]` must complete processing with the same chain. Sidekiq freezes middleware
chains on server start.

### 5.4 Chain Inspection

Implementations SHOULD provide a mechanism to inspect the current contents and ordering
of a middleware chain.

**Rationale**: Chain inspection enables debugging ("why is my middleware not running?"),
testing ("verify the chain contains the expected middleware"), and operational visibility.

---

## 6. Ordering and Composition Semantics

### 6.1 Ordering Guarantees

Implementations MUST guarantee the following ordering properties:

1. **Deterministic ordering**: Given the same sequence of chain management operations,
   the resulting middleware order MUST be identical across invocations.

2. **Insertion-order preservation**: Middleware added via `add()` MUST execute in the
   order they were added. Middleware added via `prepend()` MUST execute before all
   previously added middleware.

3. **Relative ordering preservation**: `insert_before(X, Y)` MUST guarantee that `Y`
   executes immediately before `X`. `insert_after(X, Y)` MUST guarantee that `Y` executes
   immediately after `X`.

**Rationale**: Ordering is the most important property of middleware chains. Middleware
frequently has implicit dependencies:

- Trace context injection MUST run before logging (so logs include the trace ID).
- Timeout enforcement MUST wrap the handler (so it can interrupt execution).
- Metrics MUST wrap timeout (so timeout duration is included in metrics).
- Error reporting SHOULD be outermost (so it captures errors from all inner middleware).

Deterministic, predictable ordering is the only way to reason about these dependencies.

### 6.2 Composition

Middleware chains MUST be composable. Given middleware `A`, `B`, and `C` added to a chain
in that order:

- For **enqueue middleware**, composition is linear:
  ```
  A(B(C(enqueue)))
  ```
  Where each middleware calls `next()` to invoke the next.

- For **execution middleware**, composition is nested:
  ```
  A(B(C(handler)))
  ```
  Where each middleware calls `next()` to invoke the next, forming an onion-like structure.

The outermost middleware (first in the chain) has the first opportunity to process the job
and the last opportunity to process the result.

### 6.3 Empty Chains

Implementations MUST support empty middleware chains. When no middleware is configured:

- **Enqueue**: The job is inserted directly into the queue without interception.
- **Execution**: The job handler is invoked directly without wrapping.

**Rationale**: Empty chains are the default for new applications and for testing scenarios
where middleware is intentionally removed. The system must function correctly without any
middleware.

### 6.4 Duplicate Middleware

Implementations SHOULD allow the same middleware class or type to appear multiple times
in a chain.

**Rationale**: While unusual, there are legitimate use cases for duplicate middleware.
For example, two instances of a logging middleware configured with different log levels
or output destinations.

---

## 7. Error Handling in Middleware Chains

### 7.1 Enqueue Middleware Error Handling

When an enqueue middleware throws an error or returns an error:

1. The enqueue operation MUST be aborted.
2. No subsequent middleware in the chain MUST execute.
3. The error MUST propagate to the caller of the enqueue operation.
4. No job MUST be inserted into any queue.

**Rationale**: An error during enqueue interception indicates that the job should not be
processed. Common scenarios include validation failure (invalid arguments), authorization
failure (caller not permitted to enqueue this job type), or backend failure (rate limit
exceeded). In all cases, the safe behavior is to abort and report the error.

### 7.2 Enqueue Middleware Null/Drop Handling

When an enqueue middleware returns `null` (or the language-equivalent):

1. The enqueue operation MUST be silently cancelled.
2. No subsequent middleware in the chain MUST execute.
3. The caller MUST receive an indication that the job was not enqueued (not an error).
4. No job MUST be inserted into any queue.

**Rationale**: Silent dropping serves deduplication ("this job already exists") and
conditional enqueueing ("this job type is disabled") use cases. These are not errors --
they are intentional decisions. The caller must be able to distinguish between "job was
enqueued", "job was dropped", and "enqueue failed with an error".

### 7.3 Execution Middleware Error Handling

When an error occurs within the execution middleware chain:

1. The error MUST propagate outward through each wrapping middleware, giving each
   middleware the opportunity to handle it.
2. If no middleware handles the error, it MUST propagate to the worker, which applies
   the job's retry policy.
3. Middleware MAY catch, transform, suppress, or re-throw errors.

```
// Example: Error propagation through execution middleware

OuterMiddleware.call(job, ctx, next):
  try:
    return next()
  catch error:
    // Middleware can handle the error
    error_reporter.capture(error, job=job)
    // And re-throw to continue propagation
    throw error

InnerMiddleware.call(job, ctx, next):
  return next()  // Does not catch -- error passes through

Handler.execute(job, ctx):
  throw ConnectionError("SMTP server unreachable")

// Flow:
// 1. Handler throws ConnectionError
// 2. InnerMiddleware does not catch -- error propagates
// 3. OuterMiddleware catches, reports to error service, re-throws
// 4. Worker receives ConnectionError, applies retry policy
```

**Rationale**: The nested model means that outer middleware naturally wraps error handling
around inner middleware and the handler. This is the same try/catch propagation model used
in every programming language's exception system. It gives each middleware layer the
opportunity to observe, transform, or recover from errors without requiring a separate
error-handling mechanism.

### 7.4 Middleware Internal Errors

If a middleware itself throws an error (as opposed to an error propagated from `next()`):

- For **enqueue middleware**: The error MUST abort the enqueue operation and propagate to
  the caller. The behavior is identical to handler errors per Section 7.1.
- For **execution middleware**: The error MUST propagate outward through the chain, giving
  outer middleware the opportunity to handle it. If unhandled, the worker applies the
  job's retry policy.

Implementations SHOULD distinguish between middleware errors and handler errors in error
reporting, to aid debugging.

**Rationale**: Middleware code can fail (e.g., a metrics middleware fails to connect to
the metrics backend). These failures must not silently break job processing. Propagating
them through the normal error channel ensures they are visible and actionable.

### 7.5 Middleware MUST NOT Swallow Errors Silently

Execution middleware MUST NOT catch errors from `next()` without either re-throwing them
or explicitly recording them as handled.

**Rationale**: Silently swallowed errors are the most common middleware bug. A middleware
that catches an error and does not re-throw it causes the worker to believe the job
succeeded, preventing retry logic from activating. While the spec cannot enforce this at
the language level, implementations SHOULD document this requirement prominently and MAY
provide static analysis or runtime warnings for middleware that catches without re-throwing.

---

## 8. Built-in Middleware Recommendations

### 8.1 Recommended Built-in Middleware

Implementations SHOULD provide the following middleware out of the box. These address the
most common cross-cutting concerns and serve as reference implementations for middleware
authors.

#### 8.1.1 Logging Middleware

**Chain**: Both enqueue and execution.

**Behavior**:

- **Enqueue**: Log job ID, type, and queue when a job is enqueued.
- **Execution**: Log job start, completion, and failure events with duration.

**Recommended log fields**:

| Field         | Description                         |
|---------------|-------------------------------------|
| `job_id`      | The job's unique identifier         |
| `job_type`    | The job's type (e.g., `email.send`) |
| `queue`       | The target queue                    |
| `attempt`     | Current attempt number              |
| `duration_ms` | Execution duration in milliseconds  |
| `status`      | `completed`, `failed`, or `timeout` |
| `error`       | Error message (on failure)          |

**Rationale**: Structured logging with consistent fields enables log aggregation, search,
and alerting across all job types. Every production system needs this.

#### 8.1.2 Metrics Middleware

**Chain**: Execution.

**Behavior**: Record job execution metrics using the standard OJS metric names.

**Recommended metrics**:

| Metric                   | Type      | Description                            |
|--------------------------|-----------|----------------------------------------|
| `ojs.jobs.duration_ms`   | histogram | Execution time per job type and queue  |
| `ojs.jobs.completed`     | counter   | Total completed jobs                   |
| `ojs.jobs.failed`        | counter   | Total failed jobs                      |
| `ojs.jobs.timeout`       | counter   | Total timed-out jobs                   |

**Rationale**: Standard metric names and types enable portable dashboards and alerting
rules. Implementations SHOULD emit metrics in an OpenTelemetry-compatible format.

#### 8.1.3 Timeout Middleware

**Chain**: Execution.

**Behavior**: Enforce the job's `timeout` field by wrapping `next()` with a deadline. If
the handler does not complete within the timeout, the middleware MUST abort execution and
raise a timeout error.

**Rationale**: Timeout enforcement prevents runaway jobs from consuming worker resources
indefinitely. Implementing timeout as middleware (rather than hardcoding it in the worker)
allows applications to customize or replace the timeout mechanism.

#### 8.1.4 Error Reporting Middleware

**Chain**: Execution.

**Behavior**: Capture exceptions from `next()`, format them as structured error objects
per the OJS error format, and report them to an error tracking service (e.g., Sentry,
Bugsnag, Honeybadger). MUST re-throw the error after reporting.

**Rationale**: Error reporting is a universal production requirement. Providing it as
built-in middleware with the correct error format ensures consistent error capture across
all job types.

#### 8.1.5 Trace Context Middleware

**Chain**: Both enqueue and execution.

**Behavior**:

- **Enqueue**: Extract the current distributed trace context (e.g., W3C Trace Context)
  and inject it into `job.meta` (e.g., `meta.traceparent`, `meta.tracestate`).
- **Execution**: Extract the trace context from `job.meta` and restore it as the current
  context before calling `next()`, ensuring the job's execution is linked to the
  originating trace.

**Rationale**: Distributed tracing across job boundaries is essential for debugging
asynchronous workflows. W3C Trace Context
([Trace Context](https://www.w3.org/TR/trace-context/)) is the standard propagation
format supported by OpenTelemetry, Jaeger, Zipkin, and Datadog.

### 8.2 Default Middleware Chain

Implementations SHOULD provide a sensible default middleware chain that can be used
without configuration. The recommended default execution middleware chain is:

```
1. Logging Middleware          (outermost -- logs start/complete/fail)
2. Metrics Middleware          (records duration, success/failure)
3. Error Reporting Middleware  (captures and reports errors)
4. Timeout Middleware          (enforces job timeout, innermost)
```

The recommended default enqueue middleware chain is:

```
1. Logging Middleware          (logs enqueue events)
```

Applications SHOULD be able to override the default chain entirely or modify it using the
chain management operations defined in Section 5.

---

## 9. Middleware and Batch Operations

### 9.1 Batch Enqueue

When a batch of jobs is enqueued (see OJS JSON Wire Format, Section 10), enqueue
middleware MUST execute independently for each job in the batch.

**Rationale**: Each job in a batch may have different types, arguments, and metadata.
Middleware MUST evaluate each job individually. A validation middleware might approve 9
out of 10 jobs in a batch.

### 9.2 Batch Middleware Failures

When enqueue middleware rejects one job in a batch (returns `null` or throws an error),
implementations MUST document their behavior:

- **Option A (RECOMMENDED)**: Reject only the failing job; continue processing the rest
  of the batch. Return per-job success/failure status.
- **Option B**: Reject the entire batch. This is acceptable when atomic batch semantics
  are required.

**Rationale**: Per-job middleware evaluation in batches is the expected behavior for most
use cases. However, some applications require all-or-nothing batch semantics (e.g.,
financial transactions). Implementations MUST document which behavior they provide.

---

## 10. Complete Examples

### 10.1 Enqueue Middleware Chain: Trace Injection and Deduplication

This example demonstrates a complete enqueue middleware chain with three middleware:
trace context injection, locale propagation, and deduplication checking.

```
// Configuration (application startup):
enqueue_chain.add(TraceContextMiddleware)
enqueue_chain.add(LocaleMiddleware)
enqueue_chain.add(DeduplicationMiddleware)

// TraceContextMiddleware
call(job, next):
  job.meta["traceparent"] = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
  job.meta["tracestate"] = "rojo=00f067aa0ba902b7"
  return next(job)

// LocaleMiddleware
call(job, next):
  job.meta["locale"] = current_locale()    // e.g., "en-US"
  job.meta["timezone"] = current_timezone() // e.g., "America/New_York"
  return next(job)

// DeduplicationMiddleware
call(job, next):
  if job.unique is not null:
    existing = find_duplicate(job)
    if existing is not null:
      log.info("Duplicate job detected", existing_id=existing.id, new_id=job.id)
      return null  // Drop the duplicate silently
  return next(job)

// Execution flow for:
//   client.enqueue("email.send", ["user@example.com", "welcome"])
//
// Input job:
// {
//   "specversion": "1.0",
//   "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
//   "type": "email.send",
//   "queue": "default",
//   "args": ["user@example.com", "welcome"]
// }
//
// After TraceContextMiddleware:
//   meta.traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
//   meta.tracestate = "rojo=00f067aa0ba902b7"
//
// After LocaleMiddleware:
//   meta.locale = "en-US"
//   meta.timezone = "America/New_York"
//
// DeduplicationMiddleware: no unique policy set, passes through
//
// Job enqueued successfully with enriched metadata
```

### 10.2 Execution Middleware Chain: Full Production Stack

This example demonstrates a complete production execution middleware chain.

```
// Configuration (application startup):
execution_chain.add(ErrorReportingMiddleware)
execution_chain.add(LoggingMiddleware)
execution_chain.add(MetricsMiddleware)
execution_chain.add(TraceContextMiddleware)
execution_chain.add(TimeoutMiddleware)

// ErrorReportingMiddleware (outermost -- catches all errors)
call(job, ctx, next):
  try:
    return next()
  catch error:
    error_reporter.capture(error, {
      job_id: job.id,
      job_type: job.type,
      queue: job.queue,
      attempt: ctx.attempt,
      args: job.args
    })
    throw error  // MUST re-throw

// LoggingMiddleware
call(job, ctx, next):
  log.info("Starting job",
           job_id=job.id, type=job.type, queue=job.queue, attempt=ctx.attempt)
  start_time = now()
  try:
    result = next()
    log.info("Completed job",
             job_id=job.id, type=job.type, duration_ms=elapsed(start_time))
    return result
  catch error:
    log.error("Failed job",
              job_id=job.id, type=job.type, duration_ms=elapsed(start_time),
              error=error.message)
    throw error

// MetricsMiddleware
call(job, ctx, next):
  start_time = now()
  try:
    result = next()
    metrics.increment("ojs.jobs.completed",
                      tags={type: job.type, queue: job.queue})
    metrics.histogram("ojs.jobs.duration_ms", elapsed(start_time),
                      tags={type: job.type, queue: job.queue})
    return result
  catch error:
    metrics.increment("ojs.jobs.failed",
                      tags={type: job.type, queue: job.queue})
    throw error

// TraceContextMiddleware
call(job, ctx, next):
  traceparent = job.meta["traceparent"]
  if traceparent is not null:
    span = tracer.start_span("ojs.job.execute",
                              parent=parse_traceparent(traceparent),
                              attributes={
                                "ojs.job.id": job.id,
                                "ojs.job.type": job.type,
                                "ojs.job.queue": job.queue,
                                "ojs.job.attempt": ctx.attempt
                              })
    try:
      result = with_span(span, next)
      span.set_status(OK)
      return result
    catch error:
      span.set_status(ERROR, error.message)
      span.record_exception(error)
      throw error
    finally:
      span.end()
  else:
    return next()

// TimeoutMiddleware (innermost -- directly wraps handler)
call(job, ctx, next):
  timeout_seconds = job.timeout
  if timeout_seconds is null:
    return next()
  result = with_timeout(timeout_seconds):
    return next()
  return result
  // Throws JobTimeoutError if timeout exceeded

// Complete flow for job:
// {
//   "specversion": "1.0",
//   "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
//   "type": "email.send",
//   "queue": "email",
//   "args": ["user@example.com", "welcome"],
//   "meta": {
//     "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
//     "locale": "en-US"
//   },
//   "timeout": 30
// }
//
// ErrorReportingMiddleware.call(job, ctx, next)
//   -> LoggingMiddleware.call(job, ctx, next)
//     -> log "Starting job email.send"
//     -> MetricsMiddleware.call(job, ctx, next)
//       -> start timer
//       -> TraceContextMiddleware.call(job, ctx, next)
//         -> start span "ojs.job.execute" linked to parent trace
//         -> TimeoutMiddleware.call(job, ctx, next)
//           -> set 30s timeout
//           -> Handler.execute(job, ctx)   <-- send the email
//           -> handler returns {message_id: "msg_abc123"}
//           -> timeout not exceeded
//         -> span.set_status(OK)
//         -> span.end()
//       -> stop timer, record duration = 245ms
//       -> increment ojs.jobs.completed
//     -> log "Completed job email.send in 245ms"
//   -> (no error to report)
// -> return {message_id: "msg_abc123"}
```

### 10.3 Execution Middleware: Error Handling Flow

This example demonstrates how errors propagate through the middleware chain.

```
// Same chain as 10.2. Handler throws an error:

// Handler.execute(job, ctx):
//   throw ConnectionError("SMTP connection refused")

// Flow:
//
// ErrorReportingMiddleware.call(job, ctx, next)
//   -> LoggingMiddleware.call(job, ctx, next)
//     -> log "Starting job email.send"
//     -> MetricsMiddleware.call(job, ctx, next)
//       -> start timer
//       -> TraceContextMiddleware.call(job, ctx, next)
//         -> start span
//         -> TimeoutMiddleware.call(job, ctx, next)
//           -> set 30s timeout
//           -> Handler.execute(job, ctx)
//           -> THROWS ConnectionError("SMTP connection refused")
//         -> (TimeoutMiddleware does not catch -- error propagates)
//         -> span.set_status(ERROR, "SMTP connection refused")
//         -> span.record_exception(ConnectionError)
//         -> span.end()
//         -> THROWS ConnectionError
//       -> stop timer, record duration = 12ms
//       -> increment ojs.jobs.failed
//       -> THROWS ConnectionError
//     -> log "Failed job email.send in 12ms: SMTP connection refused"
//     -> THROWS ConnectionError
//   -> error_reporter.capture(ConnectionError, {job_id: ..., attempt: 1})
//   -> THROWS ConnectionError
//
// Worker receives ConnectionError
// Worker applies retry policy: job transitions to "retryable"
// Job will be retried after backoff interval
```

### 10.4 Chain Management Example

This example demonstrates dynamic chain management operations.

```
// Start with default chain:
execution_chain.add(LoggingMiddleware)
execution_chain.add(TimeoutMiddleware)

// Chain: [LoggingMiddleware, TimeoutMiddleware]

// Add metrics before timeout (metrics should measure total time including timeout):
execution_chain.insert_before(TimeoutMiddleware, MetricsMiddleware)

// Chain: [LoggingMiddleware, MetricsMiddleware, TimeoutMiddleware]

// Add error reporting as the outermost middleware:
execution_chain.prepend(ErrorReportingMiddleware)

// Chain: [ErrorReportingMiddleware, LoggingMiddleware, MetricsMiddleware, TimeoutMiddleware]

// Add trace context after error reporting:
execution_chain.insert_after(ErrorReportingMiddleware, TraceContextMiddleware)

// Chain: [ErrorReportingMiddleware, TraceContextMiddleware, LoggingMiddleware,
//         MetricsMiddleware, TimeoutMiddleware]

// In test environment, remove error reporting:
if environment == "test":
  execution_chain.remove(ErrorReportingMiddleware)
  execution_chain.remove(MetricsMiddleware)

// Test chain: [TraceContextMiddleware, LoggingMiddleware, TimeoutMiddleware]
```

---

## 11. Implementation Guidance

### 11.1 Language-Specific Patterns

The abstract middleware interfaces defined in this specification MUST be adapted to
language-idiomatic patterns. The following table provides guidance:

| Language       | Enqueue Middleware Pattern              | Execution Middleware Pattern               |
|----------------|-----------------------------------------|--------------------------------------------|
| **Ruby**       | Class with `call(job, &block)` using `yield` | Class with `call(job, ctx, &block)` using `yield` |
| **Go**         | `func(job Job, next func(Job) (*Job, error)) (*Job, error)` | `func(job Job, ctx JobContext, next HandlerFunc) error` |
| **JavaScript** | `async (job, next) => { ... }`          | `async (job, ctx, next) => { ... }`        |
| **Python**     | Class with `async def call(self, job, call_next)` | Class with `async def call(self, job, ctx, call_next)` |
| **Java**       | Interface with `Job call(Job job, Function<Job, Job> next)` | Interface with `Result call(Job job, JobContext ctx, Supplier<Result> next)` |
| **Rust**       | Trait with `fn call(&self, job: Job, next: &dyn Fn(Job) -> Result<Job>)` | Trait with `fn call(&self, job: &Job, ctx: &JobContext, next: &dyn Fn() -> Result)` |

**Rationale**: Each language has established patterns for middleware/interceptor chains.
OJS defines the semantics; implementations choose the syntax. The important invariant is
that the `next` function (or `yield` or `block`) represents delegation to the remainder
of the chain.

### 11.2 Thread Safety

Middleware instances MUST be safe for concurrent use. Multiple worker threads or goroutines
may invoke the same middleware instance simultaneously.

Middleware MUST NOT maintain mutable state between invocations unless that state is
properly synchronized.

**Rationale**: Workers process multiple jobs concurrently. A metrics middleware instance
shared across all worker threads must not corrupt its internal state.

### 11.3 Performance Considerations

Middleware adds overhead to every job processed. Implementations SHOULD:

1. **Minimize allocations**: Reuse middleware instances across invocations.
2. **Avoid I/O in hot paths**: Middleware that performs network I/O (e.g., remote
   validation, external rate limiting) should be aware of its latency impact.
3. **Measure middleware overhead**: Implementations SHOULD provide a mechanism to measure
   the overhead of the middleware chain separately from handler execution time.

---

## 12. Prior Art

This specification draws from the following prior art:

| System / Pattern | Middleware Approach | Contribution to This Specification |
|------------------|--------------------|------------------------------------|
| **Sidekiq**      | `client_middleware` (enqueue) + `server_middleware` (execution), yield-based nesting. Five chain management operations (add, prepend, insert_before, insert_after, remove). Class identity for middleware lookup. | Gold standard. The two-chain model, chain management API, and yield-based nesting are directly adopted. Sidekiq's middleware chains are its most underrated contribution. |
| **Rack**         | Single middleware chain wrapping HTTP request/response. Each middleware calls `app.call(env)`. | Established the nested wrapper pattern ("onion model") that Sidekiq adapted for job processing. |
| **Taskiq**       | Explicit pipeline with named hooks: `pre_send`, `post_send`, `pre_execute`, `on_error`, `post_execute`, `post_save`. | Demonstrates the limitation of linear hooks vs. nested wrappers. Taskiq's hooks cannot wrap handler execution (no try/catch around the handler from middleware). OJS adopts the nested model instead. |
| **Asynq**        | `ServeMux`-style middleware matching Go's `net/http` middleware pattern. `func(next asynq.Handler) asynq.Handler`. | Demonstrates that the `net/http` middleware pattern (function wrapping) maps cleanly to job processing. Validates the language-agnostic applicability of the nested model. |
| **BullMQ**       | Limited middleware; primarily uses event listeners (`completed`, `failed`, `progress`, `stalled`). | Demonstrates the limitation of event-based observation vs. interception. Event listeners cannot modify job behavior, prevent execution, or wrap handlers. OJS requires full middleware, not just events. |
| **Celery**       | Implicit middleware via signals (`before_task_publish`, `after_task_publish`, `task_prerun`, `task_postrun`, `task_failure`, `task_success`) and task base classes. | Demonstrates the problems with implicit middleware: signals are unordered, base class inheritance is fragile, and neither provides the composability of explicit middleware chains. |
| **Express.js**   | `app.use(middleware)` with `(req, res, next)` signature. | Popularized the `next()` function pattern for middleware chains in the JavaScript ecosystem. |
| **Ring (Clojure)** | Middleware as higher-order functions wrapping a handler function. | Demonstrates the functional programming approach to middleware: each middleware is a function that takes a handler and returns a new handler. |

---

## Appendix A: Conformance Requirements Summary

The following table summarizes the normative requirements of this specification:

| Requirement                                                        | Level    | Section |
|--------------------------------------------------------------------|----------|---------|
| Implementations MUST support enqueue middleware chains              | MUST     | 3.1     |
| Implementations MUST support execution middleware chains           | MUST     | 4.1     |
| Enqueue middleware MUST execute in insertion order                  | MUST     | 3.2     |
| Execution middleware MUST execute as nested wrappers               | MUST     | 4.2     |
| Implementations MUST provide `add` chain management operation      | MUST     | 5.1     |
| Implementations MUST provide `prepend` chain management operation  | MUST     | 5.1     |
| Implementations MUST provide `insert_before` operation             | MUST     | 5.1     |
| Implementations MUST provide `insert_after` operation              | MUST     | 5.1     |
| Implementations MUST provide `remove` operation                    | MUST     | 5.1     |
| Implementations MUST provide a middleware identity mechanism       | MUST     | 5.2     |
| Chains MUST NOT be modified during job processing                  | MUST     | 5.3     |
| Ordering MUST be deterministic                                     | MUST     | 6.1     |
| Empty chains MUST be supported                                     | MUST     | 6.3     |
| Enqueue errors MUST abort the operation                            | MUST     | 7.1     |
| Enqueue null return MUST cancel silently                           | MUST     | 7.2     |
| Execution errors MUST propagate outward                            | MUST     | 7.3     |
| Middleware MUST NOT modify job `id`                                | MUST     | 3.5     |
| Middleware MUST be thread-safe                                     | MUST     | 11.2    |
| Batch enqueue MUST apply middleware per job                        | MUST     | 9.1     |
| Implementations SHOULD provide logging middleware                  | SHOULD   | 8.1.1   |
| Implementations SHOULD provide metrics middleware                  | SHOULD   | 8.1.2   |
| Implementations SHOULD provide timeout middleware                  | SHOULD   | 8.1.3   |
| Implementations SHOULD provide error reporting middleware          | SHOULD   | 8.1.4   |
| Implementations SHOULD provide trace context middleware            | SHOULD   | 8.1.5   |
| Implementations SHOULD provide chain inspection                   | SHOULD   | 5.4     |
| Implementations SHOULD provide a default middleware chain          | SHOULD   | 8.2     |

---

## Appendix B: Changelog

### 1.0.0-rc.1 (2025-06-01)

- Initial release candidate.
- Defined enqueue middleware chain as a MUST requirement.
- Defined execution middleware chain as a MUST requirement.
- Adopted Sidekiq's two-chain model (client + server) as the canonical pattern.
- Defined five chain management operations: add, prepend, insert_before, insert_after, remove.
- Specified nested wrapper ("onion") model for execution middleware.
- Specified linear pass-through model for enqueue middleware.
- Defined three enqueue middleware outcomes: pass (return job), drop (return null), abort (throw).
- Defined error propagation semantics for both chains.
- Specified built-in middleware recommendations: logging, metrics, timeout, error reporting, trace context.
- Documented prior art: Sidekiq, Rack, Taskiq, Asynq, BullMQ, Celery, Express.js, Ring.

---

*Open Job Spec v1.0.0-rc.1 -- Middleware Chain Specification*
*https://openjobspec.org*
