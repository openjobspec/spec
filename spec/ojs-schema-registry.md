# Open Job Spec: Schema Registry Extension

> **⚠️ EXPERIMENTAL**: This extension is under active development. The specification
> may change in breaking ways between versions. Implementations and SDKs that adopt
> this extension should expect migration work when the spec evolves. Feedback is
> encouraged via the OJS RFC process.

| Field        | Value                                                    |
|-------------|----------------------------------------------------------|
| **Title**   | OJS Schema Registry                                      |
| **Version** | 0.1.0                                                    |
| **Date**    | 2026-02-19                                               |
| **Status**  | Draft                                                    |
| **Maturity** | Experimental                                             |
| **Layer**   | Extension                                                |
| **URI**     | `urn:ojs:ext:experimental:schema-registry`               |
| **Requires**| OJS Core Specification (Layer 1), OJS Job Versioning     |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Schema Registration API](#4-schema-registration-api)
5. [Schema Format](#5-schema-format)
6. [Version Semantics](#6-version-semantics)
7. [Validation Modes](#7-validation-modes)
8. [Breaking Change Detection](#8-breaking-change-detection)
9. [Worker Version Routing](#9-worker-version-routing)
10. [HTTP Binding](#10-http-binding)
11. [Conformance Requirements](#11-conformance-requirements)
12. [Prior Art](#12-prior-art)
13. [Examples](#13-examples)

---

## 1. Introduction

The OJS Job Versioning specification defines how job types evolve over time and how versioned jobs are routed to compatible workers. However, versioning alone does not solve schema management at scale: teams need a central registry to store, discover, and validate schemas for job arguments.

Kafka's Schema Registry has proven that centralized schema storage with compatibility checking prevents schema drift and enables safe evolution. This specification brings that pattern to OJS, adapted for the simpler JSON-based job argument model.

A schema registry enables:

- **Validation at enqueue time**: Reject jobs with invalid arguments before they enter the queue, catching errors early.
- **Schema discovery**: Workers and producers can discover the expected argument structure for any job type.
- **Compatibility enforcement**: The registry can reject schema registrations that introduce breaking changes.
- **Version catalog**: A single source of truth for all versions of a job type's argument schema.

### 1.1 Scope

This specification defines:

- An HTTP API for registering, retrieving, and listing job type schemas.
- The schema format (JSON Schema draft 2020-12) for argument validation.
- Version semantics using SemVer for job types.
- Validation modes controlling how invalid arguments are handled.
- Breaking change detection rules.
- Integration with worker version routing from the Job Versioning extension.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term                     | Definition                                                                                      |
|--------------------------|-------------------------------------------------------------------------------------------------|
| schema                   | A JSON Schema document describing the expected structure of a job type's `args` field.          |
| schema registry          | A centralized store for job type schemas, indexed by job type and version.                       |
| schema version           | A SemVer string identifying a specific revision of a job type's argument schema.                |
| validation mode          | A configuration controlling how the backend responds to argument validation failures.            |
| breaking change          | A schema modification that is not backward compatible with the previous version.                 |
| compatible version       | A schema version that can process arguments from an earlier version without errors.              |

---

## 4. Schema Registration API

### 4.1 Register a Schema

Producers or operators register a schema for a job type and version:

```http
POST /ojs/v1/schemas
Content-Type: application/json

{
  "job_type": "invoice.generate",
  "version": "2.0.0",
  "schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["customer_id", "amount", "currency"],
    "properties": {
      "customer_id": { "type": "string" },
      "amount": { "type": "integer", "minimum": 0 },
      "currency": { "type": "string", "pattern": "^[A-Z]{3}$" }
    },
    "additionalProperties": false
  }
}
```

**Response** (201 Created):
```json
{
  "schema": {
    "job_type": "invoice.generate",
    "version": "2.0.0",
    "schema": { "..." },
    "created_at": "2026-02-19T12:00:00.000Z"
  }
}
```

Implementations MUST validate that the `schema` field is a valid JSON Schema document before storing it.

If a schema with the same job type and version already exists, the implementation MUST return a `409 Conflict` error.

### 4.2 Get Latest Schema

Retrieve the latest registered schema for a job type:

```http
GET /ojs/v1/schemas/{type}
```

**Response** (200 OK):
```json
{
  "schema": {
    "job_type": "invoice.generate",
    "version": "2.0.0",
    "schema": { "..." },
    "created_at": "2026-02-19T12:00:00.000Z"
  }
}
```

If no schema is registered for the job type, the implementation MUST return a `404 Not Found` error.

### 4.3 List Schema Versions

List all registered versions for a job type, ordered by version (newest first):

```http
GET /ojs/v1/schemas/{type}/versions
```

**Response** (200 OK):
```json
{
  "versions": [
    { "version": "2.0.0", "created_at": "2026-02-19T12:00:00.000Z", "is_latest": true },
    { "version": "1.1.0", "created_at": "2026-02-01T10:00:00.000Z", "is_latest": false },
    { "version": "1.0.0", "created_at": "2026-01-15T09:00:00.000Z", "is_latest": false }
  ]
}
```

### 4.4 Delete a Schema Version

Remove a specific schema version:

```http
DELETE /ojs/v1/schemas/{type}/{version}
```

Implementations SHOULD prevent deletion of a schema version if active workers are currently declaring compatibility with that version.

---

## 5. Schema Format

### 5.1 JSON Schema Draft 2020-12

All schemas MUST be valid [JSON Schema draft 2020-12](https://json-schema.org/draft/2020-12/json-schema-core) documents. This is the most widely supported JSON Schema version across languages and provides features needed for job argument validation:

- `required` for mandatory fields
- `properties` for field type declarations
- `additionalProperties` for controlling extensibility
- `$ref` for schema composition (OPTIONAL support)

### 5.2 Schema Target

The schema applies to the `args` field of the job envelope. When validating a job, the implementation extracts the `args` field and validates it against the registered schema.

```json
{
  "type": "invoice.generate",
  "version": "2.0.0",
  "args": { "customer_id": "cust_123", "amount": 9999, "currency": "USD" }
}
```

The schema for `invoice.generate@2.0.0` validates the value of `args`, not the entire job envelope.

---

## 6. Version Semantics

### 6.1 SemVer for Job Types

Schema versions use [Semantic Versioning 2.0.0](https://semver.org/) with the format `{major}.{minor}.{patch}`:

- **Major**: Backward-incompatible changes (required field additions, type changes, field removals).
- **Minor**: Backward-compatible additions (new optional fields, widened constraints).
- **Patch**: Non-structural changes (description updates, documentation).

### 6.2 Default Routing to Latest Compatible Version

When a job is enqueued without an explicit version, the backend SHOULD route it to a worker that supports the latest registered schema version for that job type.

When a job specifies a version, the backend MUST route it to a worker that declares compatibility with that specific version (per the Job Versioning specification).

### 6.3 Version Ordering

Versions MUST be compared using SemVer precedence rules. The "latest" version is the one with the highest SemVer precedence among all registered versions.

---

## 7. Validation Modes

### 7.1 Configuration

Validation mode is configured per job type or globally:

```json
{
  "validation": {
    "mode": "strict",
    "default_mode": "warn"
  }
}
```

### 7.2 Modes

| Mode     | Behavior                                                                              |
|----------|---------------------------------------------------------------------------------------|
| `strict` | Reject jobs with invalid arguments. Return a `422 Unprocessable Entity` error.       |
| `warn`   | Accept the job but log a validation warning. Include warnings in the response.        |
| `off`    | No validation. Schemas are stored for documentation purposes only.                    |

The default mode SHOULD be `warn` to enable gradual adoption without breaking existing producers.

### 7.3 Validation Response

In `strict` mode, an invalid job receives:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Job arguments do not match schema for invoice.generate@2.0.0.",
    "details": {
      "validation_errors": [
        "required property 'currency' is missing",
        "property 'amount' must be integer, got string"
      ]
    }
  }
}
```

In `warn` mode, the job is accepted with warnings in the response:

```json
{
  "job": { "..." },
  "warnings": [
    "Schema validation warning: required property 'currency' is missing"
  ]
}
```

---

## 8. Breaking Change Detection

### 8.1 Automatic Detection

When a new schema version is registered, the implementation SHOULD compare it against the previous version and detect breaking changes.

### 8.2 Breaking Changes

The following changes are considered breaking (require a major version bump):

| Change                          | Example                                                  |
|---------------------------------|----------------------------------------------------------|
| Adding a required field         | Adding `"currency"` to `required` array                  |
| Removing a field                | Removing `"amount"` from `properties`                    |
| Changing a field's type         | `"amount": integer` → `"amount": string`                 |
| Narrowing a constraint          | `"maxLength": 100` → `"maxLength": 50`                   |
| Setting `additionalProperties: false` | When previously `true` or absent                  |

### 8.3 Non-Breaking Changes

The following changes are considered non-breaking (minor version bump):

| Change                          | Example                                                  |
|---------------------------------|----------------------------------------------------------|
| Adding an optional field        | Adding `"notes"` to `properties` without `required`      |
| Widening a constraint           | `"maxLength": 50` → `"maxLength": 100`                   |
| Adding a new enum value         | `["USD", "EUR"]` → `["USD", "EUR", "GBP"]`               |
| Relaxing `additionalProperties` | `false` → `true`                                          |

### 8.4 Enforcement

When a non-major version bump introduces a breaking change, the registry SHOULD reject the registration with a descriptive error:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Schema version 1.2.0 introduces breaking changes compared to 1.1.0. Use a major version bump (2.0.0).",
    "details": {
      "breaking_changes": [
        "Required field 'currency' was added"
      ]
    }
  }
}
```

---

## 9. Worker Version Routing

### 9.1 Integration with Job Versioning

The schema registry integrates with the Worker Version Routing defined in the Job Versioning specification. Workers declare which schema versions they support:

```json
{
  "worker_id": "worker-01HXYZ",
  "handlers": [
    {
      "type": "invoice.generate",
      "versions": ">=1.0.0 <3.0.0"
    }
  ]
}
```

### 9.2 Routing Behavior

When a versioned job is fetched:

1. The backend identifies the job's version.
2. The backend selects a worker whose declared version range includes the job's version.
3. If no compatible worker is available, the job remains in `available` state.

When an unversioned job is fetched:

1. If a schema registry is configured, the backend MAY resolve the job to the latest registered version.
2. The job is routable to any worker that handles the type.

---

## 10. HTTP Binding

| Method | Path                                    | Description                                  |
|--------|-----------------------------------------|----------------------------------------------|
| POST   | `/ojs/v1/schemas`                       | Register a new schema.                       |
| GET    | `/ojs/v1/schemas/{type}`                | Get latest schema for a job type.            |
| GET    | `/ojs/v1/schemas/{type}/versions`       | List all versions for a job type.            |
| DELETE | `/ojs/v1/schemas/{type}/{version}`      | Delete a specific schema version.            |

---

## 11. Conformance Requirements

An implementation declaring support for the schema-registry extension MUST support:

| ID           | Requirement                                                                      |
|--------------|----------------------------------------------------------------------------------|
| SR-001       | Register schemas with job type, version, and JSON Schema document.               |
| SR-002       | Retrieve the latest schema for a job type.                                       |
| SR-003       | List all registered versions for a job type.                                     |
| SR-004       | Delete a schema version.                                                         |
| SR-005       | Validate that registered schemas are valid JSON Schema documents.                |
| SR-006       | Reject duplicate registrations (same type + version) with 409 Conflict.          |

Recommended:

| ID           | Requirement                                                                      |
|--------------|----------------------------------------------------------------------------------|
| SR-R001      | Validate job arguments against registered schemas at enqueue time.               |
| SR-R002      | Support configurable validation modes (strict, warn, off).                       |
| SR-R003      | Detect breaking changes on schema registration.                                  |
| SR-R004      | Integrate with worker version routing.                                           |

---

## 12. Prior Art

| System              | Schema Approach                                                                          |
|---------------------|------------------------------------------------------------------------------------------|
| **Kafka**           | Schema Registry (Avro/Protobuf/JSON Schema) with BACKWARD, FORWARD, FULL modes.         |
| **Temporal**        | No schema registry. Versioning handled via Build ID and Worker Deployments.              |
| **AWS EventBridge** | Schema Registry with automatic schema discovery from events.                             |
| **gRPC/Protobuf**   | `.proto` files as schemas with field number-based compatibility.                         |
| **GraphQL**         | Introspection schema with `@deprecated` directive for evolution.                         |

Kafka's Schema Registry is the closest prior art. OJS adapts the concept for JSON Schema (instead of Avro) and simplifies the compatibility modes to match the job processing use case.

---

## 13. Examples

### 13.1 Registering a Schema

```http
POST /ojs/v1/schemas
Content-Type: application/json

{
  "job_type": "email.send",
  "version": "1.0.0",
  "schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["to", "subject", "body"],
    "properties": {
      "to": { "type": "string", "format": "email" },
      "subject": { "type": "string", "maxLength": 200 },
      "body": { "type": "string" }
    }
  }
}
```

### 13.2 Adding an Optional Field (Minor Version)

```http
POST /ojs/v1/schemas
Content-Type: application/json

{
  "job_type": "email.send",
  "version": "1.1.0",
  "schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["to", "subject", "body"],
    "properties": {
      "to": { "type": "string", "format": "email" },
      "subject": { "type": "string", "maxLength": 200 },
      "body": { "type": "string" },
      "cc": { "type": "array", "items": { "type": "string", "format": "email" } }
    }
  }
}
```

### 13.3 Strict Validation Rejection

```http
POST /ojs/v1/jobs
Content-Type: application/json

{
  "type": "email.send",
  "version": "1.0.0",
  "args": { "to": "not-an-email", "subject": "Hello" }
}
```

Response (422):
```json
{
  "error": {
    "code": "validation_error",
    "message": "Job arguments do not match schema for email.send@1.0.0.",
    "details": {
      "validation_errors": [
        "required property 'body' is missing",
        "'to' does not match format 'email'"
      ]
    }
  }
}
```

---

## Appendix A: Changelog

| Date       | Change                          |
|------------|---------------------------------|
| 2026-02-19 | Initial draft.                  |
