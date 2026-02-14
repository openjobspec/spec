# ADR-006: Conformance Level Hierarchy

## Status

Accepted

## Context

OJS has a large specification surface area: core lifecycle, retries, scheduling, workflows, unique jobs, rate limiting, dead letter management, and more. Not all backends need to (or can) implement everything.

For example:
- **Amazon SQS** has native visibility timeouts but no built-in cron scheduling
- **Redis** can implement everything but requires Lua scripts for atomicity
- **A simple in-memory backend** might only support basic enqueue/dequeue for testing

We needed a way to:
1. Allow backends to claim a clear level of spec compliance
2. Give users confidence about what operations a backend supports
3. Enable incremental implementation — start with basics, add features over time
4. Structure the conformance test suite for progressive validation

We evaluated approaches from other standards:
- **SQL compliance levels** (SQL-92 Entry/Intermediate/Full) — too few levels, large gaps between them
- **OpenGL versions** — linear progression that requires complete previous levels
- **Web platform features** — feature-flag based, no levels (too granular for a spec)
- **CloudEvents** — no formal conformance levels (missed opportunity)

## Decision

OJS defines **5 conformance levels (0–4)**, each a strict superset of the previous:

| Level | Name | Scope |
|-------|------|-------|
| **Level 0** | Core | Job envelope validation, 8-state lifecycle, basic operations (PUSH/FETCH/ACK/FAIL/CANCEL/INFO) |
| **Level 1** | Reliable | Retry policies, dead-letter queues, heartbeat/BEAT, visibility timeout |
| **Level 2** | Scheduled | Delayed jobs (`scheduled_at`), cron scheduling, TTL/expiration |
| **Level 3** | Orchestration | Workflow primitives: chain (sequential), group (parallel fan-out/fan-in), batch (completion callbacks) |
| **Level 4** | Advanced | Priority queues, job deduplication (unique jobs), batch enqueue, queue management operations |

Each level has a corresponding directory of JSON test case files in `ojs-conformance/suites/level-N-*/`. The test runner (`runner/http/`) executes HTTP-based scenarios with assertions on status codes, response fields, and timing.

A backend claiming "OJS Level 2 Conformant" MUST pass all Level 0, 1, and 2 tests.

## Consequences

### Easier
- **Clear communication**: "This backend is Level 2 conformant" immediately tells users what features are available
- **Incremental adoption**: New backends can target Level 0 first and progressively implement higher levels
- **Test organization**: Each level maps to a directory of test cases, making it obvious what to test
- **Competitive differentiation**: Backend comparison tables can use levels as a standardized metric
- **SDK compatibility**: SDKs can declare minimum backend level requirements for features (e.g., workflows require Level 3+)

### Harder
- **Level boundaries are opinionated**: Deciding which features belong in which level requires judgment calls — some users may want Level 2 features but not Level 1
- **Partial level support**: A backend that passes 95% of Level 2 tests must still claim only Level 1 compliance
- **Test maintenance**: Each new spec feature must be assigned to a level, and test cases must be written before the feature is considered standardized
- **Level inflation**: Pressure to add more levels as features grow (mitigated by keeping 5 levels and using extensions for truly optional features)
