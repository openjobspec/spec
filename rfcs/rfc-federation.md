# RFC-0001: Multi-Region Federation

- **Stage**: 0 (Strawman)
- **Champion**: TBD
- **Created**: 2025-07-25
- **Last Updated**: 2025-07-25
- **Target Spec Version**: 1.1.0

## Summary

This RFC proposes a multi-region federation protocol for OJS that enables cross-region job routing, regional affinity, automatic failover, and eventual consistency across geographically distributed deployments. Federation is implemented as a client-side routing layer above standard OJS clients, requiring no changes to existing backends.

## Motivation

Organizations operating OJS across multiple geographic regions face three key challenges:

1. **Data locality**: Regulations like GDPR require certain jobs to execute within specific jurisdictions. Without federation, operators must manually partition workloads across independent OJS deployments with no coordination.

2. **Availability**: A single-region deployment is a single point of failure. When a region goes down, all pending and in-flight jobs are unavailable until recovery. Organizations need automatic failover without manual intervention.

3. **Efficiency**: Batch workloads benefit from being distributed across regions based on available capacity. Without a routing layer, operators resort to ad-hoc load balancing that doesn't account for queue depth or worker availability.

The existing `ojs-federation.md` specification defines the semantic model for federation — topology types, routing strategies, health checking, replication, and wire format extensions. This RFC formalizes the path from specification to implementation, identifies open design questions, and proposes concrete API extensions and JSON Schema definitions needed for interoperable federation.

### Use Cases

1. **GDPR-compliant job processing**: A European SaaS company routes user data processing jobs to `eu-west-1` using geo-pin routing, while analytics jobs use affinity routing to prefer the local region.

2. **Multi-cloud resilience**: A financial services company runs OJS on AWS `us-east-1` and GCP `us-central1`. When AWS experiences degraded performance, the federation layer automatically routes new jobs to GCP.

3. **Global batch processing**: A media company distributes video transcoding jobs across regions based on available GPU capacity using overflow routing, achieving 3x throughput compared to single-region processing.

## Prior Art

### Temporal (Temporal Technologies)

Temporal supports multi-cluster replication with namespace-level failover. Each namespace is assigned a primary cluster that handles all writes. During failover, the primary designation moves to another cluster. This is an active-passive model at the namespace level. Temporal uses an event-sourcing approach where the full workflow history is replicated, enabling lossless failover but at significant storage and bandwidth cost.

**Lesson**: Namespace-level failover is simple but coarse-grained. OJS federation should support per-job routing decisions for finer control.

### Celery (Python)

Celery supports multi-broker configurations through its `CELERY_BROKER_TRANSPORT_OPTIONS` and custom routing. However, there is no built-in federation protocol. Operators typically run independent Celery clusters per region and use application-level routing (e.g., publishing to region-specific broker URLs). There is no standard for health checking, failover, or cross-region job visibility.

**Lesson**: Ad-hoc multi-region setups are fragile. A standardized federation protocol with health checking and circuit breakers is needed.

### RabbitMQ Federation Plugin

RabbitMQ provides a federation plugin that replicates messages between brokers across regions. It uses a store-and-forward model: messages published to an upstream broker are forwarded to downstream brokers. This is transparent to publishers and consumers. The federation link handles reconnection and backpressure.

**Lesson**: Transparent replication is powerful but can lead to unbounded cross-region traffic. OJS federation makes replication optional and explicit, using metadata replication rather than full message replication.

### Apache Kafka MirrorMaker 2

Kafka MirrorMaker replicates topics between Kafka clusters using the Connect framework. It supports active-active configurations with automatic topic renaming to prevent infinite loops. Consumer offsets are translated between clusters for seamless failover.

**Lesson**: Loop prevention is critical in any replication scheme. OJS uses the `replicated_from` attribute to prevent infinite replication loops, similar to MirrorMaker's topic renaming approach.

## Detailed Design

### 1. Federation Topology

OJS federation supports three topology models as defined in `ojs-federation.md` Section 2:

#### Hub-Spoke

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

- One hub coordinates all cross-region routing decisions
- Spokes forward routing queries to the hub
- Simplest operational model; hub is single point of failure
- **Recommended for**: 2–3 regions with a clear primary datacenter

#### Mesh

```
    ┌─────────┐     ┌─────────┐
    │us-east-1│◄───►│eu-west-1│
    └────┬────┘     └────┬────┘
         │               │
         └──────┬────────┘
           ┌────┴────┐
           │ap-south-1│
           └─────────┘
```

- Every region communicates directly with every other region
- No central coordinator; highest availability
- O(n²) connections; practical for ≤5 regions
- **Recommended for**: Small deployments requiring maximum independence

#### Active-Active

- All regions accept writes and process jobs independently
- Cross-region replication ensures eventual visibility of job metadata
- Conflict resolution uses last-writer-wins (Section 5.2 of spec)
- **Recommended for**: Deployments requiring zero single points of failure

### 2. Job Routing

Job routing is determined by the `ojs.federation.region_affinity` attribute in the job's `meta` object:

#### Affinity Routing (default)

Route to the local region if healthy; fall back to the next-closest healthy region.

```json
{
  "type": "email.send",
  "args": ["user@example.com", "welcome"],
  "meta": {
    "ojs.federation.federation_id": "01912e4a-7b3c-7def-8a12-abcdef123456",
    "ojs.federation.region_affinity": "affinity"
  }
}
```

#### Overflow Routing

Route to the region with the lowest current load.

```json
{
  "type": "video.transcode",
  "args": ["/input/video.mp4", "1080p"],
  "meta": {
    "ojs.federation.federation_id": "01912e4a-8c4d-7ef0-9b23-bcdef1234567",
    "ojs.federation.region_affinity": "overflow"
  }
}
```

#### Geo-Pin Routing

Job MUST execute in the specified region. Fails if that region is unavailable.

```json
{
  "type": "user.data.export",
  "args": ["usr_12345"],
  "meta": {
    "ojs.federation.federation_id": "01912e4a-9d5e-7f01-ac34-cdef12345678",
    "ojs.federation.region": "eu-west-1",
    "ojs.federation.region_affinity": "geo-pin"
  }
}
```

### 3. Region Discovery and Health

#### Region Registry

Each federation maintains a registry of participating regions:

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

The registry MUST be provided at client initialization via static configuration. Implementations MAY additionally support dynamic registry updates through the `/v1/federation/regions` endpoint.

#### Health Checking

Each region is monitored by calling `GET /ojs/v1/health` at a configurable interval (default: 10 seconds). A region is healthy when the endpoint returns HTTP 200 with `"status": "ok"`.

#### Circuit Breaker

Per-region circuit breakers prevent cascading failures:

| State      | Behavior                                              | Transition                       |
|------------|-------------------------------------------------------|----------------------------------|
| `closed`   | Requests flow normally; failures are counted          | → `open` after 5 consecutive failures |
| `open`     | All requests rejected immediately                     | → `half-open` after 30s cooldown |
| `half-open`| Single probe request sent                             | → `closed` on success; → `open` on failure |

Thresholds (failure count, cooldown duration) MUST be configurable.

### 4. Failover

When a region becomes unavailable, the federation client MUST:

1. Open the circuit breaker for the failed region
2. Select an alternate region based on the routing strategy:
   - **Affinity**: Use the next-closest healthy region by latency
   - **Overflow**: Use the least-loaded healthy region
   - **Geo-pin**: Return an error (geo-pinned jobs MUST NOT be re-routed)
3. Log a structured event: `ojs.federation.failover` with `from_region`, `to_region`, and `reason`

#### Failover Policy Configuration

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

### 5. Consistency Model

Federation uses eventual consistency for cross-region job metadata. Strong cross-region consistency is explicitly a non-goal.

#### Replication

Replication of job metadata (ID, type, state, timestamps) is OPTIONAL. When supported:

- Replicated jobs MUST carry `ojs.federation.replicated_from` to identify the origin region
- A job with `replicated_from` set MUST NOT be replicated again (loop prevention)
- Replication lag SHOULD be monitored and exposed via metrics

#### Conflict Resolution

When the same `federation_id` appears in multiple regions:

1. **Last-writer-wins**: The `enqueued_at` timestamp determines precedence
2. **Tiebreaker**: If timestamps match at millisecond precision, lexicographic comparison of `federation_id`
3. **No merge**: Conflicting job envelopes are not merged; the winner replaces the loser

### 6. API Extensions

#### `GET /v1/federation/regions`

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

#### `POST /v1/federation/route`

Resolves the target region for a job without enqueuing it. Useful for dry-run validation and debugging routing decisions.

**Request**:

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

#### `GET /v1/federation/health`

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

### 7. Wire Format

Federation attributes are encoded in the job's `meta` object with the `ojs.federation.` prefix, as defined in `ojs-federation.md` Section 6:

| Attribute                          | Type   | Required | Description                                      |
|------------------------------------|--------|----------|--------------------------------------------------|
| `ojs.federation.federation_id`     | string | Yes      | UUIDv7 for cross-region tracking                 |
| `ojs.federation.region`            | string | No       | Target region for geo-pin routing                |
| `ojs.federation.region_affinity`   | string | No       | Routing strategy: `affinity`, `overflow`, `geo-pin`. Default: `affinity` |
| `ojs.federation.replicated_from`   | string | No       | Origin region for replicated jobs                |

### 8. Security

#### Cross-Region Authentication

All inter-region communication MUST use HTTPS. Implementations SHOULD support:

1. **Mutual TLS (mTLS)**: Each region presents a client certificate signed by a shared CA. This is the RECOMMENDED approach for production deployments.
2. **Shared bearer tokens**: A pre-shared token is included in the `Authorization` header. Suitable for development and testing.

#### Region Isolation

- Geo-pinned jobs MUST NOT be forwarded to non-permitted regions, even during failover
- Replication of geo-pinned job payloads to non-permitted regions MUST be configurable (metadata-only replication vs. full replication)
- Each region SHOULD maintain its own authentication credentials; a compromised region MUST NOT grant access to other regions

## Examples

### Federated Client Initialization (Go pseudocode)

```go
federation := ojs.NewFederatedClient(ojs.FederationConfig{
    LocalRegion: "us-east-1",
    Regions: []ojs.Region{
        {ID: "us-east-1", URL: "https://ojs-us-east-1.example.com", Weight: 2},
        {ID: "eu-west-1", URL: "https://ojs-eu-west-1.example.com", Weight: 1},
        {ID: "ap-south-1", URL: "https://ojs-ap-south-1.example.com", Weight: 1},
    },
    HealthCheckInterval: 10 * time.Second,
    CircuitBreaker: ojs.CircuitBreakerConfig{
        FailureThreshold: 5,
        CooldownPeriod:   30 * time.Second,
    },
    Failover: ojs.FailoverConfig{
        Enabled:      true,
        MaxRedirects: 3,
    },
})
```

### Enqueue with Affinity Routing

```go
job, err := federation.Enqueue(ctx, ojs.Job{
    Type:  "email.send",
    Queue: "email",
    Args:  []any{"user@example.com", "welcome"},
    // No region specified — uses affinity routing (default)
})
// Job is routed to us-east-1 (local region) if healthy
```

### Enqueue with Geo-Pin

```go
job, err := federation.Enqueue(ctx, ojs.Job{
    Type:  "user.data.export",
    Queue: "gdpr",
    Args:  []any{"usr_12345"},
    Meta: map[string]string{
        "ojs.federation.region": "eu-west-1",
    },
})
// Job is always routed to eu-west-1; error if eu-west-1 is unavailable
```

### Federated Client Initialization (TypeScript pseudocode)

```typescript
const federation = new FederatedClient({
  localRegion: "us-east-1",
  regions: [
    { id: "us-east-1", url: "https://ojs-us-east-1.example.com", weight: 2 },
    { id: "eu-west-1", url: "https://ojs-eu-west-1.example.com", weight: 1 },
  ],
  healthCheckInterval: 10_000,
  circuitBreaker: { failureThreshold: 5, cooldownMs: 30_000 },
});

// Enqueue with overflow routing
await federation.enqueue({
  type: "video.transcode",
  args: ["/input/video.mp4", "1080p"],
  meta: { "ojs.federation.region_affinity": "overflow" },
});
```

## Conformance Impact

Federation is an OPTIONAL extension. It does not affect conformance levels 0–4. A future conformance level 5 MAY be introduced to cover federation semantics.

New requirements introduced:

- **MUST**: Federated clients MUST generate `federation_id` using UUIDv7
- **MUST**: Federated clients MUST implement per-region circuit breakers
- **MUST**: Geo-pinned jobs MUST fail rather than route to non-permitted regions
- **MUST**: Replicated jobs MUST carry `replicated_from` and MUST NOT be re-replicated
- **SHOULD**: Implementations SHOULD support mTLS for inter-region authentication
- **MAY**: Implementations MAY support cross-region metadata replication

## Backward Compatibility

Federation is fully backward compatible. All federation attributes are carried in the `meta` object with the `ojs.federation.` prefix. Non-federated OJS servers ignore these attributes. A federated client can enqueue jobs to a non-federated server without errors, and a non-federated client can enqueue jobs to a server participating in a federation.

No changes to the core job envelope, lifecycle states, or existing API endpoints are required.

## Implementation Requirements

Per the OJS RFC process, proposals at Stage 2+ MUST include working prototypes in at least two languages:

- [ ] Go: Federated client wrapper in `ojs-go-sdk/federation/`
- [ ] TypeScript: Federated client wrapper in `ojs-js-sdk/src/federation/`

## Alternatives Considered

### Server-Side Federation

Instead of client-side routing, federation could be implemented as a server-side proxy that intercepts enqueue requests and forwards them to the appropriate region. This was rejected because:

- It introduces a new infrastructure component (the federation proxy) that must be highly available
- It couples the federation protocol to backend implementation details
- It prevents client-side optimizations like latency-based routing with local health state

### Strong Consistency via Raft/Paxos

Cross-region strong consistency was considered but rejected because:

- Background job systems already tolerate at-least-once semantics; strong consistency adds latency without meaningful benefit
- Cross-region consensus adds 100–300ms to every write operation
- The CAP theorem forces a choice between availability and consistency during partitions; availability is more important for job processing

### CRDT-Based Conflict Resolution

Using CRDTs (Conflict-free Replicated Data Types) for job state was considered but rejected because:

- Job state transitions are inherently sequential (the lifecycle is a directed graph), not commutative
- CRDTs add significant implementation complexity for all SDK authors
- Last-writer-wins is sufficient for job metadata where the latest state is almost always correct

## Open Questions

1. **Region weight semantics**: Should `weight` affect routing probability for affinity routing, or only for overflow routing? The current spec is ambiguous.

2. **Replication scope**: Should replication include job `args` (which may be large), or only metadata (ID, type, state, timestamps)? Full replication enables cross-region job inspection but increases bandwidth costs.

3. **Federation discovery protocol**: Should there be a standard discovery protocol for regions to find each other, or is static configuration sufficient? A DNS-based discovery mechanism (SRV records) could simplify operations.

4. **Metrics and observability**: What federation-specific metrics should be standardized? Candidates include cross-region routing count, failover events, replication lag, and circuit breaker state transitions.

5. **Multi-tenant federation**: How does federation interact with the multi-tenancy isolation models defined in ADR-008? Should tenant affinity be a routing dimension?

## Implementation Stages

| Stage | Name        | Description                                                                 |
|-------|-------------|-----------------------------------------------------------------------------|
| 0     | Proposal    | This RFC. Define semantics, wire format, and API extensions.                |
| 1     | Prototype   | Working Go and TypeScript federated clients with static region registry.    |
| 2     | Draft       | Add health checking, circuit breakers, and failover. Conformance tests.     |
| 3     | Stable      | Dynamic discovery, replication, and production-hardened implementations.     |

