# Open Job Spec: Multi-Region Federation Extension

| Field       | Value                        |
|-------------|------------------------------|
| Version     | 0.1.0                        |
| Date        | 2026-02-19                   |
| Status      | Draft                        |
| Stage       | 1 (Proposal)                 |
| Maturity    | Alpha                        |
| Layer       | 1 -- Core (Extension)        |
| Spec URI    | `urn:ojs:spec:federation`    |

---

## Table of Contents

1. [Overview and Rationale](#1-overview-and-rationale)
2. [Terminology](#2-terminology)
3. [Region Topology](#3-region-topology)
   - 3.1 [Hub-Spoke](#31-hub-spoke)
   - 3.2 [Mesh](#32-mesh)
   - 3.3 [Active-Active](#33-active-active)
4. [Job Routing Strategies](#4-job-routing-strategies)
   - 4.1 [Affinity Routing](#41-affinity-routing)
   - 4.2 [Overflow Routing](#42-overflow-routing)
   - 4.3 [Round-Robin Routing](#43-round-robin-routing)
   - 4.4 [Latency-Based Routing](#44-latency-based-routing)
   - 4.5 [Geo-Pin Routing](#45-geo-pin-routing)
   - 4.6 [Active-Passive Routing](#46-active-passive-routing)
   - 4.7 [Geographic Routing](#47-geographic-routing)
5. [Region Discovery and Health](#5-region-discovery-and-health)
   - 5.1 [Region Registry](#51-region-registry)
   - 5.2 [Health Checking](#52-health-checking)
   - 5.3 [Circuit Breaker](#53-circuit-breaker)
6. [Cross-Region Consistency Model](#6-cross-region-consistency-model)
   - 6.1 [Eventual Consistency](#61-eventual-consistency)
   - 6.2 [Replication](#62-replication)
   - 6.3 [Conflict Resolution](#63-conflict-resolution)
7. [Failure Handling](#7-failure-handling)
   - 7.1 [Failover Semantics](#71-failover-semantics)
   - 7.2 [Circuit Breaker Pattern](#72-circuit-breaker-pattern)
   - 7.3 [Failover Policy Configuration](#73-failover-policy-configuration)
8. [Wire Format](#8-wire-format)
   - 8.1 [Federation Metadata Attributes](#81-federation-metadata-attributes)
   - 8.2 [Job Envelope with Federation](#82-job-envelope-with-federation)
9. [API Extensions](#9-api-extensions)
   - 9.1 [Region Registry Endpoint](#91-region-registry-endpoint)
   - 9.2 [Route Resolution Endpoint](#92-route-resolution-endpoint)
   - 9.3 [Federation Health Endpoint](#93-federation-health-endpoint)
10. [Security Considerations](#10-security-considerations)
11. [Conformance Requirements](#11-conformance-requirements)
12. [Examples](#12-examples)

---

## 1. Overview and Rationale

This extension defines a multi-region federation protocol for Open Job Spec (OJS) that enables cross-region job routing, regional affinity, automatic failover, and eventual consistency across geographically distributed deployments.

**Rationale.** Organizations operating OJS across multiple geographic regions face three key challenges:

1. **Data locality**: Regulations such as GDPR require certain jobs to execute within specific jurisdictions. Without federation, operators must manually partition workloads across independent OJS deployments with no coordination.

2. **Availability**: A single-region deployment is a single point of failure. When a region goes down, all pending and in-flight jobs are unavailable until recovery. Organizations need automatic failover without manual intervention.

3. **Efficiency**: Batch workloads benefit from being distributed across regions based on available capacity. Without a routing layer, operators resort to ad-hoc load balancing that does not account for queue depth or worker availability.

Federation is implemented as a **client-side routing layer** above standard OJS clients, requiring no changes to existing backends. A federated client wraps one or more regional OJS clients and applies routing strategies, health checking, and circuit breaker patterns to determine the target region for each job.

**Key words.** The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

---

## 2. Terminology

| Term             | Definition                                                                                   |
|------------------|----------------------------------------------------------------------------------------------|
| Region           | A geographic deployment of an OJS backend with its own workers. Identified by a unique ID.   |
| Federation       | A set of regions operating together under a shared routing and health-checking protocol.      |
| Federated Client | A client-side wrapper that routes jobs across multiple regional OJS clients.                  |
| Local Region     | The region collocated with the federated client (lowest latency).                            |
| Circuit Breaker  | A pattern that prevents cascading failures by temporarily stopping requests to unhealthy regions. |
| Geo-Pin          | A routing constraint that requires a job to execute in a specific region.                    |
| Affinity         | A routing preference that favors the local region but allows fallback.                       |
| Overflow         | A load-based routing strategy that distributes jobs to the least-loaded region.              |
| Replication      | The propagation of job metadata from one region to another for cross-region visibility.       |

---

## 3. Region Topology

OJS federation supports three topology models. Implementations MUST support at least one topology and SHOULD document which topologies are supported.

### 3.1 Hub-Spoke

```
        ┌─────────┐
        │   Hub   │
        │us-east-1│
        └────┬────┘
         ┌───┼───┐
    ┌────┴┐ ┌┴──┐ ┌┴────┐
    │Spoke│ │...│ │Spoke│
    │eu-1 │ │   │ │ap-1 │
    └─────┘ └───┘ └─────┘
```

One hub region coordinates all cross-region routing decisions. Spokes forward routing queries to the hub. This is the simplest operational model; however, the hub is a single point of failure.

**RECOMMENDED for**: 2–3 regions with a clear primary datacenter.

### 3.2 Mesh

```
    ┌─────────┐     ┌─────────┐
    │us-east-1│◄───►│eu-west-1│
    └────┬────┘     └────┬────┘
         │               │
         └──────┬────────┘
           ┌────┴─────┐
           │ap-south-1 │
           └───────────┘
```

Every region communicates directly with every other region. No central coordinator; highest availability. Produces O(n²) connections; practical for ≤5 regions.

**RECOMMENDED for**: Small deployments requiring maximum regional independence.

### 3.3 Active-Active

All regions accept writes and process jobs independently. Cross-region replication ensures eventual visibility of job metadata. Conflict resolution uses last-writer-wins (see [Section 6.3](#63-conflict-resolution)).

**RECOMMENDED for**: Deployments requiring zero single points of failure.

---

## 4. Job Routing Strategies

A routing strategy determines which region receives a job. Federated clients MUST support at least `affinity` and `geo-pin` routing. All other strategies are OPTIONAL.

### 4.1 Affinity Routing

**Default strategy.** Route to the local region if healthy; fall back to the next-closest healthy region by latency.

**Behavior:**
1. If the local region is healthy, route to it.
2. Otherwise, select the healthy region with the lowest measured latency.
3. If no healthy region is available, return an error.

### 4.2 Overflow Routing

Route to the region with the lowest current load. Load MAY be determined by queue depth, active job count, or a weighted random selection based on region weights.

**Behavior:**
1. Collect health and load metrics from all healthy regions.
2. Select the region with the lowest load (or use weighted random selection).
3. If no healthy region is available, return an error.

### 4.3 Round-Robin Routing

Distribute jobs across regions in a deterministic cyclic order. Each successive job is routed to the next region in the list.

**Behavior:**
1. Maintain an internal counter (per federated client instance).
2. Select the next healthy region in order, skipping unhealthy regions.
3. If no healthy region is available, return an error.

### 4.4 Latency-Based Routing

Always route to the healthy region with the lowest measured latency, regardless of locality.

**Behavior:**
1. Measure latency to all regions via periodic health checks.
2. Select the region with the lowest latency.
3. If no healthy region is available, return an error.

### 4.5 Geo-Pin Routing

Job MUST execute in the specified region. If that region is unavailable, the enqueue operation MUST fail rather than route to a different region.

**Behavior:**
1. Read `ojs.federation.region` from the job metadata.
2. If the specified region is healthy, route to it.
3. If the specified region is unhealthy, return an error. Geo-pinned jobs MUST NOT be re-routed.

**Rationale**: Data sovereignty requirements (e.g., GDPR, HIPAA) mandate that certain jobs execute within specific jurisdictions. Silent re-routing would violate compliance requirements.

### 4.6 Active-Passive Routing

Route to the primary region. If the primary is unhealthy, fail over to secondary regions in priority order.

**Behavior:**
1. Route to the designated primary region if healthy.
2. If primary is unhealthy, route to the first healthy secondary region.
3. If no region is healthy, return an error.

### 4.7 Geographic Routing

Route based on geographic context hints in the job metadata. A mapping table translates geographic hints (e.g., country codes, continent codes) to target regions.

**Behavior:**
1. Read geographic hints from job metadata.
2. Look up the target region using the configured mapping table.
3. If the mapped region is healthy, route to it; otherwise, fall back to the default strategy.

---

## 5. Region Discovery and Health

### 5.1 Region Registry

Each federation maintains a registry of participating regions. The registry MUST be provided at client initialization via static configuration. Implementations MAY additionally support dynamic registry updates.

A region entry MUST include:

| Field    | Type    | Required | Description                                              |
|----------|---------|----------|----------------------------------------------------------|
| `id`     | string  | Yes      | Unique region identifier (e.g., `us-east-1`)            |
| `url`    | string  | Yes      | Base URL of the regional OJS server                      |
| `weight` | integer | No       | Relative weight for load-based routing (default: 1)      |
| `tags`   | array   | No       | Region tags for capability-based routing (e.g., `["gpu", "gdpr"]`) |

**Example:**

```json
{
  "federation_id": "prod-global",
  "regions": [
    {
      "id": "us-east-1",
      "url": "https://ojs-us-east-1.example.com",
      "weight": 2,
      "tags": ["gpu", "high-memory"]
    },
    {
      "id": "eu-west-1",
      "url": "https://ojs-eu-west-1.example.com",
      "weight": 1,
      "tags": ["gdpr"]
    },
    {
      "id": "ap-south-1",
      "url": "https://ojs-ap-south-1.example.com",
      "weight": 1,
      "tags": []
    }
  ]
}
```

### 5.2 Health Checking

Each region MUST be monitored by calling `GET /ojs/v1/health` at a configurable interval. The default interval is 10 seconds.

A region is **healthy** when the health endpoint returns HTTP 200 with `"status": "ok"`. Any other response (non-200 status, timeout, connection error) indicates an **unhealthy** region.

Implementations SHOULD expose measured latency for each region to support latency-based routing.

### 5.3 Circuit Breaker

Per-region circuit breakers prevent cascading failures. Implementations MUST support configurable thresholds.

| State       | Behavior                                              | Transition                            |
|-------------|-------------------------------------------------------|---------------------------------------|
| `closed`    | Requests flow normally; failures are counted          | → `open` after N consecutive failures |
| `open`      | All requests are rejected immediately                 | → `half-open` after cooldown period   |
| `half-open` | A single probe request is sent                        | → `closed` on success; → `open` on failure |

Default thresholds (MUST be configurable):
- **Failure threshold**: 5 consecutive failures
- **Cooldown period**: 30 seconds

---

## 6. Cross-Region Consistency Model

### 6.1 Eventual Consistency

Federation uses **eventual consistency** for cross-region job metadata. Strong cross-region consistency is explicitly a non-goal.

**Rationale**: Background job systems already tolerate at-least-once semantics. Cross-region strong consistency would add 100–300ms to every write operation via consensus protocols, which is unacceptable for job enqueue latency.

### 6.2 Replication

Replication of job metadata (ID, type, state, timestamps) across regions is OPTIONAL. When supported:

- Replicated jobs MUST carry `ojs.federation.replicated_from` to identify the origin region.
- A job with `replicated_from` set MUST NOT be replicated again (loop prevention).
- Replication lag SHOULD be monitored and exposed via metrics.
- Implementations MAY support metadata-only replication (ID, type, state) or full replication (including `args`).

### 6.3 Conflict Resolution

When the same `federation_id` appears in multiple regions due to concurrent writes:

1. **Last-writer-wins**: The `enqueued_at` timestamp determines precedence.
2. **Tiebreaker**: If timestamps match at millisecond precision, lexicographic comparison of `federation_id` determines the winner.
3. **No merge**: Conflicting job envelopes are not merged; the winner replaces the loser.

---

## 7. Failure Handling

### 7.1 Failover Semantics

When a region becomes unavailable, the federation client MUST:

1. Open the circuit breaker for the failed region.
2. Select an alternate region based on the active routing strategy:
   - **Affinity**: Use the next-closest healthy region by latency.
   - **Overflow**: Use the least-loaded healthy region.
   - **Round-Robin**: Skip the unhealthy region in the cycle.
   - **Latency-Based**: Use the next-lowest-latency healthy region.
   - **Geo-Pin**: Return an error. Geo-pinned jobs MUST NOT be re-routed.
   - **Active-Passive**: Use the next secondary region in priority order.
3. Log a structured event: `ojs.federation.failover` with `from_region`, `to_region`, and `reason`.

### 7.2 Circuit Breaker Pattern

The circuit breaker prevents repeated requests to a failing region:

```
    ┌────────────────────────────────────────┐
    │                                        │
    ▼           N failures                   │
 CLOSED ─────────────────► OPEN              │
    ▲                        │               │
    │                        │ cooldown      │
    │         success        ▼               │
    └──────────────────── HALF-OPEN          │
                             │               │
                             │ failure       │
                             └───────────────┘
```

Implementations MUST:
- Track consecutive failure count per region.
- Transition to `open` after the configured failure threshold.
- Transition to `half-open` after the configured cooldown period.
- Send a single probe request in `half-open` state.
- Transition to `closed` on probe success or back to `open` on probe failure.

### 7.3 Failover Policy Configuration

Federated clients SHOULD support the following configuration:

| Field             | Type    | Default | Description                                        |
|-------------------|---------|---------|----------------------------------------------------|
| `enabled`         | boolean | true    | Whether failover is enabled                        |
| `max_redirects`   | integer | 3       | Maximum failover attempts before returning error   |
| `exclude_regions` | array   | []      | Regions to never fail over to                      |
| `prefer_regions`  | array   | []      | Preferred failover targets, in priority order      |

**Example:**

```json
{
  "failover": {
    "enabled": true,
    "max_redirects": 3,
    "exclude_regions": ["ap-south-1"],
    "prefer_regions": ["us-east-1", "eu-west-1"]
  }
}
```

---

## 8. Wire Format

### 8.1 Federation Metadata Attributes

Federation attributes are encoded in the job's `meta` object with the `ojs.federation.` prefix:

| Attribute                          | Type   | Required | Description                                                          |
|------------------------------------|--------|----------|----------------------------------------------------------------------|
| `ojs.federation.federation_id`     | string | Yes      | UUIDv7 identifier for cross-region tracking                         |
| `ojs.federation.region`            | string | No       | Target region for geo-pin routing                                   |
| `ojs.federation.region_affinity`   | string | No       | Routing strategy. One of: `affinity`, `overflow`, `round-robin`, `latency-based`, `geo-pin`, `active-passive`, `geographic`. Default: `affinity` |
| `ojs.federation.source_region`     | string | No       | Region where the job was originally enqueued                        |
| `ojs.federation.replicated_from`   | string | No       | Origin region for replicated jobs (loop prevention)                 |
| `ojs.federation.routed_at`        | string | No       | RFC 3339 timestamp of the routing decision                          |

The `federation_id` MUST be a UUIDv7. Federated clients MUST generate it automatically if not provided.

### 8.2 Job Envelope with Federation

**Affinity routing example:**

```json
{
  "type": "email.send",
  "args": ["user@example.com", "welcome"],
  "meta": {
    "ojs.federation.federation_id": "01912e4a-7b3c-7def-8a12-abcdef123456",
    "ojs.federation.region_affinity": "affinity",
    "ojs.federation.source_region": "us-east-1"
  }
}
```

**Geo-pin routing example:**

```json
{
  "type": "user.data.export",
  "args": ["usr_12345"],
  "meta": {
    "ojs.federation.federation_id": "01912e4a-9d5e-7f01-ac34-cdef12345678",
    "ojs.federation.region": "eu-west-1",
    "ojs.federation.region_affinity": "geo-pin",
    "ojs.federation.source_region": "us-east-1"
  }
}
```

**Overflow routing example:**

```json
{
  "type": "video.transcode",
  "args": ["/input/video.mp4", "1080p"],
  "meta": {
    "ojs.federation.federation_id": "01912e4a-8c4d-7ef0-9b23-bcdef1234567",
    "ojs.federation.region_affinity": "overflow",
    "ojs.federation.source_region": "us-east-1"
  }
}
```

---

## 9. API Extensions

Federation introduces three OPTIONAL API endpoints. These endpoints are exposed by the federated client layer, not by individual OJS backends.

### 9.1 Region Registry Endpoint

**`GET /v1/federation/regions`**

Returns the current region registry with health status.

**Response** (200 OK):

```json
{
  "federation_id": "prod-global",
  "regions": [
    {
      "id": "us-east-1",
      "url": "https://ojs-us-east-1.example.com",
      "status": "healthy",
      "latency_ms": 12,
      "circuit_breaker": "closed",
      "last_health_check": "2026-03-15T10:30:00Z"
    },
    {
      "id": "eu-west-1",
      "url": "https://ojs-eu-west-1.example.com",
      "status": "unhealthy",
      "latency_ms": null,
      "circuit_breaker": "open",
      "last_health_check": "2026-03-15T10:29:45Z"
    }
  ]
}
```

### 9.2 Route Resolution Endpoint

**`POST /v1/federation/route`**

Resolves the target region for a job without enqueuing it. Useful for dry-run validation and debugging routing decisions.

**Request:**

```json
{
  "type": "email.send",
  "meta": {
    "ojs.federation.region_affinity": "affinity"
  }
}
```

**Response** (200 OK):

```json
{
  "target_region": "us-east-1",
  "strategy": "affinity",
  "candidates": [
    {"id": "us-east-1", "score": 0.95, "reason": "local, healthy"},
    {"id": "eu-west-1", "score": 0.72, "reason": "healthy, higher latency"}
  ]
}
```

### 9.3 Federation Health Endpoint

**`GET /v1/federation/health`**

Returns aggregate federation health, including per-region status and replication lag.

**Response** (200 OK):

```json
{
  "status": "degraded",
  "healthy_regions": 2,
  "total_regions": 3,
  "regions": [
    {
      "id": "us-east-1",
      "status": "healthy",
      "replication_lag_ms": 0
    },
    {
      "id": "eu-west-1",
      "status": "healthy",
      "replication_lag_ms": 450
    },
    {
      "id": "ap-south-1",
      "status": "unhealthy",
      "replication_lag_ms": null
    }
  ]
}
```

---

## 10. Security Considerations

### Cross-Region Authentication

All inter-region communication MUST use HTTPS. Implementations SHOULD support:

1. **Mutual TLS (mTLS)**: Each region presents a client certificate signed by a shared CA. This is the RECOMMENDED approach for production deployments.
2. **Shared bearer tokens**: A pre-shared token included in the `Authorization` header. Suitable for development and testing.

### Region Isolation

- Geo-pinned jobs MUST NOT be forwarded to non-permitted regions, even during failover.
- Replication of geo-pinned job payloads to non-permitted regions MUST be configurable (metadata-only replication vs. full replication).
- Each region SHOULD maintain its own authentication credentials; a compromised region MUST NOT grant access to other regions.

---

## 11. Conformance Requirements

Federation is an OPTIONAL extension. It does not affect conformance levels 0–4.

Implementations claiming federation support MUST satisfy:

| Requirement                                                                 | Level    |
|----------------------------------------------------------------------------|----------|
| Federated clients MUST generate `federation_id` using UUIDv7               | MUST     |
| Federated clients MUST implement per-region circuit breakers               | MUST     |
| Geo-pinned jobs MUST fail rather than route to non-permitted regions       | MUST     |
| Replicated jobs MUST carry `replicated_from` and MUST NOT be re-replicated | MUST     |
| Federation metadata MUST use the `ojs.federation.` prefix in `meta`       | MUST     |
| Implementations SHOULD support mTLS for inter-region authentication        | SHOULD   |
| Implementations SHOULD expose per-region latency metrics                   | SHOULD   |
| Implementations MAY support cross-region metadata replication              | MAY      |
| Implementations MAY support dynamic region discovery                       | MAY      |

---

## 12. Examples

### Complete Federated Job Envelope

```json
{
  "type": "user.data.export",
  "queue": "gdpr-exports",
  "args": ["usr_12345"],
  "meta": {
    "ojs.federation.federation_id": "01912e4a-9d5e-7f01-ac34-cdef12345678",
    "ojs.federation.region": "eu-west-1",
    "ojs.federation.region_affinity": "geo-pin",
    "ojs.federation.source_region": "us-east-1",
    "ojs.federation.routed_at": "2026-03-15T10:30:00.123Z"
  }
}
```

### Multi-Region Configuration

```json
{
  "federation_id": "prod-global",
  "local_region": "us-east-1",
  "default_strategy": "affinity",
  "regions": [
    {
      "id": "us-east-1",
      "url": "https://ojs-us-east-1.example.com",
      "weight": 2,
      "tags": ["gpu", "high-memory"]
    },
    {
      "id": "eu-west-1",
      "url": "https://ojs-eu-west-1.example.com",
      "weight": 1,
      "tags": ["gdpr"]
    },
    {
      "id": "ap-south-1",
      "url": "https://ojs-ap-south-1.example.com",
      "weight": 1,
      "tags": []
    }
  ],
  "health_check": {
    "interval_seconds": 10,
    "timeout_seconds": 5
  },
  "circuit_breaker": {
    "failure_threshold": 5,
    "cooldown_seconds": 30
  },
  "failover": {
    "enabled": true,
    "max_redirects": 3,
    "exclude_regions": [],
    "prefer_regions": ["us-east-1", "eu-west-1"]
  }
}
```
