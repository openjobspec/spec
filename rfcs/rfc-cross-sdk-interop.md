# RFC-0003: Cross-SDK Integration Testing

- **Stage**: 1 (Proposal)
- **Champion**: TBD
- **Created**: 2025-07-25
- **Last Updated**: 2025-07-25
- **Target Spec Version**: 0.2.0

## Summary

This RFC formalizes wire format interoperability requirements and a testing methodology to verify that jobs produced by any OJS SDK can be consumed by any other OJS SDK. It defines a CI matrix, test scenarios, and assertion patterns that ensure cross-language correctness across the Go, TypeScript, Python, Java, Rust, and Ruby SDKs.

## Motivation

OJS is designed to be language-agnostic: a Go service should be able to enqueue a job that a Python worker processes, or a TypeScript producer should be able to create a workflow that a Java worker executes. While the JSON wire format specification (`ojs-json-format.md`) defines the serialization rules, there is no automated verification that all six SDKs produce and consume compatible wire representations.

Today, each SDK has its own unit tests that validate serialization against the JSON Schema, but these tests run in isolation. They cannot detect:

1. **Subtle serialization mismatches**: One SDK might serialize `args` as `[1, 2.0, "three"]` while another expects `[1, 2, "three"]` (integer vs. float). Both are valid JSON but may cause type errors in strongly-typed consumers.

2. **Meta attribute handling differences**: The spec says `meta` values are "JSON-native values" but does not constrain nesting depth. One SDK might flatten nested objects while another preserves them.

3. **Timestamp precision divergence**: RFC 3339 allows variable fractional-second precision. A Go producer emitting nanosecond-precision timestamps may cause parse failures in an SDK that only supports millisecond precision.

4. **Encoding edge cases**: Unicode normalization (NFC vs. NFD), large number handling (integer overflow at 2^53), and null-vs-absent field semantics differ across languages and JSON libraries.

The v0.2 roadmap calls for "Cross-SDK integration tests (Go producer → JS consumer interop)." This RFC extends that to a full N×N interoperability matrix.

### Use Cases

1. **Polyglot microservices**: A company uses Go for its API gateway (producer) and Python for ML processing (consumer). They need confidence that the job envelope round-trips correctly.

2. **SDK migration**: A team migrates from the Ruby SDK to the Rust SDK. They need to verify that in-flight jobs (enqueued by Ruby) can be processed by the new Rust workers.

3. **Third-party SDK validation**: A community contributor builds an Elixir SDK. They can run the interop test suite to prove compatibility before requesting official listing.

## Prior Art

### OpenTelemetry Cross-Language Tests

The OpenTelemetry project runs cross-language interoperability tests that verify OTLP exporters in one language can be consumed by collectors in another. Tests use Docker Compose to orchestrate multi-language services and assert on trace/metric data received by a central collector.

**Lesson**: Docker Compose is the right orchestration layer for cross-language tests. A central assertion point (collector/backend) simplifies verification.

### gRPC Interop Tests

The gRPC project maintains an [interoperability test suite](https://github.com/grpc/grpc/blob/master/doc/interop-test-descriptions.md) that runs every client language against every server language. Tests are defined as language-neutral scenarios with expected behaviors.

**Lesson**: Language-neutral test scenario definitions (JSON/YAML) enable any SDK to participate without coupling to a specific test framework.

### CloudEvents Conformance

CloudEvents provides conformance tests that validate SDK serialization against the spec. Each SDK runs the same set of test vectors (JSON files with expected serialization output).

**Lesson**: Shared test vectors (golden files) are a low-cost way to catch serialization divergence without requiring a running server.

## Detailed Design

### 1. Wire Format Guarantees

This RFC formalizes the following wire format guarantees that all SDKs MUST satisfy:

#### JSON Serialization Rules

| Requirement | Spec Reference | MUST/SHOULD |
|-------------|---------------|-------------|
| `id` MUST be a valid UUIDv7 string | ojs-core.md §2.1 | MUST |
| `type` MUST be a non-empty string | ojs-core.md §2.2 | MUST |
| `args` MUST be a JSON array | ojs-core.md §2.4 | MUST |
| `meta` MUST be a JSON object with string keys | ojs-core.md §2.5 | MUST |
| Timestamps MUST be RFC 3339 in UTC with `Z` suffix | ojs-json-format.md §3 | MUST |
| Absent optional fields MUST be omitted (not `null`) | ojs-json-format.md §4 | MUST |
| Integer args in range [-2^53+1, 2^53-1] MUST round-trip exactly | ojs-json-format.md §5 | MUST |
| String args MUST round-trip as UTF-8 without normalization | ojs-json-format.md §5 | MUST |
| `meta` values MUST support nesting up to 4 levels deep | This RFC | MUST |
| Timestamps MUST be parsed with at least millisecond precision | This RFC | MUST |

#### Type Mapping

Each SDK MUST document its type mapping between native types and JSON `args` values:

| JSON Type | Go | TypeScript | Python | Java | Rust | Ruby |
|-----------|-----|------------|--------|------|------|------|
| `string` | `string` | `string` | `str` | `String` | `String` | `String` |
| `number` (integer) | `int64` | `number` | `int` | `long` | `i64` | `Integer` |
| `number` (float) | `float64` | `number` | `float` | `double` | `f64` | `Float` |
| `boolean` | `bool` | `boolean` | `bool` | `boolean` | `bool` | `TrueClass`/`FalseClass` |
| `null` | `nil` | `null` | `None` | `null` | `None` | `nil` |
| `array` | `[]any` | `any[]` | `list` | `List<Object>` | `Vec<Value>` | `Array` |
| `object` | `map[string]any` | `Record<string, any>` | `dict` | `Map<String, Object>` | `HashMap<String, Value>` | `Hash` |

### 2. Test Vector Format

Test vectors are JSON files that define a job envelope and expected serialization properties:

```json
{
  "test_id": "basic-string-args",
  "description": "Job with simple string arguments round-trips correctly",
  "job": {
    "type": "email.send",
    "queue": "email",
    "args": ["user@example.com", "Welcome to OJS!"],
    "meta": {
      "tenant_id": "acme-corp"
    }
  },
  "assertions": {
    "args_count": 2,
    "args_types": ["string", "string"],
    "meta_keys": ["tenant_id"],
    "meta_values": {"tenant_id": "acme-corp"}
  }
}
```

#### Test Vector Categories

| Category | Count | Description |
|----------|-------|-------------|
| `basic-types` | 8 | Strings, integers, floats, booleans, null, arrays, objects |
| `edge-cases` | 12 | Unicode (emoji, CJK, RTL), large numbers, deep nesting, empty values |
| `timestamps` | 6 | Various RFC 3339 precisions (seconds, millis, micros, nanos) |
| `meta-handling` | 8 | Nested meta, well-known keys (`ojs.otel.*`, `ojs.federation.*`), large meta |
| `lifecycle` | 10 | Retry attributes, scheduled_at, unique keys, priority, workflow refs |
| `round-trip` | 6 | Values that must survive enqueue → store → fetch without mutation |

### 3. Testing Methodology

#### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Test Orchestrator (Go)                    │
│                                                             │
│  1. Read test vectors from JSON files                       │
│  2. For each (producer SDK, consumer SDK) pair:             │
│     a. Producer enqueues job via HTTP                       │
│     b. Consumer fetches + acks job via HTTP                 │
│     c. Orchestrator asserts on consumed job envelope        │
│                                                             │
│  Backend: Any OJS-compliant server (Redis or Postgres)      │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
    ┌────┴───┐          ┌────┴───┐          ┌────┴───┐
    │ Go SDK │          │ JS SDK │          │ Py SDK │
    │Producer│          │Consumer│          │  Both  │
    └────────┘          └────────┘          └────────┘
```

Each SDK provides two small CLI programs:

- **`interop-producer`**: Reads a test vector JSON from stdin, enqueues the job, prints the enqueued job ID to stdout.
- **`interop-consumer`**: Fetches one job from a specified queue, prints the full job envelope JSON to stdout, then acks the job.

The orchestrator coordinates execution and compares the consumed envelope against the test vector assertions.

#### Execution Flow

1. Start an OJS backend (Docker container)
2. For each test vector:
   a. For each `(producer, consumer)` pair in the SDK matrix:
      - Call `interop-producer` with the test vector
      - Call `interop-consumer` targeting the same queue
      - Parse the consumed job envelope
      - Run assertions: type equality, value equality, timestamp precision, meta preservation
3. Report results in JUnit XML format

### 4. CI Matrix

The full interoperability matrix tests all 36 producer-consumer combinations (6 SDKs × 6 SDKs):

| | Go Consumer | TS Consumer | Py Consumer | Java Consumer | Rust Consumer | Ruby Consumer |
|-|-------------|-------------|-------------|---------------|---------------|---------------|
| **Go Producer** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **TS Producer** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Py Producer** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Java Producer** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Rust Producer** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Ruby Producer** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

The CI pipeline runs on every push to `main` and on every PR that modifies an SDK. To manage CI costs:

- **Full matrix**: Runs nightly and on releases
- **Reduced matrix**: Runs on PRs — each SDK is tested against Go and TypeScript consumers (the two reference implementations), reducing to 12 combinations

### 5. Assertion Patterns

#### Value Equality Assertions

```json
{
  "assert_equal": {
    "path": "$.args[0]",
    "expected": "user@example.com",
    "description": "First argument must be preserved exactly"
  }
}
```

#### Type Assertions

```json
{
  "assert_type": {
    "path": "$.args[1]",
    "expected_type": "number",
    "expected_subtype": "integer",
    "description": "Integer args must not become floats"
  }
}
```

#### Timestamp Assertions

```json
{
  "assert_timestamp": {
    "path": "$.enqueued_at",
    "min_precision": "millisecond",
    "timezone": "UTC",
    "description": "Timestamps must have at least millisecond precision in UTC"
  }
}
```

#### Round-Trip Assertions

```json
{
  "assert_round_trip": {
    "path": "$.meta.complex_value",
    "original": {"nested": {"deep": [1, "two", true, null]}},
    "description": "Nested meta values must survive round-trip"
  }
}
```

## Examples

### Test Vector: Unicode String Args

```json
{
  "test_id": "unicode-emoji-args",
  "description": "Emoji and multi-byte Unicode characters round-trip in args",
  "job": {
    "type": "notification.send",
    "queue": "notifications",
    "args": ["Hello 🌍!", "日本語テスト", "مرحبا"],
    "meta": {}
  },
  "assertions": {
    "args_count": 3,
    "round_trips": [
      {"path": "$.args[0]", "expected": "Hello 🌍!"},
      {"path": "$.args[1]", "expected": "日本語テスト"},
      {"path": "$.args[2]", "expected": "مرحبا"}
    ]
  }
}
```

### Test Vector: Large Number Boundary

```json
{
  "test_id": "number-boundary-safe-integer",
  "description": "Integers at JSON safe integer boundary round-trip exactly",
  "job": {
    "type": "analytics.process",
    "queue": "analytics",
    "args": [9007199254740991, -9007199254740991, 0, 1, -1],
    "meta": {}
  },
  "assertions": {
    "args_count": 5,
    "round_trips": [
      {"path": "$.args[0]", "expected": 9007199254740991},
      {"path": "$.args[1]", "expected": -9007199254740991},
      {"path": "$.args[2]", "expected": 0},
      {"path": "$.args[3]", "expected": 1},
      {"path": "$.args[4]", "expected": -1}
    ]
  }
}
```

### Test Vector: Nested Meta Preservation

```json
{
  "test_id": "meta-nested-objects",
  "description": "Nested meta objects up to 4 levels deep are preserved",
  "job": {
    "type": "audit.log",
    "queue": "audit",
    "args": ["action:login"],
    "meta": {
      "context": {
        "request": {
          "headers": {
            "x-forwarded-for": "203.0.113.42"
          }
        }
      },
      "tenant_id": "acme-corp"
    }
  },
  "assertions": {
    "meta_keys": ["context", "tenant_id"],
    "round_trips": [
      {
        "path": "$.meta.context.request.headers.x-forwarded-for",
        "expected": "203.0.113.42"
      }
    ]
  }
}
```

## Conformance Impact

Cross-SDK interoperability testing does not introduce a new conformance level. Instead, it validates existing Level 0 (core envelope) requirements from a cross-language perspective.

New requirements introduced:

- **MUST**: SDKs MUST preserve integer args in the range `[-2^53+1, 2^53-1]` without converting to floating-point. *Rationale: JavaScript's `Number.MAX_SAFE_INTEGER` is 2^53-1; values outside this range lose precision, causing silent data corruption.*
- **MUST**: SDKs MUST parse RFC 3339 timestamps with at least millisecond precision. *Rationale: Millisecond precision is the minimum needed for meaningful enqueue-to-process latency measurement.*
- **MUST**: SDKs MUST preserve `meta` object values including nested objects up to 4 levels deep. *Rationale: A depth limit prevents pathological nesting while supporting common patterns like trace context and federation attributes.*
- **MUST**: Each SDK MUST ship `interop-producer` and `interop-consumer` CLI tools in its repository. *Rationale: Standardized CLI tools enable the orchestrator to test any SDK without language-specific integration.*
- **SHOULD**: SDKs SHOULD not normalize Unicode strings. *Rationale: Unicode normalization can change byte sequences, breaking equality checks in consumers that expect the original bytes.*

## Backward Compatibility

This proposal is fully backward compatible. It introduces testing infrastructure and formalizes existing implicit requirements from the wire format spec. No changes to the job envelope, APIs, or existing SDK interfaces are required.

## Implementation Requirements

Per the OJS RFC process, proposals at Stage 2+ MUST include working prototypes in at least two languages:

- [ ] Go: `interop-producer` and `interop-consumer` in `ojs-go-sdk/cmd/interop/`
- [ ] TypeScript: `interop-producer` and `interop-consumer` in `ojs-js-sdk/src/interop/`
- [ ] Test orchestrator: `ojs-conformance/interop/`
- [ ] Test vectors: `ojs-conformance/interop/vectors/`

## Alternatives Considered

### Shared Test Server with Snapshot Comparison

Instead of testing through a live backend, each SDK could serialize a job to JSON and compare the output byte-for-byte against a golden file. This was rejected because:

- Byte-for-byte comparison is too strict — JSON allows key reordering and whitespace variation
- It does not test the actual enqueue/fetch path, missing bugs in HTTP client serialization
- It does not verify that the backend preserves the envelope faithfully

### Property-Based Testing

Using property-based testing (e.g., QuickCheck, Hypothesis) to generate random job envelopes and verify round-trip properties. This was rejected as the primary approach because:

- Property generators need to be implemented in each language, creating N implementations to maintain
- It complements but does not replace known-edge-case testing
- It is suitable as a future enhancement (see Open Questions)

### Schema Validation Only

Relying solely on JSON Schema validation was considered. This was rejected because:

- Schema validation confirms structural correctness but not semantic equivalence
- Two envelopes can both be schema-valid but contain subtly different values (e.g., `1` vs. `1.0`)
- Schema validation does not catch round-trip data loss

## Open Questions

1. **Test vector versioning**: Should test vectors be versioned independently from the spec? A breaking change to the wire format would require updating all vectors.

2. **Performance interop**: Should the test suite include performance-oriented tests (e.g., 10,000-job batch enqueue/consume) to catch serialization performance regressions?

3. **Property-based fuzzing**: Should the orchestrator include a fuzz mode that generates random envelopes and tests round-trip properties? This could catch edge cases not covered by explicit vectors.

4. **Third-party SDK certification**: Should there be a formal "OJS Certified" badge for SDKs that pass the full interop test suite? What would the certification process look like?

5. **Binary data handling**: How should SDKs handle binary data in args? The JSON spec does not support raw bytes. Should there be a convention for base64 encoding, and should the interop tests verify it?
