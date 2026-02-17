# Open Job Spec: Multi-Region Federation

| Field       | Value                     |
|-------------|---------------------------|
| Version     | 1.0.0-rc.1                |
| Date        | 2026-02-19                |
| Status      | Release Candidate         |
| Maturity    | Beta                      |
| Layer       | 1 -- Core                 |
| Spec URI    | `urn:ojs:spec:federation` |

---

## 1. Overview

This document defines multi-region federation for Open Job Spec (OJS). Federation enables multiple independent OJS deployments -- each operating in a distinct geographic region -- to cooperate as a unified logical system. Jobs can be routed to specific regions based on affinity rules, overflow capacity, or geo-pinning constraints. Regions replicate job metadata for observability and failover.

Federation is designed as a client-side concern. A federation-aware client wraps one or more standard OJS clients, each pointing at a region-local OJS server. This composable design means federation requires **no changes to OJS backends** -- any conforming OJS server can participate in a federated topology.

### 1.1 Design Principles

1. **Client-side composition.** Federation is implemented as a routing layer above standard OJS clients. Backend servers are unaware of federation; they process jobs normally. This avoids coupling the specification to a specific replication protocol or consensus algorithm.

2. **Explicit routing over implicit magic.** Every job is routed by an explicit strategy -- affinity, overflow, or geo-pin. There is no hidden load balancer. The producer controls where a job lands.

3. **Eventual consistency is sufficient.** Cross-region replication of job metadata uses an eventual consistency model. Strong consistency across regions would require distributed transactions, which are impractical for background job systems that already tolerate at-least-once semantics.

4. **Graceful degradation.** When a region becomes unhealthy, the federation layer MUST route jobs to healthy regions rather than failing requests. Circuit breakers prevent cascading failures.

### 1.2 Terminology

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt).

| Term              | Definition                                                                                      |
|-------------------|-------------------------------------------------------------------------------------------------|
| region            | An independent OJS deployment identified by a unique string (e.g., `us-east-1`, `eu-west-1`).  |
| local region      | The region to which the current client has the lowest latency or strongest affinity.             |
| federation        | A set of regions that cooperate to process jobs, sharing routing metadata.                      |
| routing strategy  | An algorithm that selects a target region for a given job.                                      |
| affinity          | A preference for routing jobs to the local region when capacity is available.                   |
| overflow          | Routing jobs to alternate regions when the preferred region is at capacity or unhealthy.        |
| geo-pin           | A hard constraint requiring a job to execute in a specific region.                              |
| circuit breaker   | A pattern that temporarily marks a region as unavailable after consecutive failures.            |
| federation ID     | A UUIDv7 identifier assigned to a federated job for cross-region tracking.                     |

---

## 2. Federation Topology

A federation consists of two or more regions. OJS supports three topology models. Implementations MAY support any combination.

### 2.1 Hub-Spoke

A single hub region acts as the coordination point. Spoke regions forward routing decisions through the hub. This topology is simplest to operate but introduces a single point of failure at the hub.

**Rationale:** Hub-spoke is appropriate when one region is the primary datacenter and others are satellite deployments. The hub handles all cross-region coordination.

An implementation using hub-spoke MUST designate exactly one region as the hub. If the hub becomes unavailable, spoke regions MUST continue processing locally-enqueued jobs but SHOULD NOT attempt cross-region routing until the hub recovers.

### 2.2 Mesh

Every region communicates directly with every other region. There is no central coordinator. This topology provides the highest availability but requires O(n²) connections.

**Rationale:** Mesh is appropriate for deployments with a small number of regions (2–5) where each region must independently route to any other.

An implementation using mesh topology MUST maintain health state for every peer region. Each region SHOULD independently evaluate routing decisions without requiring consensus.

### 2.3 Active-Active

All regions accept writes and process jobs independently. Cross-region replication ensures that job metadata is eventually visible in all regions. Conflict resolution uses last-writer-wins semantics (Section 5.2).

**Rationale:** Active-active is the most resilient topology. It eliminates single points of failure and allows every region to operate autonomously during network partitions.

An implementation using active-active topology MUST assign a `federation_id` (Section 6) to every federated job. This ID is used for cross-region deduplication and conflict resolution.

---

## 3. Job Routing Rules

When a federated client enqueues a job, it MUST select a target region using one of the following routing strategies. The strategy is determined by the `region_affinity` attribute (Section 6) or by the client's default configuration.

### 3.1 Affinity Routing (prefer local)

The job is routed to the local region if the region is healthy and has available capacity. If the local region is unavailable, the client falls back to the next-closest healthy region.

**Rationale:** Affinity routing minimizes cross-region latency and network costs. It is the correct default for most workloads.

An implementation MUST check the health of the local region before routing. If the local region's circuit breaker is open, the implementation MUST select an alternate region using the configured fallback order.

### 3.2 Overflow Routing (least-loaded)

The job is routed to the region with the lowest current load, measured by available queue depth or active job count. This strategy balances work across regions.

**Rationale:** Overflow routing is appropriate for batch workloads where throughput matters more than data locality.

An implementation MUST periodically collect load metrics from all healthy regions. The collection interval SHOULD be configurable and SHOULD default to 10 seconds. An implementation MUST NOT route to a region whose circuit breaker is open.

### 3.3 Geo-Pin Routing (require specific region)

The job MUST execute in the region specified by the `region` attribute. If that region is unavailable, the job MUST NOT be routed elsewhere; instead, the enqueue operation MUST return an error.

**Rationale:** Geo-pinning is required for workloads with data residency requirements (e.g., GDPR) where a job must execute in a specific jurisdiction.

An implementation MUST validate that the target region exists in the federation registry. If the region is not registered, the implementation MUST return an error. If the region is registered but unhealthy, the implementation MUST return an error indicating the region is temporarily unavailable.

---

## 4. Region Discovery and Health

### 4.1 Region Registry

A federation maintains a registry of participating regions. Each entry contains:

| Field    | Type     | Required | Description                                                    |
|----------|----------|----------|----------------------------------------------------------------|
| `id`     | string   | Yes      | Unique region identifier (e.g., `us-east-1`).                 |
| `url`    | string   | Yes      | Base URL of the OJS server in this region.                     |
| `weight` | integer  | No       | Routing weight for weighted load balancing. Default: `1`.      |
| `tags`   | string[] | No       | Arbitrary tags for filtering (e.g., `["gpu", "high-memory"]`). |

An implementation MUST support static registry configuration at client initialization. An implementation MAY additionally support dynamic registry updates via a discovery service.

### 4.2 Health Checking

Each region MUST be monitored for availability. An implementation MUST call the standard OJS health endpoint (`GET /ojs/v1/health`) at a configurable interval to determine region status.

A region is considered healthy when its health endpoint returns HTTP 200 with `"status": "ok"`. A region is considered unhealthy when:

- The health check fails (network error, timeout, or non-200 response).
- The health endpoint returns `"status"` other than `"ok"`.

**Rationale:** Using the existing OJS health endpoint avoids introducing federation-specific health infrastructure.

### 4.3 Circuit Breaker

An implementation MUST implement a circuit breaker per region to prevent cascading failures. The circuit breaker has three states:

| State      | Behavior                                                                         |
|------------|----------------------------------------------------------------------------------|
| `closed`   | Requests flow normally. Failures are counted.                                    |
| `open`     | All requests to this region are rejected immediately. No health checks are sent. |
| `half-open`| A single probe request is sent. Success closes the breaker; failure re-opens it. |

The circuit breaker MUST open after a configurable number of consecutive failures (default: 5). The circuit breaker MUST transition from `open` to `half-open` after a configurable cooldown period (default: 30 seconds).

**Rationale:** Circuit breakers prevent a failing region from consuming client resources and adding latency to every request.

### 4.4 Latency-Based Routing

When multiple regions are healthy and the routing strategy permits fallback, an implementation SHOULD prefer the region with the lowest observed latency. Latency SHOULD be measured from health check round-trip times.

An implementation MAY use exponentially weighted moving averages to smooth latency measurements.

---

## 5. Replication

### 5.1 Eventual Consistency Model

Federation uses an eventual consistency model for cross-region job metadata. When a job is enqueued in one region, its metadata (ID, type, state, timestamps) MAY be replicated to other regions for observability and failover.

Replication is OPTIONAL. An implementation that supports replication MUST annotate replicated jobs with the `replicated_from` attribute (Section 6) to distinguish them from locally-enqueued jobs.

**Rationale:** Eventual consistency is the only practical model for geographically distributed background job systems. Requiring strong consistency would make cross-region enqueue latencies unacceptable.

### 5.2 Conflict Resolution

When the same `federation_id` appears in multiple regions (due to replication or re-routing), conflicts MUST be resolved using **last-writer-wins** semantics. The `enqueued_at` timestamp (RFC 3339, UTC) serves as the ordering key.

**Rationale:** Last-writer-wins is simple, deterministic, and well-suited to background job metadata where the latest state is almost always the correct state. More complex conflict resolution (CRDTs, vector clocks) is unnecessary for job envelopes.

An implementation MUST compare timestamps at millisecond precision. If two writes have identical timestamps, the implementation MUST use the `federation_id` as a tiebreaker (lexicographic comparison).

---

## 6. Wire Format Extensions

Federation adds the following OPTIONAL attributes to the OJS job envelope. These attributes are carried in the `meta` object to maintain backward compatibility with non-federated OJS servers.

### 6.1 Attribute Definitions

| Attribute         | Type   | Description                                                              |
|-------------------|--------|--------------------------------------------------------------------------|
| `region`          | string | The region where this job MUST execute (geo-pin). Omit for flexible routing. |
| `region_affinity` | string | The preferred routing strategy: `"affinity"`, `"overflow"`, or `"geo-pin"`. Default: `"affinity"`. |
| `replicated_from` | string | The region ID from which this job was replicated. Absent on origin jobs.  |
| `federation_id`   | string | A UUIDv7 identifier for cross-region tracking and deduplication.         |

### 6.2 Encoding

Federation attributes are encoded in the job's `meta` object with the `ojs.federation.` prefix:

```json
{
  "type": "email.send",
  "args": [{"to": "user@example.com"}],
  "meta": {
    "ojs.federation.federation_id": "01912e4a-7b3c-7def-8a12-abcdef123456",
    "ojs.federation.region": "eu-west-1",
    "ojs.federation.region_affinity": "geo-pin",
    "ojs.federation.replicated_from": "us-east-1"
  }
}
```

**Rationale:** Using the `meta` object with a namespaced prefix ensures that federation attributes are ignored by non-federated OJS servers. This preserves full backward compatibility -- a federated client can enqueue jobs to a non-federated server without errors.

### 6.3 Attribute Semantics

#### `federation_id` (string, UUIDv7)

A globally unique identifier assigned by the federated client at enqueue time. This ID is stable across regions -- if a job is replicated from `us-east-1` to `eu-west-1`, both copies share the same `federation_id`.

An implementation MUST generate `federation_id` using UUIDv7 format. The timestamp component of the UUIDv7 MUST reflect the time of enqueue.

#### `region` (string)

When set, the job MUST execute in the specified region. The routing strategy MUST be `"geo-pin"` when this attribute is present. If `region` is set but `region_affinity` is not `"geo-pin"`, the implementation MUST treat the routing strategy as `"geo-pin"` regardless of the `region_affinity` value.

#### `region_affinity` (string)

Specifies the routing strategy for this job. Valid values are `"affinity"`, `"overflow"`, and `"geo-pin"`. When omitted, the implementation MUST use `"affinity"` as the default.

#### `replicated_from` (string)

Set by the replication layer to indicate the origin region. An implementation MUST NOT set this attribute on jobs enqueued directly by a client. This attribute is used to prevent infinite replication loops -- a job with `replicated_from` set MUST NOT be replicated again.

---

## 7. Security Considerations

### 7.1 Cross-Region Authentication

Each region in a federation operates as an independent OJS server. Cross-region communication (health checks, replication) MUST use authenticated HTTPS connections. An implementation SHOULD support mutual TLS or shared bearer tokens for inter-region authentication.

### 7.2 Data Residency

The `region` attribute and geo-pin routing strategy enable compliance with data residency regulations. An implementation MUST respect geo-pin constraints even during failover. A geo-pinned job MUST fail rather than execute in a non-permitted region.

---

## 8. Backward Compatibility

Federation is a purely additive extension. All federation attributes are carried in the `meta` object, which non-federated OJS servers ignore. A federated client can interoperate with non-federated servers without modification.

A non-federated OJS client can enqueue jobs to a federated server. The server processes the job normally; federation routing only applies when the federated client layer is present.
