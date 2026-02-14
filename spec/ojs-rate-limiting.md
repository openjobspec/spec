# Open Job Spec: Rate Limiting and Concurrency Control

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Rate Limiting Specification                |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-13                                     |
| **Status**  | Release Candidate                              |
| **Tier**    | Official Extension                             |
| **URI**     | `urn:ojs:ext:rate-limiting`                    |
| **Requires**| OJS Core Specification (Layer 1)               |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Design Principles](#4-design-principles)
5. [Rate Limiting Strategies](#5-rate-limiting-strategies)
   - 5.1 [Concurrency Limiting](#51-concurrency-limiting)
   - 5.2 [Window-Based Rate Limiting](#52-window-based-rate-limiting)
   - 5.3 [Throttling](#53-throttling)
6. [RateLimitPolicy Structure](#6-ratelimitpolicy-structure)
7. [Rate Limit Scope and Keys](#7-rate-limit-scope-and-keys)
8. [Behavior When Limits Are Reached](#8-behavior-when-limits-are-reached)
9. [Dynamic Rate Limiting](#9-dynamic-rate-limiting)
10. [HTTP Binding](#10-http-binding)
11. [Observability](#11-observability)
12. [Conformance Requirements](#12-conformance-requirements)
13. [Prior Art](#13-prior-art)
14. [Examples](#14-examples)

---

## 1. Introduction

Rate limiting and concurrency control are the single most requested production feature across all background job processing systems. Sidekiq's Mike Perham identified rate limiting as the "#1 customer request." River's creators report that "concurrency control has been the most frequent request, particularly among Pro customers." Every major system -- Temporal, Inngest, BullMQ, Oban, Sidekiq, Asynq -- eventually adds these controls.

The need is universal: without rate limiting, job workers overwhelm external APIs, exhaust database connection pools, saturate disk I/O, or trigger provider rate limits that affect the entire organization. Without concurrency control, a burst of enqueued jobs can consume all available workers, starving other job types and creating cascading failures.

This specification defines three rate limiting strategies that cover the full spectrum of production needs: **concurrency limiting** (max simultaneous jobs), **window-based rate limiting** (max jobs per time window), and **throttling** (controlled execution rate). These three strategies correspond to the three fundamental approaches identified across all systems studied.

### 1.1 Scope

This specification defines:

- Three rate limiting strategies and their semantics.
- The `RateLimitPolicy` structure for declaring rate limits on jobs.
- Rate limit scope and key mechanisms for per-resource, per-queue, and per-tenant limiting.
- Behavior when limits are reached (backpressure strategies).
- Dynamic rate limit adjustment.
- HTTP binding for rate limit operations.
- Observability requirements.

This specification does **not** define:

- Distributed rate limiting consensus algorithms (implementation detail).
- Token bucket or leaky bucket implementation details (implementations MAY use any algorithm that produces conformant behavior).
- Per-worker rate limits (rate limits are server-side, not client-side).

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

Every MUST requirement includes a rationale explaining why the requirement is mandatory.

---

## 3. Terminology

| Term                  | Definition                                                                                         |
|-----------------------|----------------------------------------------------------------------------------------------------|
| concurrency limit     | The maximum number of jobs that may execute simultaneously for a given scope.                      |
| rate limit            | A constraint on the number of jobs that may begin execution within a time window.                  |
| throttle              | A constraint on the rate at which jobs begin execution, expressed as maximum starts per unit time.  |
| rate limit key        | A string that identifies the rate-limited resource (e.g., an external API, a tenant, a queue).     |
| scope                 | The boundary within which a rate limit applies: global, per-queue, per-type, or per-key.           |
| partition             | A unique rate limit counter identified by a scope + key combination.                               |
| backpressure action   | What happens when a job cannot execute due to rate limits: wait, reschedule, or reject.            |
| window                | A fixed or sliding time period over which rate limits are counted.                                 |

---

## 4. Design Principles

1. **Server-side enforcement.** Rate limits are enforced by the OJS backend, not by SDKs or workers. This ensures limits are respected even when workers are deployed across multiple processes, hosts, or data centers.

2. **Composable strategies.** A single job MAY be subject to multiple rate limits simultaneously (e.g., a concurrency limit per queue AND a rate limit per API key). All applicable limits MUST be satisfied before a job begins execution.

3. **Non-lossy by default.** When a rate limit is reached, the default behavior is to hold the job and execute it later -- not to discard it. This is the correct default for background jobs, where data loss is unacceptable. Lossy behavior (dropping) is available as an explicit opt-in.

4. **Key-based partitioning.** Rate limits are partitioned by a key that can be derived from job attributes. This enables per-tenant, per-API, per-customer, or per-resource limits without requiring separate queues.

---

## 5. Rate Limiting Strategies

### 5.1 Concurrency Limiting

**Definition**: A concurrency limit constrains the maximum number of jobs of a given scope that may be in the `active` state simultaneously.

**Use cases**:
- Limit the number of concurrent database-intensive jobs to avoid exhausting connection pools.
- Limit the number of concurrent file-processing jobs to avoid disk I/O saturation.
- Limit the number of concurrent API calls to a third-party service.

**Semantics**:

When a worker requests a job via FETCH and the applicable concurrency limit is already at its maximum:
- The backend MUST NOT assign the job to the worker.
- The job MUST remain in the `available` state.
- The job MUST be assigned to a worker when the concurrency count decreases (via ACK, FAIL, or visibility timeout expiry).

**Rationale**: Concurrency limiting is the simplest and most universally needed form of rate control. It directly maps to the "how many connections/handles/threads can this downstream resource handle?" question that every production system must answer.

Implementations MUST track active job counts atomically with job state transitions (FETCH and ACK/FAIL). Non-atomic tracking can lead to counts drifting over time, eventually allowing too many or too few concurrent jobs.

**Rationale**: Counter drift is a documented issue in Sidekiq's concurrent limiter and BullMQ's rate limiter. Atomic tracking (using Redis Lua scripts, database transactions, or similar mechanisms) is the only reliable approach.

### 5.2 Window-Based Rate Limiting

**Definition**: A window-based rate limit constrains the number of jobs that may begin execution within a fixed or sliding time window.

**Use cases**:
- Respect third-party API rate limits (e.g., "1,000 requests per minute to Stripe").
- Limit notification sends per user per day.
- Enforce billing tier quotas.

**Semantics**:

When a worker requests a job via FETCH and the applicable window-based rate limit has been reached:
- The backend MUST NOT assign the job to the worker.
- The job MUST remain in the `available` state.
- The backend SHOULD resume dispatching jobs when the window resets or advances.

Implementations MAY use either fixed windows or sliding windows:

- **Fixed window**: The counter resets at regular intervals (e.g., every minute at :00). Simple but allows bursts at window boundaries (up to 2x the limit across two adjacent windows).
- **Sliding window**: The counter tracks events in a rolling time period. More accurate but requires more state. RECOMMENDED for applications where burst prevention is important.

Implementations MUST document which window algorithm they use.

**Rationale**: Both algorithms are valid and widely used. Fixed windows are simpler to implement (especially in Redis with `INCR` + `EXPIRE`) and sufficient for most use cases. Sliding windows provide stricter guarantees. Requiring documentation rather than mandating one algorithm gives implementations flexibility while ensuring users can make informed decisions.

### 5.3 Throttling

**Definition**: Throttling constrains the rate at which jobs begin execution, expressed as a maximum number of job starts per unit time, with even spacing between starts.

**Use cases**:
- Smooth out bursty workloads to maintain predictable downstream load.
- Ensure even distribution of API calls over time to avoid triggering rate limits that use leaky bucket algorithms.

**Semantics**:

When throttling is active, the backend MUST space job starts evenly across the time window. For a throttle of N jobs per second, the minimum interval between consecutive job starts MUST be approximately `1/N` seconds (with tolerance for implementation precision).

**Rationale**: Throttling differs from window-based rate limiting in an important way: a rate limit of "60 per minute" allows all 60 to fire in the first second, while a throttle of "60 per minute" spaces them at approximately one per second. Many external APIs use leaky bucket or token bucket algorithms that are sensitive to burst patterns, making even spacing essential.

---

## 6. RateLimitPolicy Structure

A `RateLimitPolicy` is a JSON object that MAY be attached to a job at enqueue time via the `rate_limit` field in job options.

### 6.1 Field Definitions

```json
{
  "rate_limit": {
    "key": "stripe-api",
    "concurrency": 5,
    "rate": {
      "limit": 100,
      "period": "PT1M"
    },
    "throttle": {
      "limit": 10,
      "period": "PT1S"
    },
    "on_limit": "wait"
  }
}
```

| Field              | Type    | Required | Default  | Description                                                        |
|--------------------|---------|----------|----------|--------------------------------------------------------------------|
| `key`              | string  | Yes      | --       | The rate limit partition key. Jobs with the same key share limits.  |
| `concurrency`      | integer | No       | --       | Maximum concurrent active jobs for this key. Null means unlimited.  |
| `rate`             | object  | No       | --       | Window-based rate limit configuration. Null means no rate limit.    |
| `rate.limit`       | integer | Yes*     | --       | Maximum number of job starts within the period.                     |
| `rate.period`      | string  | Yes*     | --       | ISO 8601 duration for the rate window (e.g., `"PT1M"`, `"PT1H"`).  |
| `throttle`         | object  | No       | --       | Throttle configuration for even spacing. Null means no throttle.    |
| `throttle.limit`   | integer | Yes*     | --       | Maximum job starts per period with even spacing.                    |
| `throttle.period`  | string  | Yes*     | --       | ISO 8601 duration for the throttle window.                          |
| `on_limit`         | string  | No       | `"wait"` | Action when the limit is reached: `"wait"`, `"reschedule"`, or `"drop"`. |

*Required when the parent object is present.

### 6.2 Field Semantics

#### `key` (string, REQUIRED)

The rate limit partition key. All jobs with the same `key` value share the same rate limit counters. This is the mechanism that enables per-resource, per-tenant, or per-API rate limiting.

Keys MUST match the pattern `^[a-zA-Z0-9][a-zA-Z0-9._:-]*$`.

**Rationale**: The key is required (not optional) because keyless rate limits are effectively per-queue or per-type limits, which SHOULD be configured at the queue/type level rather than per-job. Requiring a key makes the rate-limited resource explicit and prevents accidental global limiting.

#### `concurrency` (integer)

The maximum number of jobs with this key that may be in the `active` state simultaneously. A value of `0` means no jobs may execute (effectively pausing this key). When omitted, no concurrency limit is applied.

Implementations MUST enforce concurrency limits atomically with job assignment. The sequence MUST be: check limit → assign job → increment counter as a single atomic operation.

**Rationale**: Non-atomic check-then-assign sequences allow race conditions where N+1 jobs pass the check before any of them increment the counter, violating the concurrency limit.

#### `rate` (object)

Configures a window-based rate limit. When present, the backend MUST track the number of job starts for this key within the specified period and prevent new starts when the limit is reached.

#### `throttle` (object)

Configures throttling with even spacing. When present, the backend MUST space job starts evenly across the period. This is more restrictive than `rate` because it prevents bursts.

A job MAY have both `rate` and `throttle` specified. When both are present, both constraints MUST be satisfied before a job starts.

#### `on_limit` (string)

Defines what happens when a job cannot start due to a rate limit:

| Value        | Behavior                                                                                                |
|--------------|---------------------------------------------------------------------------------------------------------|
| `"wait"`     | The job remains `available` and is dispatched when the limit allows. This is the default. **Non-lossy.** |
| `"reschedule"` | The job is moved to `scheduled` state with a `scheduled_at` time set to when the limit is expected to allow execution. **Non-lossy.** |
| `"drop"`     | The job is moved to `discarded` state. **Lossy.** Use only for non-critical jobs where freshness matters more than completeness. |

Implementations MUST default to `"wait"` when `on_limit` is not specified.

**Rationale**: The non-lossy default prevents data loss in the common case. Inngest distinguishes between throttling (non-lossy) and rate limiting (lossy), which caused confusion in their user base. OJS makes the loss behavior explicit via `on_limit` rather than implicit in the strategy choice.

---

## 7. Rate Limit Scope and Keys

### 7.1 Key Derivation

Rate limit keys MAY be static strings or derived from job attributes at enqueue time. The key derivation is the client's responsibility; the backend receives the fully resolved key.

**Examples of key patterns**:

| Pattern                      | Example Key                    | Use Case                                      |
|------------------------------|--------------------------------|-----------------------------------------------|
| API endpoint                 | `"api.stripe.com"`             | Limit calls to Stripe                         |
| Tenant ID                    | `"tenant:acme-corp"`           | Per-tenant rate limiting                      |
| Queue name                   | `"queue:email"`                | Per-queue concurrency control                 |
| Job type                     | `"type:report.generate"`       | Per-type concurrency control                  |
| Composite                    | `"tenant:acme:api:stripe"`     | Per-tenant, per-API limit                     |

### 7.2 Queue-Level Rate Limits

In addition to per-job rate limit policies, implementations SHOULD support queue-level rate limit configuration. Queue-level limits apply to all jobs in a queue regardless of their individual `rate_limit` settings.

Queue-level rate limits are configured via the Admin API (see ojs-admin-api.md) rather than per-job:

```http
PUT /ojs/v1/admin/queues/email/rate-limit
Content-Type: application/json

{
  "concurrency": 20,
  "rate": {
    "limit": 1000,
    "period": "PT1H"
  }
}
```

When both queue-level and job-level rate limits apply, all limits MUST be satisfied. The most restrictive limit wins.

**Rationale**: Queue-level limits provide a safety net that cannot be circumvented by individual job settings. This is essential for protecting shared resources: even if a developer forgets to set a rate limit on their job, the queue-level limit prevents runaway execution.

---

## 8. Behavior When Limits Are Reached

### 8.1 Interaction with FETCH

When a worker calls FETCH and the next available job is rate-limited, the backend MUST:

1. Skip the rate-limited job.
2. Attempt to assign the next eligible job in the queue (if any).
3. If no eligible jobs remain, return an empty response (same as an empty queue).

The rate-limited job MUST remain in the `available` state and MUST NOT be invisible to future FETCH requests (unless it has been moved to `scheduled` by the `reschedule` action).

**Rationale**: Skipping rate-limited jobs and attempting the next one is critical for throughput. If the backend blocked on the rate-limited job, all workers polling that queue would stall even if there are non-rate-limited jobs available.

### 8.2 Interaction with Priority

Rate-limited jobs MUST NOT bypass priority ordering. If a high-priority job is rate-limited, a lower-priority job that is not rate-limited SHOULD be assigned instead.

### 8.3 Interaction with Retry

When a rate-limited job eventually executes and fails, it follows the standard retry policy. The retry backoff is independent of the rate limit wait time. Rate limit wait time does NOT count toward the job's visibility timeout or retry delay.

---

## 9. Dynamic Rate Limiting

### 9.1 Rate Limit Adjustment

Implementations SHOULD support dynamic adjustment of rate limits in response to external signals. The most common signal is an HTTP 429 (Too Many Requests) response from a downstream API.

When a job handler reports a rate limit error (by including `rate_limit_until` in the error response), the backend SHOULD temporarily reduce the rate for that key:

```json
{
  "error": {
    "type": "RateLimitExceeded",
    "message": "Stripe API rate limit exceeded",
    "rate_limit_until": "2026-02-13T12:05:00Z"
  }
}
```

When `rate_limit_until` is present in an error response, the backend SHOULD NOT dispatch jobs with the same rate limit key until the specified time.

**Rationale**: This pattern was pioneered by BullMQ's dynamic rate limiting feature, which adjusts the rate limiter when a job reports a 429 response. It closes the feedback loop between the external API's rate limits and the job system's dispatching, preventing repeated failures against an already-saturated API.

---

## 10. HTTP Binding

### 10.1 Rate Limit Inspection

```
GET /ojs/v1/rate-limits/{key}
```

Returns the current state of a rate limit partition:

```json
{
  "key": "stripe-api",
  "concurrency": {
    "limit": 5,
    "active": 3,
    "available": 2
  },
  "rate": {
    "limit": 100,
    "period": "PT1M",
    "current_count": 47,
    "window_resets_at": "2026-02-13T12:01:00Z"
  },
  "throttle": {
    "limit": 10,
    "period": "PT1S",
    "next_allowed_at": "2026-02-13T12:00:00.100Z"
  },
  "waiting_count": 12
}
```

### 10.2 Rate Limit Override

```
PUT /ojs/v1/rate-limits/{key}
```

Temporarily overrides the rate limit for a key. Useful for incident response (e.g., reducing the limit to zero when an external API is down).

```json
{
  "concurrency": 0,
  "expires_at": "2026-02-13T13:00:00Z"
}
```

### 10.3 Rate Limit Listing

```
GET /ojs/v1/rate-limits
```

Lists all active rate limit partitions with their current state. Supports pagination.

```json
{
  "items": [
    {
      "key": "stripe-api",
      "concurrency": { "limit": 5, "active": 3 },
      "rate": { "limit": 100, "period": "PT1M", "current_count": 47 },
      "waiting_count": 12
    },
    {
      "key": "tenant:acme-corp",
      "concurrency": { "limit": 10, "active": 7 },
      "waiting_count": 3
    }
  ],
  "pagination": {
    "total": 42,
    "page": 1,
    "per_page": 20
  }
}
```

---

## 11. Observability

### 11.1 Events

Implementations MUST emit the following events when rate limiting is active:

| Event Type                    | Trigger                                           | Data Fields                          |
|-------------------------------|---------------------------------------------------|--------------------------------------|
| `rate_limit.exceeded`         | A job cannot start because its rate limit is hit.  | `key`, `strategy`, `limit`, `current`|
| `rate_limit.released`         | A rate-limited job is now eligible for execution.  | `key`, `strategy`, `job_id`          |
| `rate_limit.dropped`          | A job is discarded due to `on_limit: "drop"`.      | `key`, `job_id`, `job_type`          |
| `rate_limit.dynamic_adjusted` | Rate limit was adjusted via handler feedback.      | `key`, `until`, `reason`             |

### 11.2 Metrics

Implementations SHOULD expose the following metrics:

| Metric Name                           | Type      | Labels                     | Description                              |
|---------------------------------------|-----------|----------------------------|------------------------------------------|
| `ojs.rate_limit.active`               | Gauge     | `key`                      | Current active count for concurrency.    |
| `ojs.rate_limit.waiting`              | Gauge     | `key`                      | Jobs waiting due to rate limit.          |
| `ojs.rate_limit.exceeded_total`       | Counter   | `key`, `strategy`          | Total times rate limit was hit.          |
| `ojs.rate_limit.wait_duration`        | Histogram | `key`                      | Time jobs waited due to rate limits.     |

---

## 12. Conformance Requirements

### 12.1 Required Capabilities

An implementation declaring support for the rate-limiting extension MUST support:

| ID           | Requirement                                                                             |
|--------------|-----------------------------------------------------------------------------------------|
| RL-001       | Concurrency limiting: enforce `concurrency` field atomically with job assignment.       |
| RL-002       | Rate limit keys: partition counters by the `key` field.                                 |
| RL-003       | Wait behavior: hold rate-limited jobs in `available` state when `on_limit` is `"wait"`. |
| RL-004       | Skip behavior: skip rate-limited jobs during FETCH and assign the next eligible job.    |
| RL-005       | Rate limit inspection: `GET /ojs/v1/rate-limits/{key}` returns current state.           |
| RL-006       | Rate limit events: emit `rate_limit.exceeded` and `rate_limit.released` events.         |

### 12.2 Recommended Capabilities

| ID           | Requirement                                                                             |
|--------------|-----------------------------------------------------------------------------------------|
| RL-R001      | Window-based rate limiting with `rate` field.                                           |
| RL-R002      | Throttling with `throttle` field and even spacing.                                      |
| RL-R003      | Dynamic rate limiting via handler error response.                                       |
| RL-R004      | Rate limit override via `PUT /ojs/v1/rate-limits/{key}`.                                |
| RL-R005      | Queue-level rate limits via Admin API.                                                  |

---

## 13. Prior Art

| System           | Approach                                                                                  |
|------------------|-------------------------------------------------------------------------------------------|
| **Sidekiq Enterprise** | Concurrent limiters (semaphore) and rate limiters (window). "#1 customer request."  |
| **BullMQ**       | Per-queue rate limiter with dynamic adjustment on 429 responses.                          |
| **Oban Pro**     | Global rate limiting via Smart Engine. Per-worker and per-queue concurrency.              |
| **Temporal**     | Task queue rate limiting (added 2025). `maxTaskQueueActivitiesPerSecond`.                 |
| **Inngest**      | Four distinct controls: concurrency, throttling (FIFO, non-lossy), rate limiting (lossy), debouncing. |
| **Asynq**        | Server-level concurrency via `MaxConcurrency`. No per-key rate limiting in OSS.           |
| **River**        | Most requested feature. Concurrency control added in Pro tier.                            |

OJS synthesizes these approaches into three composable strategies (concurrency, rate, throttle) with explicit backpressure control (`on_limit`), avoiding the confusion Inngest's four-way distinction creates while providing equivalent expressiveness.

---

## 13.1 Relationship to Backpressure

Rate limiting (this specification) controls dequeue and execution rate to prevent consumer overload. Backpressure ([ojs-backpressure.md](./ojs-backpressure.md)) controls enqueue behavior when queues are full to prevent producer overload. The two are complementary: rate limiting throttles execution throughput, while backpressure bounds queue depth. Implementations SHOULD support both to provide end-to-end flow control.

---

## 14. Examples

### 14.1 Concurrency Limit on External API

Limit concurrent calls to a payment API to 5:

```json
{
  "type": "payment.process",
  "args": [{"order_id": "ord_123", "amount": 9999}],
  "rate_limit": {
    "key": "payment-api",
    "concurrency": 5
  }
}
```

### 14.2 Window-Based Rate Limit for Email Sending

Limit email sends to 1,000 per hour:

```json
{
  "type": "email.send",
  "args": [{"to": "user@example.com", "template": "welcome"}],
  "rate_limit": {
    "key": "email-provider",
    "rate": {
      "limit": 1000,
      "period": "PT1H"
    }
  }
}
```

### 14.3 Per-Tenant Concurrency with Throttle

Limit each tenant to 3 concurrent report jobs, throttled to 1 per second:

```json
{
  "type": "report.generate",
  "args": [{"report_id": "rpt_456"}],
  "meta": {"tenant_id": "acme-corp"},
  "rate_limit": {
    "key": "tenant:acme-corp:reports",
    "concurrency": 3,
    "throttle": {
      "limit": 1,
      "period": "PT1S"
    }
  }
}
```

### 14.4 Lossy Rate Limit for Non-Critical Notifications

Drop excess notification jobs rather than queuing them:

```json
{
  "type": "notification.push",
  "args": [{"user_id": "u_789", "message": "New follower!"}],
  "rate_limit": {
    "key": "push-notifications",
    "rate": {
      "limit": 10000,
      "period": "PT1M"
    },
    "on_limit": "drop"
  }
}
```

### 14.5 Combined Limits

A job subject to both concurrency and rate limits:

```json
{
  "type": "api.sync",
  "args": [{"endpoint": "/users", "page": 1}],
  "rate_limit": {
    "key": "api.partner.com",
    "concurrency": 10,
    "rate": {
      "limit": 500,
      "period": "PT1M"
    },
    "throttle": {
      "limit": 10,
      "period": "PT1S"
    },
    "on_limit": "wait"
  }
}
```

This job will:
1. Not start if 10 other `api.partner.com` jobs are already active (concurrency).
2. Not start if 500 `api.partner.com` jobs have already started in the current minute (rate).
3. Wait at least 100ms since the last `api.partner.com` job started (throttle).
4. Remain in `available` state until all three conditions are satisfied (wait).

---

## Appendix A: Changelog

| Date       | Change                        |
|------------|-------------------------------|
| 2026-02-13 | Initial release candidate.    |
