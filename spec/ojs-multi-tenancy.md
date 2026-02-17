# Open Job Spec: Multi-Tenancy and Fairness

> **⚠️ EXPERIMENTAL**: This extension is under active development. The specification
> may change in breaking ways between versions. Implementations and SDKs that adopt
> this extension should expect migration work when the spec evolves. Feedback is
> encouraged via the OJS RFC process.

| Field        | Value                                                    |
|-------------|----------------------------------------------------------|
| **Title**   | OJS Multi-Tenancy Specification                          |
| **Version** | 0.1.0                                                    |
| **Date**    | 2026-02-19                                               |
| **Status**  | Experimental                                             |
| **Maturity** | Experimental                                             |
| **Tier**    | Experimental Extension                                   |
| **URI**     | `urn:ojs:ext:experimental:multi-tenancy`                 |
| **Requires**| OJS Core Specification (Layer 1)                         |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [The Problem](#4-the-problem)
5. [Tenant Identification](#5-tenant-identification)
6. [Isolation Models](#6-isolation-models)
   - 6.1 [Namespace Isolation](#61-namespace-isolation)
   - 6.2 [Shared Queue with Tenant Tags](#62-shared-queue-with-tenant-tags)
   - 6.3 [Hybrid: Sharded Queues](#63-hybrid-sharded-queues)
7. [Fairness and Scheduling](#7-fairness-and-scheduling)
   - 7.1 [Round-Robin Fairness](#71-round-robin-fairness)
   - 7.2 [Weighted Fairness](#72-weighted-fairness)
   - 7.3 [Strict Isolation](#73-strict-isolation)
8. [Per-Tenant Resource Limits](#8-per-tenant-resource-limits)
9. [Noisy Neighbor Mitigation](#9-noisy-neighbor-mitigation)
10. [HTTP Binding](#10-http-binding)
11. [Observability](#11-observability)
12. [Conformance Requirements](#12-conformance-requirements)
13. [Prior Art](#13-prior-art)
14. [Examples](#14-examples)
15. [Resolved Design Decisions](#15-resolved-design-decisions)

---

## 1. Introduction

Multi-tenancy becomes a critical requirement for any SaaS product using a background job system. When multiple customers (tenants) share the same job processing infrastructure, three problems emerge immediately: **isolation** (one tenant's jobs must not interfere with another's), **fairness** (no tenant should starve others of processing capacity), and **observability** (operators need per-tenant metrics and controls).

Every mature job processing system eventually adds multi-tenancy features. Temporal provides namespace-level isolation as a first-class primitive. Sidekiq 7 introduced Capsules for isolated concurrency pools. BullMQ Pro's Groups feature implements virtual queues with round-robin processing. THRON's sharded queue pattern uses per-tenant shards with round-robin consumers. The convergence is clear, but the implementations vary dramatically.

This specification defines a tenant-aware job processing model that supports multiple isolation strategies, fairness guarantees, and per-tenant resource limits. As an experimental extension, the design space is intentionally broad to invite community feedback on which patterns should be standardized.

### 1.1 Scope

This specification defines:

- Tenant identification in job envelopes.
- Three isolation models (namespace, shared, hybrid).
- Fairness scheduling algorithms (round-robin, weighted, strict).
- Per-tenant resource limits (concurrency, rate, queue depth).
- Noisy neighbor detection and mitigation.
- Per-tenant observability.

This specification does **not** define:

- Tenant authentication or authorization (deployment concern).
- Billing or usage metering (application concern).
- Data encryption at rest per tenant (see potential future ojs-encryption spec).

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term                | Definition                                                                                       |
|---------------------|--------------------------------------------------------------------------------------------------|
| tenant              | An isolated unit of work ownership, typically a customer, organization, or workspace.            |
| tenant ID           | A unique string identifier for a tenant.                                                         |
| namespace           | A fully isolated partition with its own queues, workers, and resource limits.                    |
| noisy neighbor      | A tenant whose workload disproportionately consumes shared resources, degrading others.          |
| fairness            | The guarantee that each tenant receives a reasonable share of processing capacity.                |
| starvation          | The condition where a tenant's jobs cannot be processed because other tenants consume all capacity.|
| sharded queue       | A logical queue backed by per-tenant physical sub-queues.                                        |

---

## 4. The Problem

Consider a SaaS platform where 100 tenants share one OJS deployment. Tenant A suddenly enqueues 100,000 report-generation jobs. Without multi-tenancy controls:

1. **Starvation**: Tenant A's jobs fill all queues and workers. Tenants B through Z experience increased latency or complete starvation.
2. **Resource exhaustion**: Tenant A's jobs consume all database connections, all worker memory, and all downstream API quotas.
3. **Invisible impact**: Without per-tenant metrics, operators cannot identify which tenant is causing the problem.
4. **Blunt remediation**: The only option is to pause the entire queue, affecting all tenants.

Multi-tenancy solves these problems by introducing tenant awareness at every layer: enqueue, dispatch, execution, and observation.

---

## 5. Tenant Identification

### 5.1 Tenant ID in Job Envelope

Jobs are associated with a tenant via the `tenant_id` field in the job's `meta` object:

```json
{
  "type": "report.generate",
  "args": [{ "report_id": "rpt_456" }],
  "meta": {
    "tenant_id": "tenant_acme-corp"
  }
}
```

When multi-tenancy is enabled, implementations MUST require the `tenant_id` field in `meta` for all enqueued jobs. Jobs without a `tenant_id` MUST be rejected with a `422 Unprocessable Entity` response.

**Rationale**: Making tenant ID mandatory (when the extension is enabled) prevents untagged jobs from bypassing tenant controls. An untagged job in a multi-tenant system is a bug that should fail loudly rather than silently consume shared resources.

### 5.2 Tenant ID Format

Tenant IDs MUST be non-empty strings matching the pattern `^[a-zA-Z0-9][a-zA-Z0-9._:-]*$`.

Implementations SHOULD support a configurable tenant ID extraction strategy. Common strategies:

| Strategy          | Description                                                    | Example                     |
|-------------------|----------------------------------------------------------------|-----------------------------|
| `meta.tenant_id`  | Read from the `meta` object (default).                         | `meta.tenant_id: "acme"`    |
| HTTP header       | Extract from a request header.                                  | `X-OJS-Tenant: acme`        |
| API key mapping   | Derive from the API key used for authentication.               | API key → tenant lookup     |

### 5.3 Tenant Header

When a tenant ID is provided via HTTP header, the header SHOULD be `X-OJS-Tenant`:

```http
POST /ojs/v1/jobs HTTP/1.1
X-OJS-Tenant: acme-corp
Content-Type: application/openjobspec+json

{
  "type": "report.generate",
  "args": [{ "report_id": "rpt_456" }]
}
```

The backend MUST inject the tenant ID into `meta.tenant_id` if it is provided via header and not already present in the body. If both are present and conflict, the backend MUST reject the request with `400 Bad Request`.

---

## 6. Isolation Models

This specification defines three isolation models. Implementations MUST support at least one and SHOULD document which model(s) they provide.

### 6.1 Namespace Isolation

**Isolation: Strong. Each tenant gets fully separate queues and resource pools.**

In namespace isolation, each tenant operates in its own namespace with:
- Separate queues (e.g., `acme:default`, `acme:email`).
- Separate worker pools (workers are assigned to specific namespaces).
- Separate resource limits.
- No cross-namespace visibility.

```
Tenant A: acme:default  → acme-workers (pool of 5)
Tenant B: beta:default  → beta-workers (pool of 10)
Tenant C: gamma:default → gamma-workers (pool of 3)
```

**Advantages**: Strongest isolation. One tenant's workload cannot affect another's. Simple to reason about.

**Disadvantages**: Resource inefficiency. If Tenant A's pool is idle while Tenant B's is overloaded, capacity is wasted. Requires provisioning workers per tenant.

**When to use**: Compliance-sensitive workloads, enterprise customers with SLA guarantees, tenants with dramatically different workload profiles.

### 6.2 Shared Queue with Tenant Tags

**Isolation: Weak. All tenants share queues; fairness is enforced at dispatch time.**

In shared-queue isolation, all tenants enqueue into the same queues. The backend uses tenant tags and fairness algorithms to prevent starvation:

```
All tenants → default queue → fairness scheduler → shared workers
```

**Advantages**: Maximum resource utilization. Workers process jobs from any tenant. Simpler operational model.

**Disadvantages**: Weaker isolation. A tenant with huge job volume can still increase latency for others even with fairness algorithms. Harder to provide per-tenant SLAs.

**When to use**: Homogeneous workloads, cost-sensitive deployments, tenants with similar processing needs.

### 6.3 Hybrid: Sharded Queues

**Isolation: Medium. Shared workers consume from per-tenant sub-queues in round-robin.**

Sharded queues combine the resource efficiency of shared workers with the isolation of per-tenant queues:

```
Tenant A → shard:acme:default  ─┐
Tenant B → shard:beta:default  ─┼─→ shared workers (round-robin across shards)
Tenant C → shard:gamma:default ─┘
```

Each logical queue (e.g., `default`) is backed by per-tenant shards. Workers dequeue in round-robin across shards, ensuring each tenant gets a fair share of processing time regardless of queue depth.

**Advantages**: Fair by design. One tenant's burst doesn't block others. Workers are shared for efficiency.

**Disadvantages**: More complex dequeue logic. Slightly higher overhead per FETCH operation.

**When to use**: SaaS platforms with mixed workload sizes, when both fairness and efficiency matter.

This is the RECOMMENDED model for most multi-tenant deployments.

**Rationale**: The sharded queue pattern was validated at scale by THRON and is conceptually similar to BullMQ Pro's Groups and Oban's queue rate limiting. It provides the best balance of fairness, efficiency, and operational simplicity.

---

## 7. Fairness and Scheduling

### 7.1 Round-Robin Fairness

The simplest fairness strategy: the backend cycles through tenants in round-robin order when assigning jobs to workers.

**Algorithm**:
1. Maintain a list of tenants with available jobs.
2. On each FETCH, select the next tenant in round-robin order.
3. Dequeue one job from that tenant's shard/tag.
4. Advance the round-robin pointer.

**Properties**: Every tenant gets equal turns, regardless of queue depth. A tenant with 100,000 jobs gets the same number of turns as a tenant with 10 jobs.

### 7.2 Weighted Fairness

Tenants are assigned weights that determine their share of processing capacity:

```json
{
  "tenants": {
    "acme-corp": { "weight": 10 },
    "beta-inc": { "weight": 5 },
    "gamma-llc": { "weight": 1 }
  }
}
```

In weighted fairness, Tenant A receives 10/(10+5+1) ≈ 62.5% of processing capacity, Tenant B receives ~31.25%, and Tenant C receives ~6.25%.

**Algorithm**: Weighted round-robin or deficit round-robin (DRR). DRR is RECOMMENDED because it handles variable job processing times more fairly.

### 7.3 Strict Isolation

Each tenant has a dedicated concurrency pool. A tenant's jobs can only be processed by workers in their pool. This is equivalent to namespace isolation at the worker level.

```json
{
  "tenants": {
    "acme-corp": { "concurrency": 20 },
    "beta-inc": { "concurrency": 10 },
    "gamma-llc": { "concurrency": 5 }
  }
}
```

---

## 8. Per-Tenant Resource Limits

### 8.1 Tenant Configuration

Each tenant MAY have resource limits configured:

```json
{
  "tenant_id": "acme-corp",
  "limits": {
    "max_concurrency": 20,
    "max_enqueue_rate": {
      "limit": 1000,
      "period": "PT1M"
    },
    "max_queue_depth": 50000,
    "max_scheduled": 10000
  },
  "fairness_weight": 10,
  "priority_boost": 0
}
```

| Field                | Type    | Description                                                          |
|----------------------|---------|----------------------------------------------------------------------|
| `max_concurrency`    | integer | Maximum concurrent active jobs for this tenant across all queues.    |
| `max_enqueue_rate`   | object  | Rate limit on job enqueue operations (prevents burst flooding).      |
| `max_queue_depth`    | integer | Maximum total available + scheduled jobs. Enqueue rejected when full.|
| `max_scheduled`      | integer | Maximum scheduled (future) jobs.                                     |
| `fairness_weight`    | number  | Weight for weighted fairness scheduling. Default: 1.                 |
| `priority_boost`     | integer | Added to job priority for this tenant. Enables premium tier tenants. |

### 8.2 Enqueue Rejection

When a tenant exceeds a limit, the backend MUST reject the enqueue request:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 30

{
  "error": {
    "code": "TENANT_LIMIT_EXCEEDED",
    "message": "Tenant 'acme-corp' has exceeded max_queue_depth (50000)",
    "tenant_id": "acme-corp",
    "limit": "max_queue_depth",
    "current": 50000,
    "maximum": 50000
  }
}
```

**Rationale**: Rejecting at enqueue time (backpressure) is more effective than accepting and dropping later. The producer can implement retry logic, queue locally, or notify the user. This follows the distributed systems principle: "control the producer" is the best backpressure strategy.

---

## 9. Noisy Neighbor Mitigation

### 9.1 Detection

Implementations SHOULD detect noisy neighbors automatically using these signals:

| Signal                        | Threshold (configurable)                    |
|-------------------------------|---------------------------------------------|
| Queue depth ratio             | Tenant's queue > 10x median queue depth     |
| Enqueue rate ratio            | Tenant's rate > 5x average enqueue rate     |
| Active job ratio              | Tenant's active jobs > 50% of total         |
| Error rate                    | Tenant's error rate > 3x average            |

### 9.2 Automatic Throttling

When a noisy neighbor is detected, implementations MAY automatically reduce the tenant's effective weight or concurrency:

```json
{
  "event_type": "tenant.throttled",
  "tenant_id": "acme-corp",
  "reason": "queue_depth_ratio_exceeded",
  "action": "weight_reduced",
  "original_weight": 10,
  "effective_weight": 2,
  "until": "2026-02-13T12:30:00Z"
}
```

Automatic throttling MUST be logged as an event and SHOULD be reversible (time-bounded or manual reset).

### 9.3 Manual Controls

Operators MUST be able to manually adjust tenant limits via the Admin API:

```http
PUT /ojs/v1/admin/tenants/acme-corp/limits
Content-Type: application/json

{
  "max_concurrency": 5,
  "reason": "Incident response: reducing capacity during downstream outage"
}
```

---

## 10. HTTP Binding

### 10.1 Tenant Management

```
GET /ojs/v1/admin/tenants                    # List all tenants with stats
GET /ojs/v1/admin/tenants/{id}               # Get tenant detail
PUT /ojs/v1/admin/tenants/{id}               # Create or update tenant config
PUT /ojs/v1/admin/tenants/{id}/limits        # Update tenant limits
DELETE /ojs/v1/admin/tenants/{id}            # Deregister a tenant
```

### 10.2 Tenant Statistics

```
GET /ojs/v1/admin/tenants/{id}/stats
```

```json
{
  "tenant_id": "acme-corp",
  "jobs": {
    "available": 42,
    "active": 8,
    "scheduled": 15,
    "completed_24h": 5841,
    "failed_24h": 23
  },
  "throughput": {
    "processed_per_minute": 12.5,
    "enqueued_per_minute": 13.1
  },
  "limits": {
    "max_concurrency": { "limit": 20, "current": 8 },
    "max_queue_depth": { "limit": 50000, "current": 57 }
  },
  "fairness": {
    "weight": 10,
    "effective_share": 0.32,
    "actual_share": 0.28
  }
}
```

### 10.3 Per-Tenant Job Listing

```
GET /ojs/v1/admin/tenants/{id}/jobs?state=active&page=1&per_page=20
```

---

## 11. Observability

### 11.1 Events

| Event Type                     | Trigger                                                 |
|--------------------------------|---------------------------------------------------------|
| `tenant.created`               | A new tenant is configured.                             |
| `tenant.limit_exceeded`        | A tenant hits a resource limit.                         |
| `tenant.throttled`             | A tenant is automatically throttled (noisy neighbor).   |
| `tenant.throttle_released`     | Automatic throttle is lifted.                           |

### 11.2 Metrics

All existing OJS metrics SHOULD be extended with a `tenant_id` label when multi-tenancy is enabled:

| Metric Name                            | Labels                            | Description                           |
|----------------------------------------|-----------------------------------|---------------------------------------|
| `ojs.tenant.jobs.active`              | `tenant_id`, `queue`              | Active jobs per tenant.               |
| `ojs.tenant.jobs.enqueued_total`      | `tenant_id`, `queue`              | Total jobs enqueued per tenant.       |
| `ojs.tenant.jobs.processed_total`     | `tenant_id`, `queue`              | Total jobs processed per tenant.      |
| `ojs.tenant.jobs.failed_total`        | `tenant_id`, `queue`              | Total failed jobs per tenant.         |
| `ojs.tenant.fairness.share`           | `tenant_id`                       | Actual processing share (0.0-1.0).   |
| `ojs.tenant.queue.depth`              | `tenant_id`, `queue`              | Queue depth per tenant.               |

---

## 12. Conformance Requirements

An implementation declaring support for the multi-tenancy extension MUST support:

| ID           | Requirement                                                                        |
|--------------|------------------------------------------------------------------------------------|
| MT-001       | Tenant ID extraction from `meta.tenant_id`.                                        |
| MT-002       | At least one isolation model (namespace, shared, or hybrid).                       |
| MT-003       | Per-tenant concurrency limits.                                                     |
| MT-004       | Tenant limit rejection at enqueue time (429 response).                             |
| MT-005       | Tenant listing and stats via Admin API.                                            |
| MT-006       | Per-tenant metrics with `tenant_id` label.                                         |

---

## 13. Prior Art

| System           | Multi-Tenancy Approach                                                                    |
|------------------|-------------------------------------------------------------------------------------------|
| **Temporal**     | Namespace-level isolation as a first-class primitive. Separate resource quotas per namespace. |
| **Sidekiq 7**    | Capsules: isolated concurrency pools per workload type (not per-tenant, but similar pattern). |
| **BullMQ Pro**   | Groups: virtual queues with round-robin processing. Solves noisy neighbor.                |
| **THRON**        | Sharded queue pattern: per-tenant sub-queues, round-robin consumers.                      |
| **Oban Pro**     | Queue rate limiting via Smart Engine. Per-queue concurrency.                               |
| **Kubernetes**   | Namespace + ResourceQuota + LimitRange for per-tenant resource control.                   |

OJS synthesizes these approaches into a unified model where the isolation strategy (namespace, shared, hybrid) is configurable per deployment, and fairness + limits apply regardless of the chosen isolation model.

---

## 14. Examples

### 14.1 SaaS Platform with Sharded Queues

A SaaS platform with three tiers:

```json
// Enterprise tenant (high limits, high weight)
{
  "tenant_id": "enterprise-acme",
  "limits": {
    "max_concurrency": 50,
    "max_queue_depth": 200000,
    "max_enqueue_rate": { "limit": 5000, "period": "PT1M" }
  },
  "fairness_weight": 20
}

// Standard tenant
{
  "tenant_id": "standard-beta",
  "limits": {
    "max_concurrency": 10,
    "max_queue_depth": 50000,
    "max_enqueue_rate": { "limit": 1000, "period": "PT1M" }
  },
  "fairness_weight": 5
}

// Free tier tenant
{
  "tenant_id": "free-gamma",
  "limits": {
    "max_concurrency": 2,
    "max_queue_depth": 1000,
    "max_enqueue_rate": { "limit": 100, "period": "PT1M" }
  },
  "fairness_weight": 1
}
```

### 14.2 Enqueuing a Tenant-Scoped Job

```bash
curl -X POST http://localhost:8080/ojs/v1/jobs \
  -H "Content-Type: application/openjobspec+json" \
  -H "X-OJS-Tenant: enterprise-acme" \
  -d '{
    "type": "report.generate",
    "args": [{ "report_id": "rpt_789" }]
  }'
```

### 14.3 Checking Tenant Health

```bash
# List all tenants with summary stats
curl http://localhost:8080/ojs/v1/admin/tenants

# Check a specific tenant
curl http://localhost:8080/ojs/v1/admin/tenants/enterprise-acme/stats

# Reduce a noisy tenant's capacity during an incident
curl -X PUT http://localhost:8080/ojs/v1/admin/tenants/enterprise-acme/limits \
  -H "Content-Type: application/json" \
  -d '{ "max_concurrency": 5 }'
```

---

## 15. Resolved Design Decisions

The following design decisions were resolved during the experimental phase:

### 15.1 Static vs Dynamic Tenant Configuration

**Question:** Should tenant configuration be static or dynamic?

**Decision:** Both. Backends MUST support static configuration (config file, environment variables) for initial deployment. Backends SHOULD support dynamic configuration via the Admin API for runtime changes. Dynamic configuration MUST NOT require backend restart.

**Rationale:** Static is sufficient for simple deployments; dynamic enables self-service provisioning for SaaS platforms.

### 15.2 Multi-Tenancy and Workflow Interaction

**Question:** How should multi-tenancy interact with workflows?

**Decision:** All jobs within a workflow MUST inherit the parent workflow's `tenant_id`. Cross-tenant workflows are NOT supported. If a workflow step attempts to enqueue a job with a different tenant_id, the backend MUST reject it.

**Rationale:** Cross-tenant workflows create data isolation violations and audit complications. Tenant boundary is a hard security boundary.

### 15.3 Default Tenant

**Question:** Should there be a default tenant for jobs without a tenant_id?

**Decision:** Yes. Backends MUST support a configurable default tenant (default: `"_default"`). Jobs without an explicit tenant_id are assigned to the default tenant. This enables gradual migration to multi-tenancy. The default tenant SHOULD have the same resource limits as any other tenant.

**Rationale:** A default tenant removes the requirement to update all producers simultaneously when enabling multi-tenancy.

### 15.4 Tenant Metrics Cardinality Limits

**Question:** What is the right cardinality limit for tenant metrics?

**Decision:** The spec RECOMMENDS a maximum of 1,000 distinct tenant_id values in per-tenant metrics. Beyond this threshold, implementations SHOULD aggregate into an `"_other"` bucket.

**Rationale:** Prometheus-style metrics systems degrade significantly above ~10K label cardinality. A 1,000-tenant recommendation provides a safe margin.

### 15.5 Soft vs Hard Tenant Quotas

**Question:** Should tenant quotas be soft or hard?

**Decision:** Backends MUST support hard quotas (strict rejection). Backends SHOULD also support soft quotas (allow burst with alerting). Hard quota is the default.

**Rationale:** Hard quotas provide predictable behavior; soft quotas serve operational flexibility.

---

## Appendix A: Changelog

| Date       | Change                          |
|------------|---------------------------------|
| 2026-02-13 | Initial experimental release.   |
