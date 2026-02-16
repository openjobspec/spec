# Open Job Spec: Webhook Delivery

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Webhook Delivery Specification             |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-15                                     |
| **Status**  | Release Candidate                              |
| **Maturity** | Beta                                           |
| **Tier**    | Official Extension                             |
| **URI**     | `urn:ojs:ext:webhooks`                         |
| **Requires**| OJS Core Specification (Layer 1), OJS Events   |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Design Principles](#4-design-principles)
5. [Webhook Model](#5-webhook-model)
   - 5.1 [Subscriptions](#51-subscriptions)
   - 5.2 [Event Filtering](#52-event-filtering)
   - 5.3 [Delivery Payload](#53-delivery-payload)
6. [Subscription Management](#6-subscription-management)
   - 6.1 [Create Subscription](#61-create-subscription)
   - 6.2 [List Subscriptions](#62-list-subscriptions)
   - 6.3 [Get Subscription](#63-get-subscription)
   - 6.4 [Update Subscription](#64-update-subscription)
   - 6.5 [Delete Subscription](#65-delete-subscription)
   - 6.6 [Test Subscription](#66-test-subscription)
7. [Delivery Semantics](#7-delivery-semantics)
   - 7.1 [Delivery Guarantees](#71-delivery-guarantees)
   - 7.2 [Retry Policy](#72-retry-policy)
   - 7.3 [Timeout](#73-timeout)
   - 7.4 [Ordering](#74-ordering)
   - 7.5 [Idempotency](#75-idempotency)
8. [Security](#8-security)
   - 8.1 [Request Signing](#81-request-signing)
   - 8.2 [Signature Verification](#82-signature-verification)
   - 8.3 [Secret Rotation](#83-secret-rotation)
   - 8.4 [Transport Security](#84-transport-security)
9. [Interaction with Other Extensions](#9-interaction-with-other-extensions)
   - 9.1 [Events](#91-events)
   - 9.2 [Workflows](#92-workflows)
   - 9.3 [Multi-Tenancy](#93-multi-tenancy)
10. [HTTP Binding](#10-http-binding)
11. [Observability](#11-observability)
12. [Conformance Requirements](#12-conformance-requirements)
13. [Prior Art](#13-prior-art)
14. [Examples](#14-examples)

---

## 1. Introduction

The OJS Events specification (ojs-events.md) defines a standard vocabulary of lifecycle events but leaves the delivery transport implementation-defined. While in-process callbacks and event bus integrations serve internal consumers well, external systems -- dashboards, third-party services, serverless functions, and partner integrations -- require push-based delivery via HTTP webhooks.

Webhooks are the de facto standard for event delivery across web services. Every major platform (GitHub, Stripe, Twilio, Slack) provides webhook delivery with a remarkably consistent set of features: subscription management, request signing, retry with backoff, and delivery logging. This specification standardizes webhook delivery for OJS events, ensuring that any OJS implementation's webhook behavior is predictable, secure, and interoperable.

### 1.1 Scope

This specification defines:

- A subscription model for registering webhook endpoints with event filters.
- Delivery payload format based on the OJS event envelope.
- Delivery semantics including at-least-once guarantees, retry, and timeout.
- Request signing using HMAC-SHA256 for authenticity verification.
- Subscription management API endpoints.

This specification does **not** define:

- Non-HTTP push delivery (WebSocket, gRPC streaming, SNS/Pub-Sub) — these are alternative transports covered by individual implementations.
- Fan-in event aggregation or event batching across multiple jobs into a single webhook call.
- Webhook endpoint implementation (the receiver is the consumer's responsibility).

### 1.2 Companion Specifications

| Document | Layer | Description |
|----------|-------|-------------|
| **ojs-core.md** | 1 -- Core | Job envelope, lifecycle states, operations |
| **ojs-events.md** | Core | Event envelope format, event type catalog |
| **ojs-security.md** | Extension | Threat model, transport security, authentication |
| **ojs-retry.md** | Core | Retry semantics, backoff strategies |

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term | Definition |
|------|------------|
| **Subscription** | A persistent registration that associates a target URL with a set of event type filters. |
| **Webhook Endpoint** | The HTTP URL that receives event deliveries. Owned by the consumer. |
| **Delivery** | A single HTTP POST request to a webhook endpoint carrying an event payload. |
| **Delivery Attempt** | One try of a delivery, including the HTTP request and response handling. |
| **Signing Secret** | A shared secret used to compute HMAC signatures for request authenticity. |
| **Dead Delivery** | A delivery that has exhausted all retry attempts without a successful response. |

---

## 4. Design Principles

1. **At-least-once delivery.** Webhook delivery is inherently at-least-once. Network failures, consumer downtime, and timeout ambiguity make exactly-once delivery impossible over HTTP. Consumers MUST be prepared to receive duplicate events.

2. **Verifiable authenticity.** Every webhook request is signed. Consumers can verify that the request originated from the OJS server and was not tampered with in transit. This is a security requirement, not optional.

3. **Fail-open for the job system.** Webhook delivery failures MUST NOT affect job processing. A webhook endpoint that is down does not block, retry, or slow down job execution. Webhook delivery is a side-channel, not part of the job's critical path.

4. **Standard HTTP semantics.** Webhook delivery follows standard HTTP conventions. Success is a 2xx response. Redirects are followed. Client errors (4xx) are not retried. Server errors (5xx) and timeouts are retried.

---

## 5. Webhook Model

### 5.1 Subscriptions

A subscription is a persistent object that routes matching events to a webhook endpoint:

```json
{
  "id": "sub_019539a4-b68c-7def-8000-aabbccddeeff",
  "url": "https://api.example.com/webhooks/ojs",
  "events": ["job.completed", "job.failed", "job.discarded"],
  "active": true,
  "secret": "whsec_...",
  "metadata": {
    "description": "Production alerting",
    "owner": "platform-team"
  },
  "created_at": "2026-01-15T10:00:00Z"
}
```

**Subscription fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | System-generated | Unique subscription identifier. |
| `url` | string (HTTPS URL) | REQUIRED | The endpoint URL. MUST use HTTPS in production. |
| `events` | string[] | REQUIRED | List of event types to deliver. Supports wildcards (`job.*`). |
| `active` | boolean | Default: true | Whether the subscription is active. |
| `secret` | string | System-generated | HMAC signing secret. Never returned in GET responses. |
| `metadata` | object | Optional | Arbitrary key-value pairs for human reference. |
| `filter` | object | Optional | Additional filter criteria (queue, job_type). |
| `created_at` | ISO 8601 | System-generated | Creation timestamp. |

### 5.2 Event Filtering

Subscriptions filter events by type and optionally by queue or job type:

**Type filtering:**

- Exact match: `"job.completed"` — matches only `job.completed`.
- Wildcard: `"job.*"` — matches all job events (`job.completed`, `job.failed`, etc.).
- All events: `"*"` — matches every event type.

**Attribute filtering (optional):**

```json
{
  "events": ["job.completed", "job.failed"],
  "filter": {
    "queues": ["payments", "billing"],
    "job_types": ["payment.process", "invoice.generate"]
  }
}
```

When `filter` is present, an event MUST match both the event type AND the filter criteria to trigger delivery.

### 5.3 Delivery Payload

The webhook delivery payload is an HTTP POST request containing the OJS event envelope (as defined in ojs-events.md):

```http
POST /webhooks/ojs HTTP/1.1
Host: api.example.com
Content-Type: application/json
User-Agent: OJS-Webhook/1.0
X-OJS-Event-Type: job.completed
X-OJS-Delivery-ID: del_019539a4-b68c-7def-8000-ffeeddccbbaa
X-OJS-Subscription-ID: sub_019539a4-b68c-7def-8000-aabbccddeeff
X-OJS-Signature: sha256=a1b2c3d4e5f6...
X-OJS-Timestamp: 1708030665

{
  "specversion": "1.0",
  "id": "evt_019539a4-b68c-7def-8000-112233445566",
  "type": "job.completed",
  "source": "ojs://my-service/workers/worker-1",
  "time": "2026-02-15T22:00:00Z",
  "subject": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "data": {
    "job_type": "payment.process",
    "queue": "payments",
    "duration_ms": 1200,
    "attempt": 1,
    "result": { "transaction_id": "txn_abc123" }
  }
}
```

**Required headers:**

| Header | Description |
|--------|-------------|
| `Content-Type` | MUST be `application/json`. |
| `User-Agent` | MUST identify the OJS implementation (e.g., `OJS-Webhook/1.0`). |
| `X-OJS-Event-Type` | The event type being delivered. |
| `X-OJS-Delivery-ID` | Unique identifier for this delivery attempt. Used for idempotency. |
| `X-OJS-Subscription-ID` | The subscription that triggered this delivery. |
| `X-OJS-Signature` | HMAC-SHA256 signature of the request body. |
| `X-OJS-Timestamp` | Unix timestamp (seconds) when the delivery was initiated. |

---

## 6. Subscription Management

### 6.1 Create Subscription

```http
POST /ojs/v1/webhooks/subscriptions HTTP/1.1
Content-Type: application/json

{
  "url": "https://api.example.com/webhooks/ojs",
  "events": ["job.completed", "job.failed"],
  "filter": {
    "queues": ["payments"]
  },
  "metadata": {
    "description": "Payment job monitoring"
  }
}
```

**Response (201 Created):**

```json
{
  "id": "sub_019539a4-b68c-7def-8000-aabbccddeeff",
  "url": "https://api.example.com/webhooks/ojs",
  "events": ["job.completed", "job.failed"],
  "filter": { "queues": ["payments"] },
  "active": true,
  "secret": "whsec_k3j4h5g6f7d8s9a0...",
  "created_at": "2026-02-15T22:00:00Z"
}
```

The `secret` is returned ONLY in the creation response. It MUST NOT be returned in subsequent GET requests. If the consumer loses the secret, they must rotate it.

### 6.2 List Subscriptions

```http
GET /ojs/v1/webhooks/subscriptions HTTP/1.1
```

### 6.3 Get Subscription

```http
GET /ojs/v1/webhooks/subscriptions/{id} HTTP/1.1
```

The `secret` field MUST be omitted from the response.

### 6.4 Update Subscription

```http
PATCH /ojs/v1/webhooks/subscriptions/{id} HTTP/1.1
Content-Type: application/json

{
  "events": ["job.completed", "job.failed", "job.discarded"],
  "active": false
}
```

### 6.5 Delete Subscription

```http
DELETE /ojs/v1/webhooks/subscriptions/{id} HTTP/1.1
```

Pending deliveries for a deleted subscription SHOULD be cancelled.

### 6.6 Test Subscription

```http
POST /ojs/v1/webhooks/subscriptions/{id}/test HTTP/1.1
```

Sends a synthetic `ping` event to the endpoint to verify connectivity. The test event MUST use the event type `webhook.test`.

**Response (200 OK):**

```json
{
  "success": true,
  "status_code": 200,
  "response_time_ms": 145,
  "response_body": "OK"
}
```

---

## 7. Delivery Semantics

### 7.1 Delivery Guarantees

Webhook delivery provides **at-least-once** semantics. Implementations MUST retry failed deliveries according to the retry policy. Consumers MUST handle duplicate deliveries idempotently.

A delivery is considered successful when the endpoint returns an HTTP 2xx status code. Any other outcome triggers retry behavior.

| Response | Behavior |
|----------|----------|
| 2xx | Success. Delivery complete. |
| 3xx | Follow redirect (up to 3 redirects). |
| 4xx (except 429) | Client error. Do NOT retry. Mark as dead delivery. |
| 429 | Rate limited. Retry with `Retry-After` header if present. |
| 5xx | Server error. Retry according to policy. |
| Timeout | Retry according to policy. |
| Connection error | Retry according to policy. |

### 7.2 Retry Policy

Failed deliveries MUST be retried with exponential backoff:

| Attempt | Delay |
|---------|-------|
| 1 | Immediate |
| 2 | 30 seconds |
| 3 | 2 minutes |
| 4 | 10 minutes |
| 5 | 1 hour |
| 6 | 4 hours |
| 7 | 12 hours |
| 8 | 24 hours |

Implementations MUST support at least 5 retry attempts. The RECOMMENDED maximum is 8 attempts over approximately 41 hours.

After all retry attempts are exhausted, the delivery is marked as a **dead delivery**. Implementations SHOULD store dead deliveries for manual inspection and replay.

### 7.3 Timeout

The delivery HTTP request MUST use a timeout of 30 seconds. If the endpoint does not respond within 30 seconds, the delivery is considered failed and retried.

Implementations MAY allow the timeout to be configured per subscription, with a RECOMMENDED range of 5-60 seconds.

### 7.4 Ordering

Webhook deliveries are NOT guaranteed to be ordered. Events for the same job may arrive out of order due to retry timing, concurrent delivery workers, and network variability.

Consumers SHOULD use the event's `time` field to determine event ordering. Consumers SHOULD NOT rely on delivery order matching event creation order.

### 7.5 Idempotency

Each delivery carries a unique `X-OJS-Delivery-ID` header. Consumers SHOULD use this ID to deduplicate deliveries. The delivery ID is stable across retries — all retry attempts for the same event to the same subscription share the same delivery ID.

---

## 8. Security

### 8.1 Request Signing

Every webhook delivery MUST be signed using HMAC-SHA256. The signature is computed over the raw request body using the subscription's signing secret:

```
signature = HMAC-SHA256(secret, timestamp + "." + body)
```

Where:
- `secret` is the subscription's signing secret.
- `timestamp` is the value of the `X-OJS-Timestamp` header (Unix seconds).
- `body` is the raw request body (UTF-8 encoded JSON).
- The `.` is a literal period character separating the timestamp and body.

The computed signature is included in the `X-OJS-Signature` header as:

```
X-OJS-Signature: sha256=<hex-encoded-signature>
```

**Rationale:** Including the timestamp in the signed payload prevents replay attacks. A consumer that verifies the signature and checks that the timestamp is within an acceptable window (RECOMMENDED: ±5 minutes) is protected against both tampering and replay.

### 8.2 Signature Verification

Consumers SHOULD verify webhook signatures using the following algorithm:

1. Extract the `X-OJS-Timestamp` header value.
2. Extract the `X-OJS-Signature` header value (strip the `sha256=` prefix).
3. Compute `expected = HMAC-SHA256(secret, timestamp + "." + raw_body)`.
4. Compare `expected` with the received signature using constant-time comparison.
5. Verify that the timestamp is within ±5 minutes of the current time.

### 8.3 Secret Rotation

Implementations MUST support signing secret rotation:

```http
POST /ojs/v1/webhooks/subscriptions/{id}/rotate-secret HTTP/1.1
```

During rotation, the implementation SHOULD sign deliveries with both the old and new secret for a transition period (RECOMMENDED: 24 hours). The `X-OJS-Signature` header MAY contain multiple signatures separated by commas during the transition.

### 8.4 Transport Security

Subscription URLs MUST use HTTPS in production environments. Implementations SHOULD reject subscription creation with HTTP URLs unless explicitly configured to allow insecure endpoints (for development/testing only).

---

## 9. Interaction with Other Extensions

### 9.1 Events

This extension builds directly on the OJS Events specification. The webhook payload is an OJS event envelope. All event types defined in ojs-events.md are available for webhook subscription.

### 9.2 Workflows

Workflow events (`workflow.completed`, `workflow.failed`) are subscribable via webhooks. This enables external orchestration systems to react to workflow completion without polling.

### 9.3 Multi-Tenancy

When multi-tenancy is enabled, subscriptions are scoped to a tenant. A subscription created by tenant A MUST NOT receive events for tenant B's jobs. The tenant context is determined by the authentication credentials used to create the subscription.

---

## 10. HTTP Binding

All webhook management endpoints reside under the `/ojs/v1/webhooks/` path prefix.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/ojs/v1/webhooks/subscriptions` | Create subscription |
| GET | `/ojs/v1/webhooks/subscriptions` | List subscriptions |
| GET | `/ojs/v1/webhooks/subscriptions/{id}` | Get subscription |
| PATCH | `/ojs/v1/webhooks/subscriptions/{id}` | Update subscription |
| DELETE | `/ojs/v1/webhooks/subscriptions/{id}` | Delete subscription |
| POST | `/ojs/v1/webhooks/subscriptions/{id}/test` | Test delivery |
| POST | `/ojs/v1/webhooks/subscriptions/{id}/rotate-secret` | Rotate signing secret |
| GET | `/ojs/v1/webhooks/deliveries` | List recent deliveries |
| GET | `/ojs/v1/webhooks/deliveries/{id}` | Get delivery details |
| POST | `/ojs/v1/webhooks/deliveries/{id}/retry` | Retry a failed delivery |

---

## 11. Observability

### 11.1 Events

| Event Type | Trigger |
|------------|---------|
| `webhook.delivered` | Successful delivery (2xx response). |
| `webhook.failed` | Delivery attempt failed (will retry). |
| `webhook.dead` | All retry attempts exhausted. |
| `webhook.subscription.created` | New subscription created. |
| `webhook.subscription.deleted` | Subscription deleted. |

### 11.2 Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `ojs.webhook.delivery.count` | Counter | Total deliveries, labeled by `event_type`, `status` (success, failed, dead). |
| `ojs.webhook.delivery.duration_ms` | Histogram | HTTP request duration, labeled by `event_type`, `subscription_id`. |
| `ojs.webhook.delivery.retry_count` | Histogram | Number of retry attempts before success, labeled by `event_type`. |
| `ojs.webhook.dead_delivery.count` | Counter | Dead deliveries, labeled by `event_type`, `subscription_id`. |
| `ojs.webhook.subscription.count` | Gauge | Active subscriptions. |

---

## 12. Conformance Requirements

### 12.1 Required

| Capability | Requirement |
|------------|-------------|
| Subscription CRUD | Implementations MUST support create, read, update, delete for subscriptions. |
| Event filtering | Implementations MUST support filtering by event type. |
| HMAC-SHA256 signing | Implementations MUST sign all webhook deliveries. |
| At-least-once delivery | Implementations MUST retry failed deliveries. |
| Delivery ID | Implementations MUST include a unique `X-OJS-Delivery-ID` header. |

### 12.2 Recommended

| Capability | Requirement |
|------------|-------------|
| Attribute filtering | Implementations SHOULD support filtering by queue and job_type. |
| Wildcard events | Implementations SHOULD support `*` and `job.*` wildcards. |
| Secret rotation | Implementations SHOULD support signing secret rotation. |
| Delivery logging | Implementations SHOULD store recent delivery history. |
| Dead delivery replay | Implementations SHOULD support manual retry of dead deliveries. |
| Test endpoint | Implementations SHOULD support `POST .../test` for connectivity verification. |

### 12.3 Optional

| Capability | Requirement |
|------------|-------------|
| Event batching | Implementations MAY batch multiple events into a single delivery. |
| Custom headers | Implementations MAY allow subscriptions to include custom headers in deliveries. |
| IP allowlisting | Implementations MAY publish webhook source IP ranges. |

---

## 13. Prior Art

| System | Webhook Implementation |
|--------|----------------------|
| **GitHub** | HMAC-SHA256 signing (`X-Hub-Signature-256`), event type filtering, delivery logs, redelivery. OJS aligns closely with GitHub's model. |
| **Stripe** | HMAC-SHA256 with timestamp (`Stripe-Signature: t=...,v1=...`). Timestamp-based replay prevention inspired OJS signing format. |
| **Twilio** | Request validation via URL + auth token signature. |
| **Svix** | Open-source webhook delivery service. Provides retry, signing, and idempotency patterns that informed this specification. |
| **AWS EventBridge** | Rule-based event routing to HTTP endpoints. |
| **Temporal** | No built-in webhooks; relies on custom activities or Nexus for external notifications. |
| **BullMQ** | No built-in webhooks; events are in-process only. |

---

## 14. Examples

### 14.1 Monitor All Payment Failures

```json
{
  "url": "https://alerts.example.com/ojs",
  "events": ["job.failed", "job.discarded"],
  "filter": {
    "queues": ["payments"]
  }
}
```

### 14.2 Notify External System on Workflow Completion

```json
{
  "url": "https://partner-api.example.com/callbacks",
  "events": ["workflow.completed", "workflow.failed"]
}
```

### 14.3 Broad Monitoring with Wildcards

```json
{
  "url": "https://monitoring.example.com/ojs-events",
  "events": ["*"]
}
```

### 14.4 Verifying a Webhook Signature (Node.js)

```javascript
const crypto = require('crypto');

function verifyWebhook(secret, timestamp, body, signature) {
  const expected = crypto
    .createHmac('sha256', secret)
    .update(`${timestamp}.${body}`)
    .digest('hex');

  const received = signature.replace('sha256=', '');

  // Constant-time comparison
  return crypto.timingSafeEqual(
    Buffer.from(expected),
    Buffer.from(received)
  );
}
```

### 14.5 Verifying a Webhook Signature (Python)

```python
import hmac
import hashlib

def verify_webhook(secret: str, timestamp: str, body: str, signature: str) -> bool:
    expected = hmac.new(
        secret.encode(),
        f"{timestamp}.{body}".encode(),
        hashlib.sha256
    ).hexdigest()

    received = signature.removeprefix("sha256=")

    return hmac.compare_digest(expected, received)
```

---

## Appendix A: Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0-rc.1 | 2026-02-15 | Initial release candidate. |
