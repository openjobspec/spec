# ADR-008: Multi-Tenancy Isolation Models

## Status

Accepted

## Context

Multi-tenant job processing systems face two fundamental challenges: preventing noisy neighbors (one tenant's workload starving another's) and preventing data leakage (one tenant accessing another's job data). As OJS targets both single-tenant deployments and SaaS platforms running jobs on behalf of many customers, the spec must accommodate a range of isolation requirements.

Three isolation models exist in practice. Full namespace isolation gives each tenant a completely separate set of queues, storage, and worker pools — maximum isolation but highest cost. Shared infrastructure with logical isolation runs all tenants on the same queues and storage, using metadata tags to separate workloads — most cost-efficient but requires careful implementation to prevent leakage. Hybrid models mix both approaches, using namespace isolation for high-value tenants and shared infrastructure for the rest.

Different organizations have different requirements. A regulated financial platform may require full namespace isolation for audit and compliance reasons. A startup running a multi-tenant SaaS may prefer shared infrastructure to minimize costs. A growing platform may start shared and migrate specific tenants to dedicated namespaces as they scale. The spec needed to support all these scenarios without mandating a single approach.

## Decision

We support all three isolation models as a spectrum, allowing implementations and operators to choose the appropriate level of isolation for their requirements. The spec does not mandate a single multi-tenancy strategy; instead, it defines the building blocks that enable each model.

Namespace isolation is supported through the existing queue and namespace mechanisms — a tenant gets its own queues, and workers are bound to those queues exclusively. Shared infrastructure uses a `tenant_id` field in job metadata (not as a core job attribute) to tag jobs with their owning tenant. The hybrid model combines both: some tenants get dedicated namespaces while others share common infrastructure with `tenant_id`-based routing.

Tenant identification is deliberately placed in job metadata rather than as a first-class core attribute. This keeps the core spec lean for single-tenant deployments (the common case) while providing a standardized convention for multi-tenant systems. Implementations that support multi-tenancy SHOULD recognize `tenant_id` in metadata for routing, fairness scheduling, and access control.

## Consequences

### Easier

- **Flexible deployment**: Operators choose the isolation model that fits their security, compliance, and cost requirements
- **Gradual adoption**: Single-tenant deployments can add multi-tenancy later by introducing `tenant_id` metadata without schema changes
- **Cost optimization**: Shared infrastructure models avoid the overhead of per-tenant resource provisioning for low-risk workloads
- **Mixed workloads**: Hybrid models allow high-value tenants to get dedicated resources while long-tail tenants share infrastructure

### Harder

- **Shared model fairness**: Implementations using shared infrastructure must implement tenant-aware fair scheduling to prevent noisy neighbors, which adds scheduling complexity
- **Tenant-aware routing**: Backends must handle routing logic that inspects metadata to direct jobs to the correct tenant context
- **Inconsistent guarantees**: Different isolation models provide different security guarantees, requiring clear documentation for operators choosing between them
