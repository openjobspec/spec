# RFC-0004: gRPC Conformance Testing

- **Stage**: 1 (Proposal)
- **Champion**: TBD
- **Created**: 2025-07-25
- **Last Updated**: 2025-07-25
- **Target Spec Version**: 0.2.0

## Summary

This RFC proposes extending the OJS conformance test suite to cover the gRPC protocol binding defined in `ojs-grpc-binding.md`. It introduces gRPC-specific test case definitions, streaming test scenarios, error code mapping assertions, and an implementation plan for a gRPC test runner that complements the existing HTTP runner.

## Motivation

The OJS conformance test suite (`ojs-conformance`) currently validates only the HTTP protocol binding. The gRPC binding specification (`ojs-grpc-binding.md`) defines a complete protobuf service with unary RPCs, server streaming, and bidirectional streaming, but there is no automated way to verify that a backend's gRPC implementation conforms to the spec.

This creates three problems:

1. **Untested surface area**: Backends that implement the gRPC binding (such as the Redis and Postgres backends) have no conformance validation. Bugs in gRPC-specific code paths (e.g., streaming job delivery, gRPC error code mapping) go undetected.

2. **Spec ambiguity**: Without executable tests, ambiguities in the gRPC binding spec are discovered only during implementation. Tests serve as a second specification that clarifies intent.

3. **New backend barrier**: Developers building new OJS-compliant backends cannot verify their gRPC implementation against a test suite, making it harder to achieve interoperability.

The v0.2 roadmap calls for a "gRPC conformance test runner (currently HTTP-only)." This RFC defines the test format, runner architecture, and test scenarios.

### Use Cases

1. **Backend development**: A developer implementing a new OJS backend runs the gRPC conformance suite alongside the HTTP suite to verify both protocol bindings simultaneously.

2. **Protocol parity verification**: An operator deploying an OJS backend behind a gRPC load balancer runs the gRPC conformance suite to verify that the backend's gRPC interface has feature parity with its HTTP interface.

3. **SDK validation**: SDK developers testing their gRPC client implementations can use the conformance suite as a known-good server behavior reference.

## Prior Art

### gRPC Interop Tests

The [gRPC interop test suite](https://github.com/grpc/grpc/blob/master/doc/interop-test-descriptions.md) defines language-neutral test scenarios for validating gRPC implementations. Tests cover unary calls, streaming, metadata handling, error codes, and cancellation. Each scenario is described as a named test with preconditions, actions, and assertions.

**Lesson**: Named test scenarios with structured preconditions and assertions are the right abstraction. OJS should adopt a similar approach but extend it with job-lifecycle-aware assertions.

### Envoy Proxy Conformance

Envoy's conformance tests verify HTTP/gRPC proxy behavior using YAML test definitions that describe request/response sequences. Tests can assert on headers, status codes, body content, and timing.

**Lesson**: YAML/JSON test definitions enable non-programmers to contribute test cases. The test runner should be separate from the test definitions.

### CloudEvents SDK Conformance

The CloudEvents project provides conformance tests that validate SDK behavior against the spec. Each SDK runs the same test vectors. Tests focus on serialization, protocol binding, and extension handling.

**Lesson**: Conformance tests organized by spec section make it easy to track coverage. OJS gRPC tests should reference specific sections of `ojs-grpc-binding.md`.

## Detailed Design

### 1. Test Case Format Extension

The existing conformance test format uses JSON files with HTTP-specific fields. This RFC extends the format to support gRPC:

```json
{
  "id": "grpc-push-basic",
  "description": "Push a job via gRPC and verify it is stored correctly",
  "level": 0,
  "protocol": "grpc",
  "spec_ref": "ojs-grpc-binding.md §3.1",
  "steps": [
    {
      "action": "grpc_call",
      "service": "ojs.v1.OJSService",
      "method": "Push",
      "request": {
        "type": "email.send",
        "queue": "default",
        "args": [
          {"string_value": "user@example.com"},
          {"string_value": "Welcome!"}
        ]
      },
      "expect": {
        "status": "OK",
        "response": {
          "job.id": {"pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"},
          "job.type": "email.send",
          "job.state": "AVAILABLE"
        }
      }
    },
    {
      "action": "grpc_call",
      "service": "ojs.v1.OJSService",
      "method": "Get",
      "request": {
        "id": "{{steps[0].response.job.id}}"
      },
      "expect": {
        "status": "OK",
        "response": {
          "job.type": "email.send",
          "job.queue": "default",
          "job.args[0].string_value": "user@example.com"
        }
      }
    }
  ]
}
```

#### New Test Format Fields

| Field | Type | Description |
|-------|------|-------------|
| `protocol` | string | `"http"` or `"grpc"`. Existing tests default to `"http"`. |
| `steps[].action` | string | Extended to include `grpc_call`, `grpc_stream_open`, `grpc_stream_send`, `grpc_stream_recv`, `grpc_stream_close` |
| `steps[].service` | string | Fully qualified gRPC service name |
| `steps[].method` | string | RPC method name |
| `steps[].request` | object | Protobuf message as JSON (using proto3 JSON mapping) |
| `steps[].expect.status` | string | gRPC status code name (e.g., `"OK"`, `"NOT_FOUND"`, `"ALREADY_EXISTS"`) |
| `steps[].expect.metadata` | object | Expected gRPC response metadata (trailing headers) |

### 2. gRPC Error Code Mapping

The gRPC binding MUST map OJS error conditions to gRPC status codes. The conformance suite tests each mapping:

| OJS Error Condition | gRPC Status Code | HTTP Status Code | Test ID |
|---------------------|------------------|------------------|---------|
| Job not found | `NOT_FOUND` | 404 | `grpc-error-not-found` |
| Job already exists (unique constraint) | `ALREADY_EXISTS` | 409 | `grpc-error-already-exists` |
| Invalid job envelope | `INVALID_ARGUMENT` | 400 | `grpc-error-invalid-argument` |
| Queue paused | `FAILED_PRECONDITION` | 409 | `grpc-error-queue-paused` |
| Job not in expected state | `FAILED_PRECONDITION` | 409 | `grpc-error-wrong-state` |
| Server overloaded | `RESOURCE_EXHAUSTED` | 429 | `grpc-error-overloaded` |
| Heartbeat on expired job | `DEADLINE_EXCEEDED` | 410 | `grpc-error-deadline-exceeded` |
| Internal server error | `INTERNAL` | 500 | `grpc-error-internal` |
| Unauthorized | `UNAUTHENTICATED` | 401 | `grpc-error-unauthenticated` |
| Permission denied | `PERMISSION_DENIED` | 403 | `grpc-error-permission-denied` |

#### Error Detail Messages

gRPC errors MUST include structured error details using the `google.rpc.Status` message. The conformance suite asserts on the error detail format:

```json
{
  "id": "grpc-error-not-found",
  "description": "Get non-existent job returns NOT_FOUND with structured error",
  "level": 0,
  "protocol": "grpc",
  "spec_ref": "ojs-grpc-binding.md §5.1",
  "steps": [
    {
      "action": "grpc_call",
      "service": "ojs.v1.OJSService",
      "method": "Get",
      "request": {
        "id": "01912e4a-0000-7000-8000-000000000000"
      },
      "expect": {
        "status": "NOT_FOUND",
        "error_details": {
          "code": "JOB_NOT_FOUND",
          "message": {"pattern": ".*01912e4a-0000-7000-8000-000000000000.*"}
        }
      }
    }
  ]
}
```

### 3. Streaming Test Scenarios

#### Server Streaming: StreamJobs

The `StreamJobs` RPC delivers jobs to workers via server-side streaming. Tests verify:

```json
{
  "id": "grpc-stream-jobs-basic",
  "description": "StreamJobs delivers enqueued jobs to the connected worker",
  "level": 2,
  "protocol": "grpc",
  "spec_ref": "ojs-grpc-binding.md §4.1",
  "steps": [
    {
      "action": "grpc_call",
      "service": "ojs.v1.OJSService",
      "method": "Push",
      "request": {
        "type": "email.send",
        "queue": "stream-test",
        "args": [{"string_value": "test@example.com"}]
      },
      "expect": {"status": "OK"}
    },
    {
      "action": "grpc_stream_open",
      "service": "ojs.v1.OJSService",
      "method": "StreamJobs",
      "request": {
        "queues": ["stream-test"],
        "concurrency": 1
      },
      "stream_id": "worker-stream"
    },
    {
      "action": "grpc_stream_recv",
      "stream_id": "worker-stream",
      "timeout_ms": 5000,
      "expect": {
        "job.type": "email.send",
        "job.queue": "stream-test",
        "job.state": "ACTIVE"
      }
    },
    {
      "action": "grpc_call",
      "service": "ojs.v1.OJSService",
      "method": "Ack",
      "request": {
        "id": "{{steps[2].response.job.id}}"
      },
      "expect": {"status": "OK"}
    },
    {
      "action": "grpc_stream_close",
      "stream_id": "worker-stream"
    }
  ]
}
```

#### Server Streaming: StreamEvents

The `StreamEvents` RPC delivers lifecycle events via server-side streaming:

```json
{
  "id": "grpc-stream-events-lifecycle",
  "description": "StreamEvents delivers lifecycle events for enqueued and completed jobs",
  "level": 3,
  "protocol": "grpc",
  "spec_ref": "ojs-grpc-binding.md §4.2",
  "steps": [
    {
      "action": "grpc_stream_open",
      "service": "ojs.v1.OJSService",
      "method": "StreamEvents",
      "request": {
        "event_types": ["job.enqueued", "job.completed"]
      },
      "stream_id": "event-stream"
    },
    {
      "action": "grpc_call",
      "service": "ojs.v1.OJSService",
      "method": "Push",
      "request": {
        "type": "test.noop",
        "queue": "events-test",
        "args": []
      },
      "expect": {"status": "OK"}
    },
    {
      "action": "grpc_stream_recv",
      "stream_id": "event-stream",
      "timeout_ms": 5000,
      "expect": {
        "type": "job.enqueued",
        "subject": "{{steps[1].response.job.id}}"
      }
    },
    {
      "action": "grpc_stream_close",
      "stream_id": "event-stream"
    }
  ]
}
```

### 4. Conformance Levels for gRPC

gRPC tests are organized into the same 5 conformance levels as HTTP tests. Each level is a superset of the previous:

| Level | Name | gRPC Coverage |
|-------|------|---------------|
| 0 | Core | Push, Get, Fetch, Ack, Nack — unary RPCs only |
| 1 | Retry & Scheduling | Retry attributes, scheduled_at, cron registration |
| 2 | Streaming | StreamJobs, StreamEvents, concurrent streaming |
| 3 | Advanced | Workflows, unique jobs, batch operations, dead letter |
| 4 | Operational | Queue management, admin operations, backpressure |

A backend MAY implement only the HTTP binding and still pass conformance. gRPC conformance is separately tracked:

```
Conformance Report: ojs-backend-redis v0.2.0
  HTTP Level 4: PASS (147/147 tests)
  gRPC Level 2: PASS (89/89 tests)
  gRPC Level 3: PARTIAL (34/42 tests — workflows not implemented via gRPC)
```

### 5. Test Runner Architecture

```
┌──────────────────────────────────────────────┐
│           Conformance Test Runner             │
│                                               │
│  ┌─────────────┐     ┌─────────────────────┐ │
│  │ HTTP Runner  │     │    gRPC Runner       │ │
│  │ (existing)   │     │    (new)             │ │
│  │              │     │                      │ │
│  │ net/http     │     │ google.golang.org/   │ │
│  │              │     │ grpc                 │ │
│  └──────────────┘     └──────────────────────┘ │
│            │                   │                │
│            └───────┬───────────┘                │
│                    │                            │
│  ┌─────────────────┴──────────────────────────┐│
│  │          Shared Assertion Engine            ││
│  │  - JSON path matching                      ││
│  │  - Regex patterns                          ││
│  │  - Value interpolation ({{steps[n]...}})   ││
│  │  - Timing assertions                       ││
│  └────────────────────────────────────────────┘│
└──────────────────────────────────────────────────┘
```

The gRPC runner is implemented in Go (matching the existing HTTP runner) and shares the assertion engine. It uses dynamically generated gRPC clients from the `ojs-proto` protobuf definitions.

#### Runner Configuration

```bash
# Run all gRPC conformance tests against a server
ojs-conformance --protocol grpc \
  --target localhost:9090 \
  --level 2 \
  --timeout 30s

# Run both HTTP and gRPC tests
ojs-conformance --protocol all \
  --http-target http://localhost:8080 \
  --grpc-target localhost:9090 \
  --level 4
```

### 6. gRPC-Specific Assertions

Beyond standard value assertions, gRPC tests introduce protocol-specific assertions:

#### Metadata Assertions

```json
{
  "expect": {
    "metadata": {
      "x-ojs-request-id": {"pattern": "^[0-9a-f-]+$"},
      "x-ojs-server-version": {"pattern": "^\\d+\\.\\d+\\.\\d+$"}
    }
  }
}
```

#### Streaming Assertions

```json
{
  "action": "grpc_stream_recv",
  "stream_id": "worker-stream",
  "timeout_ms": 5000,
  "expect_count": 3,
  "expect_ordered": true,
  "expect_all": [
    {"job.type": "step-1"},
    {"job.type": "step-2"},
    {"job.type": "step-3"}
  ]
}
```

#### Deadline/Timeout Assertions

```json
{
  "action": "grpc_call",
  "service": "ojs.v1.OJSService",
  "method": "Fetch",
  "request": {"queues": ["empty-queue"]},
  "grpc_options": {
    "timeout_ms": 1000
  },
  "expect": {
    "status": "DEADLINE_EXCEEDED"
  }
}
```

## Examples

### Complete Level 0 Test: Enqueue and Process via gRPC

```json
{
  "id": "grpc-level0-enqueue-process",
  "description": "Full lifecycle: Push → Fetch → Ack via gRPC unary RPCs",
  "level": 0,
  "protocol": "grpc",
  "spec_ref": "ojs-grpc-binding.md §3",
  "steps": [
    {
      "action": "grpc_call",
      "service": "ojs.v1.OJSService",
      "method": "Push",
      "request": {
        "type": "test.grpc.basic",
        "queue": "grpc-test",
        "args": [{"string_value": "hello"}, {"number_value": 42}],
        "meta": {
          "fields": {
            "tenant_id": {"string_value": "acme-corp"}
          }
        }
      },
      "expect": {
        "status": "OK",
        "response": {
          "job.id": {"not_empty": true},
          "job.type": "test.grpc.basic",
          "job.state": "AVAILABLE"
        }
      }
    },
    {
      "action": "grpc_call",
      "service": "ojs.v1.OJSService",
      "method": "Fetch",
      "request": {
        "queues": ["grpc-test"],
        "max_jobs": 1
      },
      "expect": {
        "status": "OK",
        "response": {
          "jobs[0].id": "{{steps[0].response.job.id}}",
          "jobs[0].type": "test.grpc.basic",
          "jobs[0].state": "ACTIVE",
          "jobs[0].args[0].string_value": "hello",
          "jobs[0].args[1].number_value": 42,
          "jobs[0].meta.fields.tenant_id.string_value": "acme-corp"
        }
      }
    },
    {
      "action": "grpc_call",
      "service": "ojs.v1.OJSService",
      "method": "Ack",
      "request": {
        "id": "{{steps[0].response.job.id}}"
      },
      "expect": {
        "status": "OK"
      }
    },
    {
      "action": "grpc_call",
      "service": "ojs.v1.OJSService",
      "method": "Get",
      "request": {
        "id": "{{steps[0].response.job.id}}"
      },
      "expect": {
        "status": "OK",
        "response": {
          "job.state": "COMPLETED"
        }
      }
    }
  ]
}
```

### Streaming Backpressure Test

```json
{
  "id": "grpc-stream-backpressure",
  "description": "StreamJobs respects concurrency limit and does not over-deliver",
  "level": 2,
  "protocol": "grpc",
  "spec_ref": "ojs-grpc-binding.md §4.1.3",
  "steps": [
    {
      "action": "grpc_call",
      "service": "ojs.v1.OJSService",
      "method": "Push",
      "repeat": 5,
      "request": {
        "type": "test.backpressure",
        "queue": "bp-test",
        "args": []
      },
      "expect": {"status": "OK"}
    },
    {
      "action": "grpc_stream_open",
      "service": "ojs.v1.OJSService",
      "method": "StreamJobs",
      "request": {
        "queues": ["bp-test"],
        "concurrency": 2
      },
      "stream_id": "bp-stream"
    },
    {
      "action": "grpc_stream_recv",
      "stream_id": "bp-stream",
      "timeout_ms": 5000,
      "expect_count": 2,
      "description": "Only 2 jobs delivered (concurrency limit)"
    },
    {
      "action": "grpc_stream_close",
      "stream_id": "bp-stream"
    }
  ]
}
```

## Conformance Impact

This RFC extends the conformance test suite without changing existing conformance levels. gRPC conformance is reported separately from HTTP conformance.

New requirements introduced:

- **MUST**: Backends implementing the gRPC binding MUST map OJS error conditions to the gRPC status codes defined in this RFC. *Rationale: Consistent error code mapping enables SDK authors to write generic error handling logic.*
- **MUST**: The `StreamJobs` RPC MUST respect the `concurrency` parameter and not deliver more jobs than the client can process concurrently. *Rationale: Over-delivery defeats the purpose of worker-side concurrency control.*
- **MUST**: gRPC error responses MUST include structured error details in the `google.rpc.Status` message. *Rationale: Structured errors enable programmatic error handling beyond status code inspection.*
- **SHOULD**: Backends SHOULD pass gRPC conformance at the same level as their HTTP conformance. *Rationale: Feature parity between protocol bindings prevents operational surprises when switching transports.*
- **MAY**: Backends MAY implement gRPC streaming (Level 2+) independently of unary RPC support (Level 0–1). *Rationale: Streaming adds implementation complexity; backends should be able to adopt gRPC incrementally.*

## Backward Compatibility

This proposal is fully backward compatible. It adds new test files and a new test runner without modifying existing HTTP test definitions or the runner. The `protocol` field defaults to `"http"` for existing tests.

## Implementation Requirements

Per the OJS RFC process, proposals at Stage 2+ MUST include working prototypes in at least two languages:

- [ ] Go: gRPC test runner in `ojs-conformance/runner/grpc/`
- [ ] Go: gRPC test definitions in `ojs-conformance/tests/grpc/`
- [ ] Validation: Run gRPC tests against `ojs-backend-redis` and `ojs-backend-postgres`

## Alternatives Considered

### Reflection-Based Testing

Using gRPC reflection to discover and test services dynamically was considered. This was rejected because:

- Not all backends enable gRPC reflection in production
- Reflection-based tests cannot validate expected message structure without a schema
- Explicit test definitions provide better documentation of expected behavior

### Protocol Buffers Binary Comparison

Comparing serialized protobuf bytes directly was considered. This was rejected because:

- Protobuf serialization is not deterministic (field order may vary)
- Binary comparison does not test semantic correctness
- JSON test definitions are more readable and maintainable

### Reusing HTTP Tests via gRPC-Web

Reusing HTTP tests by running them through a gRPC-Web proxy was considered. This was rejected because:

- gRPC-Web is a subset of gRPC and does not support server streaming
- Proxy translation may mask protocol-specific bugs
- gRPC-native testing is needed to validate streaming, metadata, and error details

## Open Questions

1. **TLS testing**: Should the conformance suite test TLS termination and mTLS authentication for gRPC, or is that considered infrastructure-level concern outside the spec?

2. **Load testing integration**: Should the conformance suite include gRPC load tests (e.g., sustained streaming at high throughput) or is that better handled by the separate benchmarking suite?

3. **gRPC-Web support**: Should gRPC-Web conformance be a separate track? Some deployments use gRPC-Web for browser-based admin UIs.

4. **Protobuf version**: Should tests pin to a specific protobuf version (proto3) or support both proto2 and proto3?

5. **Streaming reconnection**: Should tests verify that `StreamJobs` correctly handles and recovers from network interruptions? This is difficult to test deterministically.
