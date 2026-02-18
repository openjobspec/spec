# OJS Serverless Backend Design Considerations

**Open Job Spec v1.0.0-rc.1 — Informational**

| Field       | Value                       |
|-------------|-----------------------------|
| Version     | 0.1.0                       |
| Date        | 2026-02-19                  |
| Status      | Draft                       |
| Layer       | Informational               |
| Related     | ojs-serverless.md, ojs-http-binding.md |

---

## 1. Overview

This document describes design considerations for running an OJS-compliant backend entirely on serverless infrastructure. Unlike the [OJS Serverless Integration Spec](spec/ojs-serverless.md)—which covers *workers* processing jobs on serverless functions—this document covers running the *backend itself* (the control plane that stores jobs, manages state, and serves the OJS HTTP API) on serverless platforms.

### 1.1 Motivation

Traditional OJS backends (Redis, PostgreSQL, Lite) require always-on server processes. A serverless backend eliminates this operational overhead for use cases where:

- Job volume is low-to-moderate (< 10M jobs/month)
- Traffic is bursty or unpredictable
- Zero-ops deployment is preferred over maximum throughput
- Edge deployment is desired (Cloudflare Workers + D1)

### 1.2 Relationship to Other Specifications

- **ojs-core.md**: The serverless backend MUST implement the same job lifecycle and state machine
- **ojs-http-binding.md**: The serverless backend exposes the standard OJS HTTP API
- **ojs-serverless.md**: Complements this spec (that covers serverless workers, this covers serverless backends)

---

## 2. Architecture Patterns

### 2.1 API Gateway + Function + Database

The canonical serverless backend pattern:

```
Client → API Gateway → Function → Database
```

| Component | AWS | Cloudflare | Azure | GCP |
|-----------|-----|------------|-------|-----|
| API Gateway | API Gateway | Workers Routes | API Management | Cloud Endpoints |
| Function | Lambda | Workers | Functions | Cloud Functions |
| Database | DynamoDB | D1 (SQLite) | Cosmos DB | Firestore |

### 2.2 Stateless Function Design

Each function invocation MUST be stateless. All job state MUST be persisted to the backing database before returning a response. This is a fundamental constraint of serverless architectures:

```
Request → Parse → Validate → Database Write → Response
```

No in-memory state survives between invocations. This rules out:
- In-memory job queues (use database queries instead)
- Connection pools (use per-invocation connections or platform-managed pools)
- Background goroutines/timers (use external schedulers)

### 2.3 Edge Deployment (Cloudflare Workers + D1)

Cloudflare Workers with D1 is uniquely suited for OJS because D1 is SQLite-based, which aligns with ojs-backend-lite's storage model:

```
ojs-backend-lite (SQLite)  →  Cloudflare Worker + D1 (SQLite at edge)
```

Benefits:
- Sub-millisecond cold starts (V8 isolates, not containers)
- SQLite query compatibility with ojs-backend-lite
- 300+ edge locations for global low-latency access
- Automatic read replication

---

## 3. State Management Options

### 3.1 DynamoDB (AWS)

**Best for**: High-throughput, single-region deployments on AWS

| Aspect | Details |
|--------|---------|
| Consistency | Strong consistency per partition |
| Query model | Key-value with GSI for fetch queries |
| Scaling | Automatic, pay-per-request |
| Latency | 5-10ms per operation |
| Cost model | Per-request + storage |

**Schema design**: Use composite sort keys on GSI for efficient fetch:
- PK: `job_id`
- GSI1: `queue#state` → `priority#created_at`

**Fetch query**: Jobs are fetched via a GSI query on `queue#available`, sorted by priority and creation time. Conditional updates ensure atomic state transitions to prevent double-delivery.

### 3.2 D1 / SQLite (Cloudflare)

**Best for**: Edge deployment, SQLite-compatible query patterns

| Aspect | Details |
|--------|---------|
| Consistency | Strong per-location, eventually-consistent replicas |
| Query model | Full SQL (SQLite) |
| Scaling | Automatic read replicas |
| Latency | 1-5ms per query |
| Cost model | Per-row-read + per-row-write |

**Advantage**: Schema and queries are nearly identical to ojs-backend-lite's SQLite storage, minimizing adaptation effort.

### 3.3 Turso (LibSQL)

**Best for**: Multi-region SQLite with embedded replicas

| Aspect | Details |
|--------|---------|
| Consistency | Strong at primary, eventual at replicas |
| Query model | Full SQL (SQLite-compatible) |
| Scaling | Manual region selection |
| Latency | <1ms local reads, cross-region for writes |
| Cost model | Per-row-read + per-row-write |

### 3.4 PlanetScale (MySQL)

**Best for**: Teams with MySQL expertise, high-write workloads

| Aspect | Details |
|--------|---------|
| Consistency | Strong consistency |
| Query model | Full SQL (MySQL-compatible, no foreign keys) |
| Scaling | Horizontal via Vitess sharding |
| Latency | 5-15ms per query |
| Cost model | Per-row-read + per-row-write |

---

## 4. Cold Start Mitigation

Cold starts are the primary performance concern for serverless backends.

### 4.1 Measured Cold Start Times

| Platform | Runtime | Cold Start | Warm Invocation |
|----------|---------|------------|-----------------|
| **Cloudflare Workers** | V8 isolate | < 5ms | < 1ms |
| **AWS Lambda** | Go (ARM64) | ~200ms | ~5ms |
| **AWS Lambda** | Node.js 20 | ~300ms | ~10ms |
| **AWS Lambda** | Python 3.12 | ~400ms | ~15ms |
| **AWS Lambda** | Java 21 (SnapStart) | ~200ms | ~5ms |
| **Azure Functions** | Node.js | ~500ms | ~10ms |
| **GCP Cloud Functions** | Go | ~300ms | ~5ms |

### 4.2 Mitigation Strategies

1. **Choose low-cold-start runtimes**: Go on ARM64 or Cloudflare Workers (V8 isolates)

2. **Provisioned concurrency** (AWS Lambda): Pre-warm N instances. Eliminates cold starts but adds fixed cost:
   ```yaml
   ProvisionedConcurrencyConfig:
     ProvisionedConcurrentExecutions: 5
   ```

3. **Warm-up pings**: Schedule periodic health check invocations via EventBridge/Cron Triggers:
   ```yaml
   Events:
     WarmUp:
       Type: Schedule
       Properties:
         Schedule: rate(5 minutes)
   ```

4. **Minimize initialization**: Defer database connection to first actual request, not module load time

5. **Binary size optimization** (Go): Use `-ldflags="-s -w"` and `CGO_ENABLED=0` to reduce binary size, which directly impacts cold start time

---

## 5. Scaling Characteristics

### 5.1 Concurrency Model

Serverless backends scale by concurrent function instances, not threads:

| Platform | Default Concurrent | Max Concurrent | Scaling Speed |
|----------|-------------------|----------------|---------------|
| AWS Lambda | 1,000 | 10,000 (requestable) | ~500/min burst |
| Cloudflare Workers | Unlimited | Unlimited | Instant |
| Azure Functions | 200 | 200 (per plan) | ~1/sec |
| GCP Cloud Functions | 1,000 | 3,000 (requestable) | Instant |

### 5.2 Database as Bottleneck

The serverless functions scale horizontally, but the database becomes the bottleneck:

- **DynamoDB**: Scales automatically; well-suited for serverless
- **D1**: Scales reads automatically; writes are serialized per database
- **Traditional SQL** (PlanetScale, Aurora Serverless): Connection limits become the bottleneck

**Recommendation**: Use DynamoDB or D1 for serverless backends. Avoid connection-pooled databases unless using a proxy (e.g., RDS Proxy, PgBouncer).

### 5.3 Fetch Operation Contention

The `POST /workers/fetch` endpoint requires atomic "claim" operations (read available job → transition to active). Under high concurrency, this creates contention:

- **DynamoDB**: Use conditional updates (`ConditionExpression`); retries on `ConditionalCheckFailedException`
- **D1**: Use `UPDATE ... WHERE state = 'available'` with row-level locking; check `changes` count
- **General**: Keep fetch batch sizes small (1-5) to reduce contention window

---

## 6. Cost Comparison

### 6.1 Monthly Cost at Various Volumes

*Assumptions: 128MB memory, 100ms avg duration, us-east-1 pricing*

| Volume | Lambda + DynamoDB | CF Workers + D1 | EC2 + Redis | EC2 + PostgreSQL |
|--------|-------------------|------------------|-------------|------------------|
| **10K jobs** | ~$0.07 | ~$0.00 (free tier) | ~$15 | ~$15 |
| **100K jobs** | ~$0.62 | ~$0.15 | ~$15 | ~$15 |
| **1M jobs** | ~$6.20 | ~$1.51 | ~$15 | ~$15 |
| **10M jobs** | ~$62.00 | ~$15.10 | ~$30 | ~$30 |
| **100M jobs** | ~$620.00 | ~$151.00 | ~$60 | ~$60 |

### 6.2 Break-Even Analysis

Serverless is more cost-effective than a traditional deployment when:
- **Lambda + DynamoDB**: Below ~15M jobs/month (vs. t3.small + ElastiCache)
- **CF Workers + D1**: Below ~50M jobs/month (vs. t3.small + Redis)

Above these thresholds, the per-invocation cost of serverless exceeds the fixed cost of a small server.

---

## 7. Limitations

### 7.1 Hard Limits

| Limitation | AWS Lambda | Cloudflare Workers |
|-----------|-----------|-------------------|
| Max execution time | 15 min (29s via API GW) | 30s (15min Unbound) |
| Max payload size | 6MB (sync), 256KB (async) | 100MB |
| Max concurrent | 10,000 | Unlimited |
| WebSocket/SSE | Not supported | Durable Objects only |
| Background processing | Not supported | Not supported |

### 7.2 Features Not Supported

The following OJS features cannot be implemented in a purely serverless backend:

1. **Real-time events (SSE/WebSocket)**: Requires long-lived connections. Use polling or external services (e.g., Pusher, Ably).

2. **Built-in cron scheduler**: No background process to tick. Use platform-native cron:
   - AWS: EventBridge Scheduled Rules → Lambda
   - Cloudflare: Cron Triggers → Worker

3. **Heartbeat-based stall detection**: No background scanner. Options:
   - Trigger stall check on every fetch request
   - Use platform cron to periodically scan for stalled jobs

4. **Connection-based worker tracking**: Workers are ephemeral; no persistent connection. Track via heartbeat timestamps with TTL.

### 7.3 Eventual Consistency Caveats

Some serverless databases (D1 replicas, DynamoDB global tables) provide eventual consistency for reads. This means:

- A job enqueued in one region MAY not be immediately visible in another
- Fetch operations SHOULD use strong consistency reads where available
- For DynamoDB, use `ConsistentRead: true` for fetch queries

---

## 8. Implementation Checklist

A serverless OJS backend MUST:

- [ ] Implement the OJS HTTP binding (`/ojs/v1/jobs`, `/ojs/v1/workers/*`)
- [ ] Persist all state to the backing database before responding
- [ ] Use atomic operations for job state transitions (no double-delivery)
- [ ] Return standard OJS error responses with proper error codes
- [ ] Include `X-OJS-Version` and `X-OJS-Media-Type` response headers
- [ ] Support the 8-state job lifecycle

A serverless OJS backend SHOULD:

- [ ] Implement health check endpoint (`/ojs/v1/health`)
- [ ] Support API key authentication
- [ ] Use conditional writes to prevent race conditions on fetch
- [ ] Set TTL on completed/discarded jobs for automatic cleanup
- [ ] Log structured JSON for observability

A serverless OJS backend MAY:

- [ ] Implement queue management endpoints
- [ ] Implement dead letter endpoints
- [ ] Implement workflow endpoints
- [ ] Support batch enqueue
- [ ] Implement cron via platform-native schedulers
