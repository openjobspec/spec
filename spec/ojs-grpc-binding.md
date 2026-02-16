# Open Job Spec -- Layer 3: gRPC Protocol Binding

**Version:** 1.0.0-rc.1
**Date:** 2025-02-12
**Status:** Release Candidate
**Maturity:** Stable

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Conventions and Terminology](#2-conventions-and-terminology)
3. [Overview and When to Use gRPC vs HTTP](#3-overview-and-when-to-use-grpc-vs-http)
4. [Logical Operation Mapping](#4-logical-operation-mapping)
5. [Protobuf Service Definition](#5-protobuf-service-definition)
6. [Message Type Definitions](#6-message-type-definitions)
7. [gRPC Status Code Mapping](#7-grpc-status-code-mapping)
8. [Error Details and Structured Errors](#8-error-details-and-structured-errors)
9. [Metadata Propagation](#9-metadata-propagation)
10. [Streaming Semantics](#10-streaming-semantics)
11. [Authentication and Security](#11-authentication-and-security)
12. [Interoperability with HTTP Binding](#12-interoperability-with-http-binding)
13. [Performance Characteristics](#13-performance-characteristics)
14. [Examples](#14-examples)
15. [Conformance Requirements](#15-conformance-requirements)

---

## 1. Introduction

This document defines the gRPC protocol binding for the Open Job Spec (OJS). It specifies how OJS logical operations (defined in the Core Specification, `ojs-core.md`) map to gRPC service methods, request/response messages, status codes, metadata, and streaming semantics.

gRPC is an **OPTIONAL** protocol binding. Implementations that support gRPC provide higher performance and native streaming capabilities compared to the HTTP/REST binding. The HTTP binding (defined in `ojs-http-binding.md`) remains the **REQUIRED** baseline protocol that every networked OJS implementation MUST support.

The canonical protobuf definitions referenced throughout this document are maintained in the `ojs-proto` repository under the `ojs.v1` package. This specification defines the normative semantics; the `ojs-proto` repository provides the machine-readable `.proto` files suitable for code generation.

### 1.1 Relationship to Other Specifications

| Document | Layer | Relationship |
|----------|-------|-------------|
| `ojs-core.md` | Layer 1 (Core) | Defines the job envelope, lifecycle states, and logical operations this binding maps |
| `ojs-json-format.md` | Layer 2 (Wire Format) | Defines JSON serialization; gRPC uses Protobuf but MUST produce equivalent semantics |
| `ojs-http-binding.md` | Layer 3 (Protocol) | The REQUIRED HTTP binding; gRPC MUST maintain identical semantics |
| `ojs-proto` repository | Reference | Contains the full `.proto` files for code generation |

---

## 2. Conventions and Terminology

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt).

**OJS Server**: A process that implements the `OJSService` gRPC service and manages job lifecycle.

**OJS Client**: A process that connects to an OJS Server via gRPC to enqueue jobs, query state, or perform administrative operations.

**OJS Worker**: A specialized OJS Client that fetches jobs for execution and reports completion or failure.

**Job Envelope**: The canonical OJS job representation as defined in `ojs-core.md`. In the gRPC binding, this is the `Job` protobuf message.

**Logical Operation**: A named operation from the OJS Core Specification (e.g., PUSH, FETCH, ACK) that is independent of any specific protocol binding.

---

## 3. Overview and When to Use gRPC vs HTTP

### 3.1 Overview

The gRPC binding maps every OJS logical operation to a unary or server-streaming RPC method on a single `OJSService`. The binding uses Protocol Buffers (proto3) as the interface definition language and serialization format. All timestamps use `google.protobuf.Timestamp`. Job arguments use `repeated google.protobuf.Value` to maintain JSON-compatible semantics. Job IDs are UUIDv7 strings.

### 3.2 When to Use gRPC

The gRPC binding is RECOMMENDED over the HTTP binding in the following scenarios:

| Scenario | Rationale |
|----------|-----------|
| **High-throughput job ingestion** | gRPC's binary serialization and HTTP/2 multiplexing reduce per-message overhead by 5-10x compared to JSON over HTTP/1.1 |
| **Real-time job assignment** | `StreamJobs` provides server-push delivery of jobs to workers without polling, reducing latency from poll-interval to near-zero |
| **Real-time monitoring** | `StreamEvents` delivers lifecycle events as a continuous server-stream, eliminating the need for polling or WebSocket connections |
| **Polyglot service meshes** | gRPC's code generation produces type-safe clients in 10+ languages from a single `.proto` definition |
| **Internal microservice communication** | gRPC is the standard RPC framework for service-to-service calls within Kubernetes and similar environments |

### 3.3 When to Use HTTP

The HTTP binding is RECOMMENDED over gRPC in the following scenarios:

| Scenario | Rationale |
|----------|-----------|
| **Browser-based clients** | gRPC requires gRPC-Web or a proxy; HTTP/REST is natively supported |
| **Simple integrations** | curl, wget, and standard HTTP libraries require no code generation |
| **Environments without HTTP/2** | gRPC requires HTTP/2; some proxies and load balancers do not support it |
| **Debugging and inspection** | JSON payloads are human-readable; protobuf is binary |
| **Webhook-driven architectures** | HTTP callbacks are the standard mechanism for webhook delivery |

### 3.4 Dual-Protocol Deployments

Implementations that support both protocols SHOULD expose them on separate ports. The RECOMMENDED default ports are:

- HTTP: `8080`
- gRPC: `9090`

Both protocols MUST share the same backend state. A job enqueued via HTTP MUST be fetchable via gRPC and vice versa.

> **Rationale**: Separate ports simplify load balancer configuration, TLS termination, and protocol-specific middleware. Shared backend state is mandatory because clients and workers may use different protocols; a heterogeneous deployment (e.g., HTTP producers, gRPC workers) MUST behave identically to a homogeneous one.

---

## 4. Logical Operation Mapping

The following table maps each OJS logical operation (defined in `ojs-core.md`) to its corresponding gRPC RPC method.

| Logical Operation | gRPC RPC | Request Type | Response Type | RPC Kind |
|---|---|---|---|---|
| PUSH | `Enqueue` | `EnqueueRequest` | `EnqueueResponse` | Unary |
| PUSH (batch) | `EnqueueBatch` | `EnqueueBatchRequest` | `EnqueueBatchResponse` | Unary |
| FETCH | `Fetch` | `FetchRequest` | `FetchResponse` | Unary |
| FETCH (streaming) | `StreamJobs` | `StreamJobsRequest` | `stream Job` | Server streaming |
| ACK | `Ack` | `AckRequest` | `AckResponse` | Unary |
| FAIL | `Nack` | `NackRequest` | `NackResponse` | Unary |
| BEAT | `Heartbeat` | `HeartbeatRequest` | `HeartbeatResponse` | Unary |
| CANCEL | `CancelJob` | `CancelJobRequest` | `CancelJobResponse` | Unary |
| INFO | `GetJob` | `GetJobRequest` | `GetJobResponse` | Unary |

### 4.1 Additional RPCs

Beyond the core logical operations, the gRPC binding defines additional RPCs for system introspection, queue management, dead letter handling, cron scheduling, and workflow orchestration.

| Category | gRPC RPC | Request Type | Response Type | RPC Kind |
|----------|----------|-------------|---------------|----------|
| System | `Manifest` | `ManifestRequest` | `ManifestResponse` | Unary |
| System | `Health` | `HealthRequest` | `HealthResponse` | Unary |
| Queues | `ListQueues` | `ListQueuesRequest` | `ListQueuesResponse` | Unary |
| Queues | `QueueStats` | `QueueStatsRequest` | `QueueStatsResponse` | Unary |
| Queues | `PauseQueue` | `PauseQueueRequest` | `PauseQueueResponse` | Unary |
| Queues | `ResumeQueue` | `ResumeQueueRequest` | `ResumeQueueResponse` | Unary |
| Dead Letter | `ListDeadLetter` | `ListDeadLetterRequest` | `ListDeadLetterResponse` | Unary |
| Dead Letter | `RetryDeadLetter` | `RetryDeadLetterRequest` | `RetryDeadLetterResponse` | Unary |
| Dead Letter | `DeleteDeadLetter` | `DeleteDeadLetterRequest` | `DeleteDeadLetterResponse` | Unary |
| Cron | `RegisterCron` | `RegisterCronRequest` | `RegisterCronResponse` | Unary |
| Cron | `UnregisterCron` | `UnregisterCronRequest` | `UnregisterCronResponse` | Unary |
| Cron | `ListCron` | `ListCronRequest` | `ListCronResponse` | Unary |
| Workflows | `CreateWorkflow` | `CreateWorkflowRequest` | `CreateWorkflowResponse` | Unary |
| Workflows | `GetWorkflow` | `GetWorkflowRequest` | `GetWorkflowResponse` | Unary |
| Workflows | `CancelWorkflow` | `CancelWorkflowRequest` | `CancelWorkflowResponse` | Unary |
| Streaming | `StreamEvents` | `StreamEventsRequest` | `stream Event` | Server streaming |

---

## 5. Protobuf Service Definition

The following is the complete `OJSService` definition. Implementations MUST implement all RPCs corresponding to their declared conformance level. Implementations MUST NOT remove or rename any RPC method; unsupported methods MUST return `UNIMPLEMENTED` (see Section 7).

> **Rationale**: A stable service definition allows clients to be generated once and used against any conformant server. Returning `UNIMPLEMENTED` for unsupported RPCs (rather than omitting them) enables clients to detect missing capabilities at runtime rather than encountering connection-level errors.

```protobuf
syntax = "proto3";
package ojs.v1;

import "google/protobuf/timestamp.proto";
import "google/protobuf/duration.proto";
import "google/protobuf/struct.proto";

option go_package = "github.com/openjobspec/ojs-proto/gen/go/ojs/v1;ojsv1";

service OJSService {
  // ---- System ----

  // Returns the conformance manifest for this OJS implementation.
  // Conformance level: 0 (Core).
  rpc Manifest(ManifestRequest) returns (ManifestResponse);

  // Returns the health status of the OJS server and its backend.
  // Conformance level: 0 (Core).
  rpc Health(HealthRequest) returns (HealthResponse);

  // ---- Jobs ----

  // Enqueues a single job. Maps to the PUSH logical operation.
  // Conformance level: 0 (Core).
  rpc Enqueue(EnqueueRequest) returns (EnqueueResponse);

  // Enqueues multiple jobs atomically. Maps to PUSH (batch).
  // Conformance level: 4 (Advanced).
  rpc EnqueueBatch(EnqueueBatchRequest) returns (EnqueueBatchResponse);

  // Retrieves the current state and data of a job by ID.
  // Maps to the INFO logical operation.
  // Conformance level: 1 (Reliable).
  rpc GetJob(GetJobRequest) returns (GetJobResponse);

  // Cancels a job that has not yet reached a terminal state.
  // Maps to the CANCEL logical operation.
  // Conformance level: 1 (Reliable).
  rpc CancelJob(CancelJobRequest) returns (CancelJobResponse);

  // ---- Workers ----

  // Fetches one or more jobs from the specified queues for processing.
  // Maps to the FETCH logical operation. This is the unary (polling) variant.
  // Conformance level: 0 (Core).
  rpc Fetch(FetchRequest) returns (FetchResponse);

  // Acknowledges successful completion of a job.
  // Maps to the ACK logical operation.
  // Conformance level: 0 (Core).
  rpc Ack(AckRequest) returns (AckResponse);

  // Reports job failure with structured error information.
  // Maps to the FAIL logical operation.
  // Conformance level: 0 (Core).
  rpc Nack(NackRequest) returns (NackResponse);

  // Extends the visibility timeout for an active job and reports worker state.
  // Maps to the BEAT logical operation.
  // Conformance level: 1 (Reliable).
  rpc Heartbeat(HeartbeatRequest) returns (HeartbeatResponse);

  // ---- Streaming ----

  // Opens a server-streaming connection that pushes jobs to the worker
  // as they become available. High-throughput alternative to polling via Fetch.
  // See Section 10 for streaming semantics.
  // Conformance level: OPTIONAL (any level).
  rpc StreamJobs(StreamJobsRequest) returns (stream Job);

  // Opens a server-streaming connection that delivers real-time lifecycle
  // events. Used for monitoring dashboards and observability tooling.
  // See Section 10 for streaming semantics.
  // Conformance level: OPTIONAL (any level).
  rpc StreamEvents(StreamEventsRequest) returns (stream Event);

  // ---- Queues ----

  // Lists all known queues.
  // Conformance level: 0 (Core).
  rpc ListQueues(ListQueuesRequest) returns (ListQueuesResponse);

  // Returns statistics for a specific queue.
  // Conformance level: 4 (Advanced).
  rpc QueueStats(QueueStatsRequest) returns (QueueStatsResponse);

  // Pauses a queue, preventing workers from fetching new jobs from it.
  // Conformance level: 4 (Advanced).
  rpc PauseQueue(PauseQueueRequest) returns (PauseQueueResponse);

  // Resumes a previously paused queue.
  // Conformance level: 4 (Advanced).
  rpc ResumeQueue(ResumeQueueRequest) returns (ResumeQueueResponse);

  // ---- Dead Letter ----

  // Lists jobs in the dead letter queue.
  // Conformance level: 1 (Reliable).
  rpc ListDeadLetter(ListDeadLetterRequest) returns (ListDeadLetterResponse);

  // Retries a specific dead letter job by re-enqueueing it.
  // Conformance level: 1 (Reliable).
  rpc RetryDeadLetter(RetryDeadLetterRequest) returns (RetryDeadLetterResponse);

  // Permanently deletes a dead letter job.
  // Conformance level: 1 (Reliable).
  rpc DeleteDeadLetter(DeleteDeadLetterRequest) returns (DeleteDeadLetterResponse);

  // ---- Cron ----

  // Registers a new cron (periodic) job schedule.
  // Conformance level: 2 (Scheduled).
  rpc RegisterCron(RegisterCronRequest) returns (RegisterCronResponse);

  // Removes a registered cron job schedule.
  // Conformance level: 2 (Scheduled).
  rpc UnregisterCron(UnregisterCronRequest) returns (UnregisterCronResponse);

  // Lists all registered cron job schedules.
  // Conformance level: 2 (Scheduled).
  rpc ListCron(ListCronRequest) returns (ListCronResponse);

  // ---- Workflows ----

  // Creates and starts a new workflow.
  // Conformance level: 3 (Orchestration).
  rpc CreateWorkflow(CreateWorkflowRequest) returns (CreateWorkflowResponse);

  // Retrieves the current state of a workflow and all its steps.
  // Conformance level: 3 (Orchestration).
  rpc GetWorkflow(GetWorkflowRequest) returns (GetWorkflowResponse);

  // Cancels a running workflow and all of its pending/active steps.
  // Conformance level: 3 (Orchestration).
  rpc CancelWorkflow(CancelWorkflowRequest) returns (CancelWorkflowResponse);
}
```

---

## 6. Message Type Definitions

This section defines every protobuf message referenced by the `OJSService`. Field numbers are normative; implementations MUST NOT reassign them.

> **Rationale**: Stable field numbers are required for binary compatibility. Changing a field number is a breaking wire-format change that would prevent interoperability between clients and servers compiled against different versions of the `.proto` files.

### 6.1 Common Types

These messages are shared across multiple RPCs.

```protobuf
// Job represents the canonical OJS job envelope.
// See ojs-core.md Section 3.1 for the logical definition.
message Job {
  // Globally unique job identifier. MUST be a UUIDv7 string.
  // Rationale: UUIDv7 provides time-ordered, globally unique identifiers
  // without coordination, enabling sortability and distributed generation.
  string id = 1;

  // Dot-namespaced job type (e.g., "email.send", "report.generate").
  // Used for routing to the appropriate handler.
  string type = 2;

  // The queue this job belongs to. Defaults to "default" if not specified
  // at enqueue time.
  string queue = 3;

  // Positional arguments for the job handler. Uses google.protobuf.Value
  // to maintain JSON-compatible type semantics (string, number, bool,
  // null, list, struct).
  // Rationale: args is an array (not a single Struct) because Sidekiq's
  // experience proved that positional arguments with simple JSON types
  // enforce clean separation and enable cross-language inspection.
  repeated google.protobuf.Value args = 4;

  // Extensible key-value metadata for cross-cutting concerns
  // (locale, user_id, trace context, etc.).
  google.protobuf.Struct meta = 5;

  // Current lifecycle state of the job.
  JobState state = 6;

  // Job priority within the queue. Higher values indicate higher priority.
  // Default: 0.
  int32 priority = 7;

  // Current attempt number (1-indexed once execution begins).
  int32 attempt = 8;

  // Maximum number of attempts before the job is discarded.
  int32 max_attempts = 9;

  // Retry policy governing backoff behavior on failure.
  RetryPolicy retry_policy = 10;

  // Optional unique job policy for deduplication.
  UniquePolicy unique_policy = 11;

  // Optional result data set by the handler on successful completion.
  google.protobuf.Struct result = 12;

  // Ordered list of errors from each failed attempt.
  repeated JobError errors = 13;

  // Timestamp when the job was created by the client.
  google.protobuf.Timestamp created_at = 14;

  // Timestamp when the job entered the queue.
  google.protobuf.Timestamp enqueued_at = 15;

  // Timestamp when the job is scheduled to become available.
  // Only set for delayed/scheduled jobs.
  google.protobuf.Timestamp scheduled_at = 16;

  // Timestamp when a worker began executing the job.
  google.protobuf.Timestamp started_at = 17;

  // Timestamp when the job reached a terminal state (completed, cancelled,
  // or discarded).
  google.protobuf.Timestamp completed_at = 18;

  // Timestamp after which the job should be discarded if not yet started.
  google.protobuf.Timestamp expires_at = 19;

  // Maximum execution time for a single attempt.
  google.protobuf.Duration timeout = 20;

  // Visibility timeout / reservation period. When a job is fetched,
  // it is reserved for this duration. If not acknowledged within this
  // window, the job is automatically requeued.
  google.protobuf.Duration visibility_timeout = 21;

  // Optional tags for filtering and observability.
  repeated string tags = 22;

  // Optional distributed trace identifier (W3C Trace Context or custom).
  string trace_id = 23;

  // Optional workflow reference, set if this job is part of a workflow.
  string workflow_id = 24;
}

// JobState enumerates the lifecycle states defined in ojs-core.md Section 4.
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

// RetryPolicy defines backoff behavior on job failure.
// Adopts Temporal's structured retry policy format.
// See ojs-retry.md for full specification.
message RetryPolicy {
  // Total number of attempts including the initial execution.
  // 0 means unlimited retries.
  int32 max_attempts = 1;

  // Delay before the first retry attempt.
  google.protobuf.Duration initial_interval = 2;

  // Multiplier applied to the interval after each retry.
  // Default: 2.0.
  double backoff_coefficient = 3;

  // Maximum delay between retry attempts (cap on exponential growth).
  google.protobuf.Duration max_interval = 4;

  // Whether to add random jitter to retry delays to prevent thundering herd.
  bool jitter = 5;

  // Error types that MUST NOT trigger a retry. If a handler returns an
  // error whose type matches any string in this list, the job transitions
  // directly to discarded.
  repeated string non_retryable_errors = 6;
}

// UniquePolicy defines deduplication constraints for a job.
// See ojs-unique-jobs.md for full specification.
message UniquePolicy {
  // Fields from args used to compute the uniqueness key.
  repeated string key = 1;

  // Time window during which the uniqueness constraint is enforced.
  google.protobuf.Duration period = 2;

  // Behavior when a duplicate is detected.
  UniqueConflictAction on_conflict = 3;

  // States to consider when checking for duplicates.
  repeated JobState states = 4;
}

// UniqueConflictAction defines what happens when a duplicate job is detected.
enum UniqueConflictAction {
  UNIQUE_CONFLICT_ACTION_UNSPECIFIED = 0;
  UNIQUE_CONFLICT_ACTION_REJECT = 1;
  UNIQUE_CONFLICT_ACTION_REPLACE = 2;
  UNIQUE_CONFLICT_ACTION_IGNORE = 3;
}

// JobError captures structured error information from a failed attempt.
// Modeled after Faktory's {errtype, message, backtrace} format.
message JobError {
  // Machine-readable error code (e.g., "handler_error", "timeout").
  // See ojs-core.md Section 10 for standard error codes.
  string code = 1;

  // Human-readable error message.
  string message = 2;

  // Whether this error is considered retryable.
  bool retryable = 3;

  // Attempt number when this error occurred.
  int32 attempt = 4;

  // Timestamp when the error occurred.
  google.protobuf.Timestamp occurred_at = 5;

  // Optional stack trace or backtrace for debugging.
  string backtrace = 6;

  // Optional structured details about the error.
  google.protobuf.Struct details = 7;
}

// Event represents a lifecycle event emitted by the OJS server.
// See ojs-events.md for the full event vocabulary.
message Event {
  // Unique event identifier.
  string id = 1;

  // Event type (e.g., "job.enqueued", "job.completed", "workflow.started").
  string type = 2;

  // ID of the job this event relates to (if applicable).
  string job_id = 3;

  // Job type of the related job (if applicable).
  string job_type = 4;

  // Queue the related job belongs to (if applicable).
  string queue = 5;

  // Timestamp when the event was emitted.
  google.protobuf.Timestamp timestamp = 6;

  // Event-specific data.
  google.protobuf.Struct data = 7;

  // ID of the workflow this event relates to (if applicable).
  string workflow_id = 8;
}
```

### 6.2 System Messages

```protobuf
// ---- Manifest ----

message ManifestRequest {}

message ManifestResponse {
  // OJS specification version (e.g., "1.0.0-rc.1").
  string ojs_version = 1;

  // Implementation-specific information.
  Implementation implementation = 2;

  // Declared conformance level (0-4).
  int32 conformance_level = 3;

  // Protocols supported by this server.
  repeated string protocols = 4;

  // Backend type (e.g., "redis", "postgres", "memory").
  string backend = 5;

  // Optional non-standard extensions supported.
  repeated string extensions = 6;

  // Whether payload schema validation is enabled.
  bool schema_validation = 7;
}

message Implementation {
  // Implementation name (e.g., "ojs-backend-redis").
  string name = 1;

  // Implementation version (e.g., "1.0.0").
  string version = 2;

  // Implementation language (e.g., "go", "typescript").
  string language = 3;
}

// ---- Health ----

message HealthRequest {}

message HealthResponse {
  // Overall health status.
  HealthStatus status = 1;

  // Timestamp of the health check.
  google.protobuf.Timestamp timestamp = 2;

  // Backend-specific health details.
  google.protobuf.Struct details = 3;
}

enum HealthStatus {
  HEALTH_STATUS_UNSPECIFIED = 0;
  HEALTH_STATUS_OK = 1;
  HEALTH_STATUS_DEGRADED = 2;
  HEALTH_STATUS_UNHEALTHY = 3;
}
```

### 6.3 Job Messages

```protobuf
// ---- Enqueue ----

message EnqueueRequest {
  // Required. Dot-namespaced job type.
  string type = 1;

  // Required. Positional arguments for the job handler.
  repeated google.protobuf.Value args = 2;

  // Optional enqueue options.
  EnqueueOptions options = 3;
}

message EnqueueOptions {
  // Target queue. Default: "default".
  string queue = 1;

  // Job priority. Higher values = higher priority. Default: 0.
  int32 priority = 2;

  // Schedule the job for future execution.
  google.protobuf.Timestamp delay_until = 3;

  // Maximum execution time per attempt.
  google.protobuf.Duration timeout = 4;

  // Retry policy override.
  RetryPolicy retry = 5;

  // Unique job policy for deduplication.
  UniquePolicy unique = 6;

  // Time-to-live: discard the job if not started within this duration.
  google.protobuf.Duration ttl = 7;

  // Tags for filtering and observability.
  repeated string tags = 8;

  // Distributed trace identifier.
  string trace_id = 9;

  // Extensible metadata.
  google.protobuf.Struct meta = 10;

  // Maximum attempts (shorthand; overridden by retry.max_attempts if both set).
  int32 max_attempts = 11;

  // Visibility timeout / reservation period for workers.
  google.protobuf.Duration visibility_timeout = 12;
}

message EnqueueResponse {
  // The enqueued job with server-assigned fields populated (id, state,
  // enqueued_at, etc.).
  Job job = 1;
}

// ---- Enqueue Batch ----

message EnqueueBatchRequest {
  // Jobs to enqueue. Each entry specifies type, args, and optional
  // per-job options.
  repeated BatchJobEntry jobs = 1;

  // Default options applied to all jobs in the batch. Per-job options
  // override these defaults.
  EnqueueOptions default_options = 2;
}

message BatchJobEntry {
  // Required. Dot-namespaced job type.
  string type = 1;

  // Required. Positional arguments for the job handler.
  repeated google.protobuf.Value args = 2;

  // Optional per-job options that override batch defaults.
  EnqueueOptions options = 3;
}

message EnqueueBatchResponse {
  // The enqueued jobs in the same order as the request.
  repeated Job jobs = 1;

  // Number of jobs successfully enqueued.
  int32 count = 2;

  // Per-job errors for partial failures. The key is the 0-based index
  // into the request's jobs list.
  map<int32, BatchJobError> errors = 3;
}

message BatchJobError {
  // Error code.
  string code = 1;

  // Human-readable error message.
  string message = 2;
}

// ---- GetJob ----

message GetJobRequest {
  // Required. The UUIDv7 job identifier.
  string job_id = 1;
}

message GetJobResponse {
  // The job, or empty if not found (in which case the RPC returns NOT_FOUND).
  Job job = 1;
}

// ---- CancelJob ----

message CancelJobRequest {
  // Required. The UUIDv7 job identifier.
  string job_id = 1;

  // Optional reason for cancellation (stored in job metadata).
  string reason = 2;
}

message CancelJobResponse {
  // The job after cancellation, with state set to CANCELLED.
  Job job = 1;
}
```

### 6.4 Worker Messages

```protobuf
// ---- Fetch ----

message FetchRequest {
  // Required. One or more queue names to fetch from, in priority order.
  // The server SHOULD check queues in the order specified and return
  // jobs from the first non-empty queue.
  repeated string queues = 1;

  // Maximum number of jobs to return. Default: 1.
  int32 count = 2;

  // Worker identifier for tracking and observability.
  string worker_id = 3;
}

message FetchResponse {
  // Jobs assigned to this worker. May be empty if no jobs are available.
  repeated Job jobs = 1;
}

// ---- Ack ----

message AckRequest {
  // Required. The UUIDv7 job identifier being acknowledged.
  string job_id = 1;

  // Optional result data from the handler.
  google.protobuf.Struct result = 2;
}

message AckResponse {
  // Confirmation of acknowledgment.
  bool acknowledged = 1;
}

// ---- Nack ----

message NackRequest {
  // Required. The UUIDv7 job identifier being reported as failed.
  string job_id = 1;

  // Required. Structured error information from the handler.
  JobError error = 2;
}

message NackResponse {
  // The new state of the job after failure processing.
  JobState state = 1;

  // If the job will be retried, the scheduled time for the next attempt.
  google.protobuf.Timestamp next_attempt_at = 2;
}

// ---- Heartbeat ----

message HeartbeatRequest {
  // Required. The UUIDv7 job identifier (for per-job heartbeat)
  // or worker identifier (for worker-level heartbeat).
  string id = 1;

  // Worker identifier. MUST be provided for worker-level heartbeats.
  string worker_id = 2;

  // Optional: extend the visibility timeout by this duration.
  google.protobuf.Duration extend_by = 3;

  // Current worker state reported to the server.
  WorkerState current_state = 4;
}

message HeartbeatResponse {
  // Server-directed worker state. The worker SHOULD transition to this
  // state upon receiving the response. This enables the server to
  // signal "quiet" (stop fetching) or "terminate" (shut down) to workers.
  WorkerState directed_state = 1;

  // New visibility timeout deadline after extension.
  google.protobuf.Timestamp new_deadline = 2;
}

// WorkerState represents the lifecycle state of a worker process.
// See ojs-worker-protocol.md for full specification.
enum WorkerState {
  WORKER_STATE_UNSPECIFIED = 0;
  WORKER_STATE_RUNNING = 1;
  WORKER_STATE_QUIET = 2;
  WORKER_STATE_TERMINATE = 3;
}
```

### 6.5 Streaming Messages

```protobuf
// ---- StreamJobs ----

message StreamJobsRequest {
  // Required. One or more queue names to subscribe to.
  repeated string queues = 1;

  // Worker identifier. MUST be provided so the server can track
  // stream assignments and handle disconnects.
  // Rationale: Without a worker identifier, the server cannot reclaim
  // jobs that were streamed to a worker that disconnected without
  // acknowledging them.
  string worker_id = 2;

  // Maximum number of concurrent unacknowledged jobs this worker accepts.
  // The server MUST NOT send more jobs than this limit allows.
  // Default: 1.
  // Rationale: Backpressure is essential to prevent overwhelming workers.
  // Without a concurrency limit, a fast producer could flood a slow consumer.
  int32 max_concurrent = 3;
}

// The response is a stream of Job messages. Each Job sent on the stream
// represents a job assigned to the worker. The worker MUST Ack or Nack
// each received job via separate unary RPCs.

// ---- StreamEvents ----

message StreamEventsRequest {
  // Optional filter: only receive events for these queues.
  // Empty means all queues.
  repeated string queues = 1;

  // Optional filter: only receive these event types.
  // Empty means all event types.
  // Examples: "job.enqueued", "job.completed", "job.failed", "workflow.started".
  repeated string event_types = 2;

  // Optional filter: only receive events for this specific job ID.
  string job_id = 3;

  // Optional filter: only receive events for this specific workflow ID.
  string workflow_id = 4;
}

// The response is a stream of Event messages.
```

### 6.6 Queue Messages

```protobuf
// ---- ListQueues ----

message ListQueuesRequest {
  // Optional limit on the number of queues to return. Default: 100.
  int32 limit = 1;

  // Optional cursor for pagination.
  string cursor = 2;
}

message ListQueuesResponse {
  // List of queue summaries.
  repeated QueueInfo queues = 1;

  // Cursor for the next page, empty if no more results.
  string next_cursor = 2;
}

message QueueInfo {
  // Queue name.
  string name = 1;

  // Whether the queue is currently paused.
  bool paused = 2;

  // Number of jobs in the available state.
  int64 available_count = 3;

  // Timestamp when the queue was created (if tracked).
  google.protobuf.Timestamp created_at = 4;
}

// ---- QueueStats ----

message QueueStatsRequest {
  // Required. Queue name to retrieve statistics for.
  string queue = 1;
}

message QueueStatsResponse {
  // Queue name.
  string queue = 1;

  // Detailed statistics.
  QueueStatistics stats = 2;
}

message QueueStatistics {
  // Number of jobs currently in the available state.
  int64 available = 1;

  // Number of jobs currently being executed.
  int64 active = 2;

  // Number of jobs scheduled for future execution.
  int64 scheduled = 3;

  // Number of jobs in the retryable state.
  int64 retryable = 4;

  // Number of jobs in the dead letter (discarded) state.
  int64 dead = 5;

  // Number of jobs completed in the last hour.
  int64 completed_last_hour = 6;

  // Number of jobs failed in the last hour.
  int64 failed_last_hour = 7;

  // Average execution duration in milliseconds over the last hour.
  double avg_duration_ms = 8;

  // Average wait time (enqueued to started) in milliseconds.
  double avg_wait_ms = 9;

  // Throughput in jobs per second over the last minute.
  double throughput_per_second = 10;

  // Whether the queue is currently paused.
  bool paused = 11;
}

// ---- PauseQueue / ResumeQueue ----

message PauseQueueRequest {
  // Required. Queue name to pause.
  string queue = 1;
}

message PauseQueueResponse {}

message ResumeQueueRequest {
  // Required. Queue name to resume.
  string queue = 1;
}

message ResumeQueueResponse {}
```

### 6.7 Dead Letter Messages

```protobuf
// ---- ListDeadLetter ----

message ListDeadLetterRequest {
  // Optional filter by queue name.
  string queue = 1;

  // Maximum number of dead letter jobs to return. Default: 50.
  int32 limit = 2;

  // Pagination cursor.
  string cursor = 3;
}

message ListDeadLetterResponse {
  // Dead letter jobs.
  repeated Job jobs = 1;

  // Total count of dead letter jobs matching the filter.
  int64 total_count = 2;

  // Cursor for the next page, empty if no more results.
  string next_cursor = 3;
}

// ---- RetryDeadLetter ----

message RetryDeadLetterRequest {
  // Required. The UUIDv7 job identifier to retry.
  string job_id = 1;
}

message RetryDeadLetterResponse {
  // The re-enqueued job with updated state.
  Job job = 1;
}

// ---- DeleteDeadLetter ----

message DeleteDeadLetterRequest {
  // Required. The UUIDv7 job identifier to permanently delete.
  string job_id = 1;
}

message DeleteDeadLetterResponse {}
```

### 6.8 Cron Messages

```protobuf
// ---- RegisterCron ----

message RegisterCronRequest {
  // Required. Unique name for this cron schedule.
  string name = 1;

  // Required. Cron expression (5-field, with optional 6th field for seconds).
  string cron = 2;

  // IANA timezone name (e.g., "America/New_York"). Default: "UTC".
  string timezone = 3;

  // Required. Job type to enqueue on each trigger.
  string type = 4;

  // Arguments for the job.
  repeated google.protobuf.Value args = 5;

  // Enqueue options applied to each generated job.
  EnqueueOptions options = 6;
}

message RegisterCronResponse {
  // Confirmation of registration.
  string name = 1;

  // The timestamp of the next scheduled trigger.
  google.protobuf.Timestamp next_run_at = 2;
}

// ---- UnregisterCron ----

message UnregisterCronRequest {
  // Required. Name of the cron schedule to remove.
  string name = 1;
}

message UnregisterCronResponse {}

// ---- ListCron ----

message ListCronRequest {}

message ListCronResponse {
  // All registered cron schedules.
  repeated CronEntry entries = 1;
}

message CronEntry {
  // Cron schedule name.
  string name = 1;

  // Cron expression.
  string cron = 2;

  // IANA timezone.
  string timezone = 3;

  // Job type.
  string type = 4;

  // Job arguments.
  repeated google.protobuf.Value args = 5;

  // Enqueue options.
  EnqueueOptions options = 6;

  // Timestamp of the next scheduled trigger.
  google.protobuf.Timestamp next_run_at = 7;

  // Timestamp of the last trigger (if any).
  google.protobuf.Timestamp last_run_at = 8;
}
```

### 6.9 Workflow Messages

```protobuf
// ---- CreateWorkflow ----

message CreateWorkflowRequest {
  // Required. Human-readable workflow name.
  string name = 1;

  // Required. Ordered list of workflow steps.
  repeated WorkflowStep steps = 2;
}

message WorkflowStep {
  // Required. Unique step identifier within the workflow.
  string id = 1;

  // Required. Job type for this step.
  string type = 2;

  // Arguments for the step's job.
  repeated google.protobuf.Value args = 3;

  // Step IDs that must complete before this step can execute.
  repeated string depends_on = 4;

  // Optional per-step enqueue options.
  EnqueueOptions options = 5;
}

message CreateWorkflowResponse {
  // The created workflow.
  Workflow workflow = 1;
}

message Workflow {
  // Unique workflow identifier (UUIDv7).
  string id = 1;

  // Workflow name.
  string name = 2;

  // Current workflow state.
  WorkflowState state = 3;

  // Steps with their current states and assigned job IDs.
  repeated WorkflowStepStatus steps = 4;

  // Timestamp when the workflow was created.
  google.protobuf.Timestamp created_at = 5;

  // Timestamp when the workflow completed (if terminal).
  google.protobuf.Timestamp completed_at = 6;
}

enum WorkflowState {
  WORKFLOW_STATE_UNSPECIFIED = 0;
  WORKFLOW_STATE_RUNNING = 1;
  WORKFLOW_STATE_COMPLETED = 2;
  WORKFLOW_STATE_FAILED = 3;
  WORKFLOW_STATE_CANCELLED = 4;
}

message WorkflowStepStatus {
  // Step identifier.
  string id = 1;

  // Job type.
  string type = 2;

  // Current step state.
  WorkflowStepState state = 3;

  // Assigned job ID (set once the step's job has been enqueued).
  string job_id = 4;

  // Step dependencies.
  repeated string depends_on = 5;
}

enum WorkflowStepState {
  WORKFLOW_STEP_STATE_UNSPECIFIED = 0;
  WORKFLOW_STEP_STATE_WAITING = 1;
  WORKFLOW_STEP_STATE_PENDING = 2;
  WORKFLOW_STEP_STATE_ACTIVE = 3;
  WORKFLOW_STEP_STATE_COMPLETED = 4;
  WORKFLOW_STEP_STATE_FAILED = 5;
  WORKFLOW_STEP_STATE_CANCELLED = 6;
}

// ---- GetWorkflow ----

message GetWorkflowRequest {
  // Required. Workflow identifier.
  string workflow_id = 1;
}

message GetWorkflowResponse {
  Workflow workflow = 1;
}

// ---- CancelWorkflow ----

message CancelWorkflowRequest {
  // Required. Workflow identifier.
  string workflow_id = 1;

  // Optional reason for cancellation.
  string reason = 2;
}

message CancelWorkflowResponse {
  Workflow workflow = 1;
}
```

---

## 7. gRPC Status Code Mapping

Implementations MUST map OJS error conditions to gRPC status codes as defined in this section. This mapping ensures that gRPC clients can interpret errors using standard gRPC error handling mechanisms.

> **Rationale**: gRPC defines a fixed set of status codes (based on `google.rpc.Code`). A deterministic mapping from OJS error codes to gRPC status codes is required so that clients can implement consistent error handling logic regardless of which OJS server they connect to. Without this mapping, each implementation would choose its own codes, making cross-implementation error handling unreliable.

### 7.1 Status Code Table

| gRPC Status Code | OJS Error Code(s) | When Used |
|---|---|---|
| `OK` (0) | _(success)_ | The RPC completed successfully. |
| `INVALID_ARGUMENT` (3) | `invalid_payload`, `invalid_request`, `schema_validation` | The request contains invalid data: malformed fields, missing required fields, or payload that fails schema validation. |
| `NOT_FOUND` (5) | `not_found` | The referenced job, queue, workflow, or cron schedule does not exist. |
| `ALREADY_EXISTS` (6) | `duplicate` | A unique job constraint was violated and the conflict action is `reject`. |
| `FAILED_PRECONDITION` (9) | `queue_paused`, `unsupported` | The operation cannot be performed in the current system state. A queue is paused and the operation requires it to be active, or the operation requires a conformance level the server does not support. |
| `RESOURCE_EXHAUSTED` (8) | `rate_limited` | A rate limit has been exceeded. The client SHOULD retry after the duration indicated in the `retry-after` metadata key (see Section 9). |
| `INTERNAL` (13) | `backend_error` | An internal error occurred in the OJS server or its backend storage. |
| `UNAVAILABLE` (14) | _(backend unavailable)_ | The backend storage is temporarily unreachable. The client SHOULD retry with exponential backoff. |
| `UNIMPLEMENTED` (12) | `unsupported` | The RPC method is not implemented by this server (e.g., workflow RPCs on a Level 0 server). |

### 7.2 Mapping Rules

1. Implementations MUST use the gRPC status codes defined in the table above for the corresponding OJS error conditions. Using a different gRPC status code for a defined OJS error condition is a conformance violation.

   > **Rationale**: Deterministic status code mapping enables clients to implement retry logic, error categorization, and user-facing error messages based solely on the gRPC status code, without needing to parse error detail payloads.

2. Implementations MUST include the OJS error code in the `google.rpc.Status` detail payload (see Section 8) in addition to the gRPC status code.

   > **Rationale**: gRPC status codes are coarse-grained (e.g., `INVALID_ARGUMENT` covers both `invalid_payload` and `schema_validation`). The OJS error code in the detail payload provides the fine-grained classification needed for programmatic error handling.

3. When an RPC is not supported at the server's conformance level, the server MUST return `UNIMPLEMENTED` with a descriptive message indicating the required conformance level.

   > **Rationale**: `UNIMPLEMENTED` is the standard gRPC code for methods that exist in the service definition but are not available. Including the required level in the message helps operators understand what capability is missing.

4. For `RESOURCE_EXHAUSTED`, implementations SHOULD include a `retry-after` metadata key (see Section 9.3) indicating when the client may retry.

5. For `UNAVAILABLE`, clients SHOULD retry with exponential backoff. Implementations SHOULD include a `retry-after` metadata key if the unavailability duration is known.

---

## 8. Error Details and Structured Errors

### 8.1 Error Detail Format

Implementations MUST encode OJS error details using `google.rpc.Status` with `google.rpc.ErrorInfo` as the detail type. This provides structured, machine-readable error information beyond the gRPC status code and message string.

> **Rationale**: The bare gRPC status code and message string are insufficient for programmatic error handling. `google.rpc.ErrorInfo` is the standard mechanism for attaching domain-specific error metadata to gRPC errors, and it is supported by all major gRPC client libraries.

### 8.2 ErrorInfo Structure

```protobuf
// Included via google.rpc.ErrorInfo; shown here for clarity.
message OJSErrorDetail {
  // OJS error code (e.g., "invalid_payload", "duplicate", "queue_paused").
  // Maps to the standard error codes defined in ojs-core.md Section 10.
  string code = 1;      // Carried in ErrorInfo.reason

  // Human-readable error message.
  string message = 2;   // Carried in Status.message

  // Whether the error condition is retryable.
  bool retryable = 3;   // Carried in ErrorInfo.metadata["retryable"]

  // Optional request identifier for correlation.
  string request_id = 4; // Carried in ErrorInfo.metadata["request_id"]
}
```

### 8.3 Error Response Example

The following demonstrates how an OJS error is encoded in a gRPC error response (shown as conceptual JSON for clarity):

```json
{
  "code": 3,
  "message": "Payload validation failed against schema urn:ojs:schema:email.send:v1",
  "details": [
    {
      "@type": "type.googleapis.com/google.rpc.ErrorInfo",
      "reason": "schema_validation",
      "domain": "openjobspec.org",
      "metadata": {
        "retryable": "false",
        "request_id": "req_01HZ3KR200",
        "schema_uri": "urn:ojs:schema:email.send:v1"
      }
    },
    {
      "@type": "type.googleapis.com/google.rpc.BadRequest",
      "field_violations": [
        {
          "field": "args[0].to",
          "description": "required field missing"
        }
      ]
    }
  ]
}
```

### 8.4 Implementation Requirements

1. Implementations MUST include at least one `google.rpc.ErrorInfo` detail in every error response.

   > **Rationale**: Without `ErrorInfo`, clients cannot determine the OJS-specific error code from the gRPC error alone, since multiple OJS codes map to the same gRPC status code.

2. The `domain` field in `ErrorInfo` MUST be set to `"openjobspec.org"`.

   > **Rationale**: The domain identifies the error as originating from an OJS server, distinguishing it from errors generated by gRPC infrastructure, proxies, or other middleware.

3. The `reason` field in `ErrorInfo` MUST contain the OJS error code string.

4. For validation errors (`invalid_payload`, `schema_validation`), implementations SHOULD include a `google.rpc.BadRequest` detail with per-field violation descriptions.

5. For rate limiting (`rate_limited`), implementations SHOULD include a `google.rpc.RetryInfo` detail with the minimum retry delay.

---

## 9. Metadata Propagation

gRPC metadata (analogous to HTTP headers) is used to propagate cross-cutting concerns such as authentication credentials, request identifiers, trace context, and rate-limit information.

### 9.1 Request Metadata (Client to Server)

Implementations MUST support the following request metadata keys. Metadata keys are case-insensitive as per the gRPC specification.

| Metadata Key | Type | Required | Description |
|---|---|---|---|
| `x-ojs-request-id` | string | SHOULD | Unique request identifier for correlation and debugging. The server MUST echo this value in response metadata if provided. |
| `x-ojs-api-key` | string | MAY | API key for authentication (see Section 11). |
| `traceparent` | string | MAY | W3C Trace Context propagation header. |
| `tracestate` | string | MAY | W3C Trace Context state header. |
| `x-ojs-idempotency-key` | string | MAY | Idempotency key for safe retries of mutating operations. |

> **Rationale**: `x-ojs-request-id` enables end-to-end request tracing across protocol boundaries. When a request originates via HTTP and triggers a gRPC call (or vice versa), the request ID ties the operations together. The server MUST echo it so that clients can correlate responses with requests in async or multiplexed scenarios.

### 9.2 Response Metadata (Server to Client)

| Metadata Key | Type | Always Present | Description |
|---|---|---|---|
| `x-ojs-request-id` | string | When sent by client | Echoed from the request. |
| `x-ojs-server-version` | string | SHOULD | The OJS implementation version string. |
| `x-ojs-conformance-level` | string | SHOULD | The server's conformance level as a digit (e.g., "2"). |

### 9.3 Rate Limiting Metadata

When a server returns `RESOURCE_EXHAUSTED`, the following response metadata keys provide retry guidance:

| Metadata Key | Type | Description |
|---|---|---|
| `retry-after` | string | Seconds (as a decimal string) until the client may retry. |
| `x-ojs-ratelimit-limit` | string | The rate limit ceiling for the current window. |
| `x-ojs-ratelimit-remaining` | string | The number of requests remaining in the current window. |
| `x-ojs-ratelimit-reset` | string | Unix timestamp (seconds) when the rate limit window resets. |

### 9.4 Distributed Trace Context

Implementations that support distributed tracing MUST propagate W3C Trace Context headers (`traceparent`, `tracestate`) through gRPC metadata. When a job is enqueued with trace context metadata, the server MUST store the trace context in the job's `meta` field so that workers processing the job can continue the trace.

> **Rationale**: Trace context propagation across job boundaries is essential for end-to-end observability. Without it, the trace breaks at the enqueue-dequeue boundary, making it impossible to correlate a job's execution with the request that created it.

---

## 10. Streaming Semantics

The gRPC binding defines two server-streaming RPCs: `StreamJobs` for real-time job assignment and `StreamEvents` for lifecycle event monitoring. This section specifies the normative behavior of these streams.

### 10.1 StreamJobs

`StreamJobs` provides a persistent, server-streaming connection over which the OJS server pushes jobs to a worker as they become available. It is a high-throughput alternative to polling via the `Fetch` RPC.

#### 10.1.1 Connection Lifecycle

1. The worker opens a `StreamJobs` stream by sending a `StreamJobsRequest` specifying the queues to watch, a `worker_id`, and a `max_concurrent` limit.

2. The server registers the stream and begins sending `Job` messages as jobs become available on the specified queues.

3. Each `Job` sent on the stream represents a job assigned to the worker. The job transitions to the `active` state and the visibility timeout begins.

4. The worker MUST acknowledge or fail each received job by calling the `Ack` or `Nack` RPC (unary). The worker MUST NOT acknowledge jobs on the stream itself.

   > **Rationale**: Acknowledgment via separate unary RPCs (rather than client-streaming on the same connection) decouples job delivery from acknowledgment, simplifies flow control, and allows the server to track individual job outcomes independently of stream health.

5. The server MUST NOT send more unacknowledged jobs than `max_concurrent`. Once the worker acknowledges a job, the server MAY send a new job.

   > **Rationale**: Backpressure prevents worker overload. Without this constraint, a burst of available jobs could overwhelm a worker with limited processing capacity, leading to visibility timeout expirations and unnecessary requeues.

6. If the stream disconnects (client cancellation, network failure, or server shutdown), the server MUST reclaim all unacknowledged jobs sent on that stream by transitioning them back to the `available` state after their visibility timeout expires.

   > **Rationale**: Workers may crash or lose connectivity. Without reclamation, jobs assigned to a dead stream would be stuck in the `active` state indefinitely.

#### 10.1.2 Queue Pause Behavior

If a queue is paused while a `StreamJobs` connection is active for that queue, the server MUST stop sending jobs from the paused queue but MUST NOT close the stream. When the queue is resumed, the server MUST resume sending jobs.

> **Rationale**: Closing the stream on pause would force the worker to reconnect, which is disruptive and may trigger unnecessary reconnection storms in large deployments. Pausing delivery on the stream preserves the connection for when the queue is resumed.

#### 10.1.3 Ordering

Jobs delivered via `StreamJobs` SHOULD follow the same ordering guarantees as the `Fetch` RPC (FIFO within a priority level, higher priority first). However, strict ordering is NOT guaranteed across concurrent streams to different workers.

### 10.2 StreamEvents

`StreamEvents` provides a server-streaming connection that delivers real-time lifecycle events for monitoring, dashboards, and observability tooling.

#### 10.2.1 Connection Lifecycle

1. The client opens a `StreamEvents` stream by sending a `StreamEventsRequest` with optional filters (queues, event types, job ID, workflow ID).

2. The server begins sending `Event` messages matching the filter criteria.

3. Events are delivered on a best-effort basis. The server SHOULD buffer events briefly during transient backpressure, but MAY drop events if the client cannot consume them fast enough.

   > **Rationale**: Event streams are for monitoring, not transactional processing. Dropping events under backpressure prevents unbounded server-side memory growth and is consistent with the semantics of observability data.

4. If no filters are specified, the server MUST send all events.

5. The server SHOULD send a heartbeat event (type `"stream.keepalive"`) at least every 30 seconds on an idle stream to detect stale connections.

#### 10.2.2 Event Types

The following event types MUST be supported by implementations that offer `StreamEvents`:

| Event Type | Conformance Level | Description |
|---|---|---|
| `job.enqueued` | 0 | Job entered the `available` state |
| `job.started` | 0 | Worker began executing the job |
| `job.completed` | 0 | Job handler succeeded |
| `job.failed` | 0 | Job handler failed (per attempt) |
| `job.dead` | 1 | Job moved to dead letter queue (discarded) |
| `job.retrying` | 1 | Job scheduled for retry |
| `job.heartbeat` | 1 | Heartbeat extended for a job |
| `job.cancelled` | 1 | Job was cancelled |
| `workflow.started` | 3 | First step of a workflow began |
| `workflow.step_completed` | 3 | A workflow step completed |
| `workflow.completed` | 3 | All workflow steps completed |
| `workflow.failed` | 3 | A workflow step failed terminally |
| `stream.keepalive` | 0 | Heartbeat to keep the connection alive |

#### 10.2.3 Filtering

Filters in `StreamEventsRequest` are combined with AND logic:

- If `queues` is non-empty, only events for those queues are delivered.
- If `event_types` is non-empty, only those event types are delivered.
- If `job_id` is set, only events for that specific job are delivered.
- If `workflow_id` is set, only events for that workflow and its jobs are delivered.

---

## 11. Authentication and Security

Authentication is a protocol-binding concern, not a core spec concern. This section defines the authentication mechanisms available for the gRPC binding.

### 11.1 Mutual TLS (mTLS)

mTLS is the RECOMMENDED authentication mechanism for production gRPC deployments.

1. Implementations SHOULD support mTLS for both server authentication (verifying the server's identity to the client) and client authentication (verifying the client's identity to the server).

2. When mTLS is enabled, the server MUST reject connections from clients that do not present a valid client certificate.

3. The server MAY extract authorization information (roles, permissions, tenant ID) from the client certificate's Subject or Subject Alternative Name fields.

> **Rationale**: mTLS provides strong mutual authentication and encryption without application-level credential management. It is the standard authentication mechanism for gRPC in service mesh environments (Istio, Linkerd) and Kubernetes-native deployments.

### 11.2 API Key Authentication

For simpler deployments where mTLS is not feasible, implementations MAY support API key authentication via gRPC metadata.

1. The client MUST send the API key in the `x-ojs-api-key` metadata key.

2. The server MUST validate the API key before processing any RPC.

3. If the API key is missing or invalid, the server MUST return `UNAUTHENTICATED` (gRPC status code 16).

4. API keys MUST be transmitted over TLS-encrypted connections. Implementations MUST NOT accept API keys over plaintext connections in production.

   > **Rationale**: API keys transmitted in plaintext are trivially interceptable. Requiring TLS prevents credential theft via network sniffing.

### 11.3 Token-Based Authentication

Implementations MAY support bearer token authentication (e.g., JWT, OAuth2 access tokens) via the `authorization` metadata key.

1. The client sends `authorization: Bearer <token>` in the request metadata.

2. The server validates the token and extracts claims for authorization decisions.

3. Invalid or expired tokens MUST result in `UNAUTHENTICATED`.

### 11.4 Per-RPC Authorization

Implementations MAY enforce per-RPC authorization policies. For example:

- Read-only tokens may call `GetJob`, `ListQueues`, `QueueStats`, and `StreamEvents` but not `Enqueue` or `CancelJob`.
- Worker tokens may call `Fetch`, `Ack`, `Nack`, `Heartbeat`, and `StreamJobs` but not queue management RPCs.

Authorization failures MUST return `PERMISSION_DENIED` (gRPC status code 7).

---

## 12. Interoperability with HTTP Binding

This section defines the requirements for implementations that support both the gRPC and HTTP protocol bindings simultaneously.

### 12.1 Semantic Equivalence

The gRPC and HTTP bindings MUST maintain identical semantics. The following invariants MUST hold:

1. **Cross-protocol job access**: A job enqueued via HTTP `POST /ojs/v1/jobs` MUST be retrievable via the gRPC `GetJob` RPC, and vice versa. The job's state, metadata, and all fields MUST be identical regardless of which protocol is used to access them.

   > **Rationale**: OJS supports heterogeneous deployments where producers use HTTP (e.g., a web application) and workers use gRPC (e.g., high-throughput Go services). Without cross-protocol equivalence, these deployments would silently produce inconsistent behavior.

2. **Cross-protocol worker interop**: A job enqueued via gRPC `Enqueue` MUST be fetchable by an HTTP worker via `POST /ojs/v1/workers/fetch`, and a job fetched via gRPC `Fetch` MUST be acknowledgeable via HTTP `POST /ojs/v1/workers/ack`.

   > **Rationale**: Workers may be implemented in different languages using different protocol bindings. A Go gRPC worker and a Python HTTP worker MUST be able to process jobs from the same queues without conflicts.

3. **State consistency**: Both protocols MUST operate against the same backend state. There MUST NOT be separate job stores for HTTP and gRPC.

4. **Event parity**: Events emitted for operations performed via HTTP MUST be visible on the gRPC `StreamEvents` stream, and vice versa.

### 12.2 Field Mapping

The following table defines how key data types map between the HTTP (JSON) and gRPC (protobuf) representations:

| Concept | HTTP/JSON | gRPC/Protobuf |
|---|---|---|
| Job ID | `string` (UUIDv7) | `string` (UUIDv7) |
| Timestamps | ISO 8601 / RFC 3339 string | `google.protobuf.Timestamp` |
| Durations | Integer milliseconds (`timeout_ms`) | `google.protobuf.Duration` |
| Job arguments | `"args": [...]` (JSON array) | `repeated google.protobuf.Value args` |
| Metadata | `"meta": {...}` (JSON object) | `google.protobuf.Struct meta` |
| Job state | String enum (`"available"`, `"active"`, etc.) | `JobState` enum |
| Error code | String in `error.code` field | `ErrorInfo.reason` |
| Null values | JSON `null` | `google.protobuf.NullValue` within `Value` |

### 12.3 Manifest Protocol Declaration

An implementation that supports both HTTP and gRPC MUST declare both protocols in its manifest:

```json
{
  "ojs_version": "1.0.0-rc.1",
  "protocols": ["http", "grpc"],
  ...
}
```

The same manifest content MUST be returned by both `GET /ojs/manifest` (HTTP) and the `Manifest` RPC (gRPC).

---

## 13. Performance Characteristics

This section describes the expected performance characteristics of the gRPC binding relative to the HTTP binding. These are guidelines, not normative requirements.

### 13.1 Comparison

| Dimension | HTTP/JSON | gRPC/Protobuf | Notes |
|---|---|---|---|
| **Serialization overhead** | ~2-5x larger payloads | Baseline | Protobuf binary encoding is 2-5x smaller than JSON for typical job envelopes |
| **Serialization speed** | ~5-10x slower | Baseline | JSON parsing is significantly slower than protobuf decoding |
| **Connection overhead** | New connection per request (HTTP/1.1) or multiplexed (HTTP/2) | Multiplexed (HTTP/2) | gRPC always uses HTTP/2; HTTP APIs may use HTTP/1.1 |
| **Latency (single job enqueue)** | ~1-5ms | ~0.5-2ms | Reduced serialization and header overhead |
| **Throughput (sustained)** | ~5,000-15,000 jobs/sec | ~15,000-50,000 jobs/sec | gRPC's binary framing and multiplexing improve throughput |
| **Streaming** | Requires polling or WebSocket | Native server-streaming | Eliminates polling latency for `StreamJobs` and `StreamEvents` |
| **Client code generation** | Manual or OpenAPI-based | Native protoc/buf generation | gRPC produces type-safe clients from `.proto` files |
| **Debugging** | Human-readable JSON | Requires grpcurl or similar | JSON is easier to inspect manually |

### 13.2 Recommendations

- For **job ingestion exceeding 10,000 jobs/second**, gRPC is RECOMMENDED due to lower per-message overhead.
- For **worker pools exceeding 100 workers**, `StreamJobs` is RECOMMENDED over `Fetch` polling to reduce server load and latency.
- For **monitoring dashboards**, `StreamEvents` is RECOMMENDED over HTTP polling for real-time responsiveness.
- For **batch operations**, gRPC reduces the serialization cost proportionally to the batch size.

---

## 14. Examples

This section provides concrete examples of interacting with an OJS gRPC server using `grpcurl`, a command-line tool for gRPC. All examples assume the server is running on `localhost:9090` with reflection enabled.

### 14.1 Health Check

```bash
grpcurl -plaintext localhost:9090 ojs.v1.OJSService/Health
```

Response:

```json
{
  "status": "HEALTH_STATUS_OK",
  "timestamp": "2025-02-12T10:30:00Z"
}
```

### 14.2 Manifest

```bash
grpcurl -plaintext localhost:9090 ojs.v1.OJSService/Manifest
```

Response:

```json
{
  "ojsVersion": "1.0.0-rc.1",
  "implementation": {
    "name": "ojs-backend-redis",
    "version": "1.0.0",
    "language": "go"
  },
  "conformanceLevel": 2,
  "protocols": ["http", "grpc"],
  "backend": "redis",
  "schemaValidation": true
}
```

### 14.3 Enqueue a Job

```bash
grpcurl -plaintext -d '{
  "type": "email.send",
  "args": [
    {"stringValue": "user@example.com"},
    {"stringValue": "welcome"}
  ],
  "options": {
    "queue": "email",
    "retry": {
      "maxAttempts": 5,
      "initialInterval": "1s",
      "backoffCoefficient": 2.0,
      "maxInterval": "300s",
      "jitter": true
    },
    "tags": ["onboarding", "email"]
  }
}' localhost:9090 ojs.v1.OJSService/Enqueue
```

Response:

```json
{
  "job": {
    "id": "019462a0-b1c2-7def-8abc-123456789012",
    "type": "email.send",
    "queue": "email",
    "args": [
      {"stringValue": "user@example.com"},
      {"stringValue": "welcome"}
    ],
    "state": "JOB_STATE_AVAILABLE",
    "attempt": 0,
    "maxAttempts": 5,
    "retryPolicy": {
      "maxAttempts": 5,
      "initialInterval": "1s",
      "backoffCoefficient": 2.0,
      "maxInterval": "300s",
      "jitter": true
    },
    "createdAt": "2025-02-12T10:30:00.123Z",
    "enqueuedAt": "2025-02-12T10:30:00.125Z",
    "tags": ["onboarding", "email"]
  }
}
```

### 14.4 Batch Enqueue

```bash
grpcurl -plaintext -d '{
  "jobs": [
    {
      "type": "email.send",
      "args": [{"stringValue": "a@example.com"}]
    },
    {
      "type": "email.send",
      "args": [{"stringValue": "b@example.com"}]
    }
  ],
  "defaultOptions": {
    "queue": "email"
  }
}' localhost:9090 ojs.v1.OJSService/EnqueueBatch
```

Response:

```json
{
  "jobs": [
    {
      "id": "019462a0-b1c2-7def-8abc-123456789013",
      "type": "email.send",
      "state": "JOB_STATE_AVAILABLE"
    },
    {
      "id": "019462a0-b1c2-7def-8abc-123456789014",
      "type": "email.send",
      "state": "JOB_STATE_AVAILABLE"
    }
  ],
  "count": 2
}
```

### 14.5 Fetch a Job

```bash
grpcurl -plaintext -d '{
  "queues": ["email", "default"],
  "count": 1,
  "workerId": "worker-go-01"
}' localhost:9090 ojs.v1.OJSService/Fetch
```

Response:

```json
{
  "jobs": [
    {
      "id": "019462a0-b1c2-7def-8abc-123456789012",
      "type": "email.send",
      "queue": "email",
      "args": [
        {"stringValue": "user@example.com"},
        {"stringValue": "welcome"}
      ],
      "state": "JOB_STATE_ACTIVE",
      "attempt": 1
    }
  ]
}
```

### 14.6 Acknowledge a Job

```bash
grpcurl -plaintext -d '{
  "jobId": "019462a0-b1c2-7def-8abc-123456789012",
  "result": {
    "fields": {
      "message_id": {"stringValue": "msg_abc123"}
    }
  }
}' localhost:9090 ojs.v1.OJSService/Ack
```

Response:

```json
{
  "acknowledged": true
}
```

### 14.7 Report Failure (Nack)

```bash
grpcurl -plaintext -d '{
  "jobId": "019462a0-b1c2-7def-8abc-123456789012",
  "error": {
    "code": "handler_error",
    "message": "SMTP connection refused",
    "retryable": true,
    "attempt": 1,
    "occurredAt": "2025-02-12T10:30:05Z"
  }
}' localhost:9090 ojs.v1.OJSService/Nack
```

Response:

```json
{
  "state": "JOB_STATE_RETRYABLE",
  "nextAttemptAt": "2025-02-12T10:31:00Z"
}
```

### 14.8 Get Job

```bash
grpcurl -plaintext -d '{
  "jobId": "019462a0-b1c2-7def-8abc-123456789012"
}' localhost:9090 ojs.v1.OJSService/GetJob
```

### 14.9 Stream Events (Monitoring)

```bash
grpcurl -plaintext -d '{
  "queues": ["email"],
  "eventTypes": ["job.completed", "job.failed"]
}' localhost:9090 ojs.v1.OJSService/StreamEvents
```

This opens a long-lived connection. Events are printed as they arrive:

```json
{
  "id": "evt_019462a1-0001",
  "type": "job.completed",
  "jobId": "019462a0-b1c2-7def-8abc-123456789012",
  "jobType": "email.send",
  "queue": "email",
  "timestamp": "2025-02-12T10:30:02.789Z",
  "data": {
    "fields": {
      "duration_ms": {"numberValue": 1333},
      "attempt": {"numberValue": 1}
    }
  }
}
```

### 14.10 Stream Jobs (Worker)

```bash
grpcurl -plaintext -d '{
  "queues": ["email", "default"],
  "workerId": "worker-go-01",
  "maxConcurrent": 5
}' localhost:9090 ojs.v1.OJSService/StreamJobs
```

Jobs are pushed to the client as they become available. Each job MUST be acknowledged via a separate `Ack` or `Nack` call.

### 14.11 Queue Statistics

```bash
grpcurl -plaintext -d '{"queue": "email"}' \
  localhost:9090 ojs.v1.OJSService/QueueStats
```

Response:

```json
{
  "queue": "email",
  "stats": {
    "available": 1234,
    "active": 42,
    "scheduled": 56,
    "retryable": 8,
    "dead": 3,
    "completedLastHour": 8920,
    "failedLastHour": 12,
    "avgDurationMs": 234.5,
    "avgWaitMs": 1456.2,
    "throughputPerSecond": 2.48,
    "paused": false
  }
}
```

### 14.12 Create a Workflow

```bash
grpcurl -plaintext -d '{
  "name": "etl-pipeline",
  "steps": [
    {
      "id": "extract",
      "type": "data.fetch",
      "args": [{"stringValue": "api.example.com/data"}],
      "dependsOn": []
    },
    {
      "id": "transform",
      "type": "data.transform",
      "args": [{"stringValue": "csv"}],
      "dependsOn": ["extract"]
    },
    {
      "id": "load",
      "type": "data.load",
      "args": [{"stringValue": "warehouse"}],
      "dependsOn": ["transform"]
    }
  ]
}' localhost:9090 ojs.v1.OJSService/CreateWorkflow
```

Response:

```json
{
  "workflow": {
    "id": "019462a0-c3d4-7def-8abc-123456789099",
    "name": "etl-pipeline",
    "state": "WORKFLOW_STATE_RUNNING",
    "steps": [
      {"id": "extract", "type": "data.fetch", "state": "WORKFLOW_STEP_STATE_PENDING", "jobId": "019462a0-c3d4-7def-8abc-123456789100"},
      {"id": "transform", "type": "data.transform", "state": "WORKFLOW_STEP_STATE_WAITING"},
      {"id": "load", "type": "data.load", "state": "WORKFLOW_STEP_STATE_WAITING"}
    ],
    "createdAt": "2025-02-12T10:30:00Z"
  }
}
```

### 14.13 With Metadata (Authentication + Request ID)

```bash
grpcurl -plaintext \
  -H 'x-ojs-api-key: sk_live_abc123' \
  -H 'x-ojs-request-id: req_019462a0' \
  -H 'traceparent: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01' \
  -d '{"type": "email.send", "args": [{"stringValue": "user@example.com"}]}' \
  localhost:9090 ojs.v1.OJSService/Enqueue
```

---

## 15. Conformance Requirements

### 15.1 Conformance Levels for gRPC RPCs

Implementations that advertise gRPC support MUST implement all RPCs corresponding to their declared conformance level, plus all RPCs from lower levels. RPCs for higher conformance levels MUST return `UNIMPLEMENTED`.

| Conformance Level | Required RPCs |
|---|---|
| **Level 0 (Core)** | `Manifest`, `Health`, `Enqueue`, `Fetch`, `Ack`, `Nack`, `ListQueues` |
| **Level 1 (Reliable)** | Level 0 + `GetJob`, `CancelJob`, `Heartbeat`, `ListDeadLetter`, `RetryDeadLetter`, `DeleteDeadLetter` |
| **Level 2 (Scheduled)** | Level 1 + `RegisterCron`, `UnregisterCron`, `ListCron` |
| **Level 3 (Orchestration)** | Level 2 + `CreateWorkflow`, `GetWorkflow`, `CancelWorkflow` |
| **Level 4 (Advanced)** | Level 3 + `EnqueueBatch`, `QueueStats`, `PauseQueue`, `ResumeQueue` |
| **Optional (any level)** | `StreamJobs`, `StreamEvents` |

### 15.2 Reflection

Implementations SHOULD support [gRPC Server Reflection](https://github.com/grpc/grpc/blob/master/doc/server-reflection.md) to enable discovery by tools such as `grpcurl`, `grpcui`, and Postman.

> **Rationale**: Reflection enables dynamic client discovery and debugging without requiring pre-compiled protobuf stubs. This is particularly valuable during development, integration testing, and incident response.

### 15.3 Health Checking

In addition to the OJS-specific `Health` RPC, implementations SHOULD implement the standard [gRPC Health Checking Protocol](https://github.com/grpc/grpc/blob/master/doc/health-checking.md) (`grpc.health.v1.Health`) for compatibility with Kubernetes liveness/readiness probes and load balancer health checks.

> **Rationale**: The standard gRPC health checking protocol is understood by Kubernetes, Envoy, and other infrastructure components. Supporting it allows the OJS server to participate in standard health checking workflows without custom configuration.

### 15.4 Deadlines and Timeouts

1. Clients SHOULD set gRPC deadlines on all unary RPCs. A RECOMMENDED default deadline is 30 seconds.

2. Servers MUST respect client-set deadlines and return `DEADLINE_EXCEEDED` if processing cannot complete within the deadline.

3. For streaming RPCs (`StreamJobs`, `StreamEvents`), deadlines apply to the initial connection setup, not the stream lifetime. Streams are expected to be long-lived.

### 15.5 Graceful Shutdown

When the OJS server is shutting down:

1. The server MUST stop accepting new RPC calls.

2. The server MUST complete in-flight unary RPCs.

3. The server MUST close all active streams with a `UNAVAILABLE` status code and a message indicating shutdown.

4. The server SHOULD send a `HeartbeatResponse` with `directed_state = WORKER_STATE_TERMINATE` to all connected workers before closing streams.

   > **Rationale**: Sending `TERMINATE` via the heartbeat mechanism allows workers to initiate graceful shutdown of their own processing, rather than discovering the server is gone only when their next RPC fails.

---

_Open Job Spec v1.0.0-rc.1 -- gRPC Protocol Binding -- February 2025_
_https://openjobspec.org_
