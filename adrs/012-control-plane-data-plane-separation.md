# ADR-012: Control Plane / Data Plane Separation

## Status

Accepted

## Context

Job processing systems expose two fundamentally different API surfaces. The data plane handles the high-throughput, latency-sensitive operations that application code uses in production: enqueuing jobs, fetching jobs for processing, acknowledging completion, and reporting failures. The control plane handles lower-throughput operational tasks: creating and configuring queues, inspecting job state, performing bulk operations (pause, cancel, retry), and gathering system metrics.

Mixing these two surfaces into a single API creates coupling problems. A dashboard polling for job statistics should not compete for resources with the critical path of job enqueue and processing. An operator running a bulk cancel operation should not be able to accidentally affect data plane authentication tokens. Security requirements also differ: data plane access is typically granted to application services, while control plane access is restricted to operators and admin tools.

Production systems that separate these concerns — Kubernetes (API server vs. kubelet), cloud messaging services (management API vs. data API), databases (admin connections vs. application connections) — consistently demonstrate better operational characteristics. The separation enables independent scaling, targeted rate limiting, and distinct authentication policies for each surface.

## Decision

We separate the Admin API (control plane) from the core job operations (data plane) into distinct API surfaces. Data plane operations (PUSH, FETCH, ACK, FAIL, BEAT) live under the existing `/ojs/v1/` path and handle all application-level job processing. Admin operations (queue management, job inspection, bulk operations, metrics) live under `/ojs/v1/admin/` with separate endpoint definitions.

The Admin API uses separate authentication from the data plane. While the data plane might use API keys scoped to specific queues, the Admin API requires operator-level credentials with explicit admin permissions. This prevents application services from accidentally (or maliciously) performing administrative operations.

The Admin API is optional — it is not required for Level 0 conformance. Implementations may start with data plane support only and add the Admin API later. However, implementations that do provide admin functionality SHOULD follow the standardized Admin API specification to enable portable operator tooling (CLIs, dashboards, monitoring integrations) across different OJS backends.

## Consequences

### Easier

- **Independent scaling**: Data plane and control plane can be scaled independently — add more data plane capacity during traffic spikes without scaling admin infrastructure
- **Separate auth policies**: Operator credentials and application credentials are managed independently, reducing blast radius of credential compromise
- **Operator tooling standardization**: A standardized Admin API enables portable CLIs and dashboards that work across any OJS backend
- **Rate limiting**: Admin operations (potentially expensive bulk queries) can be rate-limited independently without affecting data plane throughput

### Harder

- **Two API surfaces to maintain**: Implementations must design, document, and version two distinct API surfaces instead of one
- **Cross-cutting concerns**: Some operations span both planes (e.g., cancelling a job affects the data plane state but is initiated from the control plane), requiring careful coordination
- **Discovery and routing**: Clients and infrastructure must know how to reach both API surfaces, which may be deployed on different hosts or ports
