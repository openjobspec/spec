# Open Job Spec -- Extension Lifecycle Specification

| Field        | Value                                            |
|-------------|--------------------------------------------------|
| **Title**   | OJS Extension Lifecycle                          |
| **Version** | 1.0.0-rc.1                                       |
| **Status**  | Release Candidate                                |
| **Date**    | 2026-02-13                                       |
| **Layer**   | Meta (cross-cutting governance)                  |
| **URI**     | https://openjobspec.org/spec/v1/ojs-extension-lifecycle |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Extension Tiers](#4-extension-tiers)
   - 4.1 [Core Specifications](#41-core-specifications)
   - 4.2 [Official Extensions](#42-official-extensions)
   - 4.3 [Experimental Extensions](#43-experimental-extensions)
5. [Extension Identification](#5-extension-identification)
6. [Promotion Criteria](#6-promotion-criteria)
   - 6.1 [Experimental to Official](#61-experimental-to-official)
   - 6.2 [Official to Core](#62-official-to-core)
   - 6.3 [Deprecation and Retirement](#63-deprecation-and-retirement)
7. [Manifest Declaration](#7-manifest-declaration)
8. [SDK and Backend Negotiation](#8-sdk-and-backend-negotiation)
9. [Community Extension Process](#9-community-extension-process)
10. [Prior Art](#10-prior-art)
11. [Examples](#11-examples)

---

## 1. Introduction

The Open Job Spec (OJS) is designed to be the most comprehensive standard for background job processing. However, comprehensiveness must not come at the cost of adoptability. A monolithic specification that requires every implementation to support every feature creates an impossibly high bar that discourages adoption.

This document defines the **Extension Lifecycle** -- a three-tier model that governs how OJS features are categorized, how implementations declare support for them, and how features progress from experimental community proposals to stable core requirements. The model is inspired by OpenTelemetry's per-component stability levels, Kubernetes' API versioning (alpha/beta/stable), and TC39's staged proposal process for JavaScript.

### 1.1 Goals

- Define a **clear tiering model** that separates mandatory core behavior from optional extensions.
- Enable **community-driven innovation** by allowing experimental extensions to be proposed, implemented, and iterated upon without waiting for spec committee approval.
- Provide a **well-defined promotion path** so that successful experimental extensions can become official, and universally adopted official extensions can become core requirements.
- Give **implementations and SDKs** a machine-readable mechanism to declare which extensions they support, at what stability level, enabling graceful feature negotiation.
- Prevent **specification bloat** by keeping the core lean while enabling the ecosystem to grow in breadth.

### 1.2 Scope

This specification defines:

- The three extension tiers (core, official, experimental) and their stability guarantees.
- The naming, identification, and versioning scheme for extensions.
- The criteria and process for promoting extensions between tiers.
- The manifest format for declaring extension support.
- The negotiation protocol for SDKs discovering backend extension support.

This specification does **not** define the content of any specific extension. Each extension is defined in its own companion specification document.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

Every MUST requirement includes a rationale explaining why the requirement is mandatory.

---

## 3. Terminology

| Term                   | Definition                                                                                          |
|------------------------|-----------------------------------------------------------------------------------------------------|
| extension              | A specification document that defines functionality beyond the core job envelope and lifecycle.      |
| tier                   | The stability classification of an extension: core, official, or experimental.                       |
| promotion              | The process of moving an extension from a lower tier to a higher tier (experimental → official → core). |
| deprecation            | The process of marking an extension as no longer recommended, with a defined sunset timeline.        |
| extension identifier   | A unique URI string that identifies an extension (e.g., `urn:ojs:ext:rate-limiting`).               |
| conformance level      | The numeric level (0-4) defined in ojs-conformance.md that groups feature sets.                     |
| capability negotiation | The process by which an SDK discovers which extensions a backend supports via the manifest.          |

---

## 4. Extension Tiers

OJS defines three tiers of specification documents, each with distinct stability guarantees, backward compatibility commitments, and governance requirements.

### 4.1 Core Specifications

**Stability: Stable. Breaking changes require a major version increment.**

Core specifications define the foundational behavior that every OJS implementation MUST support at the appropriate conformance level. They represent the non-negotiable contract between producers, consumers, and backends.

| Property               | Value                                                                     |
|------------------------|---------------------------------------------------------------------------|
| Stability guarantee    | No breaking changes within a major version                                |
| Backward compatibility | Full backward compatibility required                                      |
| Implementation         | MUST be implemented at the appropriate conformance level                  |
| Governance             | Changes require formal RFC process with community review                  |
| Examples               | ojs-core, ojs-json-format, ojs-http-binding, ojs-retry, ojs-conformance  |

Core specifications are the documents listed in the Companion Specifications table of ojs-core.md. An implementation declaring conformance at Level N MUST implement all core specifications required for that level, as defined in ojs-conformance.md.

**Rationale**: The core tier exists to guarantee a baseline of interoperability. Without a stable core, SDKs cannot depend on any server-side behavior, and the standard provides no value over ad hoc integration.

### 4.2 Official Extensions

**Stability: Stable. Breaking changes follow a deprecation cycle.**

Official extensions are opt-in specifications that have been vetted through the promotion process and carry stability guarantees. Implementations MAY choose to support zero, some, or all official extensions.

| Property               | Value                                                                     |
|------------------------|---------------------------------------------------------------------------|
| Stability guarantee    | No breaking changes without at least one spec version deprecation cycle   |
| Backward compatibility | Backward compatible within a major version; deprecated features sunset in the next major |
| Implementation         | OPTIONAL -- implementations declare support via manifest                  |
| Governance             | Maintained by the OJS working group; changes require RFC                  |
| Promotion from         | Experimental tier, after meeting promotion criteria (Section 6.1)         |
| Examples               | ojs-rate-limiting, ojs-admin-api                                          |

When an implementation supports an official extension, it MUST implement the full specification for that extension. Partial implementations MUST NOT declare support for an official extension.

**Rationale**: "Partial support" for a spec-defined feature is worse than no support because it creates false confidence. If a client discovers that a backend "supports" rate limiting but only implements per-queue limits (not per-key), the client cannot trust the feature declaration. Requiring full implementation ensures that the extension identifier is a reliable signal.

### 4.3 Experimental Extensions

**Stability: Unstable. May change or be removed without notice.**

Experimental extensions are community-proposed specifications that are under active development. They provide a structured way for the community to innovate, prototype, and iterate on new features before committing to stability guarantees.

| Property               | Value                                                                     |
|------------------------|---------------------------------------------------------------------------|
| Stability guarantee    | None. The spec MAY change in breaking ways between any two versions.      |
| Backward compatibility | Not guaranteed                                                            |
| Implementation         | OPTIONAL -- implementations declare support via manifest                  |
| Governance             | Maintained by the proposing author(s); reviewed by the working group      |
| Promotion to           | Official tier, after meeting promotion criteria (Section 6.1)             |
| Examples               | ojs-job-versioning, ojs-multi-tenancy                                     |

Implementations that support an experimental extension MUST clearly communicate the experimental nature to users. SDKs that interact with experimental extensions SHOULD log a warning on first use.

**Rationale**: Every successful open standard provides a mechanism for community innovation without destabilizing the core. Kubernetes uses alpha/beta API versions. TC39 uses Stage 0-4 proposals. OpenTelemetry uses per-component stability levels. Without an experimental tier, OJS would face a choice between two bad outcomes: blocking all innovation until the working group approves it (slow, discouraging), or allowing unstable features to masquerade as stable (dangerous, fragmenting).

Experimental extensions MUST include a clear warning at the top of the specification document:

```
> **⚠️ EXPERIMENTAL**: This extension is under active development. The specification
> may change in breaking ways between versions. Implementations and SDKs that adopt
> this extension should expect migration work when the spec evolves. Feedback is
> encouraged via the OJS RFC process.
```

---

## 5. Extension Identification

### 5.1 Extension URIs

Every extension MUST have a unique identifier expressed as a URN.

**Format**:

| Tier         | URI Pattern                                      | Example                              |
|--------------|--------------------------------------------------|--------------------------------------|
| Core         | `urn:ojs:spec:{name}`                            | `urn:ojs:spec:retry`                 |
| Official     | `urn:ojs:ext:{name}`                             | `urn:ojs:ext:rate-limiting`          |
| Experimental | `urn:ojs:ext:experimental:{name}`                | `urn:ojs:ext:experimental:job-versioning` |

**Rationale**: URN-based identifiers provide globally unique, protocol-independent names that are safe for use in manifests, headers, logs, and configuration files. The tier is embedded in the URI structure so that any consumer can immediately determine the stability level without looking up metadata.

### 5.2 Extension Names

Extension names MUST be lowercase, hyphen-separated strings matching the pattern `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`.

**Rationale**: Consistent naming prevents case-sensitivity bugs and ensures names are safe for use in URLs, file paths, environment variables (with underscore substitution), and metric labels.

### 5.3 Extension Versioning

Each extension specification MUST declare its own version using Semantic Versioning (SemVer 2.0).

- **Core and official extensions**: MUST follow SemVer strictly. A breaking change requires a major version increment.
- **Experimental extensions**: SHOULD follow SemVer, but breaking changes MAY occur in minor versions (0.x.y). This matches the SemVer convention that 0.x versions have no stability guarantees.

The extension version is independent of the OJS core specification version. An extension at version 2.1.0 may be used with OJS core 1.0.

---

## 6. Promotion Criteria

### 6.1 Experimental to Official

An experimental extension MAY be promoted to official status when ALL of the following criteria are met:

1. **Two independent implementations**: The extension MUST have been implemented by at least two independent implementations in different programming languages or using different backends. This proves the specification is language-agnostic and backend-agnostic.

2. **Conformance tests**: The extension MUST have a conformance test suite following the format defined in ojs-conformance.md. Both implementations MUST pass the test suite.

3. **Community review period**: The extension MUST have completed a minimum 8-week community review period with no unresolved blocking issues.

4. **Stability period**: The extension specification MUST have had no breaking changes for at least 4 consecutive weeks before the promotion vote.

5. **RFC approval**: An RFC proposing the promotion MUST be submitted and approved through the standard RFC process as defined in CONTRIBUTING.md.

6. **Documentation**: The extension MUST include complete specification text, at least three worked examples, and an implementation guide.

**Rationale**: These criteria are drawn from the governance models of successful open standards. OpenTelemetry requires working prototypes in two languages before OTEP acceptance. GraphQL requires champion-led proposals with working implementations. The two-implementation rule is the minimum needed to prove that a spec is not unconsciously biased toward one language's idioms. The stability and review periods prevent premature promotion of specs that are still actively changing.

### 6.2 Official to Core

An official extension MAY be promoted to core (meaning it becomes REQUIRED at a specific conformance level) when ALL of the following criteria are met:

1. **Universal adoption**: The extension MUST be implemented by at least 80% of actively maintained OJS implementations. This threshold proves that the community considers the feature essential.

2. **Production validation**: The extension MUST have been deployed in production by at least three independent organizations for a minimum of 6 months.

3. **Conformance level assignment**: The promotion RFC MUST specify which conformance level (0-4) the extension's requirements will be assigned to.

4. **Backward compatibility**: The promotion MUST NOT break any existing conformant implementation. Implementations that do not yet support the newly promoted feature MUST be given at least one OJS major version cycle to add support.

5. **Working group consensus**: Promotion to core requires consensus approval from the OJS working group, not simple majority.

**Rationale**: Promoting an extension to core is the highest-impact specification change possible because it increases the requirements for all implementations. The 80% adoption threshold ensures that the feature is genuinely universal rather than desired by a vocal minority. The backward compatibility requirement prevents surprise failures in production deployments.

### 6.3 Deprecation and Retirement

Extensions may be deprecated and eventually retired:

1. **Deprecation notice**: A deprecated extension MUST be marked with a deprecation notice in its specification document, including the deprecation date and the recommended replacement (if any).

2. **Sunset period**: A deprecated official extension MUST remain supported for at least one OJS major version cycle after deprecation. Experimental extensions MAY be retired immediately.

3. **Manifest signaling**: Implementations SHOULD include deprecated extensions in their manifest with a `deprecated: true` flag to aid client migration.

4. **Removal**: After the sunset period, a deprecated extension MAY be removed from the specification. The extension URI MUST NOT be reassigned to a different extension.

**Rationale**: The "never reassign URIs" rule prevents a class of subtle bugs where a client designed for the old extension accidentally uses the new, unrelated extension that reused the same identifier.

---

## 7. Manifest Declaration

### 7.1 Extension Declaration Format

Implementations declare their extension support in the conformance manifest (exposed at `GET /ojs/manifest`). The `extensions` field is structured to convey both the extension identity and its tier:

```json
{
  "specversion": "1.0",
  "implementation": {
    "name": "ojs-redis",
    "version": "1.0.0",
    "language": "go"
  },
  "conformance_level": 4,
  "conformance_tier": "runtime",
  "protocols": ["http"],
  "backend": "redis",
  "capabilities": {
    "batch_enqueue": true,
    "rate_limiting": true,
    "unique_jobs": true,
    "workflows": true
  },
  "extensions": {
    "official": [
      {
        "name": "rate-limiting",
        "uri": "urn:ojs:ext:rate-limiting",
        "version": "1.0.0"
      },
      {
        "name": "admin-api",
        "uri": "urn:ojs:ext:admin-api",
        "version": "1.0.0"
      }
    ],
    "experimental": [
      {
        "name": "job-versioning",
        "uri": "urn:ojs:ext:experimental:job-versioning",
        "version": "0.1.0"
      }
    ]
  }
}
```

### 7.2 Extension Object Fields

Each extension entry in the manifest MUST contain:

| Field     | Type   | Required | Description                                                    |
|-----------|--------|----------|----------------------------------------------------------------|
| `name`    | string | Yes      | The extension name (matches the name segment of the URI).      |
| `uri`     | string | Yes      | The full extension URI (e.g., `urn:ojs:ext:rate-limiting`).    |
| `version` | string | Yes      | The SemVer version of the extension specification implemented. |

An implementation MUST NOT declare support for an extension it does not fully implement.

**Rationale**: Including the version alongside the URI enables clients to detect version mismatches. A client built against rate-limiting v2.0 can detect that the server implements v1.0 and adapt accordingly, rather than encountering mysterious runtime failures.

### 7.3 Backward Compatibility

For backward compatibility with implementations that predate this specification, the `extensions` field MAY also accept the legacy format (a flat array of strings). Consumers MUST handle both formats:

```json
{
  "extensions": ["bulk_purge", "queue_migration"]
}
```

When encountering the legacy format, consumers SHOULD treat all listed extensions as unofficial (neither official nor experimental) custom extensions specific to that implementation.

---

## 8. SDK and Backend Negotiation

### 8.1 Discovery

SDKs SHOULD query the backend's manifest endpoint on initialization to discover supported extensions. This enables the SDK to:

1. **Enable features**: Automatically enable extension-specific client functionality when the backend supports it.
2. **Warn on gaps**: Log a warning when the SDK requires an extension the backend does not support.
3. **Degrade gracefully**: Fall back to core-only behavior when optional extensions are unavailable.

### 8.2 Negotiation Protocol

The negotiation protocol is as follows:

1. The SDK sends `GET /ojs/manifest`.
2. The backend responds with the conformance manifest including extension declarations.
3. The SDK compares the backend's declared extensions against the SDK's known extensions.
4. For each extension the SDK wants to use:
   - If the backend declares support: the SDK enables the feature.
   - If the backend does not declare support: the SDK disables the feature and SHOULD log a message at `INFO` level.
   - If the backend declares an experimental extension the SDK supports: the SDK enables the feature and SHOULD log a warning noting the experimental status.

### 8.3 Extension Requirement Headers

When an SDK makes a request that depends on a specific extension, it SHOULD include the `OJS-Requires-Extension` header:

```http
POST /ojs/v1/jobs HTTP/1.1
Content-Type: application/openjobspec+json
OJS-Requires-Extension: urn:ojs:ext:rate-limiting

{
  "type": "api.call",
  "args": ["https://api.example.com/data"],
  "rate_limit": {
    "key": "api.example.com",
    "max_per_second": 10
  }
}
```

If the backend does not support the declared extension, it SHOULD respond with:

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "error": {
    "code": "EXTENSION_NOT_SUPPORTED",
    "message": "Extension 'urn:ojs:ext:rate-limiting' is not supported by this implementation",
    "extension": "urn:ojs:ext:rate-limiting"
  }
}
```

**Rationale**: Explicit extension requirement headers provide a fail-fast mechanism. Without them, the backend might silently ignore extension-specific fields (like `rate_limit`), and the client would believe rate limiting is active when it is not. This is the "silent failure" anti-pattern that has caused production incidents in every job processing system.

---

## 9. Community Extension Process

### 9.1 Proposing an Experimental Extension

Any community member MAY propose a new experimental extension by following this process:

1. **Open an RFC**: Submit an RFC following the template in `spec/rfcs/RFC-0000-template.md` with:
   - Problem statement and motivation
   - Proposed extension name and URI
   - Draft specification text
   - At least one worked example
   - Prior art survey (how do existing systems handle this?)

2. **Discussion period**: The RFC MUST be open for community discussion for at least 2 weeks.

3. **Prototype requirement**: Before the RFC can be accepted, the proposer MUST demonstrate a working prototype in at least one language. The prototype need not be production-quality, but it must prove that the specification is implementable.

4. **Working group review**: The OJS working group reviews the RFC and either:
   - **Accepts**: The extension is assigned an experimental URI and its specification is published under `spec/spec/ojs-{name}.md`.
   - **Requests changes**: The proposer revises and resubmits.
   - **Rejects**: With a written rationale. Rejected RFCs MAY be resubmitted with substantial changes.

### 9.2 Custom (Non-OJS) Extensions

Implementations MAY support custom extensions that are not part of the OJS specification. Custom extensions:

- MUST use the URI pattern `urn:ojs:ext:x:{vendor}:{name}` (the `x:` prefix denotes non-standard).
- MUST NOT use the `urn:ojs:ext:` or `urn:ojs:spec:` namespaces without the `x:` prefix.
- SHOULD be documented by the implementation.
- MAY be proposed for inclusion in the OJS specification via the RFC process.

**Example**: `urn:ojs:ext:x:acme:gpu-scheduling` for a vendor-specific GPU job scheduling extension.

**Rationale**: The `x:` prefix convention is borrowed from HTTP headers (now deprecated there, but useful in namespaced URIs) and MIME types. It provides a clear signal that the extension is not part of the standard, preventing confusion when clients encounter unknown extensions.

---

## 10. Prior Art

The extension lifecycle model draws from several successful open standards:

| Standard         | Model                                         | Lesson Applied                                                |
|------------------|-----------------------------------------------|---------------------------------------------------------------|
| **OpenTelemetry** | Per-component stability: Development → Alpha → Beta → Stable | Granular stability labels enable rapid ecosystem growth        |
| **Kubernetes**   | API versioning: v1alpha1 → v1beta1 → v1       | Structured progression prevents premature stability promises   |
| **TC39**         | Stage 0 → Stage 4 for JavaScript proposals    | Champion-led proposals with working implementations            |
| **Rust RFC**     | RFC process with FCP (Final Comment Period)    | Time-bounded review prevents indefinite bikeshedding           |
| **CloudEvents**  | Core + wire formats + protocol bindings        | Layered architecture separates stable core from evolving edges |

---

## 11. Examples

### 11.1 Extension Tier Summary

The following table shows the current classification of OJS specifications:

| Specification                | Tier         | URI                                            | Conformance Level |
|-----------------------------|--------------|------------------------------------------------|-------------------|
| ojs-core                    | Core         | `urn:ojs:spec:core`                            | 0                 |
| ojs-json-format             | Core         | `urn:ojs:spec:json-format`                     | 0                 |
| ojs-http-binding            | Core         | `urn:ojs:spec:http-binding`                    | 0                 |
| ojs-grpc-binding            | Core         | `urn:ojs:spec:grpc-binding`                    | --                |
| ojs-retry                   | Core         | `urn:ojs:spec:retry`                           | 1                 |
| ojs-worker-protocol         | Core         | `urn:ojs:spec:worker-protocol`                 | 1                 |
| ojs-events                  | Core         | `urn:ojs:spec:events`                          | 0                 |
| ojs-middleware              | Core         | `urn:ojs:spec:middleware`                       | 0                 |
| ojs-cron                    | Core         | `urn:ojs:spec:cron`                            | 2                 |
| ojs-workflows               | Core         | `urn:ojs:spec:workflows`                       | 3                 |
| ojs-unique-jobs             | Core         | `urn:ojs:spec:unique-jobs`                     | 4                 |
| ojs-conformance             | Core         | `urn:ojs:spec:conformance`                     | 0                 |
| ojs-extension-lifecycle     | Core         | `urn:ojs:spec:extension-lifecycle`             | --                |
| ojs-rate-limiting           | Official     | `urn:ojs:ext:rate-limiting`                    | 4                 |
| ojs-admin-api               | Official     | `urn:ojs:ext:admin-api`                        | --                |
| ojs-testing                 | Official     | `urn:ojs:ext:testing`                          | --                |
| ojs-observability           | Official     | `urn:ojs:ext:observability`                    | --                |
| ojs-backpressure            | Official     | `urn:ojs:ext:backpressure`                     | --                |
| ojs-graceful-shutdown       | Official     | `urn:ojs:ext:graceful-shutdown`                | --                |
| ojs-dead-letter             | Official     | `urn:ojs:ext:dead-letter`                      | 1                 |
| ojs-job-versioning          | Experimental | `urn:ojs:ext:experimental:job-versioning`      | --                |
| ojs-multi-tenancy           | Experimental | `urn:ojs:ext:experimental:multi-tenancy`       | --                |
| ojs-encryption              | Experimental | `urn:ojs:ext:experimental:encryption`          | --                |
| ojs-framework-adapters      | Experimental | `urn:ojs:ext:experimental:framework-adapters`  | --                |

### 11.2 Full Manifest Example

```json
{
  "specversion": "1.0",
  "implementation": {
    "name": "acme-jobs",
    "version": "2.3.0",
    "language": "go",
    "repository": "https://github.com/acme/acme-jobs"
  },
  "conformance_level": 4,
  "conformance_tier": "full",
  "protocols": ["http", "grpc"],
  "backend": "postgres",
  "capabilities": {
    "batch_enqueue": true,
    "cron_jobs": true,
    "dead_letter": true,
    "delayed_jobs": true,
    "job_ttl": true,
    "priority_queues": true,
    "rate_limiting": true,
    "schema_validation": true,
    "unique_jobs": true,
    "workflows": true,
    "pause_resume": true
  },
  "extensions": {
    "official": [
      {
        "name": "rate-limiting",
        "uri": "urn:ojs:ext:rate-limiting",
        "version": "1.0.0"
      },
      {
        "name": "admin-api",
        "uri": "urn:ojs:ext:admin-api",
        "version": "1.0.0"
      }
    ],
    "experimental": [
      {
        "name": "multi-tenancy",
        "uri": "urn:ojs:ext:experimental:multi-tenancy",
        "version": "0.2.0"
      }
    ]
  },
  "test_suite_version": "1.0.0",
  "test_suite_passed_at": "2026-02-13T10:00:00Z"
}
```

### 11.3 SDK Negotiation Example (JavaScript)

```javascript
import { OJSClient } from '@openjobspec/client';

const client = new OJSClient({ url: 'http://localhost:8080' });

// The client automatically queries GET /ojs/manifest on init.
// If the backend supports rate-limiting, the client enables it:

const job = await client.enqueue('api.call', ['https://api.example.com'], {
  rateLimit: { key: 'api.example.com', maxPerSecond: 10 }
});
// If the backend does NOT support rate-limiting, the client throws:
// Error: Extension 'urn:ojs:ext:rate-limiting' is not supported.
// Use client.enqueue() without rateLimit, or connect to a backend
// that supports the rate-limiting extension.
```

### 11.4 SDK Negotiation Example (Go)

```go
client, err := ojs.NewClient("http://localhost:8080")
if err != nil {
    log.Fatal(err)
}

// Check extension support before using it
if client.SupportsExtension("urn:ojs:ext:rate-limiting") {
    job, err := client.Enqueue(ctx, "api.call",
        ojs.Args{"url": "https://api.example.com"},
        ojs.WithRateLimit("api.example.com", 10),
    )
}

// List all supported extensions
for _, ext := range client.Extensions() {
    fmt.Printf("%s (%s) v%s\n", ext.Name, ext.Tier, ext.Version)
}
```

---

## Appendix A: Extension Tier Decision Flowchart

```
Is the feature required for basic job processing interoperability?
  ├── YES → Core specification (MUST at some conformance level)
  └── NO
      ├── Has it been implemented in 2+ languages with conformance tests?
      │   ├── YES → Official extension (opt-in, stable)
      │   └── NO
      │       ├── Is there a working prototype and community interest?
      │       │   ├── YES → Experimental extension (opt-in, unstable)
      │       │   └── NO → Not yet ready for specification (use custom x: extension)
      │       └──
      └──
```

## Appendix B: Changelog

| Date       | Change                        |
|------------|-------------------------------|
| 2026-02-13 | Initial release candidate.    |
