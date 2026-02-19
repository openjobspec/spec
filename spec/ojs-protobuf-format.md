# Open Job Spec -- Protobuf Wire Format Encoding

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

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Content Type and Content Negotiation](#3-content-type-and-content-negotiation)
4. [Protobuf Schema Design](#4-protobuf-schema-design)
5. [Field Reference](#5-field-reference)
   - 5.1 [Required Attributes](#51-required-attributes)
   - 5.2 [Optional Attributes](#52-optional-attributes)
   - 5.3 [System-Managed Attributes](#53-system-managed-attributes)
6. [Type Mapping](#6-type-mapping)
7. [Batch Encoding](#7-batch-encoding)
8. [Extension Encoding](#8-extension-encoding)
9. [Backward and Forward Compatibility](#9-backward-and-forward-compatibility)
10. [Relationship to JSON Wire Format](#10-relationship-to-json-wire-format)
11. [Relationship to gRPC Binding](#11-relationship-to-grpc-binding)
12. [Conformance Requirements](#12-conformance-requirements)
13. [Prior Art](#13-prior-art)
14. [Examples](#14-examples)

---

## 1. Introduction

This document defines the **Protocol Buffers (Protobuf) wire format encoding** for Open Job Spec (OJS) job envelopes. While JSON is the REQUIRED baseline wire format (see ojs-json-format.md), Protobuf provides a compact binary alternative for high-throughput environments where serialization overhead, message size, and schema enforcement are critical concerns.

This specification is part of the OJS three-tier architecture:

- **Layer 1 -- Core Specification**: Defines what a job IS (attributes, lifecycle, operations).
- **Layer 2 -- Wire Format Encodings**: Defines how a job is SERIALIZED (this document + ojs-json-format.md).
- **Layer 3 -- Protocol Bindings**: Defines how a job is TRANSMITTED (HTTP, gRPC, AMQP, etc.).

### 1.1 Relationship to Other Layers

Layer 2 is concerned exclusively with serialization: how the abstract job envelope defined in Layer 1 maps to concrete Protobuf binary encoding. It does not define transport semantics (Layer 3) or job lifecycle behavior (Layer 1). A Protobuf-encoded job envelope is a complete, self-describing unit that can be stored in a binary format, transmitted over any transport, or embedded in another message.

The Protobuf wire format is OPTIONAL. Implementations MUST support JSON (Layer 2 baseline) and MAY additionally support Protobuf. When both are supported, content negotiation determines which format is used for a given exchange.

### 1.2 Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 2. Notational Conventions

Proto3 syntax is used throughout this document. All message definitions use the `proto3` syntax version. Field numbers are stable and MUST NOT be reused or reassigned in future versions.

---

## 3. Content Type and Content Negotiation

### 3.1 Media Type

The media type for an OJS job envelope encoded as Protobuf is:

```
application/openjobspec+proto
```

Implementations that support Protobuf encoding MUST use this media type when transmitting OJS job envelopes over protocols that support content type headers (e.g., HTTP `Content-Type`).

**Rationale**: A dedicated media type enables content negotiation between JSON and Protobuf encodings. The `+proto` structured syntax suffix follows the pattern established by `application/grpc+proto` and signals that the content is a Protobuf-encoded message.

### 3.2 Content Negotiation

When a protocol binding supports content negotiation (e.g., HTTP `Accept` header), implementations MUST honor the client's preferred encoding:

- `Accept: application/openjobspec+proto` — Respond with Protobuf encoding.
- `Accept: application/openjobspec+json` — Respond with JSON encoding.
- `Accept: */*` or no `Accept` header — Respond with JSON encoding (the baseline format).

If the server does not support the requested encoding, it MUST respond with `406 Not Acceptable`.

### 3.3 Mixed-Format Interoperability

Implementations MUST ensure that a job serialized as Protobuf and deserialized back to the abstract model is semantically identical to the same job serialized as JSON. Round-trip equivalence between JSON and Protobuf encodings is REQUIRED.

**Rationale**: Producers and consumers may use different encodings. A producer sending Protobuf to a broker that stores JSON (or vice versa) must not lose information during format conversion.

---

## 4. Protobuf Schema Design

### 4.1 Package and Namespace

All OJS Protobuf messages reside in the `openjobspec.v1` package:

```protobuf
syntax = "proto3";

package openjobspec.v1;

option go_package = "github.com/openjobspec/ojs-proto/gen/go/openjobspec/v1";
option java_package = "org.openjobspec.proto.v1";
option java_multiple_files = true;
```

### 4.2 Job Envelope Message

```protobuf
message JobEnvelope {
  // Required attributes
  string specversion = 1;
  string id = 2;
  string type = 3;
  string queue = 4;
  repeated google.protobuf.Value args = 5;

  // Optional attributes
  map<string, google.protobuf.Value> meta = 6;
  int32 priority = 7;
  int32 timeout = 8;
  google.protobuf.Timestamp scheduled_at = 9;
  google.protobuf.Timestamp expires_at = 10;
  RetryPolicy retry = 11;
  UniquePolicy unique = 12;
  string schema = 13;

  // System-managed attributes
  JobState state = 14;
  int32 attempt = 15;
  google.protobuf.Timestamp created_at = 16;
  google.protobuf.Timestamp enqueued_at = 17;
  google.protobuf.Timestamp started_at = 18;
  google.protobuf.Timestamp completed_at = 19;
  JobError error = 20;
  google.protobuf.Value result = 21;

  // Extension fields (100+)
  int32 total_timeout = 100;
  int32 enqueue_ttl = 101;
  int32 grace_period = 102;
  int32 heartbeat_timeout = 103;
  int32 result_ttl = 104;
}
```

**Rationale for field numbering**: Fields 1-19 are reserved for core attributes (1-byte varint tag). Fields 20-99 are reserved for future core additions. Fields 100+ are used for extension attributes (2-byte varint tag). This layout optimizes wire size for the most frequently accessed fields.

### 4.3 Supporting Messages

```protobuf
enum JobState {
  JOB_STATE_UNSPECIFIED = 0;
  JOB_STATE_SCHEDULED = 1;
  JOB_STATE_AVAILABLE = 2;
  JOB_STATE_PENDING = 3;
  JOB_STATE_ACTIVE = 4;
  JOB_STATE_COMPLETED = 5;
  JOB_STATE_RETRYABLE = 6;
  JOB_STATE_CANCELLED = 7;
  JOB_STATE_DISCARDED = 8;
}

message RetryPolicy {
  int32 max_attempts = 1;
  string initial_interval = 2;     // ISO 8601 duration
  double backoff_coefficient = 3;
  string max_interval = 4;         // ISO 8601 duration
  bool jitter = 5;
  repeated string non_retryable_errors = 6;
  string on_exhaustion = 7;        // "discard" | "dead_letter"
}

message UniquePolicy {
  repeated string keys = 1;
  string period = 2;               // ISO 8601 duration
  string on_conflict = 3;          // "reject" | "replace" | "reschedule"
}

message JobError {
  string type = 1;
  string message = 2;
  string backtrace = 3;
  string timeout_kind = 4;
  int32 limit_seconds = 5;
  int32 elapsed_seconds = 6;
}
```

---

## 5. Field Reference

### 5.1 Required Attributes

| Proto Field | Field Number | Proto Type | Core Attribute | Notes |
|-------------|-------------|------------|----------------|-------|
| `specversion` | 1 | `string` | `specversion` | MUST be `"1.0"`. |
| `id` | 2 | `string` | `id` | UUIDv7 as string. |
| `type` | 3 | `string` | `type` | Dot-namespaced job type. |
| `queue` | 4 | `string` | `queue` | Default: `"default"`. |
| `args` | 5 | `repeated Value` | `args` | Uses `google.protobuf.Value` for type flexibility. |

### 5.2 Optional Attributes

| Proto Field | Field Number | Proto Type | Core Attribute | Notes |
|-------------|-------------|------------|----------------|-------|
| `meta` | 6 | `map<string, Value>` | `meta` | Key-value metadata pairs. |
| `priority` | 7 | `int32` | `priority` | Default: 0. |
| `timeout` | 8 | `int32` | `timeout` | Seconds. Default: impl-defined. |
| `scheduled_at` | 9 | `Timestamp` | `scheduled_at` | `google.protobuf.Timestamp`. |
| `expires_at` | 10 | `Timestamp` | `expires_at` | `google.protobuf.Timestamp`. |
| `retry` | 11 | `RetryPolicy` | `retry` | Nested message. |
| `unique` | 12 | `UniquePolicy` | `unique` | Nested message. |
| `schema` | 13 | `string` | `schema` | Schema URI. |

### 5.3 System-Managed Attributes

| Proto Field | Field Number | Proto Type | Core Attribute | Notes |
|-------------|-------------|------------|----------------|-------|
| `state` | 14 | `JobState` | `state` | Enum. |
| `attempt` | 15 | `int32` | `attempt` | 1-indexed. |
| `created_at` | 16 | `Timestamp` | `created_at` | Set by server on PUSH. |
| `enqueued_at` | 17 | `Timestamp` | `enqueued_at` | Set by server on PUSH. |
| `started_at` | 18 | `Timestamp` | `started_at` | Set by server on FETCH. |
| `completed_at` | 19 | `Timestamp` | `completed_at` | Set by server on ACK. |
| `error` | 20 | `JobError` | `error` | Set by server on FAIL. |
| `result` | 21 | `Value` | `result` | Set by server on ACK. |

---

## 6. Type Mapping

### 6.1 Core Type Mapping

| OJS Abstract Type | JSON Type | Protobuf Type | Notes |
|-------------------|-----------|---------------|-------|
| String | `string` | `string` | UTF-8 encoded. |
| Integer | `number` (integer) | `int32` / `int64` | `int32` for bounded values, `int64` for timestamps-as-unix. |
| Number | `number` (float) | `double` | IEEE 754 double precision. |
| Boolean | `boolean` | `bool` | |
| Timestamp | `string` (ISO 8601) | `google.protobuf.Timestamp` | Seconds + nanos precision. |
| Duration | `string` (ISO 8601) | `string` | ISO 8601 duration string (not `google.protobuf.Duration`). |
| Array | `array` | `repeated` | Element type depends on context. |
| Object | `object` | `map<string, Value>` or nested `message` | Dynamic objects use `map`; typed objects use messages. |
| Any | any JSON value | `google.protobuf.Value` | Preserves JSON type semantics via well-known `Value` wrapper. |

**Rationale for `google.protobuf.Value`**: The `args` and `result` fields accept arbitrary JSON values. Proto3's `google.protobuf.Value` is the well-known wrapper that preserves JSON type semantics (null, bool, number, string, list, struct) within a Protobuf message. This ensures lossless round-tripping between JSON and Protobuf encodings.

### 6.2 Default Value Handling

Proto3 does not distinguish between "field not set" and "field set to default value" for scalar types. To handle optional semantics:

- **Timestamps**: An unset timestamp is represented as `null` / zero value (`seconds: 0, nanos: 0`). Implementations MUST NOT interpret the Protobuf epoch (1970-01-01T00:00:00Z) as a valid OJS timestamp.
- **Integers**: Optional integer fields (e.g., `total_timeout`) use the `optional` keyword or wrapper types to distinguish "not set" from "set to 0".
- **Strings**: An unset optional string is the empty string. Implementations MUST treat empty string as "not set" for optional fields.

---

## 7. Batch Encoding

### 7.1 Batch Envelope

```protobuf
message BatchEnqueueRequest {
  repeated JobEnvelope jobs = 1;
}

message BatchEnqueueResponse {
  repeated BatchResult results = 1;
}

message BatchResult {
  int32 index = 1;
  string id = 2;
  bool success = 3;
  JobError error = 4;
}
```

Batch requests encode multiple job envelopes in a single `repeated` field. Each job in the batch is independently validated, and the response includes per-job success/failure status.

### 7.2 Length-Delimited Streaming

For very large batches, implementations MAY support length-delimited streaming where each job envelope is prefixed with its byte length (standard Protobuf delimited format):

```
[4-byte length][JobEnvelope bytes][4-byte length][JobEnvelope bytes]...
```

The media type for length-delimited streaming is:

```
application/openjobspec+proto; delimited=true
```

---

## 8. Extension Encoding

### 8.1 Known Extensions

Extensions with well-known fields (e.g., `total_timeout`, `result_ttl`) are encoded as named fields in the `JobEnvelope` message using field numbers 100+. This approach provides type safety and efficient encoding.

### 8.2 Custom Extensions

For vendor-specific or experimental extensions that are not defined in the standard schema, implementations MUST use the `extensions` map:

```protobuf
message JobEnvelope {
  // ... standard fields ...

  // Custom extension data
  map<string, google.protobuf.Value> extensions = 200;
}
```

Extension keys MUST follow the naming convention `x-{vendor}-{name}` (e.g., `x-acme-gpu-tier`).

### 8.3 Extension Discovery

Implementations that support Protobuf encoding MUST include supported extension URIs in capability negotiation responses, following the same mechanism defined in the core specification for JSON encoding.

---

## 9. Backward and Forward Compatibility

### 9.1 Schema Evolution Rules

Protobuf's wire format provides inherent forward and backward compatibility. The following rules ensure OJS-specific compatibility:

1. **New optional fields** MAY be added in minor versions. They MUST use field numbers not previously assigned.
2. **Required fields** (1-5) MUST NOT be removed or renumbered.
3. **Field types** MUST NOT be changed in a way that breaks wire compatibility (e.g., `int32` to `string`).
4. **Enum values** MUST NOT be renumbered. New values MAY be added.
5. **Removed fields** MUST be reserved (`reserved 50;`) to prevent accidental reuse.

### 9.2 Unknown Field Handling

Implementations MUST preserve unknown fields during deserialization and re-serialization. This ensures that a proxy or middleware that does not understand a newer extension field does not silently drop it.

**Rationale**: In a heterogeneous deployment, some components may run newer versions of the schema. Unknown field preservation prevents data loss during transit through older intermediaries.

---

## 10. Relationship to JSON Wire Format

The Protobuf wire format is an alternative to, not a replacement for, the JSON wire format. The following invariants MUST hold:

1. **Semantic equivalence**: Any job envelope that is valid in JSON MUST be expressible in Protobuf with identical semantics, and vice versa.
2. **Round-trip fidelity**: `JSON → abstract model → Protobuf → abstract model → JSON` MUST produce a semantically identical document (field ordering and whitespace may differ).
3. **Type preservation**: The JSON type of `args` elements and `result` values MUST be preserved through Protobuf encoding via `google.protobuf.Value`.

### 10.1 Conversion Rules

| Conversion | Rule |
|------------|------|
| JSON `null` → Protobuf | `google.protobuf.Value` with `null_value` kind. |
| JSON `number` → Protobuf | `google.protobuf.Value` with `number_value` kind (IEEE 754 double). |
| JSON `string` → Protobuf | `google.protobuf.Value` with `string_value` kind. |
| JSON `boolean` → Protobuf | `google.protobuf.Value` with `bool_value` kind. |
| JSON `array` → Protobuf | `google.protobuf.Value` with `list_value` kind. |
| JSON `object` → Protobuf | `google.protobuf.Value` with `struct_value` kind. |
| ISO 8601 timestamp → Protobuf | `google.protobuf.Timestamp` with `seconds` and `nanos`. |

---

## 11. Relationship to gRPC Binding

The gRPC protocol binding (ojs-grpc-binding.md, Layer 3) naturally uses Protobuf as its serialization format. When using the gRPC binding with Protobuf encoding:

- The gRPC binding's `.proto` service definitions MUST import and reuse the message types defined in this specification.
- The gRPC binding MUST NOT define alternative message types for the job envelope.
- The gRPC binding adds RPC service methods and streaming semantics; this document defines only the message serialization.

**Rationale**: A single source of truth for message definitions prevents divergence between the wire format and the gRPC service contract.

---

## 12. Conformance Requirements

### 12.1 Required (when Protobuf is supported)

| Capability | Requirement |
|------------|-------------|
| Media type | Implementations MUST use `application/openjobspec+proto`. |
| Content negotiation | Implementations MUST support format selection via `Accept` header. |
| Round-trip equivalence | JSON ↔ Protobuf conversion MUST be lossless. |
| Unknown field preservation | Implementations MUST preserve unknown fields. |
| Schema evolution | Implementations MUST follow the compatibility rules in Section 9. |

### 12.2 Recommended

| Capability | Requirement |
|------------|-------------|
| Batch encoding | Implementations SHOULD support `BatchEnqueueRequest`. |
| Extension map | Implementations SHOULD support the `extensions` field for custom extensions. |

### 12.3 Optional

| Capability | Requirement |
|------------|-------------|
| Length-delimited streaming | Implementations MAY support delimited streaming for large batches. |
| Protobuf-only mode | Implementations MAY operate in Protobuf-only mode without JSON support, but this is NOT RECOMMENDED. |

---

## 13. Prior Art

| System | Binary Encoding |
|--------|----------------|
| **CloudEvents** | Defines both JSON and Protobuf encodings with round-trip equivalence. OJS follows the same dual-format approach. |
| **gRPC** | Native Protobuf encoding with `google.protobuf.Any` for dynamic types. OJS uses `Value` instead of `Any` for JSON compatibility. |
| **Apache Kafka** | Schema Registry with Avro, Protobuf, and JSON Schema support. Demonstrates the value of multiple wire formats. |
| **Temporal** | Protobuf-native with `Payloads` wrapper for arbitrary data. Uses data converters for format flexibility. |
| **NATS** | Format-agnostic message transport. Headers indicate encoding. Validates the content-negotiation approach. |

---

## 14. Examples

### 14.1 Minimal Job Envelope (Protobuf Text Format)

```protobuf
# Proto text format (for documentation; wire format is binary)
specversion: "1.0"
id: "019539a4-b68c-7def-8000-1a2b3c4d5e6f"
type: "email.send"
queue: "default"
args: [
  { string_value: "user@example.com" },
  { string_value: "welcome" }
]
```

Equivalent JSON:

```json
{
  "specversion": "1.0",
  "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "type": "email.send",
  "queue": "default",
  "args": ["user@example.com", "welcome"]
}
```

### 14.2 Job with Extensions (Protobuf Text Format)

```protobuf
specversion: "1.0"
id: "019539a4-b68c-7def-8000-2b3c4d5e6f7a"
type: "video.transcode"
queue: "media"
args: [
  { string_value: "video_001" },
  { string_value: "1080p" }
]
priority: 5
timeout: 3600
retry: {
  max_attempts: 3
  initial_interval: "PT10S"
  backoff_coefficient: 2.0
  jitter: true
  on_exhaustion: "dead_letter"
}
total_timeout: 86400
grace_period: 60
```

### 14.3 Wire Size Comparison

For a typical job envelope with type, queue, args (2 strings), priority, timeout, and retry policy:

| Encoding | Approximate Size | Ratio |
|----------|-----------------|-------|
| JSON (minified) | ~280 bytes | 1.0× |
| JSON (pretty-printed) | ~450 bytes | 1.6× |
| Protobuf (binary) | ~120 bytes | 0.43× |

Protobuf encoding typically achieves 40-60% size reduction compared to minified JSON, with faster serialization and deserialization.

---

## Appendix A: Well-Known Protobuf Imports

Implementations using the OJS Protobuf encoding MUST import the following well-known types:

```protobuf
import "google/protobuf/timestamp.proto";
import "google/protobuf/struct.proto";  // provides Value, Struct, ListValue
```

---

## Appendix B: Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0-rc.1 | 2026-02-15 | Initial release candidate. |

