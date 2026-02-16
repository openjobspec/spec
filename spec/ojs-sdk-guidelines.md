# Open Job Spec: SDK Design Guidelines

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS SDK Design Guidelines                      |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-15                                     |
| **Status**  | Release Candidate 1                            |
| **Maturity** | Informational                                  |
| **Tier**    | Official Extension                             |
| **URI**     | `urn:ojs:ext:sdk-guidelines`                   |
| **Requires**| OJS Core Specification (Layer 1)               |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Design Principles](#4-design-principles)
5. [Client Architecture](#5-client-architecture)
   - 5.1 [OJS.Client (Producer)](#51-ojsclient-producer)
   - 5.2 [OJS.Worker (Consumer)](#52-ojsworker-consumer)
   - 5.3 [OJS.Admin (Operator)](#53-ojsadmin-operator)
   - 5.4 [Separation of Concerns](#54-separation-of-concerns)
   - 5.5 [Configuration](#55-configuration)
6. [Naming Conventions](#6-naming-conventions)
   - 6.1 [Method Names](#61-method-names)
   - 6.2 [Type Names](#62-type-names)
   - 6.3 [Event Names](#63-event-names)
   - 6.4 [Language Adaptation Table](#64-language-adaptation-table)
7. [Configuration](#7-configuration)
   - 7.1 [Builder Pattern](#71-builder-pattern)
   - 7.2 [Environment Variables](#72-environment-variables)
   - 7.3 [Configuration Options Table](#73-configuration-options-table)
8. [Error Handling](#8-error-handling)
   - 8.1 [Error Type Hierarchy](#81-error-type-hierarchy)
   - 8.2 [Throw vs Return](#82-throw-vs-return)
   - 8.3 [Error Context](#83-error-context)
   - 8.4 [Retry-Aware Errors](#84-retry-aware-errors)
9. [Async Patterns](#9-async-patterns)
   - 9.1 [Native Async/Await](#91-native-asyncawait)
   - 9.2 [Goroutine-Based Languages](#92-goroutine-based-languages)
   - 9.3 [Thread-Based Languages](#93-thread-based-languages)
   - 9.4 [Cancellation Propagation](#94-cancellation-propagation)
10. [Middleware API](#10-middleware-api)
    - 10.1 [Registration](#101-registration)
    - 10.2 [Middleware Signatures](#102-middleware-signatures)
11. [Testing Support](#11-testing-support)
12. [Logging](#12-logging)
13. [Observability Integration](#13-observability-integration)
14. [Versioning and Compatibility](#14-versioning-and-compatibility)
15. [Language-Specific Guidance](#15-language-specific-guidance)
    - 15.1 [Go](#151-go)
    - 15.2 [JavaScript / TypeScript](#152-javascript--typescript)
    - 15.3 [Python](#153-python)
    - 15.4 [Java](#154-java)
    - 15.5 [Ruby](#155-ruby)
    - 15.6 [Rust](#156-rust)
16. [Conformance Requirements](#16-conformance-requirements)
17. [Prior Art](#17-prior-art)

---

## 1. Introduction

SDK quality determines ecosystem adoption. A well-designed SDK converts specification fidelity into developer productivity; a poorly designed one turns even the best specification into a source of friction. When developers evaluate a job processing system, they evaluate the SDK -- not the specification.

This document defines the design principles, architectural patterns, naming conventions, and conformance requirements that every OJS SDK MUST or SHOULD follow. The goal is to ensure that developers moving between OJS SDKs in different languages encounter a consistent mental model while benefiting from language-idiomatic APIs.

These guidelines draw from the practices proven at scale by Azure SDK Design Guidelines, AWS SDK guidelines, Google API Design Guide, Stripe's API design principles, and Temporal's SDK design. Each of these projects demonstrated that explicit, opinionated SDK guidelines produce ecosystems where developers can transfer knowledge across languages and where third-party integrations compose reliably.

### 1.1 Scope

This document covers:

- The three-role client architecture (Client, Worker, Admin).
- Naming conventions and their language-specific adaptations.
- Configuration, error handling, async patterns, and middleware APIs.
- Testing, logging, and observability integration requirements.
- Per-language guidance for Go, JavaScript/TypeScript, Python, Java, Ruby, and Rust.
- Conformance requirements for SDK implementers.

This document does **not** define the OJS job envelope, lifecycle, or wire formats. Those are defined in the [Core Specification](./ojs-core.md), [JSON Wire Format](./ojs-json-format.md), and protocol binding specifications.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

When these words are used in lowercase, they carry their ordinary English meaning and do not imply specification requirements.

---

## 3. Terminology

In addition to the terms defined in the [OJS Core Specification](./ojs-core.md), this document uses the following:

**SDK**
: A language-specific library that implements the OJS specification and exposes an idiomatic API for producing, consuming, and managing background jobs.

**Producer**
: Application code that creates and enqueues jobs via `OJS.Client`.

**Consumer**
: Application code that registers handlers and processes jobs via `OJS.Worker`.

**Operator**
: Application code or tooling that inspects and manages queues and jobs via `OJS.Admin`.

**Canonical Name**
: The language-neutral reference name for an OJS concept (e.g., `enqueue`). Each language adapts the canonical name to its idiomatic convention.

**Progressive Disclosure**
: A design strategy that presents common operations simply while making advanced features discoverable without cluttering the primary API surface.

---

## 4. Design Principles

SDK implementations MUST be guided by the following principles:

### 4.1 Idiomatic to the Target Language

An OJS SDK MUST feel native to its language. A Go SDK MUST use `context.Context`, return `error`, and follow the standard library's naming conventions. A Python SDK MUST use snake_case, support `async/await`, and integrate with type hints. A developer SHOULD NOT be able to distinguish an OJS SDK from a first-party library by style alone.

*Rationale*: Azure's SDK rewrite from "one design for all languages" to "idiomatic per language" produced a measurable increase in developer satisfaction and adoption. Developers resist APIs that fight their language's conventions.

### 4.2 Consistent Across Languages Where Possible

While APIs MUST be idiomatic, the underlying mental model MUST be consistent. The three-role split (Client, Worker, Admin), the operation names (enqueue, fetch, ack, fail), and the configuration structure SHOULD map recognizably across languages. A developer who knows the Go SDK SHOULD be able to read the Python SDK without consulting documentation.

*Rationale*: Stripe and Temporal demonstrate that cross-language consistency in concept naming -- while allowing syntactic divergence -- accelerates multi-language adoption.

### 4.3 Progressive Disclosure

Simple things MUST be simple; complex things MUST be possible. Enqueuing a job MUST require no more than a job type and arguments. Advanced features (retry policies, unique constraints, scheduled execution) MUST be available but MUST NOT clutter the primary API.

*Rationale*: AWS SDK guidelines call this "easy things should be easy." Google's API Design Guide formalizes it as "API surface area minimization." Both demonstrate that progressive disclosure reduces time-to-first-success.

### 4.4 Pit of Success

Default configurations MUST produce correct, safe behavior. An SDK with default settings MUST connect securely (TLS), MUST NOT lose jobs silently, and MUST apply reasonable timeouts. A developer who accepts all defaults MUST end up with a working, production-reasonable system.

*Rationale*: The "pit of success" principle, coined by Rico Mariani and adopted by the .NET design guidelines, asserts that the easiest path through an API should also be the correct path.

---

## 5. Client Architecture

### 5.1 OJS.Client (Producer)

The `Client` is the producer-side entry point. It is responsible for enqueuing jobs and, optionally, cancelling them.

An OJS Client MUST provide:

| Method           | Description                                        |
|------------------|----------------------------------------------------|
| `enqueue`        | Enqueue a single job. Maps to the PUSH operation.  |
| `enqueue_batch`  | Enqueue multiple jobs atomically where possible.   |
| `cancel`         | Cancel a pending or scheduled job by ID.           |

**Go example:**

```go
client, err := ojs.NewClient(ojs.WithBackendURL("redis://localhost:6379"))
if err != nil {
    log.Fatal(err)
}
defer client.Close()

job, err := client.Enqueue(ctx, ojs.Job{
    Type:  "email.send",
    Args:  map[string]any{"to": "user@example.com", "template": "welcome"},
    Queue: "emails",
})
```

**TypeScript example:**

```typescript
const client = new OjsClient({ backendUrl: "redis://localhost:6379" });

const job = await client.enqueue({
  type: "email.send",
  args: { to: "user@example.com", template: "welcome" },
  queue: "emails",
});
```

**Python example:**

```python
client = OjsClient(backend_url="redis://localhost:6379")

job = await client.enqueue(
    job_type="email.send",
    args={"to": "user@example.com", "template": "welcome"},
    queue="emails",
)
```

### 5.2 OJS.Worker (Consumer)

The `Worker` is the consumer-side entry point. It fetches jobs from one or more queues, dispatches them to registered handlers, and manages the fetch-execute-ack/fail lifecycle.

An OJS Worker MUST provide:

| Method             | Description                                           |
|--------------------|-------------------------------------------------------|
| `register`         | Register a handler function for a job type.           |
| `start`            | Begin fetching and processing jobs.                   |
| `stop`             | Initiate graceful shutdown (drain in-flight jobs).    |

**Go example:**

```go
worker, err := ojs.NewWorker(ojs.WithBackendURL("redis://localhost:6379"))
if err != nil {
    log.Fatal(err)
}

worker.Register("email.send", func(ctx context.Context, job *ojs.Job) error {
    return sendEmail(ctx, job.Args["to"].(string), job.Args["template"].(string))
})

if err := worker.Start(ctx); err != nil {
    log.Fatal(err)
}
```

**TypeScript example:**

```typescript
const worker = new OjsWorker({ backendUrl: "redis://localhost:6379" });

worker.register("email.send", async (job) => {
  await sendEmail(job.args.to, job.args.template);
});

await worker.start();
```

**Python example:**

```python
worker = OjsWorker(backend_url="redis://localhost:6379")

@worker.register("email.send")
async def handle_email(job: Job) -> None:
    await send_email(job.args["to"], job.args["template"])

await worker.start()
```

### 5.3 OJS.Admin (Operator)

The `Admin` is the operator-side entry point. It provides queue and job introspection and management operations.

An OJS Admin MUST provide:

| Method           | Description                                        |
|------------------|----------------------------------------------------|
| `list_queues`    | List all known queues and their depths.            |
| `get_job`        | Retrieve a job by ID.                              |
| `list_jobs`      | List jobs with filters (queue, state, type).       |
| `retry_job`      | Re-enqueue a failed or discarded job.              |
| `discard_job`    | Move a job to the discarded state.                 |
| `pause_queue`    | Pause processing on a queue.                       |
| `resume_queue`   | Resume processing on a paused queue.               |

*Rationale*: Sidekiq Pro, Oban Pro, and Asynq all provide admin/operator APIs. Separating operator capabilities from producer/consumer APIs prevents application code from accidentally invoking destructive operations.

### 5.4 Separation of Concerns

An SDK MUST separate Client, Worker, and Admin into distinct types or modules. An SDK MUST NOT combine producer and consumer functionality into a single class.

*Rationale*: Mixing concerns leads to APIs where application code has access to `pause_queue` and `discard_job` alongside `enqueue`. The Azure SDK guidelines explicitly require this separation ("clients should have a single responsibility"), and production incidents at scale have demonstrated why.

### 5.5 Configuration

Each role (Client, Worker, Admin) MUST accept configuration at construction time. Configuration options that are shared across roles (backend URL, TLS settings, authentication) SHOULD use a shared configuration type.

An SDK MUST support:

- Connection string or backend URL.
- TLS configuration (certificates, skip verification for development).
- Authentication credentials (tokens, passwords).
- Timeouts (connection, operation, shutdown).

---

## 6. Naming Conventions

### 6.1 Method Names

The following canonical method names MUST be used. SDKs MUST NOT use alternative names for these operations.

| Canonical Name   | Maps to Core Op | Alternatives NOT allowed     |
|------------------|-----------------|------------------------------|
| `enqueue`        | PUSH            | push, add, send, submit      |
| `enqueue_batch`  | PUSH (batch)    | push_many, add_all, bulk_add |
| `fetch`          | FETCH           | pop, pull, receive, dequeue  |
| `ack`            | ACK             | complete, done, finish       |
| `fail`           | FAIL            | reject, nack, error          |
| `cancel`         | CANCEL          | abort, kill, delete          |

*Rationale*: Naming divergence is the single largest source of confusion in multi-language ecosystems. Sidekiq uses `perform_async`, Celery uses `delay`, Bull uses `add`, Oban uses `insert` -- all for the same operation. OJS standardizes on `enqueue` because it accurately describes the action and is universally understood.

### 6.2 Type Names

| Canonical Name | Description                                         |
|----------------|-----------------------------------------------------|
| `Job`          | The job envelope structure.                         |
| `RetryPolicy`  | Retry configuration (max attempts, backoff).        |
| `UniquePolicy` | Uniqueness constraint configuration.                |
| `CronJob`      | A periodic job definition.                          |
| `Workflow`     | A composed set of jobs (chain, group, batch).       |
| `OjsClient`    | Producer-side client.                               |
| `OjsWorker`    | Consumer-side worker.                               |
| `OjsAdmin`     | Operator-side admin.                                |

### 6.3 Event Names

Event callback names MUST follow the pattern `on_<event>` where `<event>` is a past-tense or present-tense descriptor:

| Canonical Event Name | Trigger                                |
|----------------------|----------------------------------------|
| `on_job_enqueued`    | A job has been submitted to a queue.   |
| `on_job_started`     | A job handler has begun execution.     |
| `on_job_completed`   | A job handler completed successfully.  |
| `on_job_failed`      | A job handler returned an error.       |
| `on_job_retrying`    | A failed job is being re-enqueued.     |
| `on_job_discarded`   | A job has exhausted all retries.       |
| `on_job_cancelled`   | A job was cancelled.                   |

### 6.4 Language Adaptation Table

SDKs MUST adapt canonical names to the target language's idiomatic convention:

| Canonical Name   | Go (`PascalCase`)  | JS/TS (`camelCase`)  | Python (`snake_case`) | Java (`camelCase`)  | Ruby (`snake_case`) | Rust (`snake_case`) | C# (`PascalCase`)  |
|------------------|--------------------|-----------------------|-----------------------|---------------------|---------------------|---------------------|---------------------|
| `enqueue`        | `Enqueue`          | `enqueue`             | `enqueue`             | `enqueue`           | `enqueue`           | `enqueue`           | `Enqueue`           |
| `enqueue_batch`  | `EnqueueBatch`     | `enqueueBatch`        | `enqueue_batch`       | `enqueueBatch`      | `enqueue_batch`     | `enqueue_batch`     | `EnqueueBatch`      |
| `fetch`          | `Fetch`            | `fetch`               | `fetch`               | `fetch`             | `fetch`             | `fetch`             | `Fetch`             |
| `ack`            | `Ack`              | `ack`                 | `ack`                 | `ack`               | `ack`               | `ack`               | `Ack`               |
| `fail`           | `Fail`             | `fail`                | `fail`                | `fail`              | `fail`              | `fail`              | `Fail`              |
| `cancel`         | `Cancel`           | `cancel`              | `cancel`              | `cancel`            | `cancel`            | `cancel`            | `Cancel`            |
| `on_job_completed` | `OnJobCompleted` | `onJobCompleted`      | `on_job_completed`    | `onJobCompleted`    | `on_job_completed`  | `on_job_completed`  | `OnJobCompleted`    |
| `RetryPolicy`    | `RetryPolicy`      | `RetryPolicy`         | `RetryPolicy`         | `RetryPolicy`       | `RetryPolicy`       | `RetryPolicy`       | `RetryPolicy`       |
| `OjsClient`      | `Client`           | `OjsClient`           | `OjsClient`           | `OjsClient`         | `OjsClient`         | `OjsClient`         | `OjsClient`         |

> **Note**: Go conventionally drops the package prefix from type names (the package *is* the namespace), so `ojs.Client` is idiomatic rather than `ojs.OjsClient`.

---

## 7. Configuration

### 7.1 Builder Pattern

SDKs in languages that support builder patterns (Go functional options, Java builders, Rust builders) SHOULD use them for complex configuration. The builder pattern enables progressive disclosure: required parameters in the constructor, optional parameters via builder methods.

**Go (functional options):**

```go
client, err := ojs.NewClient(
    ojs.WithBackendURL("redis://localhost:6379"),
    ojs.WithQueue("critical"),
    ojs.WithTimeout(30 * time.Second),
    ojs.WithTLS(tlsConfig),
)
```

**TypeScript (options object):**

```typescript
const client = new OjsClient({
  backendUrl: "redis://localhost:6379",
  queue: "critical",
  timeout: 30_000,
  tls: { rejectUnauthorized: true },
});
```

**Python (keyword arguments):**

```python
client = OjsClient(
    backend_url="redis://localhost:6379",
    queue="critical",
    timeout=30.0,
    tls=TlsConfig(verify=True),
)
```

### 7.2 Environment Variables

An SDK MUST support configuration via environment variables. Environment variables MUST use the `OJS_` prefix and uppercase snake_case.

| Variable               | Description                          | Maps to            |
|------------------------|--------------------------------------|---------------------|
| `OJS_BACKEND_URL`      | Backend connection string            | `backend_url`       |
| `OJS_QUEUE`            | Default queue name                   | `queue`             |
| `OJS_CONCURRENCY`      | Worker concurrency (thread/goroutine count) | `concurrency` |
| `OJS_SHUTDOWN_TIMEOUT`  | Graceful shutdown timeout (seconds)  | `shutdown_timeout`  |
| `OJS_LOG_LEVEL`        | Logging level                        | `log_level`         |
| `OJS_TLS_CERT_FILE`    | Path to TLS client certificate       | `tls.cert_file`     |
| `OJS_TLS_KEY_FILE`     | Path to TLS client key               | `tls.key_file`      |
| `OJS_TLS_CA_FILE`      | Path to TLS CA certificate           | `tls.ca_file`       |
| `OJS_AUTH_TOKEN`       | Authentication token                 | `auth_token`        |

Environment variables MUST be overridden by explicit programmatic configuration. The precedence order is: programmatic > environment variable > default.

### 7.3 Configuration Options Table

| Option              | Type      | Default              | Description                                       |
|---------------------|-----------|----------------------|---------------------------------------------------|
| `backend_url`       | `string`  | `redis://localhost:6379` | Backend connection string.                    |
| `queue`             | `string`  | `"default"`          | Default queue for enqueue and fetch operations.   |
| `queues`            | `list`    | `["default"]`        | Queues the worker subscribes to (Worker only).    |
| `concurrency`       | `integer` | `10`                 | Number of concurrent job processors (Worker).     |
| `shutdown_timeout`  | `duration`| `30s`                | Time to wait for in-flight jobs during shutdown.  |
| `poll_interval`     | `duration`| `1s`                 | Interval between fetch attempts when idle.        |
| `connection_timeout`| `duration`| `5s`                 | Timeout for establishing backend connections.     |
| `operation_timeout` | `duration`| `30s`                | Timeout for individual backend operations.        |
| `tls_enabled`       | `boolean` | `true`               | Whether to use TLS for backend connections.       |
| `log_level`         | `string`  | `"info"`             | Minimum log level (`debug`, `info`, `warn`, `error`). |
| `retry_policy`      | `object`  | See ojs-retry.md     | Default retry policy for enqueued jobs.           |

Every option MUST have a sensible default. An SDK constructed with zero configuration MUST be functional for local development.

---

## 8. Error Handling

### 8.1 Error Type Hierarchy

An SDK MUST define the following error types:

| Error Type              | Description                                              |
|-------------------------|----------------------------------------------------------|
| `OjsError`              | Base error type. All OJS errors MUST inherit from this.  |
| `ConnectionError`       | Backend is unreachable or connection was dropped.        |
| `ValidationError`       | Invalid job attributes (missing type, malformed args).   |
| `TimeoutError`          | Operation exceeded configured timeout.                   |
| `AuthenticationError`   | Backend rejected credentials.                            |
| `JobNotFoundError`      | Referenced job ID does not exist.                        |
| `QueuePausedError`      | Attempted to enqueue to a paused queue.                  |

SDKs MUST use the language's idiomatic error mechanism:

- **Go**: Custom error types implementing the `error` interface. Use `errors.Is` and `errors.As` for type checking.
- **JavaScript/TypeScript**: Custom `Error` subclasses.
- **Python**: Custom `Exception` subclasses.
- **Java**: Custom checked or unchecked exceptions (SHOULD use unchecked).
- **Ruby**: Custom exception subclasses of `StandardError`.
- **Rust**: Custom error enum implementing `std::error::Error`.

### 8.2 Throw vs Return

The SDK MUST follow the target language's idiomatic convention for error reporting:

| Language    | Convention                                                    |
|-------------|---------------------------------------------------------------|
| Go          | Return `error` as the last return value. MUST NOT panic.      |
| TypeScript  | Reject the `Promise`. MUST NOT throw synchronously in async functions. |
| Python      | Raise exceptions. Async functions MUST raise, not return error values. |
| Java        | Throw exceptions. SHOULD prefer unchecked `RuntimeException` subclasses. |
| Ruby        | Raise exceptions.                                              |
| Rust        | Return `Result<T, OjsError>`. MUST NOT panic.                 |
| C#          | Throw exceptions. Use `OperationCanceledException` for cancellation. |

### 8.3 Error Context

Every error MUST carry sufficient context for debugging. At minimum:

- `job_id` (when applicable): The ID of the job that caused the error.
- `queue` (when applicable): The queue involved.
- `operation`: The operation that failed (`enqueue`, `fetch`, `ack`, etc.).
- `attempt` (in handler context): The current attempt number.

**Go example:**

```go
type OjsError struct {
    Op      string  // "enqueue", "fetch", "ack"
    JobID   string  // may be empty
    Queue   string  // may be empty
    Attempt int     // 0 if not in handler context
    Err     error   // underlying error
}

func (e *OjsError) Error() string {
    return fmt.Sprintf("ojs: %s failed (job=%s queue=%s attempt=%d): %v",
        e.Op, e.JobID, e.Queue, e.Attempt, e.Err)
}

func (e *OjsError) Unwrap() error { return e.Err }
```

**TypeScript example:**

```typescript
class OjsError extends Error {
  constructor(
    message: string,
    public readonly operation: string,
    public readonly jobId?: string,
    public readonly queue?: string,
    public readonly attempt?: number,
    public readonly cause?: Error,
  ) {
    super(message);
    this.name = "OjsError";
  }
}
```

### 8.4 Retry-Aware Errors

Within job handlers, an SDK MUST provide a mechanism to distinguish between retryable and non-retryable failures. A handler SHOULD be able to signal "do not retry this job" by returning or throwing a specific error type.

| Error Signal       | Behavior                                                   |
|--------------------|------------------------------------------------------------|
| Normal error/exception | Job fails and is retried according to its retry policy. |
| `DiscardError`     | Job is moved directly to `discarded`. No further retries.  |
| `SnoozeError(duration)` | Job is rescheduled after the specified duration.      |

**Python example:**

```python
@worker.register("payment.charge")
async def handle_charge(job: Job) -> None:
    try:
        await charge_card(job.args["card_id"], job.args["amount"])
    except CardDeclinedError:
        raise DiscardError("Card permanently declined")
    except GatewayTimeoutError:
        raise  # Normal exception -- will be retried
```

---

## 9. Async Patterns

### 9.1 Native Async/Await

Languages with built-in async/await (JavaScript, TypeScript, Python, C#, Rust) MUST use the native async mechanism for all I/O-bound operations. The SDK MUST NOT block the event loop or executor.

- **JavaScript/TypeScript**: All Client, Worker, and Admin methods that perform I/O MUST return `Promise`.
- **Python**: All I/O methods MUST be `async def`. A synchronous wrapper MAY be provided for simple use cases.
- **C#**: All I/O methods MUST return `Task<T>` or `ValueTask<T>`.
- **Rust**: All I/O methods MUST be `async fn`. The SDK SHOULD be runtime-agnostic (work with both `tokio` and `async-std`).

### 9.2 Goroutine-Based Languages

Go SDKs MUST use `context.Context` as the first parameter to every method that performs I/O or may block. Cancellation MUST be propagated through context.

```go
job, err := client.Enqueue(ctx, ojs.Job{Type: "email.send", Args: args})

// Context cancellation stops the worker gracefully
ctx, cancel := context.WithCancel(context.Background())
go func() {
    sig := make(chan os.Signal, 1)
    signal.Notify(sig, syscall.SIGTERM)
    <-sig
    cancel()
}()
worker.Start(ctx)
```

### 9.3 Thread-Based Languages

Languages primarily using threads (Java, Ruby) SHOULD provide both synchronous and asynchronous APIs:

- **Java**: SHOULD provide `CompletableFuture<T>` variants alongside synchronous methods. The async variant MUST use the suffix `Async` (e.g., `enqueueAsync`).
- **Ruby**: MUST provide synchronous methods. MAY provide `async`-compatible methods for use with `async` gem or fiber-based concurrency.

### 9.4 Cancellation Propagation

An SDK MUST propagate cancellation from the caller to in-flight operations:

| Language    | Cancellation Mechanism                          |
|-------------|------------------------------------------------|
| Go          | `context.Context` cancellation                 |
| TypeScript  | `AbortController` / `AbortSignal`              |
| Python      | `asyncio.CancelledError` / task cancellation   |
| Java        | `Future.cancel()` / thread interruption        |
| Rust        | `tokio::select!` / dropping the future         |
| C#          | `CancellationToken`                            |

Job handlers MUST receive a cancellation signal when the worker is shutting down. Handlers SHOULD check for cancellation at natural checkpoints and return promptly.

---

## 10. Middleware API

Middleware chains are a MUST requirement per the [OJS Middleware Specification](./ojs-middleware.md). This section specifies how SDKs expose middleware registration and authoring.

### 10.1 Registration

An SDK MUST support two middleware chains:

1. **Enqueue middleware**: Runs on the Client before a job is submitted to the backend.
2. **Execution middleware**: Runs on the Worker around each job handler invocation.

Middleware MUST execute in registration order. Each middleware MUST be able to:

- Inspect and modify the job envelope.
- Short-circuit the chain (skip downstream middleware and the handler).
- Execute logic before and after the next middleware or handler.

### 10.2 Middleware Signatures

**Go:**

```go
type Middleware func(ctx context.Context, job *Job, next func(context.Context, *Job) error) error

// Registration
client.Use(loggingMiddleware)
worker.Use(metricsMiddleware, tracingMiddleware)
```

**TypeScript:**

```typescript
type Middleware = (job: Job, next: () => Promise<void>) => Promise<void>;

// Registration
client.use(loggingMiddleware);
worker.use(metricsMiddleware, tracingMiddleware);
```

**Python:**

```python
# Decorator-style
@worker.middleware
async def logging_middleware(job: Job, call_next: CallNext) -> None:
    logger.info("Processing %s", job.id)
    await call_next()
    logger.info("Completed %s", job.id)

# Explicit registration
worker.use(metrics_middleware)
```

---

## 11. Testing Support

An SDK MUST provide testing utilities as defined in the [OJS Testing Specification](./ojs-testing.md). At minimum, the SDK MUST support the following modes:

| Mode     | Description                                                             |
|----------|-------------------------------------------------------------------------|
| **Fake** | In-memory backend. Jobs are stored but not executed. Enables assertion on enqueued jobs. |
| **Inline** | Jobs are executed synchronously at enqueue time. Useful for integration tests. |
| **Real** | Full backend connectivity. Used for end-to-end tests.                   |

The SDK MUST provide test helper functions:

- `assert_enqueued(type, args)` -- Assert a job was enqueued with the given type and args.
- `assert_not_enqueued(type)` -- Assert no job of the given type was enqueued.
- `drain()` -- Execute all enqueued jobs synchronously (Fake and Inline modes).
- `clear()` -- Remove all jobs from the test queue.
- `perform(type, args)` -- Execute a job handler directly in test context.

**Go example:**

```go
func TestEmailSend(t *testing.T) {
    client := ojstest.NewFakeClient(t)

    err := service.SendWelcomeEmail(ctx, client, "user@example.com")
    require.NoError(t, err)

    ojstest.AssertEnqueued(t, client, "email.send", map[string]any{
        "to":       "user@example.com",
        "template": "welcome",
    })
}
```

**TypeScript example:**

```typescript
test("sends welcome email", async () => {
  const client = new OjsFakeClient();

  await service.sendWelcomeEmail(client, "user@example.com");

  client.assertEnqueued("email.send", {
    to: "user@example.com",
    template: "welcome",
  });
});
```

**Python example:**

```python
async def test_send_welcome_email():
    client = OjsFakeClient()

    await service.send_welcome_email(client, "user@example.com")

    client.assert_enqueued("email.send", args={
        "to": "user@example.com",
        "template": "welcome",
    })
```

---

## 12. Logging

### 12.1 Structured Logging

An SDK MUST support structured logging. Log entries MUST be key-value pairs, not unstructured strings. The SDK SHOULD integrate with the language's standard structured logging facility:

| Language    | Recommended Logger                              |
|-------------|------------------------------------------------|
| Go          | `log/slog` (standard library)                  |
| TypeScript  | `pino`, `winston`, or any structured logger    |
| Python      | `structlog` or `logging` with JSON formatter   |
| Java        | SLF4J with structured MDC                      |
| Ruby        | `SemanticLogger` or `Logger` with JSON formatter |
| Rust        | `tracing` crate                                |

### 12.2 Log Levels

| Level   | Usage                                                         |
|---------|---------------------------------------------------------------|
| `debug` | Job details, middleware execution, backend protocol messages.  |
| `info`  | Job lifecycle events (enqueued, started, completed).          |
| `warn`  | Retries, transient failures, deprecation warnings.            |
| `error` | Permanent failures, connection loss, handler panics/crashes.  |

### 12.3 Sensitive Data

An SDK MUST NOT log job arguments (`args`) at `info` level or above by default. Job arguments MAY contain personally identifiable information (PII), credentials, or other sensitive data.

An SDK SHOULD provide an opt-in mechanism to include arguments in debug logs:

```go
worker, _ := ojs.NewWorker(
    ojs.WithBackendURL(url),
    ojs.WithLogArgs(true), // opt-in: include args in debug logs
)
```

---

## 13. Observability Integration

### 13.1 OpenTelemetry

OpenTelemetry integration SHOULD be built into every OJS SDK. When enabled, the SDK MUST emit traces and metrics as defined in the [OJS Observability Specification](./ojs-observability.md).

An SDK SHOULD provide OpenTelemetry support as a middleware so that it can be composed with other middleware and optionally excluded in environments where OpenTelemetry is not used.

### 13.2 Trace Context Propagation

Trace context propagation MUST be automatic when OpenTelemetry is enabled. The SDK MUST:

1. **Inject** trace context into the job envelope `meta` at enqueue time.
2. **Extract** trace context from the job envelope `meta` at execution time.
3. **Create spans** for enqueue and process operations with appropriate parent-child relationships.

This ensures that a distributed trace flows seamlessly from the producer through the queue to the consumer.

### 13.3 Metrics

When OpenTelemetry is enabled, the SDK SHOULD emit the following metrics:

| Metric Name                   | Type      | Description                                |
|-------------------------------|-----------|--------------------------------------------|
| `ojs.job.enqueue.count`      | Counter   | Number of jobs enqueued.                   |
| `ojs.job.process.duration`   | Histogram | Duration of job handler execution.         |
| `ojs.job.process.count`      | Counter   | Number of jobs processed (by outcome).     |
| `ojs.job.retry.count`        | Counter   | Number of job retries.                     |
| `ojs.worker.active_jobs`     | Gauge     | Number of concurrently executing jobs.     |
| `ojs.queue.depth`            | Gauge     | Number of jobs in a queue.                 |

---

## 14. Versioning and Compatibility

### 14.1 SDK Version vs Spec Version

An SDK MUST declare which OJS specification version it implements. The SDK's own version (e.g., `v2.3.1`) is independent of the specification version (e.g., `1.0.0-rc.1`). An SDK MUST expose the supported specification version programmatically:

```go
ojs.SpecVersion()  // "1.0.0"
```

```typescript
OjsClient.specVersion; // "1.0.0"
```

```python
ojs.SPEC_VERSION  # "1.0.0"
```

### 14.2 Backward Compatibility

An SDK MUST follow [Semantic Versioning 2.0.0](https://semver.org/):

- **Major version**: Breaking changes to the public API.
- **Minor version**: New features, backward-compatible.
- **Patch version**: Bug fixes, backward-compatible.

An SDK MUST NOT remove or rename public API methods in a minor or patch release. Behavioral changes to existing methods MUST be backward-compatible in minor and patch releases.

### 14.3 Deprecation Policy

An SDK MUST support deprecated features for at least **one minor version** after deprecation is announced. Deprecated features MUST emit a warning at runtime (log level `warn`). The deprecation warning MUST include the version in which the feature will be removed and a migration path.

---

## 15. Language-Specific Guidance

### 15.1 Go

- Package name MUST be `ojs`. Types MUST NOT repeat the package name (use `ojs.Client`, not `ojs.OjsClient`).
- All I/O methods MUST accept `context.Context` as the first parameter.
- Configuration MUST use the functional options pattern (`ojs.WithBackendURL(...)`, `ojs.WithTimeout(...)`).
- Errors MUST implement `error` and support `errors.Is` / `errors.As`.
- The SDK SHOULD provide a `ojs/ojstest` sub-package for testing utilities.
- The SDK MUST NOT use `init()` functions or package-level mutable state.

```go
package main

import (
    "context"
    "log"

    "github.com/openjobspec/ojs-go"
    "github.com/openjobspec/ojs-go/ojstest"
)

func main() {
    ctx := context.Background()

    client, err := ojs.NewClient(ojs.WithBackendURL("redis://localhost:6379"))
    if err != nil {
        log.Fatal(err)
    }
    defer client.Close()

    _, err = client.Enqueue(ctx, ojs.Job{
        Type: "report.generate",
        Args: map[string]any{"report_id": 42},
    })
    if err != nil {
        log.Fatal(err)
    }
}
```

### 15.2 JavaScript / TypeScript

- The SDK MUST ship with TypeScript type definitions.
- All I/O methods MUST return `Promise`.
- Configuration MUST use an options object passed to the constructor.
- The SDK MUST support both ESM and CommonJS module formats.
- The SDK SHOULD provide tree-shakeable exports.
- Cancellation MUST use `AbortSignal`.

```typescript
import { OjsClient, OjsWorker, Job } from "@openjobspec/sdk";

const client = new OjsClient({
  backendUrl: process.env.OJS_BACKEND_URL ?? "redis://localhost:6379",
});

await client.enqueue({
  type: "report.generate",
  args: { reportId: 42 },
});

const worker = new OjsWorker({
  backendUrl: process.env.OJS_BACKEND_URL ?? "redis://localhost:6379",
  queues: ["default", "critical"],
  concurrency: 5,
});

worker.register("report.generate", async (job: Job) => {
  const report = await generateReport(job.args.reportId);
  await uploadReport(report);
});

const controller = new AbortController();
process.on("SIGTERM", () => controller.abort());
await worker.start({ signal: controller.signal });
```

### 15.3 Python

- The SDK MUST support Python 3.10+.
- All I/O methods MUST be `async def`. A synchronous facade MAY be provided.
- The SDK MUST provide full type annotations (PEP 484) and pass `mypy --strict`.
- Configuration MUST use keyword arguments with dataclass-style config objects for complex cases.
- The SDK SHOULD support decorator-based handler registration.

```python
import asyncio
from ojs import OjsClient, OjsWorker, Job

async def main() -> None:
    client = OjsClient(backend_url="redis://localhost:6379")

    await client.enqueue(
        job_type="report.generate",
        args={"report_id": 42},
    )

    worker = OjsWorker(
        backend_url="redis://localhost:6379",
        queues=["default", "critical"],
        concurrency=5,
    )

    @worker.register("report.generate")
    async def handle_report(job: Job) -> None:
        report = await generate_report(job.args["report_id"])
        await upload_report(report)

    await worker.start()

asyncio.run(main())
```

### 15.4 Java

- The SDK MUST target Java 17+.
- Client, Worker, and Admin MUST be interfaces with default implementations.
- Configuration MUST use the builder pattern.
- The SDK SHOULD provide `CompletableFuture<T>` async variants for all I/O methods.
- The SDK MUST integrate with SLF4J for logging.
- The SDK SHOULD provide Spring Boot auto-configuration as a separate module.

```java
var client = OjsClient.builder()
    .backendUrl("redis://localhost:6379")
    .build();

client.enqueue(Job.builder()
    .type("report.generate")
    .args(Map.of("reportId", 42))
    .build());
```

### 15.5 Ruby

- The SDK MUST support Ruby 3.1+.
- All methods MUST use snake_case.
- Configuration MUST support both block-style and hash-style:

```ruby
client = Ojs::Client.new(backend_url: "redis://localhost:6379")

client.enqueue(
  type: "report.generate",
  args: { report_id: 42 }
)

# Block-style configuration
Ojs.configure do |config|
  config.backend_url = "redis://localhost:6379"
  config.concurrency = 10
end
```

### 15.6 Rust

- The SDK MUST be `async` and runtime-agnostic (default to `tokio` but SHOULD work with other runtimes).
- Errors MUST use a custom `enum` implementing `std::error::Error` and `thiserror`.
- Configuration MUST use the builder pattern.
- The SDK MUST support `#[derive]` macros for defining job types where ergonomic.

```rust
use ojs::{OjsClient, OjsWorker, Job, Result};

#[tokio::main]
async fn main() -> Result<()> {
    let client = OjsClient::builder()
        .backend_url("redis://localhost:6379")
        .build()
        .await?;

    client.enqueue(Job::new("report.generate")
        .arg("report_id", 42))
        .await?;

    let worker = OjsWorker::builder()
        .backend_url("redis://localhost:6379")
        .queues(vec!["default", "critical"])
        .concurrency(5)
        .build()
        .await?;

    worker.register("report.generate", |job: &Job| async move {
        let report = generate_report(job.arg::<i64>("report_id")?).await?;
        upload_report(&report).await
    });

    worker.start().await
}
```

---

## 16. Conformance Requirements

The following table lists all normative requirements defined in this document. An SDK claiming conformance to this specification MUST satisfy all MUST-level requirements.

| ID      | Level    | Requirement                                                                 |
|---------|----------|-----------------------------------------------------------------------------|
| SDK-001 | MUST     | Separate Client, Worker, and Admin into distinct types or modules.          |
| SDK-002 | MUST     | Client provides `enqueue`, `enqueue_batch`, and `cancel` methods.           |
| SDK-003 | MUST     | Worker provides `register`, `start`, and `stop` methods.                    |
| SDK-004 | MUST     | Admin provides `list_queues`, `get_job`, `list_jobs`, `retry_job`, `discard_job`, `pause_queue`, and `resume_queue` methods. |
| SDK-005 | MUST     | Use canonical method names (`enqueue`, `fetch`, `ack`, `fail`, `cancel`).   |
| SDK-006 | MUST     | Adapt canonical names to target language idiom (case convention).           |
| SDK-007 | MUST     | Support configuration via environment variables with `OJS_` prefix.         |
| SDK-008 | MUST     | Provide sensible defaults for all configuration options.                    |
| SDK-009 | MUST     | Configuration precedence: programmatic > environment variable > default.    |
| SDK-010 | MUST     | Define `OjsError` base error type and required subtypes.                    |
| SDK-011 | MUST     | Include `job_id`, `queue`, `operation`, and `attempt` in error context.     |
| SDK-012 | MUST     | Follow target language's idiomatic error mechanism (throw vs return).       |
| SDK-013 | MUST     | Provide `DiscardError` and `SnoozeError` for handler error signaling.       |
| SDK-014 | MUST     | Use native async mechanism for I/O in async-capable languages.              |
| SDK-015 | MUST     | Accept `context.Context` as first param for all I/O methods (Go).           |
| SDK-016 | MUST     | Support enqueue and execution middleware chains.                            |
| SDK-017 | MUST     | Provide fake, inline, and real testing modes.                               |
| SDK-018 | MUST     | Provide assertion helpers (`assert_enqueued`, `drain`, `clear`, `perform`). |
| SDK-019 | MUST     | Support structured logging with key-value pairs.                            |
| SDK-020 | MUST     | NOT log job arguments at `info` level or above by default.                  |
| SDK-021 | MUST     | Automatically propagate trace context when OpenTelemetry is enabled.        |
| SDK-022 | MUST     | Declare supported OJS specification version programmatically.               |
| SDK-023 | MUST     | Follow Semantic Versioning 2.0.0 for SDK releases.                         |
| SDK-024 | MUST     | Support deprecated features for at least one minor version after deprecation. |
| SDK-025 | SHOULD   | Provide OpenTelemetry integration as composable middleware.                  |
| SDK-026 | SHOULD   | Provide both sync and async APIs in thread-based languages (Java, Ruby).    |
| SDK-027 | SHOULD   | Use builder/functional-options pattern for complex configuration.           |
| SDK-028 | MUST     | Propagate cancellation from caller to in-flight operations.                 |
| SDK-029 | MUST     | Job handlers receive cancellation signal during worker shutdown.            |
| SDK-030 | SHOULD   | Emit metrics as defined in the OJS Observability Specification.             |

---

## 17. Prior Art

This specification draws on the design practices of the following projects:

**Azure SDK Design Guidelines** ([azure.github.io/azure-sdk](https://azure.github.io/azure-sdk/)): The most comprehensive public SDK design guidelines. Azure's principles of idiomatic design, progressive disclosure, and the "pit of success" directly informed Sections 4 and 5 of this document. Azure's per-language design boards and detailed naming conventions inspired the language adaptation table in Section 6.

**AWS SDK Guidelines**: AWS SDKs demonstrate cross-language consistency at massive scale. The three-generation evolution of AWS SDKs -- from auto-generated wrappers to hand-crafted idiomatic libraries -- validates the principle that language idiom matters more than API uniformity. The environment variable conventions in Section 7 follow the `AWS_*` prefix pattern.

**Google API Design Guide** ([cloud.google.com/apis/design](https://cloud.google.com/apis/design)): Google's emphasis on resource-oriented design and standard methods influenced the Admin API method naming. Google's guidance on error model design informed Section 8.

**Stripe API Design**: Stripe's API is widely regarded as a gold standard for developer experience. Stripe's principle of "make the right thing easy and the wrong thing hard" aligns with the pit of success principle. Stripe's consistent cross-language SDK naming directly inspired the canonical name approach in Section 6.

**Temporal SDK Design** ([docs.temporal.io](https://docs.temporal.io/)): Temporal's SDK provides a reference for workflow-oriented job processing SDKs. Temporal's approach to cancellation propagation, activity heartbeating, and deterministic replay informed the async patterns in Section 9 and the middleware API in Section 10.

**Sidekiq** ([sidekiq.org](https://sidekiq.org/)): Sidekiq's middleware chain pattern, testing modes (`fake!`, `inline!`), and convention-over-configuration approach informed Sections 10 and 11.

**Oban** ([getoban.pro](https://getoban.pro/)): Oban's testing ergonomics (`assert_enqueued`, `drain_queue`) are the benchmark for job processing test utilities and directly informed Section 11.

---

*This document is part of the Open Job Spec (OJS) family of specifications. For the complete list of companion specifications, see the [OJS Core Specification](./ojs-core.md).*
