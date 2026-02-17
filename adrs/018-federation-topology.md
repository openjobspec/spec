# ADR-018: Federation Topology — Client-Side Hub-Spoke and Mesh

## Status

Proposed

## Context

OJS needs a multi-region federation model that allows independent OJS deployments to cooperate across geographic regions. The federation specification (`ojs-federation.md`) defines three topology models: hub-spoke, mesh, and active-active. We needed to decide which topologies to support, how they interact with the existing architecture, and critically, where the federation logic lives — in the server or the client.

### Options Considered

1. **Server-side federation proxy**: A dedicated proxy sits in front of OJS backends and intercepts enqueue requests, routing them to the appropriate region. The proxy maintains the region registry and health state.

2. **Client-side federation (chosen)**: The federation layer is implemented as a client-side wrapper around standard OJS clients. Each SDK provides a `FederatedClient` that wraps one or more region-specific `Client` instances. The federated client handles routing, health checking, and circuit breaking.

3. **Backend-native federation**: Each OJS backend natively understands federation and replicates jobs across regions at the storage layer (e.g., Redis Cluster cross-region, PostgreSQL logical replication).

### Key Constraints

- Federation MUST NOT require changes to existing OJS backends. Any conforming server should be able to participate in a federation.
- Federation MUST support both hub-spoke and mesh topologies for different organizational needs.
- The design MUST allow incremental adoption — a single-region deployment can become federated without backend changes.
- Data residency requirements (geo-pinning) MUST be enforced at the routing layer, not as a best-effort hint.

## Decision

We adopt **client-side federation** (Option 2) supporting both **hub-spoke** and **mesh** topologies, with **active-active** as an extension of mesh with optional replication.

### Topology Selection

**Hub-spoke** is the RECOMMENDED starting topology for organizations with a clear primary region:

- Simplest to reason about: one hub, N spokes
- The hub region's client coordinates cross-region routing metadata
- Spokes can operate independently for local jobs; only cross-region routing requires hub involvement
- Drawback: hub is a single point of failure for cross-region operations (not for local operations)

**Mesh** is RECOMMENDED for deployments with ≤5 regions that require maximum independence:

- Each region maintains health state for all peers
- Routing decisions are made independently per region
- No single point of failure
- Drawback: O(n²) health check connections; operational complexity increases with region count

**Active-active** is an extension of mesh that adds optional cross-region metadata replication using eventual consistency with last-writer-wins conflict resolution. It does not change the routing topology.

### Why Client-Side

1. **No new infrastructure**: A federation proxy (Option 1) would be a new stateful component requiring its own high availability, monitoring, and upgrades. Client-side federation distributes this responsibility across existing application instances.

2. **Backend independence**: OJS is designed around a three-layer architecture (ADR-001). Federation as a client-side concern preserves this separation — backends remain protocol-agnostic processing engines.

3. **Latency optimization**: Client-side routing uses locally-measured latency to peer regions, enabling optimal routing decisions without an extra network hop through a proxy.

4. **Incremental adoption**: Adding federation requires only changing client initialization code. No backend redeployment, no infrastructure changes.

### Why Not Backend-Native

Backend-native federation (Option 3) was rejected because:

- It would couple the federation protocol to specific storage implementations (Redis Cluster semantics differ from PostgreSQL logical replication)
- It would require every backend to implement federation, dramatically increasing the implementation burden
- Cross-storage federation (e.g., Redis backend in us-east-1 federated with PostgreSQL backend in eu-west-1) would be impossible

## Consequences

### Easier

- **Adoption**: Any existing OJS deployment can become federated by updating client initialization code. No backend changes required.
- **Heterogeneous backends**: A federation can include regions running different backends (Redis in one, PostgreSQL in another), since federation operates above the backend layer.
- **Testing**: Federation logic can be unit-tested with mock OJS clients, without requiring multiple running backends.
- **Topology flexibility**: Organizations can start with hub-spoke and migrate to mesh without changing backends or job schemas.

### Harder

- **Client complexity**: Every SDK that supports federation must implement routing, health checking, circuit breaking, and failover. This is significant implementation work repeated across Go, TypeScript, Python, Java, Rust, and Ruby SDKs.
- **Consistency of behavior**: Client-side implementations across languages must behave identically for the same routing inputs. The conformance suite will need federation-specific test cases.
- **Observability**: Federation routing decisions happen in the client, making them harder to observe centrally. Structured logging and metrics emission are critical.
- **Replication**: Cross-region metadata replication requires a separate component (not part of the client), since clients are ephemeral. This component is not yet specified.
