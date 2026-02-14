# ADR-005: Backend Interface Design

## Status

Accepted

## Context

OJS defines a set of logical operations (PUSH, FETCH, ACK, FAIL, BEAT, CANCEL, INFO) that any backend must implement. The question is how to structure the backend interface that SDKs and protocol bindings program against.

Two approaches emerged during development:

### Option A: Monolithic Interface
A single `Backend` interface with all methods:
```go
type Backend interface {
    Push(ctx context.Context, job *Job) (*Job, error)
    Fetch(ctx context.Context, queues []string) (*Job, error)
    Ack(ctx context.Context, id string) error
    // ... 20+ methods
}
```

**Pros**: Simple to implement, single type to pass around, easy to mock in tests.
**Cons**: Every backend must implement every method (even if the underlying store doesn't support certain operations), violates Interface Segregation Principle.

### Option B: Role-Based Composition
Multiple focused interfaces composed together:
```go
type JobManager interface { Push(...); Fetch(...); Ack(...); Fail(...) }
type QueueManager interface { ListQueues(...); PauseQueue(...) }
type WorkflowManager interface { CreateWorkflow(...); GetWorkflow(...) }
type Backend interface { JobManager; QueueManager; WorkflowManager; ... }
```

**Pros**: Backends can implement subsets, better testability, clear capability boundaries.
**Cons**: More types to manage, composition complexity, harder for beginners.

## Decision

OJS recommends **Option A (monolithic interface) for reference implementations** and **Option B (role-based composition) for production implementations**.

The core spec defines logical operations grouped by concern but does not mandate a specific interface decomposition. The conformance test suite tests against protocol bindings (HTTP/gRPC endpoints), not against language-level interfaces.

In practice:
- The **Redis backend** uses a monolithic `Backend` interface — appropriate for its simpler operational model where Redis natively supports all operations
- The **PostgreSQL backend** uses role-based composition (`JobManager`, `WorkerManager`, `QueueManager`, `DeadLetterManager`, `CronManager`, `WorkflowManager`, `Subscriber`) — appropriate for its richer feature set including event streaming and auth

SDK authors should choose the approach that best fits their language idioms and backend capabilities.

## Consequences

### Easier
- **Flexibility**: Backend authors can choose the interface style that matches their architecture
- **Conformance testing**: Tests are protocol-level, so interface design is an implementation detail
- **Progressive implementation**: With role-based composition, backends can implement core operations first and add advanced features incrementally

### Harder
- **Inconsistency between backends**: Different interface styles may confuse contributors working across backends
- **SDK abstraction**: SDKs that want to support multiple backends must program against the full operation set regardless of interface style
- **Documentation**: Must explain both patterns and when each is appropriate
