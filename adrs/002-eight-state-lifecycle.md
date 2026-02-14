# ADR-002: Eight-State Job Lifecycle

## Status

Accepted

## Context

Most job processing systems use a simplified lifecycle with 3-5 states (e.g., pending → active → completed/failed). In production, this leads to ambiguous states:

- **Is a "pending" job waiting to be picked up, or scheduled for the future?** Systems like Sidekiq overload "scheduled" and "enqueued" into the same state, requiring workarounds to distinguish delay-scheduled jobs from immediately available ones.
- **What happens when a job fails but can be retried?** Most systems use "failed" for both terminal failure and retriable failure, requiring out-of-band retry state (retry sets, retry counts on the job).
- **How do you distinguish "cancelled by user" from "discarded by system"?** Most systems don't — both are "dead" jobs with different semantics.
- **What about jobs that are fetched but not yet being processed?** The gap between dequeue and handler execution is invisible in most systems.

We studied the lifecycles of Sidekiq, BullMQ, River (Go), Oban (Elixir), Celery, and Faktory. Each has ad-hoc extensions to their base states that would benefit from standardization.

## Decision

We define 8 explicit states with clear, non-overlapping semantics:

| State | Meaning |
|-------|---------|
| `scheduled` | Job exists but is not yet eligible for processing (future `scheduled_at` time) |
| `available` | Job is eligible for processing and waiting in a queue |
| `pending` | Job has been fetched by a worker but execution has not started |
| `active` | Job handler is currently executing |
| `completed` | Job finished successfully (terminal) |
| `retryable` | Job failed but will be retried (transitions back to `available` or `scheduled`) |
| `cancelled` | Job was explicitly cancelled by a user or system action (terminal) |
| `discarded` | Job exhausted all retries or was programmatically discarded (terminal) |

Valid state transitions are explicitly enumerated in the core spec. Invalid transitions MUST be rejected by the backend.

## Consequences

### Easier
- **Observability**: Each state is unambiguous — dashboards and metrics can precisely show job distribution across states
- **Retry semantics**: `retryable` is a first-class state, eliminating the need for side-channel retry tracking
- **Cancellation vs discard**: Operators can distinguish "I cancelled this" from "the system gave up on this"
- **Pending state**: Enables visibility into the fetch-to-execute gap, critical for debugging slow workers
- **State machine validation**: Backends can enforce valid transitions, catching bugs in SDK implementations

### Harder
- **Implementation burden**: Backend authors must implement all 8 states and validate all transitions, even if their underlying store (e.g., SQS) doesn't natively support all states
- **Migration**: Systems adopting OJS must map their existing states to the 8-state model, which may require data migration
- **Worker complexity**: SDKs must correctly manage `pending` → `active` transitions, adding a step that simpler systems skip
