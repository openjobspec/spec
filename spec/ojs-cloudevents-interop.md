# Open Job Spec — CloudEvents Interoperability

**Open Job Spec v1.0.0-rc.1**

| Field       | Value                                                       |
|-------------|-------------------------------------------------------------|
| Version     | 1.0.0-rc.1                                                  |
| Status      | Release Candidate 1                                         |
| Maturity    | Experimental                                                |
| Date        | 2026-02-19                                                  |
| Layer       | Cross-cutting (Layers 1–3)                                  |
| Depends On  | ojs-core.md, ojs-events.md, ojs-http-binding.md            |
| URI         | https://openjobspec.org/spec/v1/ojs-cloudevents-interop     |

---

## Abstract

This document defines bidirectional conversion between OJS job envelopes, OJS lifecycle events, and the [CloudEvents v1.0 specification](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md). It enables OJS implementations to interoperate with the broader CNCF event-driven ecosystem — including Knative Eventing, Azure Event Grid, AWS EventBridge, and Dapr pub/sub — without sacrificing the domain-specific semantics of OJS.

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Architectural Relationship](#4-architectural-relationship)
5. [OJS Event → CloudEvent Mapping](#5-ojs-event--cloudevent-mapping)
6. [CloudEvent → OJS Job Trigger Mapping](#6-cloudevent--ojs-job-trigger-mapping)
7. [Event Bridge Architecture](#7-event-bridge-architecture)
8. [Job Trigger Architecture](#8-job-trigger-architecture)
9. [HTTP Binding Interoperability](#9-http-binding-interoperability)
10. [Batch Conversion](#10-batch-conversion)
11. [Conformance Requirements](#11-conformance-requirements)
12. [Prior Art](#12-prior-art)
13. [Examples](#13-examples)

---

## 1. Introduction

The Open Job Spec and the [CloudEvents](https://cloudevents.io/) specification share a common design philosophy: separate the event model from wire formats and protocol bindings so that diverse systems can interoperate without tight coupling. OJS adopted this three-layer architecture explicitly from CloudEvents (see [ojs-core § 1](ojs-core.md#1-introduction)).

Despite this shared lineage, the two specifications serve different purposes. CloudEvents defines a universal envelope for *events* — things that have happened. OJS defines envelopes for *jobs* — units of deferred work — as well as lifecycle *events* that describe what happened to those jobs. The overlap occurs in the event layer: OJS lifecycle events (defined in [ojs-events.md](ojs-events.md)) are structurally compatible with CloudEvents and can be projected into CloudEvents format with a well-defined mapping.

Bridging OJS and CloudEvents unlocks several integration patterns:

- **Event-driven orchestration.** OJS lifecycle events flow into Knative Eventing or Azure Event Grid, triggering serverless functions, notifications, or analytics pipelines.
- **CloudEvents-triggered jobs.** An incoming CloudEvent (e.g., a Stripe webhook or a GitHub event) triggers an OJS job without custom glue code.
- **Unified observability.** A single event mesh carries both OJS lifecycle events and application-domain CloudEvents, enabling correlated dashboards and traces.

This specification defines the mapping rules, architectural patterns, and conformance requirements for these integration modes.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt).

All JSON examples use the conventions established in [ojs-core § 13](ojs-core.md#13-examples): UUIDv7 identifiers, RFC 3339 timestamps in UTC, and the hypothetical `email.send` job type for illustrative purposes.

CloudEvents examples conform to the [CloudEvents JSON Event Format v1.0](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/formats/json-format.md).

---

## 3. Terminology

| Term                     | Definition                                                                                                    |
|--------------------------|---------------------------------------------------------------------------------------------------------------|
| **CloudEvent**           | An event envelope conforming to the CloudEvents v1.0 specification.                                          |
| **CloudEvents attribute**| A named metadata field in the CloudEvents envelope (e.g., `type`, `source`, `id`).                           |
| **OJS event**            | A lifecycle event emitted by an OJS implementation, conforming to [ojs-events.md](ojs-events.md).            |
| **OJS job envelope**     | The canonical job representation defined in [ojs-core § 5](ojs-core.md#5-job-envelope).                      |
| **Source**               | A URI identifying the context in which an event happened (CloudEvents) or the OJS backend instance.           |
| **Subject**              | The entity within the source to which the event relates — typically the `job_id` in OJS context.              |
| **Data content type**    | The MIME type of the `data` attribute payload. For OJS events this is always `application/json`.              |
| **Event bridge**         | A component that converts OJS events to CloudEvents and publishes them to an external broker.                 |
| **Job trigger**          | A component that receives CloudEvents and converts them into OJS job enqueue requests.                        |
| **Type prefix**          | The namespace prefix applied to OJS event types when projected as CloudEvents: `org.openjobspec.`.            |

---

## 4. Architectural Relationship

### 4.1 Shared Layered Architecture

Both OJS and CloudEvents use a three-layer architecture:

| Layer | CloudEvents                     | OJS                                  |
|-------|---------------------------------|--------------------------------------|
| 1     | Core event attributes           | Core job envelope + lifecycle events |
| 2     | Event format encodings (JSON, Avro, Protobuf) | JSON format encoding (ojs-json-format.md) |
| 3     | Protocol bindings (HTTP, AMQP, Kafka, NATS)    | Protocol bindings (ojs-http-binding.md, ojs-grpc-binding.md) |

This structural alignment is intentional and makes interoperability between the two specifications a matter of attribute mapping rather than architectural translation.

### 4.2 Jobs Are NOT CloudEvents

An OJS job envelope represents a **unit of deferred work** — it carries intent ("do this") rather than fact ("this happened"). A CloudEvent represents a **statement of fact** — something that has already occurred. These are fundamentally different domain concepts and MUST NOT be conflated.

Implementations MUST NOT represent an OJS job envelope directly as a CloudEvent. A job envelope contains scheduling directives (`run_at`, `retry`), mutable state (`state`, `attempt`), and operational metadata that have no semantic equivalent in the CloudEvents model.

### 4.3 OJS Events CAN Be CloudEvents

OJS lifecycle events (e.g., `job.completed`, `job.failed`) are statements of fact about job state transitions. They share the same semantic purpose as CloudEvents and their envelope fields map cleanly to CloudEvents context attributes. An OJS event MAY therefore be projected into CloudEvents format using the mapping defined in [§ 5](#5-ojs-event--cloudevent-mapping).

### 4.4 Two Integration Modes

This specification defines two integration modes:

1. **Event bridge** (§ 7): OJS events are converted to CloudEvents and published to an external broker. Information flows *out* of OJS.
2. **Job trigger** (§ 8): Incoming CloudEvents are converted to OJS job enqueue requests. Information flows *into* OJS.

These modes are independent. An implementation MAY support either, both, or neither. When both are supported, they MUST operate independently — a CloudEvent produced by the event bridge MUST NOT trigger the job trigger on the same instance unless explicitly configured.

---

## 5. OJS Event → CloudEvent Mapping

### 5.1 Attribute Mapping Table

When converting an OJS event to a CloudEvent, implementations MUST apply the following attribute mapping:

| OJS Event Attribute | CloudEvents Attribute | Mapping Rule                                                                                       |
|---------------------|-----------------------|----------------------------------------------------------------------------------------------------|
| `type`              | `type`                | Prefix with `org.openjobspec.` — e.g., `job.completed` → `org.openjobspec.job.completed`          |
| `id`                | `id`                  | Direct mapping. Value MUST be preserved exactly.                                                   |
| `time`              | `time`                | Direct mapping. Both specifications require RFC 3339 format.                                       |
| `source`            | `source`              | OJS backend deployment URI (e.g., `ojs://payments-service/prod`).                                  |
| `subject`           | `subject`             | The `job_id` of the job that triggered the event.                                                  |
| _(implied)_         | `specversion`         | Set to `"1.0"` (CloudEvents specification version).                                                |
| `data`              | `data`                | OJS event payload. Transferred as-is when using structured content mode.                           |
| _(implied)_         | `datacontenttype`     | Set to `"application/json"`.                                                                       |

### 5.2 Type Prefix

The type prefix `org.openjobspec.` follows the CloudEvents [type attribute recommendations](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md#type) for reverse-DNS namespacing. Implementations MUST use this prefix for standard OJS event types. Custom event types defined by extensions SHOULD use `org.openjobspec.x.` as their prefix.

### 5.3 Source URI

The `source` attribute MUST be a valid URI-reference as defined by [RFC 3986](https://www.ietf.org/rfc/rfc3986.txt). Implementations SHOULD use the `ojs://` scheme followed by a deployment-specific path. The source URI MUST uniquely identify the OJS backend instance within the scope of the event mesh.

**Examples:**
- `ojs://payments-service/prod`
- `ojs://my-app/workers/worker-7`
- `https://jobs.example.com/ojs/v1`

### 5.4 Example: OJS Event

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-b68c-7def-8000-aabbccddeeff",
  "type": "job.completed",
  "source": "ojs://payments-service/prod",
  "time": "2026-02-15T10:30:02.789Z",
  "subject": "job_019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "data": {
    "job_type": "email.send",
    "queue": "email",
    "duration_ms": 1333,
    "attempt": 1,
    "result": { "message_id": "msg_abc123" }
  }
}
```

### 5.5 Equivalent CloudEvent (Structured Content Mode)

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-b68c-7def-8000-aabbccddeeff",
  "type": "org.openjobspec.job.completed",
  "source": "ojs://payments-service/prod",
  "time": "2026-02-15T10:30:02.789Z",
  "subject": "job_019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "datacontenttype": "application/json",
  "data": {
    "job_type": "email.send",
    "queue": "email",
    "duration_ms": 1333,
    "attempt": 1,
    "result": { "message_id": "msg_abc123" }
  }
}
```

The only differences are: (a) the `type` attribute is prefixed, (b) `datacontenttype` is explicitly set, and (c) the CloudEvents `specversion` refers to the CloudEvents version, not the OJS version.

---

## 6. CloudEvent → OJS Job Trigger Mapping

### 6.1 Attribute Mapping Table

When converting an incoming CloudEvent to an OJS job enqueue request, implementations MUST apply the following mapping:

| CloudEvents Attribute | OJS Job Attribute        | Mapping Rule                                                                                   |
|-----------------------|--------------------------|------------------------------------------------------------------------------------------------|
| `type`                | `type`                   | Strip the configured prefix or use a configured type mapping table.                            |
| `id`                  | `meta.trigger_event_id`  | Stored as job metadata for traceability.                                                       |
| `source`              | `meta.trigger_source`    | Stored as job metadata for traceability.                                                       |
| `data`                | `args`                   | CloudEvent data payload becomes the job arguments. See § 6.3 for transformation rules.         |
| `subject`             | `meta.trigger_subject`   | OPTIONAL. Stored as job metadata when present.                                                 |
| `time`                | `meta.trigger_time`      | OPTIONAL. Stored as job metadata when present.                                                 |

### 6.2 Type Mapping

The trigger MUST support at least one of the following type resolution strategies:

1. **Prefix stripping.** Remove a configured prefix (default: `org.openjobspec.trigger.`) from the CloudEvent `type` to derive the OJS job `type`. For example, `org.openjobspec.trigger.email.send` → `email.send`.
2. **Explicit mapping table.** A configuration table that maps CloudEvent types to OJS job types. This allows arbitrary CloudEvent types (e.g., `com.stripe.charge.succeeded`) to trigger specific OJS jobs.

When both strategies are configured, the explicit mapping table MUST take precedence.

### 6.3 Data Transformation

The CloudEvent `data` attribute is mapped to the OJS job `args` attribute. Implementations MUST support the following modes:

- **Pass-through.** The entire `data` object becomes `args` without modification. This is the default.
- **JSONPath extraction.** A configured JSONPath expression extracts a subset of `data` to populate `args`.
- **Template mapping.** A configured template maps fields from `data` to specific `args` keys.

The transformation mode MUST be configurable per CloudEvent type in the mapping table.

### 6.4 Example: CloudEvent Input

```json
{
  "specversion": "1.0",
  "id": "ce_a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "type": "com.stripe.charge.succeeded",
  "source": "https://api.stripe.com/v1",
  "time": "2026-02-15T14:22:00.000Z",
  "subject": "ch_3abc123",
  "datacontenttype": "application/json",
  "data": {
    "id": "ch_3abc123",
    "amount": 2000,
    "currency": "usd",
    "customer": "cus_xyz789"
  }
}
```

### 6.5 Resulting OJS Job Enqueue Request

```json
{
  "type": "billing.process_charge",
  "args": {
    "id": "ch_3abc123",
    "amount": 2000,
    "currency": "usd",
    "customer": "cus_xyz789"
  },
  "meta": {
    "trigger_event_id": "ce_a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "trigger_source": "https://api.stripe.com/v1",
    "trigger_subject": "ch_3abc123",
    "trigger_time": "2026-02-15T14:22:00.000Z"
  }
}
```

---

## 7. Event Bridge Architecture

### 7.1 Overview

The event bridge is a component that subscribes to OJS lifecycle events and publishes them as CloudEvents to an external broker. It sits between the OJS backend and the CloudEvents-compatible event mesh.

```
┌─────────────┐     OJS Events      ┌──────────────┐    CloudEvents    ┌───────────────────┐
│  OJS Backend │ ──────────────────► │ Event Bridge  │ ────────────────► │  CloudEvents      │
│  (emits      │                     │ (converts +   │                   │  Broker            │
│   events)    │                     │  publishes)   │                   │  (Knative, Azure   │
└─────────────┘                      └──────────────┘                   │   Event Grid, etc) │
                                                                        └───────────────────┘
```

### 7.2 Bridge Configuration

An event bridge implementation MUST support the following configuration parameters:

| Parameter         | Type     | Required | Description                                                  |
|-------------------|----------|----------|--------------------------------------------------------------|
| `source_uri`      | URI      | Yes      | The `source` attribute value for all emitted CloudEvents.    |
| `type_prefix`     | String   | No       | Override the default `org.openjobspec.` type prefix.         |
| `event_filter`    | String[] | No       | List of OJS event types to bridge. Empty = all events.       |
| `broker_endpoint` | URI      | Yes      | The CloudEvents broker endpoint URL.                         |
| `content_mode`    | Enum     | No       | `structured` (default) or `binary`. CloudEvents content mode.|

### 7.3 Event Filtering

Implementations SHOULD support filtering at the bridge level so that only relevant OJS events are converted and published. Filtering reduces broker load and avoids publishing high-frequency internal events (e.g., `job.heartbeat`) to external systems.

The filter MUST support inclusion by event type glob pattern. For example, `job.*` matches all job lifecycle events but not worker or queue events.

### 7.4 Delivery Guarantees

The event bridge MUST deliver events with **at-least-once** semantics. Duplicate CloudEvents MAY be emitted during retries. Consumers MUST use the `id` attribute for idempotent processing.

The bridge SHOULD implement exponential backoff with jitter when the broker endpoint is unavailable, consistent with [ojs-retry.md](ojs-retry.md).

---

## 8. Job Trigger Architecture

### 8.1 Overview

The job trigger is a component that receives CloudEvents from an external broker and converts them into OJS job enqueue requests.

```
┌───────────────────┐    CloudEvents    ┌──────────────┐    OJS PUSH     ┌─────────────┐
│  CloudEvents      │ ────────────────► │ Job Trigger   │ ─────────────► │  OJS Backend │
│  Broker           │                   │ (filters +    │                │  (enqueues   │
│  (Knative, AWS    │                   │  converts)    │                │   job)       │
│   EventBridge)    │                   └──────────────┘                 └─────────────┘
└───────────────────┘
```

### 8.2 Filter Expressions

The job trigger MUST support filter expressions to selectively convert CloudEvents into jobs. Filters MUST support matching on the following CloudEvents attributes:

- `type` — exact match or prefix match.
- `source` — exact match or prefix match.
- `subject` — exact match, prefix match, or glob pattern.

**Example filter configuration:**

```json
{
  "filters": [
    {
      "match": { "type": "com.stripe.charge.succeeded" },
      "job_type": "billing.process_charge",
      "queue": "billing",
      "transform": "pass-through"
    },
    {
      "match": { "type": "com.github.push", "source": "https://github.com/myorg/*" },
      "job_type": "ci.run_pipeline",
      "queue": "ci",
      "transform": {
        "mode": "template",
        "mapping": {
          "repo": "$.data.repository.full_name",
          "ref": "$.data.ref",
          "sha": "$.data.after"
        }
      }
    }
  ]
}
```

### 8.3 Transformation Rules

Each filter entry MAY specify a transformation rule that controls how the CloudEvent `data` is mapped to OJS job `args`. The supported transformation modes are defined in [§ 6.3](#63-data-transformation).

### 8.4 Idempotency

The job trigger MUST use the CloudEvent `id` and `source` attributes as a composite deduplication key. If a CloudEvent with the same `id` + `source` combination has already been processed, the trigger MUST NOT enqueue a duplicate job. The deduplication window SHOULD be configurable and default to 24 hours.

---

## 9. HTTP Binding Interoperability

### 9.1 Header Namespaces

The CloudEvents HTTP binding uses `ce-` prefixed headers for binary content mode. The OJS HTTP binding uses `OJS-` prefixed headers. When both sets of headers appear on the same HTTP request (e.g., a CloudEvent being forwarded to an OJS endpoint), the following rules apply:

| Scenario                                          | Precedence Rule                                                  |
|---------------------------------------------------|------------------------------------------------------------------|
| Both `ce-type` and OJS `Content-Type` present     | OJS endpoint MUST process the request as an OJS request.         |
| CloudEvent in structured mode to OJS endpoint     | OJS endpoint SHOULD extract job data from the CloudEvent `data`. |
| OJS response carrying CloudEvents headers         | CloudEvents headers are informational; OJS response semantics take precedence. |

### 9.2 Content-Type Negotiation

| Content-Type                             | Interpretation                                                      |
|------------------------------------------|---------------------------------------------------------------------|
| `application/json`                       | Standard OJS JSON format (default).                                 |
| `application/cloudevents+json`           | CloudEvents structured content mode. Indicates the body is a CloudEvent. |
| `application/cloudevents-batch+json`     | CloudEvents batched content mode. See [§ 10](#10-batch-conversion). |

An OJS endpoint that supports CloudEvents interoperability MUST accept `application/cloudevents+json` and extract the job payload from the `data` attribute.

### 9.3 Binary Content Mode

In CloudEvents binary content mode, context attributes are carried in HTTP headers and the `data` attribute is the HTTP body. When an OJS endpoint receives a request with `ce-` headers:

1. The endpoint MUST read `ce-type` to determine the CloudEvent type.
2. The endpoint MUST apply the trigger mapping (§ 6) to convert the request to an OJS job.
3. The HTTP body MUST be treated as the CloudEvent `data` attribute.

### 9.4 Example: CloudEvent Binary Mode to OJS Endpoint

```http
POST /ojs/v1/jobs HTTP/1.1
Host: jobs.example.com
Content-Type: application/json
ce-specversion: 1.0
ce-type: com.stripe.charge.succeeded
ce-source: https://api.stripe.com/v1
ce-id: ce_a1b2c3d4-e5f6-7890-abcd-ef1234567890
ce-time: 2026-02-15T14:22:00.000Z
ce-subject: ch_3abc123

{
  "id": "ch_3abc123",
  "amount": 2000,
  "currency": "usd",
  "customer": "cus_xyz789"
}
```

---

## 10. Batch Conversion

### 10.1 OJS Batch Events to CloudEvents Batch

When an OJS backend emits multiple events (e.g., during a batch job completion), the event bridge MAY aggregate them into a CloudEvents batch using the `application/cloudevents-batch+json` content type.

A CloudEvents batch is a JSON array of CloudEvent objects:

```json
[
  {
    "specversion": "1.0",
    "id": "evt_01",
    "type": "org.openjobspec.job.completed",
    "source": "ojs://payments-service/prod",
    "time": "2026-02-15T10:30:02.789Z",
    "subject": "job_01",
    "datacontenttype": "application/json",
    "data": { "job_type": "email.send", "queue": "email", "duration_ms": 420 }
  },
  {
    "specversion": "1.0",
    "id": "evt_02",
    "type": "org.openjobspec.job.completed",
    "source": "ojs://payments-service/prod",
    "time": "2026-02-15T10:30:02.812Z",
    "subject": "job_02",
    "datacontenttype": "application/json",
    "data": { "job_type": "email.send", "queue": "email", "duration_ms": 387 }
  }
]
```

### 10.2 Batch Size Limits

The event bridge SHOULD limit batch size to avoid exceeding broker payload limits. The default maximum batch size SHOULD be 100 events or 1 MiB (whichever is reached first). Both limits MUST be configurable.

### 10.3 CloudEvents Batch Triggering OJS Jobs

When a job trigger receives a CloudEvents batch (`application/cloudevents-batch+json`), it MUST process each CloudEvent in the array independently, applying the filter and transformation rules from [§ 8](#8-job-trigger-architecture) to each event. Failed conversions for individual events within a batch MUST NOT prevent processing of remaining events.

---

## 11. Conformance Requirements

Conformance requirements use the identifier prefix `CE-` (CloudEvents interop). An implementation MAY claim partial conformance by listing supported requirements.

| ID     | Requirement                                                                                                    | Level    |
|--------|----------------------------------------------------------------------------------------------------------------|----------|
| CE-001 | Event bridge MUST prefix OJS event types with `org.openjobspec.` when converting to CloudEvents.               | MUST     |
| CE-002 | Event bridge MUST preserve the OJS event `id` as the CloudEvent `id`.                                          | MUST     |
| CE-003 | Event bridge MUST set `specversion` to `"1.0"` on all emitted CloudEvents.                                     | MUST     |
| CE-004 | Event bridge MUST set `datacontenttype` to `"application/json"`.                                               | MUST     |
| CE-005 | Event bridge MUST set `source` to a valid URI-reference uniquely identifying the OJS backend.                   | MUST     |
| CE-006 | Event bridge MUST set `subject` to the `job_id` of the originating job.                                        | MUST     |
| CE-007 | Event bridge MUST deliver events with at-least-once semantics.                                                 | MUST     |
| CE-008 | Event bridge SHOULD support event type filtering via glob patterns.                                            | SHOULD   |
| CE-009 | Job trigger MUST store CloudEvent `id` in `meta.trigger_event_id`.                                             | MUST     |
| CE-010 | Job trigger MUST store CloudEvent `source` in `meta.trigger_source`.                                           | MUST     |
| CE-011 | Job trigger MUST support at least one type resolution strategy (prefix stripping or mapping table).             | MUST     |
| CE-012 | Job trigger MUST deduplicate on CloudEvent `id` + `source`.                                                    | MUST     |
| CE-013 | Job trigger SHOULD support filter expressions on `type`, `source`, and `subject`.                              | SHOULD   |
| CE-014 | OJS endpoints supporting interop MUST accept `application/cloudevents+json` content type.                      | MUST     |
| CE-015 | OJS endpoints supporting interop MUST handle `ce-` prefixed HTTP headers in binary content mode.               | MUST     |
| CE-016 | Batch processing MUST handle individual event failures independently.                                          | MUST     |
| CE-017 | Implementations MUST NOT represent OJS job envelopes directly as CloudEvents.                                  | MUST NOT |

---

## 12. Prior Art

This specification draws on the following prior art and existing CloudEvents integrations:

- **[CloudEvents v1.0 Specification](https://github.com/cloudevents/spec).** The foundational CNCF specification for describing event data in a common way. OJS event envelopes were designed with CloudEvents alignment in mind from the outset.
- **[Knative Eventing](https://knative.dev/docs/eventing/).** Kubernetes-native eventing platform built on CloudEvents. Knative Brokers and Triggers provide the reference architecture for the event bridge and job trigger patterns described in this specification.
- **[Azure Event Grid](https://learn.microsoft.com/en-us/azure/event-grid/).** Fully managed event routing service with native CloudEvents support. Demonstrates enterprise-scale event bridge patterns.
- **[AWS EventBridge](https://aws.amazon.com/eventbridge/).** Serverless event bus with CloudEvents compatibility. Demonstrates rule-based event filtering and target mapping similar to the job trigger architecture.
- **[Dapr Pub/Sub](https://docs.dapr.io/developing-applications/building-blocks/pubsub/).** Distributed Application Runtime component that uses CloudEvents as its default envelope format. Validates the approach of using CloudEvents as the interoperability layer between heterogeneous systems.
- **[CloudEvents SDKs](https://github.com/cloudevents/sdk-go).** Official SDK implementations (Go, Java, JavaScript, Python, C#, Ruby, Rust) that provide the programmatic foundation for implementing the mappings defined in this specification.

---

## 13. Examples

### 13.1 OJS Lifecycle Event as CloudEvent

**Scenario:** An OJS backend completes a job and emits a `job.completed` event. The event bridge converts it to a CloudEvent and publishes it to a Knative Broker.

**OJS event (as emitted by the backend):**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-b68c-7def-8000-aabbccddeeff",
  "type": "job.completed",
  "source": "ojs://payments-service/prod",
  "time": "2026-02-15T10:30:02.789Z",
  "subject": "job_019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "data": {
    "job_type": "email.send",
    "queue": "email",
    "duration_ms": 1333,
    "attempt": 1,
    "result": { "message_id": "msg_abc123" }
  }
}
```

**CloudEvent (published to broker):**

```json
{
  "specversion": "1.0",
  "id": "evt_019539a4-b68c-7def-8000-aabbccddeeff",
  "type": "org.openjobspec.job.completed",
  "source": "ojs://payments-service/prod",
  "time": "2026-02-15T10:30:02.789Z",
  "subject": "job_019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "datacontenttype": "application/json",
  "data": {
    "job_type": "email.send",
    "queue": "email",
    "duration_ms": 1333,
    "attempt": 1,
    "result": { "message_id": "msg_abc123" }
  }
}
```

### 13.2 CloudEvent Triggering an OJS Job

**Scenario:** A Stripe webhook delivers a `charge.succeeded` event as a CloudEvent. The job trigger converts it into an OJS job.

**Incoming CloudEvent:**

```json
{
  "specversion": "1.0",
  "id": "evt_stripe_abc123",
  "type": "com.stripe.charge.succeeded",
  "source": "https://api.stripe.com/v1",
  "time": "2026-02-15T14:22:00.000Z",
  "subject": "ch_3abc123",
  "datacontenttype": "application/json",
  "data": {
    "id": "ch_3abc123",
    "amount": 2000,
    "currency": "usd",
    "customer": "cus_xyz789",
    "metadata": { "order_id": "ord_456" }
  }
}
```

**Trigger configuration:**

```json
{
  "match": { "type": "com.stripe.charge.succeeded" },
  "job_type": "billing.process_charge",
  "queue": "billing",
  "transform": "pass-through"
}
```

**Resulting OJS PUSH request:**

```http
POST /ojs/v1/jobs HTTP/1.1
Host: jobs.example.com
Content-Type: application/json
OJS-Request-Id: req_019539a4-1234-7def-8000-ffffffffffff

{
  "type": "billing.process_charge",
  "queue": "billing",
  "args": {
    "id": "ch_3abc123",
    "amount": 2000,
    "currency": "usd",
    "customer": "cus_xyz789",
    "metadata": { "order_id": "ord_456" }
  },
  "meta": {
    "trigger_event_id": "evt_stripe_abc123",
    "trigger_source": "https://api.stripe.com/v1",
    "trigger_subject": "ch_3abc123",
    "trigger_time": "2026-02-15T14:22:00.000Z"
  }
}
```

### 13.3 HTTP Request with Both Header Sets

**Scenario:** A CloudEvents-aware proxy forwards a CloudEvent in binary content mode to an OJS endpoint. The request carries both `ce-` headers (from CloudEvents) and `OJS-` headers (added by the proxy).

```http
POST /ojs/v1/jobs HTTP/1.1
Host: jobs.example.com
Content-Type: application/json
OJS-Request-Id: req_019539a4-5678-7def-8000-ffffffffffff
OJS-Idempotency-Key: idem_stripe_abc123
ce-specversion: 1.0
ce-type: com.stripe.charge.succeeded
ce-source: https://api.stripe.com/v1
ce-id: evt_stripe_abc123
ce-time: 2026-02-15T14:22:00.000Z
ce-subject: ch_3abc123

{
  "id": "ch_3abc123",
  "amount": 2000,
  "currency": "usd",
  "customer": "cus_xyz789"
}
```

In this scenario, the OJS endpoint recognizes the `ce-` headers and applies the job trigger mapping, while the `OJS-` headers provide OJS-specific request metadata (request tracking, idempotency).
