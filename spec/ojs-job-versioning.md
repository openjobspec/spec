# Open Job Spec: Job Versioning and Schema Evolution

> **⚠️ EXPERIMENTAL**: This extension is under active development. The specification
> may change in breaking ways between versions. Implementations and SDKs that adopt
> this extension should expect migration work when the spec evolves. Feedback is
> encouraged via the OJS RFC process.

| Field        | Value                                                    |
|-------------|----------------------------------------------------------|
| **Title**   | OJS Job Versioning Specification                         |
| **Version** | 0.1.0                                                    |
| **Date**    | 2026-02-13                                               |
| **Status**  | Experimental                                             |
| **Tier**    | Experimental Extension                                   |
| **URI**     | `urn:ojs:ext:experimental:job-versioning`                |
| **Requires**| OJS Core Specification (Layer 1)                         |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [The Problem](#4-the-problem)
5. [Version Identifier](#5-version-identifier)
6. [Schema Declaration](#6-schema-declaration)
7. [Backward Compatibility Rules](#7-backward-compatibility-rules)
8. [Version Routing](#8-version-routing)
9. [Migration Strategies](#9-migration-strategies)
10. [Canary Deployments](#10-canary-deployments)
11. [HTTP Binding](#11-http-binding)
12. [Conformance Requirements](#12-conformance-requirements)
13. [Prior Art](#13-prior-art)
14. [Examples](#14-examples)
15. [Resolved Design Decisions](#15-resolved-design-decisions)

---

## 1. Introduction

Job versioning is the "sleeper requirement that causes the most production incidents" across background job processing systems. When job argument schemas change during rolling deployments, workers running old code receive jobs with new argument structures (and vice versa). The result is deserialization errors, null pointer exceptions, or silent data corruption when extra fields are ignored.

GitLab's Sidekiq documentation prescribes a three-release migration pattern for adding arguments. Temporal has iterated through four versioning approaches: GetVersion/Patch APIs, Build ID-based versioning, Assignment Rules, and Worker Deployments (v1.28.0+, 2025). The latest approach supports percentage-based canary rollouts. The fact that Temporal -- the most well-resourced workflow platform -- has redesigned versioning four times underscores how difficult this problem is.

This specification defines a versioning model for OJS jobs that addresses schema evolution, version routing, and canary deployments. As an experimental extension, the design is intentionally open to community feedback and iteration.

### 1.1 Scope

This specification defines:

- A version identifier scheme for job types.
- A schema declaration mechanism for job arguments.
- Backward compatibility rules and expectations.
- Version-based routing of jobs to compatible workers.
- Migration strategies for schema evolution.
- Canary deployment support for gradual handler rollout.

### 1.2 Design Principles

1. **Opt-in versioning.** Versioning is not mandatory. Jobs without version identifiers follow the existing OJS behavior (latest handler wins). This avoids imposing overhead on simple deployments.

2. **Producer-driven version.** The producer (enqueuer) stamps each job with the version of the argument schema it was built against. This is the only reliable source of truth because the producer knows what data it put in the job.

3. **Consumer compatibility declaration.** Workers declare which versions they can handle. The backend routes jobs to compatible workers.

4. **Graceful degradation.** When no version-compatible worker is available, the backend holds the job rather than delivering it to an incompatible worker. Silent failures are worse than delayed execution.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term                     | Definition                                                                                      |
|--------------------------|-------------------------------------------------------------------------------------------------|
| job version              | A label attached to a job indicating the schema version of its arguments.                       |
| schema version           | A SemVer-like version identifying the structure of a job type's arguments.                      |
| compatible worker        | A worker that has declared it can process a specific job version.                                |
| version range            | A constraint expression specifying which job versions a worker accepts (e.g., `>=1.0 <2.0`).   |
| rolling deployment       | A deployment strategy where old and new workers run simultaneously during the update.           |
| canary deployment        | A deployment strategy where a small percentage of traffic is routed to the new version.         |
| schema evolution         | The process of changing a job type's argument structure over time.                               |

---

## 4. The Problem

Consider a job type `invoice.generate` with this argument schema:

**Version 1**:
```json
{ "args": [{ "customer_id": "cust_123", "amount": 9999 }] }
```

During a deployment, the team adds a required `currency` field:

**Version 2**:
```json
{ "args": [{ "customer_id": "cust_123", "amount": 9999, "currency": "USD" }] }
```

During a rolling deployment, three failure modes occur:

1. **New producer → Old worker**: The old worker receives V2 args and ignores `currency`, generating invoices in the wrong currency.
2. **Old producer → New worker**: The new worker receives V1 args without `currency` and crashes with a missing field error.
3. **Stale jobs**: V1 jobs that were enqueued before the deployment but processed after it encounter V2 workers.

Without versioning, all three failure modes are possible in every deployment. With versioning, the system can route V1 jobs to V1-compatible workers and V2 jobs to V2-compatible workers.

---

## 5. Version Identifier

### 5.1 Format

Job versions use a simplified two-part version: `{major}.{minor}`.

- **Major**: Incremented for backward-incompatible changes (removing fields, changing types, changing semantics).
- **Minor**: Incremented for backward-compatible changes (adding optional fields, widening value ranges).

Full SemVer (major.minor.patch) is not used because patch-level changes should never affect argument schemas.

### 5.2 Attaching a Version to a Job

Producers MAY attach a version to a job using the `version` field in the job envelope:

```json
{
  "type": "invoice.generate",
  "version": "2.0",
  "args": [{ "customer_id": "cust_123", "amount": 9999, "currency": "USD" }]
}
```

When `version` is omitted, the job is treated as unversioned. Unversioned jobs are routable to any worker that handles the job type, regardless of version declarations.

### 5.3 Version in the Type Field

As an alternative to the separate `version` field, producers MAY encode the version in the job type using the `@` separator:

```json
{
  "type": "invoice.generate@2.0",
  "args": [{ "customer_id": "cust_123", "amount": 9999, "currency": "USD" }]
}
```

Implementations that support job versioning MUST parse the `@` separator and extract the version when present in the type field. The `version` field takes precedence over the type-embedded version if both are present.

---

## 6. Schema Declaration

### 6.1 Job Type Schema Registry

Implementations SHOULD support an optional schema registry where job type schemas are registered with their versions:

```http
PUT /ojs/v1/admin/schemas/invoice.generate/2.0
Content-Type: application/json

{
  "type": "invoice.generate",
  "version": "2.0",
  "args_schema": {
    "type": "array",
    "prefixItems": [
      {
        "type": "object",
        "required": ["customer_id", "amount", "currency"],
        "properties": {
          "customer_id": { "type": "string" },
          "amount": { "type": "integer" },
          "currency": { "type": "string", "pattern": "^[A-Z]{3}$" }
        }
      }
    ]
  },
  "compatible_with": ["1.0"]
}
```

### 6.2 Schema Validation on Enqueue

When a schema is registered for a job type + version, implementations SHOULD validate job arguments against the schema at enqueue time and reject jobs that do not match.

---

## 7. Backward Compatibility Rules

### 7.1 Minor Version Changes (Backward Compatible)

The following changes are considered backward compatible and SHOULD result in a minor version increment:

- **Adding an optional field** to the argument schema.
- **Widening a value constraint** (e.g., increasing a max length).
- **Adding a new enum value** to an existing enum field.
- **Adding a new element** to the args array at the end (when positional args are used).

Workers that declare compatibility with version N.x SHOULD be able to process any job with version N.y where y ≥ x.

### 7.2 Major Version Changes (Breaking)

The following changes are backward incompatible and MUST result in a major version increment:

- **Removing a field** from the argument schema.
- **Renaming a field**.
- **Changing a field's type** (e.g., string to integer).
- **Making an optional field required**.
- **Narrowing a value constraint** (e.g., reducing max length).
- **Changing the semantic meaning** of a field.

Workers MUST NOT process jobs with a different major version than they declare support for unless they explicitly declare a version range that spans multiple majors.

---

## 8. Version Routing

### 8.1 Worker Version Declaration

Workers declare version compatibility during registration or heartbeat:

```json
{
  "worker_id": "worker-01HXYZ",
  "handlers": [
    {
      "type": "invoice.generate",
      "versions": ">=1.0 <3.0"
    },
    {
      "type": "email.send",
      "versions": "*"
    }
  ]
}
```

The `versions` field accepts:

| Format          | Meaning                                           |
|-----------------|---------------------------------------------------|
| `"*"`           | Any version (including unversioned). Default.     |
| `"2.0"`         | Exactly version 2.0.                              |
| `">=1.0 <3.0"`  | Range: 1.0 or higher, below 3.0.                 |
| `">=2.0"`       | Version 2.0 or higher.                            |

### 8.2 Routing Semantics

When a versioned job is fetched:

1. The backend identifies the job's version.
2. The backend selects a worker whose version range for that job type includes the job's version.
3. If multiple compatible workers are available, normal selection rules apply (round-robin, least-loaded, etc.).
4. If no compatible worker is available, the job remains in `available` state and is not assigned.

When an unversioned job is fetched:

1. The job is routable to any worker that handles the type, regardless of version declarations.
2. Workers that declare specific version ranges SHOULD also accept unversioned jobs (for backward compatibility).

---

## 9. Migration Strategies

### 9.1 Expand-and-Contract

The recommended migration strategy for schema changes:

**Step 1: Expand** -- Deploy workers that handle both the old and new schema versions. Add new fields as optional in the handler code.

**Step 2: Migrate producers** -- Update producers to include the new fields and stamp the new version.

**Step 3: Drain** -- Wait for all old-version jobs to complete.

**Step 4: Contract** -- Deploy workers that only handle the new version. Remove old compatibility code.

This is the same three-phase pattern used by GitLab, documented in their Sidekiq migration guide.

### 9.2 Parallel Workers

For major version changes, deploy both V1 and V2 workers simultaneously:

```
V1 jobs → V1 workers (draining)
V2 jobs → V2 workers (ramping up)
```

The backend's version routing ensures each job reaches the correct worker. When all V1 jobs are complete, V1 workers can be decommissioned.

---

## 10. Canary Deployments

### 10.1 Percentage-Based Routing

Implementations MAY support percentage-based version routing for canary deployments:

```http
PUT /ojs/v1/admin/routing/invoice.generate
Content-Type: application/json

{
  "rules": [
    { "version": "2.0", "weight": 10 },
    { "version": "1.0", "weight": 90 }
  ]
}
```

This routes 10% of `invoice.generate` jobs to V2 workers and 90% to V1 workers, regardless of the job's own version. This enables testing new handler code with production traffic at low risk.

### 10.2 Automatic Rollback

Implementations MAY support automatic rollback based on error rates:

```json
{
  "rules": [
    { "version": "2.0", "weight": 10 },
    { "version": "1.0", "weight": 90 }
  ],
  "auto_rollback": {
    "error_rate_threshold": 0.05,
    "evaluation_window": "PT5M",
    "action": "route_all_to_previous"
  }
}
```

---

## 11. HTTP Binding

### 11.1 Schema Registration

```
PUT /ojs/v1/admin/schemas/{type}/{version}
```

Registers or updates a schema for a job type + version.

### 11.2 Schema Listing

```
GET /ojs/v1/admin/schemas/{type}
```

Lists all registered schema versions for a job type.

### 11.3 Routing Configuration

```
PUT /ojs/v1/admin/routing/{type}
GET /ojs/v1/admin/routing/{type}
```

Manages version routing rules for a job type.

---

## 12. Conformance Requirements

An implementation declaring support for the job-versioning extension MUST support:

| ID           | Requirement                                                                      |
|--------------|----------------------------------------------------------------------------------|
| VER-001      | Parse and store the `version` field on job envelopes.                            |
| VER-002      | Parse version from type field `@` separator.                                     |
| VER-003      | Accept worker version range declarations in heartbeat/registration.              |
| VER-004      | Route versioned jobs only to version-compatible workers.                          |
| VER-005      | Hold versioned jobs when no compatible worker is available.                       |
| VER-006      | Route unversioned jobs to any worker for the type.                               |

---

## 13. Prior Art

| System           | Versioning Approach                                                                       |
|------------------|-------------------------------------------------------------------------------------------|
| **Temporal**     | Four iterations: GetVersion → Patch → Build ID → Worker Deployments. Latest supports canary. |
| **GitLab/Sidekiq** | Documentation-prescribed three-release migration for argument changes.                   |
| **Celery**       | Task protocol versions (v1 → v2) for transport format. No argument schema versioning.     |
| **Kafka**        | Schema Registry (Avro/Protobuf/JSON Schema) with compatibility modes (BACKWARD, FORWARD, FULL). |
| **gRPC/Protobuf**| Wire format versioning via field numbers. Adding fields is always backward compatible.     |
| **GraphQL**      | Schema evolution via `@deprecated` directive. No breaking changes in the same version.    |

Kafka's Schema Registry model (centralized schema storage with compatibility checking) is the closest prior art for OJS job versioning. The key adaptation is that OJS schemas are simpler (JSON arrays, not Avro/Protobuf) and routing is per-worker rather than per-consumer-group.

---

## 14. Examples

### 14.1 Adding a Field (Minor Version)

```json
// V1 job (existing)
{
  "type": "invoice.generate",
  "version": "1.0",
  "args": [{ "customer_id": "cust_123", "amount": 9999 }]
}

// V1.1 job (new optional field)
{
  "type": "invoice.generate",
  "version": "1.1",
  "args": [{ "customer_id": "cust_123", "amount": 9999, "currency": "USD" }]
}
```

A worker declaring `"versions": ">=1.0 <2.0"` accepts both.

### 14.2 Breaking Change (Major Version)

```json
// V1 job (amount as cents integer)
{
  "type": "invoice.generate",
  "version": "1.0",
  "args": [{ "customer_id": "cust_123", "amount": 9999 }]
}

// V2 job (amount as decimal string with currency)
{
  "type": "invoice.generate",
  "version": "2.0",
  "args": [{ "customer_id": "cust_123", "amount": "99.99", "currency": "USD" }]
}
```

V1 and V2 workers run simultaneously until all V1 jobs drain.

### 14.3 Worker Registration with Version Ranges

```json
{
  "worker_id": "worker-new-deploy",
  "handlers": [
    { "type": "invoice.generate", "versions": ">=1.0 <3.0" },
    { "type": "email.send", "versions": "*" },
    { "type": "report.generate", "versions": "2.0" }
  ]
}
```

---

## 15. Resolved Design Decisions

The following design decisions were resolved during the experimental phase:

### 15.1 Version Range Syntax

**Question:** Should version ranges use SemVer range syntax or a simpler format?

**Decision:** Use a simplified `major.minor` format with range operators `>=`, `<`, and comma-separated constraints. Full SemVer range syntax (`^`, `~`) is NOT used. Example: `">=1.0, <2.0"`.

**Rationale:** Job versioning needs are simpler than package dependency management. A minimal syntax reduces parser complexity across all language SDKs.

### 15.2 Schema Registry Requirement

**Question:** Should the schema registry be optional or required?

**Decision:** The schema registry is OPTIONAL. Version routing MUST work without a registry (workers declare supported versions, backend routes by matching). A schema registry MAY be used for validation and documentation but is not required for conformance.

**Rationale:** Many teams version jobs informally and don't need centralized schema storage. Requiring a registry would be a barrier to adoption.

### 15.3 Versioned Jobs in Workflows

**Question:** How should versioned jobs interact with workflows?

**Decision:** Each job in a workflow carries its own version independently. Workflows MAY contain mixed-version jobs. Data passing between workflow steps MUST use the OJS JSON format, and the receiving step's handler is responsible for interpreting the data according to its own version.

**Rationale:** Forcing version homogeneity across a workflow would prevent incremental migration of individual steps.

### 15.4 Default Version Concept

**Question:** Should there be a "default version" concept?

**Decision:** Yes. When a producer does not specify a version, the job is considered "unversioned" and MUST be routable to any worker that handles that job type regardless of version constraints. Workers with version constraints MAY also accept unversioned jobs if configured to do so.

**Rationale:** This enables gradual migration to versioned jobs without requiring all producers to be updated simultaneously.

### 15.5 Job Versioning and Unique Jobs Interaction

**Question:** What is the interaction between job versioning and unique jobs?

**Decision:** `invoice.generate@1.0` and `invoice.generate@2.0` are considered DIFFERENT jobs for uniqueness purposes by default. The unique policy's dimensions array MAY include `"version"` to make version part of the uniqueness key, or exclude it to treat all versions as the same job.

**Rationale:** Explicit control gives operators the flexibility to handle both cases (rolling deployments where versions should dedup, and parallel versions where they shouldn't).

---

## Appendix A: Changelog

| Date       | Change                          |
|------------|---------------------------------|
| 2026-02-13 | Initial experimental release.   |
