# ADR-015: AWS SQS + DynamoDB Backend Architecture

## Status

Accepted

## Context

AWS SQS is a managed message queue service that provides native visibility timeouts, dead letter queues, and at-least-once delivery. However, SQS lacks job state tracking, priority ordering, scheduled delivery beyond 15 minutes, workflow orchestration, and rich query capabilities. OJS requires all of these for full conformance.

The question was how to complement SQS to achieve full OJS semantics on a serverless-native AWS stack.

### Options Considered

1. **SQS + DynamoDB**: SQS for message transport, DynamoDB for job state. Both are serverless, pay-per-use, and require no infrastructure management.
2. **SQS + Redis (ElastiCache)**: SQS for transport, Redis for state. Lower latency but requires provisioned infrastructure.
3. **SQS + RDS PostgreSQL**: SQS for transport, PostgreSQL for state. Richest query capabilities but highest operational overhead.

## Decision

Use **SQS + DynamoDB hybrid architecture** (Option 1) for a fully serverless deployment.

### Transport Layer (SQS)

- One SQS queue per OJS queue
- Job enqueue sends to the SQS queue with message attributes for job metadata
- Job fetch uses `ReceiveMessage` with `WaitTimeSeconds` for long polling
- Visibility timeout uses SQS's native `VisibilityTimeout` (extended via `ChangeMessageVisibility` on heartbeat)
- Dead letter queues use SQS's native DLQ redrive policy for additional safety

### State Layer (DynamoDB)

- Jobs table: primary key = job ID, GSIs for queue+state queries and scheduled job lookups
- Workflow table: tracks DAG state, step completion, fan-out/fan-in counters
- Cron table: stores cron definitions with next-run timestamps
- Unique jobs table: conditional puts for deduplication with TTL-based expiration
- Single-table design where appropriate to minimize table count

### Scheduling

- Jobs with delay ≤ 15 minutes use SQS's native `DelaySeconds`
- Jobs with delay > 15 minutes are stored in DynamoDB with a `run_at` attribute; a scheduler goroutine polls and enqueues when due
- Cron jobs managed in DynamoDB with a scheduler that creates SQS messages at cron intervals

### Priority

- Separate SQS queues per priority tier (high, default, low)
- Fetch logic drains higher-priority queues before lower ones

### Infrastructure as Code

- Terraform configuration provided for provisioning SQS queues, DynamoDB tables, and IAM roles
- LocalStack support via Docker Compose for local development

## Consequences

**Positive:**
- Full Level 0–4 conformance achieved (partial Level 2 for delays > 15 minutes due to SQS limitation)
- Fully serverless: zero infrastructure provisioning, pay-per-use pricing
- SQS visibility timeout and DLQ are native, reducing custom implementation
- DynamoDB scales horizontally with no capacity planning
- Terraform configuration enables reproducible deployments

**Negative:**
- SQS maximum delay is 15 minutes; longer delays require DynamoDB + scheduler workaround
- DynamoDB query patterns are limited by GSI design; ad-hoc queries require scan operations
- SQS does not guarantee FIFO ordering (standard queues); FIFO queues limit throughput to 300 msg/s per group
- Two AWS services increase cost surface and require IAM coordination

**Trade-offs:**
- Chose DynamoDB over Redis for fully serverless deployment (no ElastiCache provisioning)
- Chose standard SQS queues over FIFO for throughput (OJS does not require strict ordering within a queue)
- Chose separate queues per priority over message attributes to enable per-priority polling with SQS's native API
