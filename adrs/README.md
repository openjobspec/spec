# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records for Open Job Spec.

ADRs document significant architectural decisions made during the design of OJS, including the context, decision, and consequences. We follow the format proposed by [Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [001](001-three-layer-architecture.md) | Three-Layer Architecture | Accepted |
| [002](002-eight-state-lifecycle.md) | Eight-State Job Lifecycle | Accepted |
| [003](003-args-over-payload.md) | Args (Array) Over Payload (Object) | Accepted |
| [004](004-uuidv7-job-ids.md) | UUIDv7 for Job IDs | Accepted |
| [005](005-backend-interface-design.md) | Backend Interface Design | Accepted |
| [006](006-conformance-level-hierarchy.md) | Conformance Level Hierarchy | Accepted |
| [007](007-client-side-encryption-architecture.md) | Client-Side Encryption Architecture | Accepted |
| [008](008-multi-tenancy-isolation-models.md) | Multi-Tenancy Isolation Models | Accepted |
| [009](009-transactional-enqueue-pattern.md) | Transactional Enqueue Pattern | Accepted |
| [010](010-deduplication-strategy.md) | Deduplication Strategy | Accepted |
| [011](011-opentelemetry-native-observability.md) | OpenTelemetry-Native Observability | Accepted |
| [012](012-control-plane-data-plane-separation.md) | Control Plane / Data Plane Separation | Accepted |

## Creating New ADRs

Use the next available number and follow the template:

```markdown
# ADR-NNN: Title

## Status
Proposed | Accepted | Deprecated | Superseded by ADR-XXX

## Context
What is the issue that we're seeing that is motivating this decision?

## Decision
What is the change that we're proposing and/or doing?

## Consequences
What becomes easier or harder as a result of this decision?
```
