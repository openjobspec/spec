# Open Job Spec -- JSON Wire Format Encoding

**OJS Layer 2: Wire Format**

| Field        | Value                              |
|--------------|------------------------------------|
| **Version**  | 1.0.0-rc.1                         |
| **Date**     | 2026-02-19                         |
| **Status**   | Release Candidate                  |
| **Maturity** | Stable                             |
| **Layer**    | 2 (Wire Format Encoding)          |
| **Requires** | OJS Core Specification (Layer 1)   |
| **License**  | Apache 2.0                         |

---

## 1. Introduction

This document defines the **JSON wire format encoding** for Open Job Spec (OJS) job
envelopes. JSON is the REQUIRED baseline wire format: every conformant OJS
implementation MUST be able to produce and consume jobs serialized as JSON.

This specification is part of the OJS three-tier architecture inspired by CloudEvents:

- **Layer 1 -- Core Specification**: Defines what a job IS (attributes, lifecycle, operations).
- **Layer 2 -- Wire Format Encodings**: Defines how a job is SERIALIZED (this document).
- **Layer 3 -- Protocol Bindings**: Defines how a job is TRANSMITTED (HTTP, gRPC, etc.).

### 1.1 Relationship to Other Layers

Layer 2 is concerned exclusively with serialization: how the abstract job envelope
defined in Layer 1 maps to concrete JSON tokens. It does not define transport
semantics (Layer 3) or job lifecycle behavior (Layer 1). A JSON-encoded job envelope
is a complete, self-describing unit that can be stored in a file, transmitted over
any transport, or embedded in another document.

### 1.2 Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD",
"SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this
document are to be interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt)
and [RFC 8174](https://www.ietf.org/rfc/rfc8174.txt).

---

## 2. Content Type and Content Negotiation

### 2.1 Media Type

The media type for an OJS job envelope encoded as JSON is:

```
application/openjobspec+json
```

Implementations MUST use this media type when transmitting OJS job envelopes over
protocols that support content type headers (e.g., HTTP `Content-Type`).

**Rationale**: A dedicated media type enables content negotiation, middleware routing,
and tooling to identify OJS payloads without inspecting the body. The `+json`
structured syntax suffix follows [RFC 6839](https://www.ietf.org/rfc/rfc6839.txt)
and signals to generic JSON tooling that the content is valid JSON.

### 2.2 Content Negotiation

When a protocol binding supports content negotiation (e.g., HTTP `Accept` header),
implementations MUST accept `application/openjobspec+json` and SHOULD also accept
`application/json` as a fallback.

Implementations MUST NOT require clients to use the OJS-specific media type when
`application/json` is specified. This ensures interoperability with generic HTTP
clients and tooling.

When responding, implementations SHOULD use `application/openjobspec+json` to
signal the payload is an OJS envelope, unless the client explicitly requested
`application/json`.

### 2.3 Character Encoding

All JSON-encoded OJS documents MUST use UTF-8 encoding without a byte order mark
(BOM), as specified by [RFC 8259 Section 8.1](https://www.ietf.org/rfc/rfc8259.txt).

**Rationale**: RFC 8259 mandates UTF-8 for JSON exchanged between systems that are
not part of a closed ecosystem. Since OJS is designed for cross-language, cross-system
interoperability, enforcing UTF-8 eliminates an entire class of encoding mismatch bugs.

---

## 3. JSON Representation of a Job Envelope

### 3.1 Complete Field Reference

The following table defines every field in an OJS job envelope and its JSON
representation. Fields are grouped as REQUIRED (must appear in every valid envelope)
and OPTIONAL (may be omitted).

#### Required Fields

| OJS Attribute   | JSON Key       | JSON Type | Constraints                       | Description                              |
|-----------------|----------------|-----------|-----------------------------------|------------------------------------------|
| Spec Version    | `specversion`  | string    | MUST be `"1.0"`                   | OJS specification version                |
| ID              | `id`           | string    | UUIDv7 format (see Section 6)     | Globally unique job identifier           |
| Type            | `type`         | string    | Dot-namespaced, non-empty         | Job type used for handler routing        |
| Queue           | `queue`        | string    | Lowercase `[a-z0-9][a-z0-9\-\.]*` | Target queue name                        |
| Arguments       | `args`         | array     | JSON-native types only (see 3.3)  | Positional arguments for the job handler |

#### Optional Fields

| OJS Attribute       | JSON Key         | JSON Type       | Constraints                            | Description                                  |
|---------------------|------------------|-----------------|----------------------------------------|----------------------------------------------|
| Metadata            | `meta`           | object          | String keys, JSON-native values        | Extensible key-value metadata                |
| Priority            | `priority`       | number (integer)| Integer, higher = more important       | Job priority within queue                    |
| Timeout             | `timeout`        | number (integer)| Positive integer, seconds              | Maximum execution time                       |
| Scheduled At        | `scheduled_at`   | string          | ISO 8601 / RFC 3339 (see Section 5)   | Earliest execution time                      |
| Expires At          | `expires_at`     | string          | ISO 8601 / RFC 3339 (see Section 5)   | Job expiration deadline                      |
| Retry Policy        | `retry`          | object          | Structured retry (see Section 3.4)     | Retry behavior configuration                 |
| Unique Policy       | `unique`         | object          | Structured uniqueness (see Section 3.5)| Deduplication configuration                  |
| Visibility Timeout  | `visibility_timeout` | number (integer) | Positive integer, seconds         | Reservation period for worker crash recovery |

#### System-Managed Fields (set by the server, read-only for clients)

| OJS Attribute   | JSON Key         | JSON Type       | Description                              |
|-----------------|------------------|-----------------|------------------------------------------|
| State           | `state`          | string          | Current lifecycle state                  |
| Attempt         | `attempt`        | number (integer)| Current attempt number (1-indexed)       |
| Created At      | `created_at`     | string          | When the job was created                 |
| Enqueued At     | `enqueued_at`    | string          | When the job entered the queue           |
| Started At      | `started_at`     | string          | When a worker began execution            |
| Completed At    | `completed_at`   | string          | When the job reached a terminal state    |
| Result          | `result`         | any JSON type   | Job return value (optional)              |
| Errors          | `errors`         | array           | Array of error objects from failed attempts |

### 3.2 Minimal Job Envelope

A valid OJS job envelope requires exactly five fields:

```json
{
  "specversion": "1.0",
  "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "type": "email.send",
  "queue": "default",
  "args": ["user@example.com", "welcome"]
}
```

**Rationale for each REQUIRED field**:

- **`specversion`** MUST be present so that parsers can determine which version of
  the OJS specification governs the envelope. This enables forward-compatible evolution
  of the format. Following CloudEvents, only the major.minor portion is used (the
  patch version does not affect the wire format).

- **`id`** MUST be present to enable deduplication, correlation, status queries, and
  distributed tracing. Without a stable identifier, none of these operations are possible.

- **`type`** MUST be present because it is the routing key: workers use it to dispatch
  to the correct handler. A job without a type cannot be processed.

- **`queue`** MUST be present because it determines where the job is placed for
  consumption. Implicit defaults vary across implementations, so making the queue
  explicit removes ambiguity in cross-system interoperability.

- **`args`** MUST be present because it carries the input data for the job handler.
  An empty array (`[]`) is valid for jobs that require no arguments.

### 3.3 Argument Constraints: JSON-Native Types Only

The `args` array MUST contain only JSON-native types:

| JSON Type | Description                          | Example                    |
|-----------|--------------------------------------|----------------------------|
| string    | UTF-8 text                           | `"hello"`                  |
| number    | IEEE 754 double-precision float      | `42`, `3.14`, `-1`        |
| boolean   | True or false                        | `true`, `false`            |
| null      | Explicit absence of value            | `null`                     |
| array     | Ordered list of JSON values          | `[1, "two", true]`        |
| object    | Unordered key-value map              | `{"key": "value"}`         |

Implementations MUST reject job envelopes where `args` contains values that are
not representable as one of the six JSON types above.

**Rationale**: This constraint is the single most important design decision for
cross-language interoperability. Sidekiq's insistence on "simple types only" --
string, number, boolean, null, array, hash -- is vindicated by over a decade of
production use across thousands of organizations. The constraint forces clean
separation between job data and application objects, prevents stale serialized
state, and enables inspection of job arguments by any tool that understands JSON.

Celery's support for Python's `pickle` serialization is the canonical antipattern:
pickle allows arbitrary code execution during deserialization, has caused multiple
CVEs ([CVE-2011-4356](https://nvd.nist.gov/vuln/detail/CVE-2011-4356),
[CVE-2013-2132](https://nvd.nist.gov/vuln/detail/CVE-2013-2132)), and couples
the serialized form to the Python runtime version. The Celery documentation itself
warns against pickle and recommends JSON.

Implementations MUST NOT support language-specific serialization formats in `args`,
including but not limited to:

- Python `pickle` or `marshal`
- Ruby `Marshal`
- Java `ObjectInputStream` / Java serialization
- PHP `serialize()`
- .NET `BinaryFormatter`

### 3.4 Retry Policy Object

When present, the `retry` field MUST be a JSON object with the following structure,
adopting Temporal's structured retry policy format:

```json
{
  "max_attempts": 5,
  "initial_interval": "PT1S",
  "backoff_coefficient": 2.0,
  "max_interval": "PT5M",
  "jitter": true,
  "non_retryable_errors": ["validation_error", "not_found"]
}
```

| Field                  | JSON Type       | Required | Default    | Description                                      |
|------------------------|-----------------|----------|------------|--------------------------------------------------|
| `max_attempts`         | number (integer)| No       | 3          | Total attempts including the initial execution    |
| `initial_interval`     | string          | No       | `"PT1S"`   | ISO 8601 duration before first retry             |
| `backoff_coefficient`  | number          | No       | 2.0        | Multiplier applied to interval after each retry  |
| `max_interval`         | string          | No       | `"PT5M"`   | ISO 8601 duration cap on retry delay             |
| `jitter`               | boolean         | No       | `true`     | Whether to add randomness to prevent thundering herd |
| `non_retryable_errors` | array of string | No       | `[]`       | Error type strings that MUST NOT trigger retry   |

**Rationale**: Temporal's structured format is the most explicit and
language-agnostic retry policy representation in the ecosystem. It avoids the
pitfalls of overloaded fields (e.g., Sidekiq's `retry: true` vs `retry: 5` vs
`retry: false` all using the same field with different types) and provides enough
knobs for sophisticated backoff strategies without requiring language-specific
callbacks.

### 3.5 Unique Policy Object

When present, the `unique` field MUST be a JSON object:

```json
{
  "key": ["to", "template"],
  "period": "PT1H",
  "on_conflict": "reject",
  "states": ["available", "active", "scheduled"]
}
```

| Field         | JSON Type       | Required | Default      | Description                                        |
|---------------|-----------------|----------|--------------|----------------------------------------------------|
| `key`         | array of string | No       | all args     | Fields from args to include in uniqueness hash     |
| `period`      | string          | No       | none         | ISO 8601 duration for uniqueness window            |
| `on_conflict` | string          | No       | `"reject"`   | One of: `"reject"`, `"replace"`, `"ignore"`        |
| `states`      | array of string | No       | all non-terminal | States to consider for uniqueness checking     |

---

## 4. Type Mapping

### 4.1 OJS Core Type to JSON Type Mapping

The following table defines how each OJS abstract type maps to a JSON type:

| OJS Core Type     | JSON Type        | JSON Schema `type`       | Notes                                    |
|-------------------|------------------|--------------------------|------------------------------------------|
| String            | string           | `"string"`               | MUST be valid UTF-8                      |
| Integer           | number           | `"integer"`              | No fractional part; safe up to 2^53 - 1  |
| Float             | number           | `"number"`               | IEEE 754 double-precision                |
| Boolean           | boolean          | `"boolean"`              |                                          |
| Null              | null             | `"null"`                 | Represents explicit absence              |
| Timestamp         | string           | `"string"` with `format` | ISO 8601 / RFC 3339 (see Section 5)      |
| Duration          | string           | `"string"`               | ISO 8601 duration (e.g., `"PT30S"`)      |
| Identifier        | string           | `"string"` with `pattern`| UUIDv7 formatted as lowercase hex with hyphens |
| Enum              | string           | `"string"` with `enum`   | One of a fixed set of values             |
| Array             | array            | `"array"`                | Ordered sequence of values               |
| Map / Object      | object           | `"object"`               | Unordered key-value pairs; keys MUST be strings |
| Binary            | string           | `"string"`               | base64url-encoded (see Section 7)        |

### 4.2 Integer Safety

JSON numbers are IEEE 754 double-precision floats. Integers larger than 2^53 - 1
(9,007,199,254,740,991) MUST be encoded as strings to prevent precision loss.

**Rationale**: JavaScript (the most common JSON consumer) cannot represent integers
above `Number.MAX_SAFE_INTEGER` without precision loss. Encoding large integers as
strings is the standard mitigation, used by Twitter's API (tweet IDs), Stripe's API
(amount in cents for large values), and Discord's API (snowflake IDs).

Implementations MUST document whether their job IDs or any system-generated numeric
fields may exceed this threshold and, if so, MUST encode them as strings.

---

## 5. Timestamp Format

### 5.1 Format Specification

All timestamps in an OJS JSON envelope MUST conform to
[RFC 3339](https://www.ietf.org/rfc/rfc3339.txt), which is a profile of ISO 8601.

The format is:

```
YYYY-MM-DDThh:mm:ss[.fractional]TZ
```

Where:

- `YYYY-MM-DD` is the date in four-digit year, two-digit month, two-digit day.
- `T` is the literal character `T` separating date and time.
- `hh:mm:ss` is the time in 24-hour format.
- `[.fractional]` is an OPTIONAL fractional seconds component. When present,
  implementations SHOULD use millisecond precision (3 digits) or microsecond
  precision (6 digits).
- `TZ` is the timezone offset. Implementations SHOULD use `Z` (UTC) for all
  timestamps. When a non-UTC offset is required, it MUST be in the form `+hh:mm`
  or `-hh:mm`.

### 5.2 Examples

```
"2025-06-01T09:00:00Z"              -- UTC, no fractional seconds
"2025-06-01T09:00:00.000Z"          -- UTC, millisecond precision
"2025-06-01T09:00:00.123456Z"       -- UTC, microsecond precision
"2025-06-01T11:00:00+02:00"         -- Explicit timezone offset
```

### 5.3 Requirements

Implementations MUST satisfy the following:

1. All timestamp fields MUST include a timezone designator. Timestamps without
   timezone information (e.g., `"2025-06-01T09:00:00"`) MUST be rejected.

   **Rationale**: Ambiguous timestamps are a pervasive source of bugs in distributed
   systems. A job scheduled at "09:00:00" is meaningless without knowing whose 09:00.
   Mandating timezone information eliminates this ambiguity entirely.

2. Implementations SHOULD generate timestamps in UTC with the `Z` suffix.

   **Rationale**: UTC is the common denominator for distributed systems. Using UTC
   avoids daylight saving time transitions and simplifies cross-timezone comparison
   and sorting.

3. Implementations MUST accept any valid RFC 3339 timestamp regardless of timezone
   offset and MUST preserve the original timezone when round-tripping.

4. Duration fields (e.g., `initial_interval`, `max_interval`, `period`) MUST use
   ISO 8601 duration format: `PnYnMnDTnHnMnS`. Common examples:

   - `"PT1S"` -- 1 second
   - `"PT30S"` -- 30 seconds
   - `"PT5M"` -- 5 minutes
   - `"PT1H"` -- 1 hour
   - `"P1D"` -- 1 day

   **Rationale**: ISO 8601 durations are human-readable, unambiguous, and supported
   by standard libraries across all major programming languages. Using integer
   milliseconds (as Sidekiq 8.0 switched to) avoids float precision issues but
   sacrifices readability. ISO 8601 strings provide the best balance of precision,
   readability, and interoperability.

---

## 6. Identifier Format

### 6.1 Job IDs

Job identifiers MUST be [UUIDv7](https://www.ietf.org/rfc/rfc9562.txt) values,
serialized as lowercase hyphenated strings:

```
"019539a4-b68c-7def-8000-1a2b3c4d5e6f"
```

The format MUST match the following pattern:

```
[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}
```

**Rationale**: UUIDv7 is mandated (not merely recommended) for the following reasons:

1. **Time-ordered**: UUIDv7 embeds a Unix timestamp in the most significant bits,
   making IDs naturally sortable by creation time. This is essential for efficient
   database indexing and queue ordering without a separate `created_at` column.

2. **Globally unique without coordination**: UUIDv7 includes random bits that make
   collisions negligible (2^62 random bits per millisecond), so distributed systems
   can generate IDs without a central authority.

3. **Standardized**: UUIDv7 is defined in [RFC 9562](https://www.ietf.org/rfc/rfc9562.txt),
   unlike ULIDs which lack an RFC. Standardization ensures consistent implementations
   across languages.

4. **Wide library support**: UUIDv7 is supported by the `uuid` packages in Go, Java,
   Python, JavaScript/TypeScript, Rust, Ruby, and all other major languages.

### 6.2 String Representation

Implementations MUST serialize UUIDv7 values as lowercase hexadecimal with hyphens
in the standard 8-4-4-4-12 grouping. Implementations MUST accept uppercase hex
on input but MUST produce lowercase hex on output.

**Rationale**: Lowercase is mandated for output to ensure byte-for-byte reproducibility
in signatures, checksums, and deduplication hashes. Accepting uppercase on input
follows Postel's law (be liberal in what you accept).

---

## 7. Binary Data Encoding

### 7.1 Encoding Scheme

Binary data within `args`, `meta`, or `result` fields MUST be encoded using
**base64url** as defined in [RFC 4648 Section 5](https://www.ietf.org/rfc/rfc4648.txt),
without padding characters.

### 7.2 Format

Base64url uses the URL-safe alphabet:
- `A-Z`, `a-z`, `0-9`, `-`, `_` (replacing `+` and `/` from standard base64)
- No `=` padding characters

Example:

```json
{
  "specversion": "1.0",
  "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "type": "document.process",
  "queue": "default",
  "args": [
    {
      "filename": "report.pdf",
      "content": "JVBERi0xLjQKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZw",
      "content_encoding": "base64url"
    }
  ]
}
```

### 7.3 Requirements

1. Producers MUST use base64url (not standard base64) for all binary values.

   **Rationale**: base64url avoids the `+` and `/` characters that require
   percent-encoding in URLs and can cause issues in JSON string escaping. It is the
   encoding used by JWTs, JWKs, and other modern web standards.

2. Producers SHOULD include a sibling field (e.g., `content_encoding: "base64url"`)
   to signal that a string value contains encoded binary data, since JSON has no
   native binary type and string values are otherwise assumed to be UTF-8 text.

3. Consumers MUST NOT assume that all string values are binary. Only fields
   explicitly documented or annotated as binary SHOULD be decoded.

4. For large binary payloads, implementations SHOULD use external references (URIs
   pointing to object storage, S3 paths, etc.) rather than inline base64url encoding.

   **Rationale**: base64url encoding inflates data size by approximately 33%. For
   payloads exceeding a few kilobytes, the size overhead and memory pressure of
   inline encoding become significant. External references keep the job envelope
   compact and allow workers to stream large data rather than buffering it entirely
   in memory.

---

## 8. Size Limits and Recommendations

### 8.1 Envelope Size

Implementations MUST support job envelopes up to **1 MiB** (1,048,576 bytes) in
their JSON-serialized form.

Implementations MAY support larger envelopes but MUST document their maximum size.

Implementations SHOULD reject envelopes exceeding their documented maximum with
an `invalid_request` error (see Section 12) that includes the actual size and the
maximum allowed size.

**Rationale**: A 1 MiB minimum ensures that all conformant implementations can
exchange jobs without size negotiation. This limit is generous enough for virtually
all job arguments (which should be references to data, not the data itself) while
preventing abuse. For reference: Sidekiq warns at 100 KiB; Faktory has no formal
limit but recommends keeping jobs small; SQS limits messages to 256 KiB.

### 8.2 Field-Level Recommendations

| Field        | Recommended Maximum | Rationale                                       |
|--------------|--------------------|-------------------------------------------------|
| `type`       | 255 characters     | Enough for deep dot-namespacing                 |
| `queue`      | 255 characters     | Enough for hierarchical queue names             |
| `args`       | 64 KiB             | Arguments should be references, not large blobs |
| `meta`       | 16 KiB             | Metadata should be concise                      |
| `args` depth | 10 levels          | Deeply nested structures indicate design issues |
| `args` items | 100 elements       | Large argument lists should use a single object |

These are RECOMMENDED limits. Implementations MAY enforce stricter limits and MUST
document any limits they enforce.

### 8.3 Batch Size

When submitting batches of jobs (see Section 10), implementations MUST support
batches of at least **1,000 jobs** in a single request.

Implementations SHOULD support batches of up to **10,000 jobs** and MAY support
larger batches.

---

## 9. JSON Schema Reference

### 9.1 Schema Location

The normative JSON Schema (draft 2020-12) for the OJS job envelope is published at:

```
https://openjobspec.org/schemas/v1/job.schema.json
```

Additional schemas for related types:

| Schema                 | URI                                                        |
|------------------------|------------------------------------------------------------|
| Job Envelope           | `https://openjobspec.org/schemas/v1/job.schema.json`       |
| Retry Policy           | `https://openjobspec.org/schemas/v1/retry-policy.schema.json` |
| Unique Policy          | `https://openjobspec.org/schemas/v1/unique-policy.schema.json` |
| Error                  | `https://openjobspec.org/schemas/v1/error.schema.json`     |
| Event                  | `https://openjobspec.org/schemas/v1/event.schema.json`     |
| Batch Request          | `https://openjobspec.org/schemas/v1/batch-request.schema.json` |

### 9.2 Schema Usage

Implementations SHOULD validate incoming job envelopes against the JSON Schema
before processing.

Implementations MUST NOT reject envelopes that contain additional fields not defined
in this specification, provided those fields do not conflict with defined field names.
Unknown fields MUST be preserved when round-tripping (serializing and deserializing)
a job envelope.

**Rationale**: Forward compatibility requires that new optional fields can be added
in future versions without breaking existing consumers. This follows the "must ignore"
principle used by HTML, HTTP, and CloudEvents.

### 9.3 Minimal Job Schema

The following is the normative JSON Schema for a minimal valid OJS job envelope:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://openjobspec.org/schemas/v1/job.schema.json",
  "title": "OJS Job Envelope",
  "description": "An Open Job Spec job envelope in JSON wire format.",
  "type": "object",
  "required": ["specversion", "id", "type", "queue", "args"],
  "properties": {
    "specversion": {
      "type": "string",
      "const": "1.0",
      "description": "OJS specification version governing this envelope."
    },
    "id": {
      "type": "string",
      "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
      "description": "Globally unique job identifier in UUIDv7 format."
    },
    "type": {
      "type": "string",
      "minLength": 1,
      "pattern": "^[a-zA-Z][a-zA-Z0-9_]*(\\.[a-zA-Z][a-zA-Z0-9_]*)*$",
      "description": "Dot-namespaced job type for handler routing."
    },
    "queue": {
      "type": "string",
      "pattern": "^[a-z0-9][a-z0-9\\-\\.]*$",
      "description": "Target queue name."
    },
    "args": {
      "type": "array",
      "description": "Positional arguments for the job handler. JSON-native types only."
    },
    "meta": {
      "type": "object",
      "description": "Extensible key-value metadata for cross-cutting concerns.",
      "additionalProperties": true
    },
    "priority": {
      "type": "integer",
      "description": "Job priority. Higher values indicate higher priority."
    },
    "timeout": {
      "type": "integer",
      "minimum": 1,
      "description": "Maximum execution time in seconds."
    },
    "scheduled_at": {
      "type": "string",
      "format": "date-time",
      "description": "Earliest execution time in RFC 3339 format."
    },
    "expires_at": {
      "type": "string",
      "format": "date-time",
      "description": "Job expiration deadline in RFC 3339 format."
    },
    "retry": {
      "$ref": "https://openjobspec.org/schemas/v1/retry-policy.schema.json",
      "description": "Retry behavior configuration."
    },
    "unique": {
      "$ref": "https://openjobspec.org/schemas/v1/unique-policy.schema.json",
      "description": "Deduplication configuration."
    },
    "visibility_timeout": {
      "type": "integer",
      "minimum": 1,
      "description": "Reservation period in seconds for worker crash recovery."
    }
  },
  "additionalProperties": true
}
```

---

## 10. Batch Format

### 10.1 Batch Envelope

Multiple jobs MAY be submitted in a single batch. A batch is represented as a JSON
object containing an array of job envelopes:

```json
{
  "jobs": [
    {
      "specversion": "1.0",
      "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
      "type": "email.send",
      "queue": "email",
      "args": ["alice@example.com", "welcome"]
    },
    {
      "specversion": "1.0",
      "id": "019539a4-b68c-7def-8000-2b3c4d5e6f7a",
      "type": "email.send",
      "queue": "email",
      "args": ["bob@example.com", "welcome"]
    }
  ]
}
```

### 10.2 Batch Requirements

1. The `jobs` field MUST be a JSON array containing one or more valid job envelopes.

2. Each job in the array MUST be independently valid -- it MUST contain all REQUIRED
   fields and MUST pass schema validation on its own.

   **Rationale**: Independent validity ensures that batch semantics are simple and
   predictable. A batch is syntactic sugar for multiple individual enqueue operations,
   not a transactional unit with special semantics.

3. Implementations MUST process batch jobs atomically where the underlying backend
   supports it: either all jobs are enqueued or none are. When atomic batch enqueue
   is not possible, implementations MUST document this limitation and MUST return
   per-job success/failure status in the response.

4. Batch responses MUST include a per-job result indicating success or failure:

```json
{
  "jobs": [
    {
      "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
      "state": "available",
      "enqueued_at": "2025-06-01T09:00:00.123Z"
    },
    {
      "id": "019539a4-b68c-7def-8000-2b3c4d5e6f7a",
      "state": "available",
      "enqueued_at": "2025-06-01T09:00:00.124Z"
    }
  ],
  "count": 2
}
```

---

## 11. Complete Examples

### 11.1 Minimal Job

The smallest valid OJS job envelope:

```json
{
  "specversion": "1.0",
  "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "type": "email.send",
  "queue": "default",
  "args": ["user@example.com", "welcome"]
}
```

### 11.2 Full Job with All Optional Fields

A job envelope demonstrating every defined field:

```json
{
  "specversion": "1.0",
  "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "type": "email.send",
  "queue": "email",
  "args": ["user@example.com", "welcome"],
  "meta": {
    "trace_id": "abc123",
    "locale": "en-US",
    "user_id": "usr_42"
  },
  "priority": 10,
  "timeout": 30,
  "scheduled_at": "2025-06-01T09:00:00Z",
  "expires_at": "2025-06-01T12:00:00Z",
  "retry": {
    "max_attempts": 5,
    "initial_interval": "PT1S",
    "backoff_coefficient": 2.0,
    "max_interval": "PT5M",
    "jitter": true
  }
}
```

### 11.3 Full Job with Server-Managed Fields (as returned by the server)

```json
{
  "specversion": "1.0",
  "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "type": "email.send",
  "queue": "email",
  "args": ["user@example.com", "welcome"],
  "meta": {
    "trace_id": "abc123",
    "locale": "en-US",
    "user_id": "usr_42"
  },
  "priority": 10,
  "timeout": 30,
  "scheduled_at": "2025-06-01T09:00:00Z",
  "expires_at": "2025-06-01T12:00:00Z",
  "retry": {
    "max_attempts": 5,
    "initial_interval": "PT1S",
    "backoff_coefficient": 2.0,
    "max_interval": "PT5M",
    "jitter": true
  },
  "state": "active",
  "attempt": 2,
  "created_at": "2025-06-01T08:55:00.000Z",
  "enqueued_at": "2025-06-01T09:00:00.123Z",
  "started_at": "2025-06-01T09:00:01.456Z",
  "errors": [
    {
      "type": "handler_error",
      "message": "SMTP connection refused",
      "occurred_at": "2025-06-01T09:00:02.789Z",
      "attempt": 1
    }
  ]
}
```

### 11.4 Job with Unique Policy

```json
{
  "specversion": "1.0",
  "id": "019539a4-b68c-7def-8000-3c4d5e6f7a8b",
  "type": "report.generate",
  "queue": "reports",
  "args": [{"report_id": 42, "format": "pdf"}],
  "unique": {
    "key": ["report_id"],
    "period": "PT1H",
    "on_conflict": "ignore",
    "states": ["available", "active", "scheduled"]
  }
}
```

### 11.5 Job with Binary Data

```json
{
  "specversion": "1.0",
  "id": "019539a4-b68c-7def-8000-4d5e6f7a8b9c",
  "type": "document.process",
  "queue": "documents",
  "args": [
    {
      "filename": "avatar.png",
      "content": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk-M9QDwADhgGAWjR9awAAAABJRU5ErkJggg",
      "content_encoding": "base64url",
      "content_type": "image/png"
    }
  ]
}
```

### 11.6 Batch of Jobs

```json
{
  "jobs": [
    {
      "specversion": "1.0",
      "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
      "type": "email.send",
      "queue": "email",
      "args": ["alice@example.com", "welcome"]
    },
    {
      "specversion": "1.0",
      "id": "019539a4-b68c-7def-8000-2b3c4d5e6f7a",
      "type": "email.send",
      "queue": "email",
      "args": ["bob@example.com", "welcome"]
    },
    {
      "specversion": "1.0",
      "id": "019539a4-b68c-7def-8000-3c4d5e6f7a8b",
      "type": "notification.push",
      "queue": "notifications",
      "args": ["usr_42", "Your report is ready"],
      "priority": 5
    }
  ]
}
```

### 11.7 Job with No Arguments

```json
{
  "specversion": "1.0",
  "id": "019539a4-b68c-7def-8000-5e6f7a8b9c0d",
  "type": "system.health_check",
  "queue": "default",
  "args": []
}
```

---

## 12. Error Format

### 12.1 Error Envelope

Errors in OJS JSON responses MUST use the following structure:

```json
{
  "error": {
    "code": "invalid_request",
    "message": "Job envelope validation failed: 'type' is required",
    "retryable": false,
    "details": {
      "validation_errors": [
        {
          "path": "$.type",
          "message": "required field missing"
        }
      ]
    },
    "request_id": "req_019539a4-c000-7def-8000-aabbccddeeff"
  }
}
```

### 12.2 Error Fields

| Field        | JSON Type | Required | Description                                        |
|--------------|-----------|----------|----------------------------------------------------|
| `code`       | string    | Yes      | Machine-readable error code from the standard set  |
| `message`    | string    | Yes      | Human-readable description of the error            |
| `retryable`  | boolean   | Yes      | Whether the client SHOULD retry the request        |
| `details`    | object    | No       | Additional structured information about the error  |
| `request_id` | string    | No       | Correlation identifier for the failed request      |

### 12.3 Standard Error Codes

| Code                 | Description                                | Retryable |
|----------------------|--------------------------------------------|-----------|
| `invalid_request`    | Malformed JSON or missing required fields  | No        |
| `invalid_payload`    | Job envelope fails schema validation       | No        |
| `schema_validation`  | Args do not conform to registered schema   | No        |
| `not_found`          | Job or resource does not exist             | No        |
| `duplicate`          | Unique constraint violated                 | No        |
| `queue_paused`       | Target queue is paused                     | Yes       |
| `rate_limited`       | Rate limit exceeded                        | Yes       |
| `backend_error`      | Backend storage/transport failure          | Yes       |
| `timeout`            | Operation timed out                        | Yes       |
| `unsupported`        | Feature not supported at this level        | No        |
| `envelope_too_large` | Job envelope exceeds size limit            | No        |

### 12.4 Validation Error Details

When the error code is `invalid_payload` or `schema_validation`, the `details`
object SHOULD include a `validation_errors` array:

```json
{
  "error": {
    "code": "invalid_payload",
    "message": "Job envelope validation failed",
    "retryable": false,
    "details": {
      "validation_errors": [
        {
          "path": "$.args[0]",
          "message": "expected string, got number",
          "schema_path": "#/properties/args/items/0/type"
        },
        {
          "path": "$.scheduled_at",
          "message": "invalid RFC 3339 timestamp: missing timezone",
          "schema_path": "#/properties/scheduled_at/format"
        }
      ]
    }
  }
}
```

Each validation error MUST include:

| Field          | JSON Type | Required | Description                                  |
|----------------|-----------|----------|----------------------------------------------|
| `path`         | string    | Yes      | JSON Pointer or JSONPath to the invalid field |
| `message`      | string    | Yes      | Human-readable description of the violation  |
| `schema_path`  | string    | No       | Path within the JSON Schema that was violated |

---

## 13. Encoding Constraints and Security Considerations

### 13.1 No Executable Code in Arguments

The `args` array MUST NOT contain executable code, serialized closures, function
references, or any value that requires a language runtime to interpret.

Implementations MUST treat `args` as inert data. Deserialization of `args` MUST NOT
trigger code execution.

**Rationale**: This is the most critical security constraint in the specification.
Celery's pickle serialization format allows arbitrary Python code execution during
deserialization, which has led to remote code execution vulnerabilities. Ruby's
`Marshal.load` has similar risks. Java's `ObjectInputStream` has been the source
of numerous critical CVEs.

By restricting `args` to JSON-native types, OJS ensures that deserialization is
always safe regardless of the consuming language. A JSON parser cannot execute
code -- it can only produce strings, numbers, booleans, nulls, arrays, and objects.

### 13.2 No Language-Specific Type Annotations

The `args` array MUST NOT include language-specific type annotations, class names,
or module paths that couple the serialized form to a particular runtime.

Anti-patterns that MUST NOT appear in `args`:

```json
// INVALID: Python class reference
{"__class__": "myapp.models.User", "id": 42}

// INVALID: Ruby class name
{"_type": "MyApp::User", "id": 42}

// INVALID: Java class descriptor
{"@class": "com.example.User", "id": 42}

// INVALID: Explicit type annotation requiring runtime interpretation
{"$type": "System.DateTime", "value": "2025-06-01"}
```

**Rationale**: Language-specific type annotations defeat the purpose of a
language-agnostic standard. A Go worker cannot deserialize a Python class reference,
and a JavaScript worker cannot interpret a Java class descriptor. Job arguments
must be self-describing using only JSON's built-in type system.

### 13.3 String Content Safety

Implementations MUST properly escape all string values according to
[RFC 8259 Section 7](https://www.ietf.org/rfc/rfc8259.txt). The following characters
MUST be escaped:

- `"` (quotation mark) as `\"`
- `\` (reverse solidus) as `\\`
- Control characters U+0000 through U+001F as `\uXXXX`

Implementations SHOULD NOT include raw control characters in JSON strings, even if
some parsers tolerate them.

### 13.4 Numeric Precision

JSON numbers MUST NOT include values that cannot be represented as IEEE 754
double-precision floating-point numbers without loss of precision.

Specifically:

- Integers outside the range [-(2^53 - 1), 2^53 - 1] MUST be encoded as strings.
- Floating-point values requiring more than 17 significant digits MUST be rounded
  to 17 significant digits.

### 13.5 Depth and Complexity Limits

Implementations SHOULD enforce limits on JSON nesting depth and total number of
keys to mitigate denial-of-service attacks via deeply nested or excessively wide
JSON structures.

Recommended limits:

| Dimension          | Recommended Limit |
|--------------------|-------------------|
| Nesting depth      | 32 levels         |
| Total keys/values  | 10,000            |
| String value length| 1 MiB             |
| Array elements     | 10,000            |

### 13.6 Duplicate Keys

As per [RFC 8259](https://www.ietf.org/rfc/rfc8259.txt), JSON object keys SHOULD
be unique. When an OJS JSON document contains duplicate keys, implementations
SHOULD use the last value encountered (matching the behavior of most JSON parsers)
but SHOULD also emit a warning.

Producers MUST NOT emit JSON documents with duplicate keys.

---

## 14. JSON Serialization Rules

### 14.1 Field Ordering

Implementations MUST NOT depend on the order of fields in a JSON object.

**Rationale**: The JSON specification ([RFC 8259](https://www.ietf.org/rfc/rfc8259.txt))
states that JSON objects are unordered collections of key-value pairs. While many
implementations preserve insertion order, relying on this is non-portable.

### 14.2 Null Handling

Optional fields that are absent SHOULD be omitted from the JSON document entirely
rather than included with a `null` value.

When an optional field is explicitly set to `null`, implementations MUST treat it
as equivalent to the field being absent, unless the field's definition specifies
otherwise.

**Rationale**: Omitting absent fields produces smaller documents and avoids ambiguity
between "not specified" and "explicitly null". This matches the convention used by
most JSON APIs (GitHub, Stripe, AWS).

### 14.3 Unknown Fields

Implementations MUST NOT reject JSON documents that contain fields not defined in
this specification. Unknown fields MUST be preserved during round-tripping.

**Rationale**: This rule enables forward compatibility. Newer versions of the spec
may add optional fields; older consumers must be able to process these documents
without error.

### 14.4 Whitespace

Implementations MUST accept JSON with or without whitespace (compact or
pretty-printed). When producing JSON for transmission, implementations SHOULD
use compact encoding (no unnecessary whitespace) to minimize payload size.

When producing JSON for human inspection (e.g., logging, debugging),
implementations MAY use pretty-printed encoding with 2-space indentation.

---

## Appendix A: Prior Art

This specification draws from the following prior art:

| System / Standard | Contribution to This Specification                        |
|-------------------|-----------------------------------------------------------|
| **CloudEvents**   | Three-tier architecture, `specversion` field, `+json` suffix, forward compatibility rules |
| **Sidekiq**       | JSON-native types only constraint for arguments; "simple types" philosophy |
| **Celery**        | Negative example: pickle serialization as a security antipattern |
| **Faktory**       | JSON job envelope design; `custom` metadata hash pattern   |
| **Temporal**      | Structured retry policy format                             |
| **RFC 8259**      | JSON specification; UTF-8 mandate                          |
| **RFC 3339**      | Timestamp format profile of ISO 8601                       |
| **RFC 9562**      | UUIDv7 specification                                       |
| **RFC 4648**      | base64url encoding for binary data                         |
| **RFC 6839**      | Structured syntax suffix for media types                   |

---

## Appendix B: Changelog

### 1.0.0-rc.1 (2025-06-01)

- Initial release candidate.
- JSON established as the REQUIRED baseline wire format.
- Adopted `args` (array) over `payload` (object) for job arguments.
- Mandated UUIDv7 for job identifiers.
- Mandated RFC 3339 timestamps with timezone.
- Mandated base64url for binary data encoding.
- Defined JSON-native type constraint with security rationale.
- Adopted Temporal's structured retry policy format.
- Defined batch format, error format, and JSON Schema references.

---

*Open Job Spec v1.0.0-rc.1 -- JSON Wire Format Encoding*
*https://openjobspec.org*
