# ADR-001: Three-Layer Architecture

## Status

Accepted

## Context

Background job processing systems historically couple the job envelope format, serialization, and transport into a single implementation. This creates vendor lock-in: switching from Sidekiq to Celery requires rewriting not just the worker code, but also how jobs are serialized, transmitted, and stored.

We needed a standard that could:
- Support multiple wire formats (JSON, Protobuf, MessagePack)
- Support multiple transport protocols (HTTP, gRPC, AMQP)
- Keep the core job semantics independent of how jobs are serialized or transmitted
- Allow implementations to adopt incrementally (e.g., JSON over HTTP first, then add gRPC later)

The CloudEvents specification (CNCF) successfully solved an analogous problem for event-driven architectures using a layered approach that separates core attributes from format bindings and protocol bindings.

## Decision

We adopt a three-layer architecture inspired by CloudEvents:

1. **Layer 1 — Core** (`ojs-core`): Defines the abstract job envelope attributes, the 8-state lifecycle, and logical operations (PUSH, FETCH, ACK, FAIL, BEAT, CANCEL, INFO). This layer is protocol-agnostic and format-agnostic.

2. **Layer 2 — Wire Formats** (`ojs-json-format`, `ojs-protobuf-format`): Defines how core attributes are serialized into specific formats. JSON uses camelCase field names and RFC 3339 timestamps. Protobuf uses the generated message types from `ojs-proto`.

3. **Layer 3 — Protocol Bindings** (`ojs-http-binding`, `ojs-grpc-binding`): Defines how serialized messages are transmitted over specific protocols. HTTP binding maps operations to REST endpoints with standard status codes. gRPC binding maps operations to RPC methods.

Each layer depends only on the layer below it. Implementations MUST support Layer 1 semantics, SHOULD support at least one Layer 2 format, and MUST implement at least one Layer 3 binding.

## Consequences

### Easier
- **Incremental adoption**: Implementations can start with JSON/HTTP and add Protobuf/gRPC later without changing core logic
- **Interoperability**: A Go producer using gRPC can work with a Python consumer using HTTP, as long as the backend translates between bindings
- **Spec evolution**: New wire formats or protocols can be added without modifying the core spec
- **Testing**: The conformance suite tests against Layer 3 bindings, which implicitly validates Layers 1 and 2

### Harder
- **Implementation complexity**: Backend authors must understand the layer boundaries and implement each layer correctly
- **Specification surface area**: The spec is larger than a monolithic approach — multiple documents must be read and cross-referenced
- **Version coordination**: Changes to Layer 1 may cascade to Layers 2 and 3, requiring coordinated releases
