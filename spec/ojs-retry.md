# Open Job Spec: Retry Policy Specification

| Field       | Value                |
|-------------|----------------------|
| Version     | 1.0.0-rc.1           |
| Date        | 2026-02-12           |
| Status      | Release Candidate    |
| Layer       | 1 -- Core            |
| Spec URI    | `urn:ojs:spec:retry` |

---

## 1. Overview

This document defines the retry policy semantics for Open Job Spec (OJS). A retry policy governs how a conforming implementation behaves when a job handler fails: how many times the job is re-attempted, how long the implementation waits between attempts, and what happens when all attempts are exhausted.

Retry logic is one of the most universally needed capabilities in background job processing. Every major system -- Sidekiq, Celery, Temporal, BullMQ, Faktory, Oban -- implements retry with backoff, yet each expresses the configuration differently and with varying degrees of precision. OJS adopts Temporal's structured retry policy format as the canonical representation because it is the most explicit, the most language-agnostic, and avoids the field-overloading anti-patterns found in other systems.

### 1.1 Design Principles

1. **Explicit fields, no overloading.** Every semantic concept gets its own field. Faktory overloads a single `retry` field to mean "default retry count" (25), "no retry" (0), and "skip retry, send directly to dead letter" (-1). Sidekiq overloads `retry` to accept `true`, `false`, or an integer. These are anti-patterns that create confusion and implementation bugs. OJS uses separate fields: `max_attempts` (integer), `on_exhaustion` (enum), and so on.

2. **Polynomial growth plus jitter is correct.** Sidekiq's battle-tested backoff formula -- `(retry_count^4) + 15 + rand(10) * (retry_count + 1)` -- has proven over a decade of production use that polynomial growth (not pure exponential) combined with jitter produces the best retry behavior. Celery reinforces this with `autoretry_for`, `retry_backoff`, `retry_jitter`, and `retry_backoff_max`. OJS supports multiple backoff strategies including polynomial.

3. **Sensible defaults.** A job with no explicit retry policy MUST still receive retry behavior. The default policy is documented precisely so that every conforming implementation produces identical behavior for jobs that omit a retry configuration.

4. **Handler control over retry decisions.** The handler -- not just the policy -- can influence retry behavior at runtime. A handler MAY return structured error response codes (`RETRY`, `DISCARD`, `DEAD_LETTER`, `FAIL`) to override the default retry-or-not decision for a specific failure.

### 1.2 Terminology

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt).

| Term               | Definition                                                                                       |
|--------------------|-------------------------------------------------------------------------------------------------|
| attempt            | A single execution of a job handler. The first execution is attempt 1.                          |
| retry              | Any attempt after the first. Attempt 2 is the first retry.                                      |
| backoff            | The delay between a failed attempt and the next attempt.                                         |
| jitter             | Randomness added to backoff delay to prevent synchronized retries (thundering herd).            |
| exhaustion         | The condition when `max_attempts` have been reached and the job has not succeeded.              |
| dead letter        | A holding area for jobs that have exhausted all retry attempts, available for manual inspection. |
| non-retryable error| An error type that MUST NOT trigger a retry, regardless of remaining attempts.                  |
| visibility timeout | The reservation period during which a job is considered "owned" by a worker.                    |

---

## 2. RetryPolicy Structure

A `RetryPolicy` is a JSON object that MAY be attached to a job at enqueue time via the `retry` field in job options. When omitted, the default retry policy (Section 8) applies.

### 2.1 Field Definitions

```json
{
  "max_attempts": 3,
  "initial_interval": "PT1S",
  "backoff_coefficient": 2.0,
  "max_interval": "PT5M",
  "jitter": true,
  "non_retryable_errors": [],
  "on_exhaustion": "discard"
}
```

| Field                 | Type      | Required | Default      | Description                                                    |
|-----------------------|-----------|----------|--------------|----------------------------------------------------------------|
| `max_attempts`        | integer   | No       | `3`          | Total number of attempts including the first execution.        |
| `initial_interval`    | string    | No       | `"PT1S"`     | ISO 8601 duration for the delay before the first retry.        |
| `backoff_coefficient` | number    | No       | `2.0`        | Multiplier applied to successive retry delays.                 |
| `max_interval`        | string    | No       | `"PT5M"`     | ISO 8601 duration cap on computed backoff delay.               |
| `jitter`              | boolean   | No       | `true`       | Whether to add randomness to the computed delay.               |
| `non_retryable_errors`| string[]  | No       | `[]`         | Error type strings that MUST skip retry entirely.              |
| `on_exhaustion`       | string    | No       | `"discard"`  | Action when all attempts are exhausted: `"discard"` or `"dead_letter"`. |

### 2.2 Field Semantics

#### `max_attempts` (integer)

The total number of times the job will be attempted, including the initial execution. A value of `1` means the job runs once with no retries. A value of `0` means the job MUST NOT be retried under any circumstances; a failure on the first attempt is immediately terminal.

Implementations MUST treat `max_attempts` as an exact upper bound.

**Rationale for MUST**: Without a strict upper bound, a misbehaving implementation could retry indefinitely, consuming unbounded resources and potentially causing cascading failures in downstream systems. Deterministic retry limits are a fundamental reliability requirement.

**Rationale for counting total attempts (not retries)**: Counting total attempts avoids off-by-one confusion. If `max_attempts` is 3, the job runs at most 3 times. This convention matches Temporal's `maximumAttempts` and avoids the ambiguity of Sidekiq's `retry: 25` which means 25 retries plus the original attempt (26 total executions).

| `max_attempts` value | Behavior                                     |
|-----------------------|----------------------------------------------|
| `0`                   | No retry. Failure is immediately terminal.   |
| `1`                   | Run once. No retry on failure.               |
| `3` (default)         | Run up to 3 times (1 initial + 2 retries).   |
| `25`                  | Run up to 25 times (1 initial + 24 retries). |

#### `initial_interval` (string, ISO 8601 duration)

The delay before the first retry (i.e., the delay between attempt 1 failing and attempt 2 starting). Subsequent retry delays are computed using the backoff formula (Section 3).

Implementations MUST parse this value as an ISO 8601 duration string.

**Rationale for MUST**: A standardized duration format is necessary for interoperability across languages. ISO 8601 durations are unambiguous, human-readable, and supported by standard libraries in every major language. Using millisecond integers (as in OJS v0.2) is error-prone when values span minutes or hours.

See Section 4 for the full ISO 8601 duration format specification.

#### `backoff_coefficient` (number)

The multiplier used in the backoff formula to increase delay between successive retries. The interpretation of this field depends on the backoff strategy (Section 3).

- For `exponential` backoff (the default): the delay for attempt `n` is `initial_interval * backoff_coefficient^(n - 1)`.
- For `polynomial` backoff: the delay for attempt `n` is `initial_interval * n^backoff_coefficient`.
- For `linear` backoff: this field is ignored; the delay grows linearly by `initial_interval`.
- For `none` (constant) backoff: this field is ignored; the delay is always `initial_interval`.

Implementations MUST reject a `backoff_coefficient` value less than `1.0`.

**Rationale for MUST**: A coefficient below 1.0 would cause delays to decrease over successive retries, which is counterproductive -- it increases load on already-failing systems precisely when they need time to recover. A coefficient of exactly 1.0 is valid and produces constant backoff (equivalent to `"none"` strategy).

#### `max_interval` (string, ISO 8601 duration)

The maximum delay between any two consecutive attempts. After the backoff formula computes a delay that exceeds `max_interval`, the implementation MUST cap the delay at `max_interval`.

**Rationale for MUST**: Without a cap, exponential or polynomial backoff can produce delays of hours or days for high attempt counts, which is rarely the desired behavior. A finite cap ensures jobs are retried within a reasonable time horizon.

#### `jitter` (boolean)

When `true`, the implementation MUST add randomness to the computed delay to prevent the thundering herd problem. When `false`, the computed delay is used exactly as calculated.

**Rationale for MUST**: When jitter is enabled, the spec requires a specific jitter behavior (Section 5) to ensure predictable bounds on retry timing. An implementation that claims to support jitter but applies it inconsistently would produce unreliable retry scheduling.

See Section 5 for the jitter algorithm.

#### `non_retryable_errors` (string[])

An array of error type strings. When a handler fails with an error whose type matches any entry in this array, the job MUST NOT be retried regardless of remaining attempts. The job transitions directly to the terminal state determined by `on_exhaustion`.

See Section 6 for matching semantics.

**Rationale for MUST**: Certain errors are definitively permanent -- a malformed payload will never become valid on retry, an authorization failure will not resolve itself, a deleted resource will not reappear. Retrying these errors wastes resources and delays the visibility of the real problem. The handler author knows which errors are permanent and encodes that knowledge in this field.

#### `on_exhaustion` (string, enum)

Determines what happens when `max_attempts` is reached without success, or when a non-retryable error is encountered:

| Value          | Behavior                                                                                  |
|----------------|------------------------------------------------------------------------------------------|
| `"discard"`    | The job is permanently discarded. It transitions to the `discarded` state and is not placed in the dead letter queue. This is the default. |
| `"dead_letter"`| The job is moved to the dead letter queue for manual inspection and possible re-enqueue. It transitions to the `discarded` state with a reference in the dead letter set. |

Implementations MUST support both values.

**Rationale for MUST**: These two exhaustion behaviors represent fundamentally different operational philosophies. Some jobs (analytics events, non-critical notifications) are acceptable to lose; others (payment processing, order fulfillment) MUST be preserved for human review. The implementation MUST support both to serve both use cases.

**Rationale for `"discard"` as default**: Most background jobs are fire-and-forget operations where accumulating dead letters creates operational noise without value. Teams that need dead letter behavior opt into it explicitly. This matches Sidekiq's default behavior where jobs go to the dead set, but OJS defaults to discard because an explicit opt-in to dead letter is clearer than an implicit accumulation of failed jobs.

---

## 3. Backoff Strategies

The backoff strategy determines how the delay between retries grows across successive attempts. OJS defines four strategies. The strategy is not a field on RetryPolicy itself; instead, it is inferred from the `backoff_coefficient` value and MAY be explicitly set by implementations that support a `backoff_strategy` extension field.

The default strategy is **exponential**.

### 3.1 None (Constant Backoff)

The delay is the same for every retry. The `backoff_coefficient` is ignored.

**Formula:**

```
delay(n) = initial_interval
```

Where `n` is the retry number (1-indexed; retry 1 is the first retry, which is overall attempt 2).

**Example** with `initial_interval = "PT5S"`:

| Attempt | Retry # | Delay  |
|---------|---------|--------|
| 2       | 1       | 5s     |
| 3       | 2       | 5s     |
| 4       | 3       | 5s     |
| 5       | 4       | 5s     |

**Use case**: Polling an external service that has a known, fixed recovery time.

### 3.2 Linear

The delay increases by `initial_interval` for each successive retry. The `backoff_coefficient` is ignored.

**Formula:**

```
delay(n) = initial_interval * n
```

**Example** with `initial_interval = "PT5S"`:

| Attempt | Retry # | Delay  |
|---------|---------|--------|
| 2       | 1       | 5s     |
| 3       | 2       | 10s    |
| 4       | 3       | 15s    |
| 5       | 4       | 20s    |

**Use case**: Moderate backpressure where you want gradually increasing delays without aggressive growth.

### 3.3 Exponential (Default)

The delay grows exponentially using the `backoff_coefficient` as the base multiplier.

**Formula:**

```
delay(n) = initial_interval * backoff_coefficient^(n - 1)
```

**Example** with `initial_interval = "PT1S"`, `backoff_coefficient = 2.0`:

| Attempt | Retry # | Raw Delay | Capped (max_interval = PT5M) |
|---------|---------|-----------|-------------------------------|
| 2       | 1       | 1s        | 1s                            |
| 3       | 2       | 2s        | 2s                            |
| 4       | 3       | 4s        | 4s                            |
| 5       | 4       | 8s        | 8s                            |
| 6       | 5       | 16s       | 16s                           |
| 7       | 6       | 32s       | 32s                           |
| 8       | 7       | 64s       | 64s                           |
| 9       | 8       | 128s      | 128s                          |
| 10      | 9       | 256s      | 256s                          |
| 11      | 10      | 512s      | 300s (capped)                 |

**Use case**: General-purpose retry for transient failures. This is the default strategy used by Temporal, AWS SDKs, and most HTTP retry libraries.

### 3.4 Polynomial (Sidekiq-style)

The delay grows polynomially, using the `backoff_coefficient` as the exponent applied to the retry number. This produces slower growth than exponential backoff, making it suitable for high-retry-count scenarios.

**Formula:**

```
delay(n) = initial_interval * n^backoff_coefficient
```

**Example** with `initial_interval = "PT1S"`, `backoff_coefficient = 4.0`:

| Attempt | Retry # | Raw Delay | Capped (max_interval = PT5M) |
|---------|---------|-----------|-------------------------------|
| 2       | 1       | 1s        | 1s                            |
| 3       | 2       | 16s       | 16s                           |
| 4       | 3       | 81s       | 81s                           |
| 5       | 4       | 256s      | 256s                          |
| 6       | 5       | 625s      | 300s (capped)                 |

**Prior art**: Sidekiq's formula `(retry_count^4) + 15 + rand(10) * (retry_count + 1)` is polynomial with exponent 4, plus a constant offset and jitter. The polynomial strategy in OJS generalizes this: setting `backoff_coefficient = 4.0` produces Sidekiq-equivalent growth. The constant offset and jitter in Sidekiq's formula are handled separately by OJS's `jitter` field.

**Use case**: Long-running retry scenarios where you want many retries over an extended period (hours to days) without the delay growing as aggressively as exponential.

### 3.5 Backoff Cap

Regardless of strategy, after the raw delay is computed, implementations MUST apply the `max_interval` cap:

```
effective_delay(n) = min(raw_delay(n), max_interval)
```

This MUST be applied before jitter (Section 5).

**Rationale for MUST**: The cap ensures that no single retry delay exceeds the operator's stated maximum tolerance, regardless of which backoff formula is in use.

---

## 4. Duration Format

All duration fields in the retry policy (`initial_interval`, `max_interval`) MUST use ISO 8601 duration strings as defined in [ISO 8601:2004 Section 4.4.3.2](https://www.iso.org/standard/40874.html).

**Rationale for MUST**: ISO 8601 durations are unambiguous, human-readable, and supported by standard libraries across all major programming languages. Using integer milliseconds is error-prone for durations spanning minutes, hours, or days. Using floating-point seconds introduces precision issues in JSON serialization (as demonstrated by Sidekiq 8.0's migration away from float timestamps).

### 4.1 Format

The general form is `P[n]Y[n]M[n]DT[n]H[n]M[n]S`, where `T` separates date components from time components.

For retry policy durations, the following subset is RECOMMENDED:

| Duration   | ISO 8601 String | Meaning          |
|------------|-----------------|------------------|
| 500ms      | `"PT0.5S"`      | Half a second    |
| 1 second   | `"PT1S"`        | One second       |
| 5 seconds  | `"PT5S"`        | Five seconds     |
| 30 seconds | `"PT30S"`       | Thirty seconds   |
| 1 minute   | `"PT1M"`        | One minute       |
| 5 minutes  | `"PT5M"`        | Five minutes     |
| 15 minutes | `"PT15M"`       | Fifteen minutes  |
| 1 hour     | `"PT1H"`        | One hour         |
| 24 hours   | `"PT24H"`       | Twenty-four hours|

### 4.2 Parsing Requirements

Implementations MUST support at minimum the time components: hours (`H`), minutes (`M`), and seconds (`S`) with optional decimal fractions on seconds.

Implementations SHOULD support the full ISO 8601 duration format including date components (`Y`, `M`, `D`), but date components are NOT RECOMMENDED for retry intervals because their length is ambiguous (months and years vary in length).

Implementations MUST reject duration strings that do not conform to ISO 8601 syntax.

**Rationale for MUST**: Rejecting malformed durations at enqueue time prevents jobs from being created with invalid retry configurations that would cause runtime errors during retry scheduling.

---

## 5. Jitter Specification

Jitter adds randomness to the computed backoff delay to prevent the thundering herd problem: when many jobs fail simultaneously (e.g., due to a downstream outage), without jitter they would all retry at the same instant, recreating the same load spike that caused the original failure.

### 5.1 Algorithm

When `jitter` is `true`, the implementation MUST apply the following transformation to the computed delay (after backoff calculation and cap):

```
jittered_delay = effective_delay * random(0.5, 1.5)
```

Where `random(0.5, 1.5)` produces a uniformly distributed random floating-point number in the half-open interval `[0.5, 1.5)`.

The resulting `jittered_delay` MUST NOT be less than zero. Implementations MUST floor the result at zero (though in practice, with a minimum multiplier of 0.5 and a positive effective_delay, this cannot occur).

**Rationale for MUST (apply the specific formula)**: A standardized jitter range ensures that conformance tests can validate retry timing within predictable bounds. The `[0.5, 1.5)` range provides sufficient randomness to decorrelate retries while keeping delays within a factor of 1.5x of the intended delay, which preserves the operator's intent regarding retry pacing.

### 5.2 Jitter Bounds

Given a computed `effective_delay` of `D`:

- Minimum jittered delay: `0.5 * D`
- Maximum jittered delay: `1.5 * D` (exclusive)
- Expected (mean) jittered delay: `1.0 * D`

### 5.3 Example

With `initial_interval = "PT10S"`, `backoff_coefficient = 2.0`, `jitter = true`, exponential backoff:

| Attempt | Retry # | Raw Delay | Capped Delay | Jitter Range        |
|---------|---------|-----------|--------------|---------------------|
| 2       | 1       | 10s       | 10s          | [5s, 15s)           |
| 3       | 2       | 20s       | 20s          | [10s, 30s)          |
| 4       | 3       | 40s       | 40s          | [20s, 60s)          |
| 5       | 4       | 80s       | 80s          | [40s, 120s)         |
| 6       | 5       | 160s      | 160s         | [80s, 240s)         |
| 7       | 6       | 320s      | 300s (cap)   | [150s, 450s) -> capped at [150s, 300s] |

Note: after the `max_interval` cap is applied, jitter may produce a value that exceeds `max_interval`. Implementations MUST apply the `max_interval` cap again after jitter:

```
final_delay = min(jittered_delay, max_interval)
```

**Rationale for MUST**: Without a post-jitter cap, the jitter multiplier (up to 1.5x) could push delays beyond the operator's stated maximum, violating the semantic contract of `max_interval`.

---

## 6. Non-Retryable Error Matching

The `non_retryable_errors` field contains an array of error type strings. When a job handler fails, the implementation compares the error's type against this list to decide whether to retry.

### 6.1 Error Type Convention

Error types MUST be dot-namespaced strings following the pattern:

```
<domain>.<category>[.<subcategory>]*
```

Examples:
- `validation.payload_invalid`
- `auth.token_expired`
- `external.stripe.card_declined`
- `resource.not_found`
- `rate_limit.exceeded`

**Rationale for MUST**: A consistent naming convention enables prefix matching and ensures error types are meaningful across language boundaries. Dot-namespacing mirrors the job type convention from the core spec and is familiar from Java exception hierarchies, Python module paths, and Elixir error namespaces.

### 6.2 Matching Semantics

An error type matches an entry in `non_retryable_errors` if any of the following conditions hold:

1. **Exact match**: The error type string is identical to the entry.
2. **Prefix match**: The entry ends with `.*` (wildcard suffix), and the error type starts with the prefix portion.

Implementations MUST support exact matching. Implementations SHOULD support prefix matching.

**Rationale for MUST (exact matching)**: Exact matching is the minimum viable behavior that enables non-retryable error configuration. Without it, the field is useless.

**Examples:**

Given `non_retryable_errors: ["validation.payload_invalid", "auth.*"]`:

| Error Type                    | Matches? | Rule            |
|-------------------------------|----------|-----------------|
| `validation.payload_invalid`  | Yes      | Exact match     |
| `validation.schema_error`     | No       | No match        |
| `auth.token_expired`          | Yes      | Prefix `auth.*` |
| `auth.forbidden`              | Yes      | Prefix `auth.*` |
| `auth`                        | No       | `auth` does not start with `auth.` |
| `external.auth.failure`       | No       | Prefix is `auth`, not `external.auth` |

### 6.3 Behavior on Match

When a handler error type matches a `non_retryable_errors` entry:

1. The implementation MUST NOT schedule a retry for this job, regardless of remaining attempts.
2. The implementation MUST transition the job according to the `on_exhaustion` policy (`"discard"` or `"dead_letter"`).
3. The implementation MUST record the error in the job's error history.

**Rationale for MUST (no retry)**: Retrying a known-permanent error wastes compute resources and delays the job's arrival at its terminal state, reducing operational visibility.

**Rationale for MUST (respect on_exhaustion)**: The non-retryable error bypass is an acceleration to the exhaustion state, not a separate code path. Using the same `on_exhaustion` policy ensures consistent terminal behavior.

---

## 7. Handler Error Response Codes

When a job handler completes, it returns either a success result or an error. For errors, the handler MAY include a structured error response code that overrides the default retry behavior.

### 7.1 Response Code Definitions

| Code          | Meaning                                                                                  |
|---------------|------------------------------------------------------------------------------------------|
| `RETRY`       | Retry with normal backoff policy. This is the default behavior when a handler fails without specifying a code. |
| `DISCARD`     | Discard the job immediately. Do not retry. Do not move to dead letter queue.             |
| `DEAD_LETTER` | Move the job to the dead letter queue immediately. Skip all remaining retries.           |
| `FAIL`        | Permanent failure. Semantically identical to `DISCARD` in terms of behavior (the job is not retried), but carries the distinct intent that this is a recognized, permanent failure condition rather than an intentional discard. Implementations MAY record `FAIL` and `DISCARD` differently in metrics and events. |

### 7.2 Precedence

Handler response codes take precedence over the retry policy:

1. If the handler returns `DISCARD`, the job is discarded regardless of `max_attempts` or `on_exhaustion`.
2. If the handler returns `DEAD_LETTER`, the job moves to the dead letter queue regardless of `max_attempts` or `on_exhaustion`.
3. If the handler returns `RETRY` (or returns a plain error with no code), the normal retry policy applies: check `non_retryable_errors`, check remaining attempts, compute backoff.
4. If the handler returns `FAIL`, the job is discarded regardless of `max_attempts` or `on_exhaustion`.

Implementations MUST respect handler response codes when provided.

**Rationale for MUST**: The handler has the most context about whether a failure is retryable. A payment handler that receives a "card stolen" response from the payment processor knows definitively that retrying is futile. The handler MUST be able to communicate this to the runtime.

### 7.3 Error Response Format

When a handler returns an error with a response code, the error object MUST include:

```json
{
  "type": "external.stripe.card_declined",
  "message": "Card ending in 4242 was declined: insufficient funds",
  "code": "DISCARD",
  "details": {}
}
```

| Field     | Type   | Required | Description                                          |
|-----------|--------|----------|------------------------------------------------------|
| `type`    | string | Yes      | Dot-namespaced error type for matching and debugging. |
| `message` | string | Yes      | Human-readable error description.                    |
| `code`    | string | No       | One of `RETRY`, `DISCARD`, `DEAD_LETTER`, `FAIL`. Defaults to `RETRY` if omitted. |
| `details` | object | No       | Arbitrary structured data for debugging.             |

---

## 8. Default Retry Policy

When a job is enqueued without a `retry` field in its options, implementations MUST apply the following default retry policy:

```json
{
  "max_attempts": 3,
  "initial_interval": "PT1S",
  "backoff_coefficient": 2.0,
  "max_interval": "PT5M",
  "jitter": true,
  "non_retryable_errors": [],
  "on_exhaustion": "discard"
}
```

**Rationale for MUST**: A universal default ensures that every OJS job has predictable retry behavior out of the box. Without a mandated default, implementations would diverge (Sidekiq defaults to 25 retries; Temporal defaults to unlimited; Celery defaults to 3), making cross-implementation behavior unpredictable.

**Rationale for these specific defaults:**

- **`max_attempts: 3`**: Three total attempts (1 initial + 2 retries) is a conservative default that catches transient failures without excessive resource consumption. Celery uses the same default. Higher retry counts (like Sidekiq's 25) can be configured explicitly.
- **`initial_interval: "PT1S"`**: One second provides enough delay to survive brief transient failures (network blips, connection pool exhaustion) without introducing noticeable latency.
- **`backoff_coefficient: 2.0`**: A doubling coefficient is the industry standard for exponential backoff, used by Temporal, AWS SDKs, Google Cloud client libraries, and most HTTP retry libraries.
- **`max_interval: "PT5M"`**: Five minutes caps the maximum delay at a duration that is short enough for timely job completion but long enough to give failing systems meaningful recovery time.
- **`jitter: true`**: Jitter is enabled by default because the thundering herd problem is common in production and the cost of jitter (slightly unpredictable timing) is negligible compared to the cost of synchronized retry storms.
- **`non_retryable_errors: []`**: No errors are non-retryable by default. This is the safest default because it requires explicit opt-in to skip retries for specific error types.
- **`on_exhaustion: "discard"`**: Discarding exhausted jobs is the default because most jobs are fire-and-forget. Dead letter queues require operational investment (monitoring, manual review, re-enqueue tooling), and teams that need them should opt in explicitly.

### 8.1 Partial Override Semantics

When a job specifies a partial retry policy (some fields present, others omitted), the implementation MUST merge the provided fields with the defaults. Fields present in the job's policy override the defaults; omitted fields inherit the default values.

**Rationale for MUST**: Partial override is essential for ergonomic use. A developer who only wants to change `max_attempts` to 5 should not be required to re-specify every other field.

**Example**: A job enqueued with:

```json
{
  "retry": {
    "max_attempts": 10,
    "on_exhaustion": "dead_letter"
  }
}
```

Results in the effective policy:

```json
{
  "max_attempts": 10,
  "initial_interval": "PT1S",
  "backoff_coefficient": 2.0,
  "max_interval": "PT5M",
  "jitter": true,
  "non_retryable_errors": [],
  "on_exhaustion": "dead_letter"
}
```

---

## 9. Interaction with Visibility Timeout

The visibility timeout (reservation period) governs how long a worker "owns" a job before it is considered stalled and returned to the available state. The retry policy interacts with this mechanism in several ways.

### 9.1 Retry Delay vs. Visibility Timeout

When a job fails and is scheduled for retry, the implementation MUST NOT make the job available for pickup until the computed backoff delay has elapsed. The retry delay and visibility timeout are independent mechanisms:

- **Visibility timeout** protects against worker crashes (involuntary failure). If a worker takes a job and dies without acknowledging it, the job becomes available again after the visibility timeout expires.
- **Retry delay** protects against transient failures (voluntary failure). When a worker explicitly reports failure (via `nack`), the job is scheduled for retry after the computed backoff delay.

**Rationale for MUST**: Conflating retry delay with visibility timeout would break the semantics of both. A visibility timeout of 30 minutes and a retry delay of 1 second are perfectly valid together -- the visibility timeout applies to stalled jobs, the retry delay applies to explicitly failed jobs.

### 9.2 Stalled Job Requeue

When a job's visibility timeout expires without an `ack` or `nack`, the implementation MUST treat this as a failure and apply the retry policy:

1. Increment the attempt counter.
2. Check `non_retryable_errors` (not applicable for timeout; timeouts are always retryable unless max_attempts is exceeded).
3. Check remaining attempts against `max_attempts`.
4. If attempts remain, compute the backoff delay and schedule the next attempt.
5. If attempts are exhausted, apply `on_exhaustion`.

**Rationale for MUST**: A stalled job (worker crash, network partition, OOM kill) is a failure. It must consume an attempt and follow the retry policy to prevent infinite requeue loops.

### 9.3 Heartbeat Extension

Workers MAY extend the visibility timeout by sending heartbeat signals during long-running job execution. Heartbeat extension does not affect the retry policy -- it only prevents the job from being prematurely requeued due to timeout.

If a job's handler is still running when the visibility timeout would normally expire, and the worker has sent a heartbeat within the timeout window, the implementation MUST extend the reservation rather than requeuing the job.

**Rationale for MUST**: Without heartbeat support, long-running jobs would be forcibly requeued even while actively processing, causing duplicate execution and wasted work.

---

## 10. Retry State Tracking

Implementations MUST track the following state for each job across retry attempts:

| Field           | Type      | Description                                                        |
|-----------------|-----------|--------------------------------------------------------------------|
| `attempt`       | integer   | Current attempt number (1-indexed). Starts at 1 for the first execution. |
| `errors`        | array     | Ordered list of error objects from all failed attempts.            |
| `next_retry_at` | timestamp | ISO 8601 timestamp of when the next retry is scheduled. Null if not in retryable state. |

**Rationale for MUST**: Without attempt tracking, the implementation cannot enforce `max_attempts`. Without error history, operators cannot diagnose recurring failures. Without `next_retry_at`, monitoring tools cannot display retry schedules.

### 10.1 Error History

Each entry in the `errors` array MUST contain:

```json
{
  "attempt": 2,
  "type": "external.api_timeout",
  "message": "Request to payment API timed out after 30s",
  "code": "RETRY",
  "timestamp": "2026-02-12T10:31:05Z",
  "details": {
    "endpoint": "https://api.stripe.com/v1/charges",
    "timeout_ms": 30000
  }
}
```

Implementations MUST preserve at least the most recent 10 error entries. Implementations MAY preserve more.

**Rationale for MUST (minimum 10)**: Error history is essential for debugging. A minimum of 10 entries ensures that even high-retry-count jobs have meaningful diagnostic data. Implementations that need to limit storage may truncate older entries.

---

## 11. Retry Policy Validation

Implementations MUST validate the retry policy at enqueue time and reject jobs with invalid policies.

**Rationale for MUST**: Catching configuration errors at enqueue time is far less costly than discovering them at retry time, when the job is already in-flight and partially executed.

### 11.1 Validation Rules

| Rule                                              | Error Type                          |
|---------------------------------------------------|-------------------------------------|
| `max_attempts` MUST be a non-negative integer     | `validation.retry_policy_invalid`   |
| `initial_interval` MUST be a valid ISO 8601 duration | `validation.retry_policy_invalid` |
| `initial_interval` MUST be greater than zero      | `validation.retry_policy_invalid`   |
| `backoff_coefficient` MUST be >= 1.0              | `validation.retry_policy_invalid`   |
| `max_interval` MUST be a valid ISO 8601 duration  | `validation.retry_policy_invalid`   |
| `max_interval` MUST be >= `initial_interval`      | `validation.retry_policy_invalid`   |
| `jitter` MUST be a boolean                        | `validation.retry_policy_invalid`   |
| `non_retryable_errors` MUST be an array of strings | `validation.retry_policy_invalid`  |
| `on_exhaustion` MUST be `"discard"` or `"dead_letter"` | `validation.retry_policy_invalid` |

---

## 12. Examples

### 12.1 No Retry

A job that should never be retried. If the handler fails, the job is immediately discarded.

```json
{
  "type": "analytics.page_view",
  "args": ["user_123", "/home", "2026-02-12T10:30:00Z"],
  "options": {
    "retry": {
      "max_attempts": 1
    }
  }
}
```

Effective policy:

```json
{
  "max_attempts": 1,
  "initial_interval": "PT1S",
  "backoff_coefficient": 2.0,
  "max_interval": "PT5M",
  "jitter": true,
  "non_retryable_errors": [],
  "on_exhaustion": "discard"
}
```

Behavior: The job runs once. If it fails, it is discarded. No retry occurs.

### 12.2 Simple Retry (Default Policy)

A job that relies on the default retry policy. No explicit retry configuration needed.

```json
{
  "type": "email.send_welcome",
  "args": ["user_456", "welcome_v2"]
}
```

Effective policy (the default):

```json
{
  "max_attempts": 3,
  "initial_interval": "PT1S",
  "backoff_coefficient": 2.0,
  "max_interval": "PT5M",
  "jitter": true,
  "non_retryable_errors": [],
  "on_exhaustion": "discard"
}
```

Behavior: The job runs up to 3 times. Retry delays (before jitter) are 1s, 2s. If all 3 attempts fail, the job is discarded.

### 12.3 Aggressive Retry with Dead Letter

A payment processing job that retries many times with polynomial backoff and moves to the dead letter queue on exhaustion.

```json
{
  "type": "payment.charge",
  "args": ["order_789", 4999, "usd"],
  "options": {
    "retry": {
      "max_attempts": 25,
      "initial_interval": "PT15S",
      "backoff_coefficient": 4.0,
      "max_interval": "PT1H",
      "jitter": true,
      "non_retryable_errors": [
        "payment.card_stolen",
        "payment.card_expired",
        "validation.*"
      ],
      "on_exhaustion": "dead_letter"
    }
  }
}
```

Behavior:
- Up to 25 attempts (1 initial + 24 retries).
- With polynomial backoff (`backoff_coefficient = 4.0`), the retry number raised to the 4th power times 15 seconds gives Sidekiq-comparable growth.
- Delays are capped at 1 hour.
- If the payment processor returns a "card stolen" or "card expired" error, no retry occurs.
- If any validation error occurs (prefix match on `validation.*`), no retry occurs.
- If all 25 attempts fail (with retryable errors), the job moves to the dead letter queue for manual review.

Retry delay schedule (polynomial, before jitter, selected attempts):

| Attempt | Retry # | Formula: 15s * n^4  | Capped at PT1H |
|---------|---------|----------------------|-----------------|
| 2       | 1       | 15s                  | 15s             |
| 3       | 2       | 240s (4m)            | 240s            |
| 4       | 3       | 1215s (~20m)         | 1215s           |
| 5       | 4       | 3840s (~64m)         | 3600s (capped)  |
| 6       | 5       | 9375s (~2.6h)        | 3600s (capped)  |

### 12.4 Custom Non-Retryable Errors

An API integration job that knows which upstream errors are permanent.

```json
{
  "type": "integration.sync_crm",
  "args": ["account_001"],
  "options": {
    "retry": {
      "max_attempts": 5,
      "initial_interval": "PT30S",
      "backoff_coefficient": 2.0,
      "max_interval": "PT15M",
      "jitter": true,
      "non_retryable_errors": [
        "auth.invalid_credentials",
        "auth.account_suspended",
        "resource.not_found",
        "validation.*",
        "external.crm.api_deprecated"
      ],
      "on_exhaustion": "dead_letter"
    }
  }
}
```

Behavior:
- If the CRM returns a 401 (mapped to `auth.invalid_credentials`), the job goes directly to the dead letter queue. No retry.
- If the CRM returns a 404 (mapped to `resource.not_found`), the job goes directly to the dead letter queue. No retry.
- If the CRM returns a 503 (mapped to `external.crm.service_unavailable`, which is not in the non-retryable list), the job retries with exponential backoff.

### 12.5 Constant Backoff for Polling

A job that polls an external system at a fixed interval.

```json
{
  "type": "export.check_status",
  "args": ["export_id_555"],
  "options": {
    "retry": {
      "max_attempts": 60,
      "initial_interval": "PT10S",
      "backoff_coefficient": 1.0,
      "max_interval": "PT10S",
      "jitter": false,
      "non_retryable_errors": [],
      "on_exhaustion": "dead_letter"
    }
  }
}
```

Behavior:
- Up to 60 attempts, each 10 seconds apart.
- `backoff_coefficient = 1.0` combined with `max_interval` equal to `initial_interval` produces constant backoff.
- Jitter is disabled because the job is polling a single-tenant resource, not competing with other retriers.
- Total retry window: ~10 minutes (60 attempts * 10 seconds).

### 12.6 No Retry, Direct to Dead Letter

A critical job that must not be retried but must be preserved for manual inspection.

```json
{
  "type": "compliance.generate_report",
  "args": ["q4_2025", "sec_filing"],
  "options": {
    "retry": {
      "max_attempts": 1,
      "on_exhaustion": "dead_letter"
    }
  }
}
```

Behavior: The job runs once. If it fails, it goes directly to the dead letter queue. An operator can inspect the failure, fix the underlying issue, and manually re-enqueue the job.

### 12.7 Handler Override Example

A job handler that uses response codes to control retry behavior at runtime:

```
Handler logic (pseudocode):

function handle_payment(ctx):
  try:
    result = payment_api.charge(ctx.job.args)
    return result
  catch CardDeclinedError as e:
    return Error(type="payment.card_declined", code="DISCARD", message=e.message)
  catch CardStolenError as e:
    return Error(type="payment.card_stolen", code="DEAD_LETTER", message=e.message)
  catch TimeoutError as e:
    return Error(type="external.timeout", code="RETRY", message=e.message)
  catch InternalServerError as e:
    // No code specified -- defaults to RETRY
    return Error(type="external.server_error", message=e.message)
```

In this example:
- A declined card is discarded silently (no dead letter, no retry).
- A stolen card goes to dead letter for fraud investigation.
- A timeout retries with normal backoff.
- A server error retries with normal backoff (default `RETRY` code).

---

## 13. Prior Art

This specification draws from the following systems:

### 13.1 Temporal

Temporal's `RetryPolicy` is the primary inspiration for OJS's retry policy structure. Temporal defines: `initialInterval`, `backoffCoefficient`, `maximumInterval`, `maximumAttempts`, and `nonRetryableErrorTypes`. OJS adopts this structure with snake_case naming (for JSON consistency), adds `jitter` (which Temporal handles internally), and adds `on_exhaustion` (which Temporal does not need because it always preserves workflow history).

**Reference**: [Temporal Retry Policies](https://docs.temporal.io/retry-policies)

### 13.2 Sidekiq

Sidekiq's backoff formula `(retry_count^4) + 15 + rand(10) * (retry_count + 1)` has been battle-tested since 2012 across millions of production deployments. The polynomial growth (exponent 4) was chosen to spread retries over a 21-day window with 25 retries. OJS's polynomial backoff strategy generalizes this formula, and the `jitter` field captures the `rand(10) * (retry_count + 1)` component.

Sidekiq's `sidekiq_retry_in` callback, which can return `:kill` or `:discard`, inspired OJS's handler error response codes (`DEAD_LETTER` and `DISCARD`).

**Anti-pattern avoided**: Sidekiq overloads the `retry` field to mean `true` (use default), `false` (no retry), or an integer (retry count). OJS uses separate fields for each semantic.

**Reference**: [Sidekiq Error Handling](https://github.com/sidekiq/sidekiq/wiki/Error-Handling)

### 13.3 Celery

Celery's `autoretry_for` decorator with `retry_backoff`, `retry_jitter`, `retry_backoff_max`, and `max_retries` parameters informed OJS's field naming and default value choices. Celery's default of 3 max retries is adopted as OJS's default. Celery's `retry_jitter = True` default (enabling "full jitter" from the AWS Architecture Blog) validated OJS's decision to enable jitter by default.

**Reference**: [Celery Task Retry](https://docs.celeryq.dev/en/stable/userguide/tasks.html#retrying)

### 13.4 Faktory

Faktory's approach of overloading a single `retry` integer field (where 25 = default, 0 = no retry, -1 = skip retry and go to dead) is explicitly avoided in OJS as an anti-pattern. However, Faktory's structured error format (`{jid, errtype, message, backtrace}`) informed OJS's error response format.

**Reference**: [Faktory Wiki -- Job Lifecycle](https://github.com/contribsys/faktory/wiki/Job-Lifecycle)

### 13.5 BullMQ

BullMQ's `attempts` and `backoff` options (supporting `exponential` and `fixed` strategies with customizable delay) validated the multi-strategy backoff approach. BullMQ's separate `removeOnComplete` and `removeOnFail` options informed the design of `on_exhaustion`.

**Reference**: [BullMQ Guide -- Retrying](https://docs.bullmq.io/guide/retrying-failing-jobs)

### 13.6 Oban

Oban's approach of defining `max_attempts` as total attempts (not retry count) validated OJS's counting convention. Oban's `discard` and `snooze` return values from workers inspired OJS's handler response codes.

**Reference**: [Oban Documentation -- Worker](https://hexdocs.pm/oban/Oban.Worker.html)

---

## 14. JSON Schema

The following JSON Schema defines the `RetryPolicy` object. Conforming implementations MUST validate retry policies against this schema (or an equivalent constraint set).

**Rationale for MUST**: Schema validation at enqueue time prevents malformed retry policies from entering the system, where they would cause runtime errors during retry scheduling.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://openjobspec.org/schemas/v1/retry-policy.json",
  "title": "OJS Retry Policy",
  "description": "Defines how a job should be retried on failure.",
  "type": "object",
  "properties": {
    "max_attempts": {
      "type": "integer",
      "minimum": 0,
      "default": 3,
      "description": "Total number of attempts including the first execution. 0 means no retry."
    },
    "initial_interval": {
      "type": "string",
      "pattern": "^P(?!$)(\\d+Y)?(\\d+M)?(\\d+D)?(T(?=\\d)(\\d+H)?(\\d+M)?(\\d+(\\.\\d+)?S)?)?$",
      "default": "PT1S",
      "description": "ISO 8601 duration for the delay before the first retry."
    },
    "backoff_coefficient": {
      "type": "number",
      "minimum": 1.0,
      "default": 2.0,
      "description": "Multiplier for successive retry delays. Must be >= 1.0."
    },
    "max_interval": {
      "type": "string",
      "pattern": "^P(?!$)(\\d+Y)?(\\d+M)?(\\d+D)?(T(?=\\d)(\\d+H)?(\\d+M)?(\\d+(\\.\\d+)?S)?)?$",
      "default": "PT5M",
      "description": "ISO 8601 duration cap on the computed backoff delay."
    },
    "jitter": {
      "type": "boolean",
      "default": true,
      "description": "Whether to add randomness to prevent thundering herd on mass retries."
    },
    "non_retryable_errors": {
      "type": "array",
      "items": {
        "type": "string",
        "minLength": 1
      },
      "default": [],
      "description": "Error type strings that bypass retry and go directly to exhaustion behavior."
    },
    "on_exhaustion": {
      "type": "string",
      "enum": ["discard", "dead_letter"],
      "default": "discard",
      "description": "Action when max_attempts is reached: discard the job or move to dead letter queue."
    }
  },
  "additionalProperties": false
}
```

---

## 15. Conformance Requirements Summary

The following table summarizes all MUST-level requirements in this specification:

| ID     | Requirement                                                                                     | Section |
|--------|-------------------------------------------------------------------------------------------------|---------|
| RET-01 | Implementations MUST treat `max_attempts` as an exact upper bound on total execution attempts.  | 2.2     |
| RET-02 | Implementations MUST parse duration fields as ISO 8601 duration strings.                        | 2.2     |
| RET-03 | Implementations MUST reject `backoff_coefficient` values less than 1.0.                         | 2.2     |
| RET-04 | Implementations MUST cap computed delay at `max_interval`.                                      | 2.2     |
| RET-05 | Implementations MUST apply jitter using `random(0.5, 1.5)` multiplier when `jitter` is true.   | 5.1     |
| RET-06 | Implementations MUST apply `max_interval` cap after jitter.                                     | 5.3     |
| RET-07 | Implementations MUST NOT retry when error type matches `non_retryable_errors`.                  | 6.3     |
| RET-08 | Implementations MUST respect handler error response codes when provided.                        | 7.2     |
| RET-09 | Implementations MUST apply the default retry policy when no policy is specified.                 | 8       |
| RET-10 | Implementations MUST merge partial policies with defaults.                                       | 8.1     |
| RET-11 | Implementations MUST NOT make a retrying job available before the backoff delay elapses.         | 9.1     |
| RET-12 | Implementations MUST treat visibility timeout expiry as a failure attempt.                       | 9.2     |
| RET-13 | Implementations MUST extend reservation on valid heartbeat rather than requeuing.                | 9.3     |
| RET-14 | Implementations MUST track attempt count, error history, and next retry timestamp.               | 10      |
| RET-15 | Implementations MUST preserve at least the 10 most recent error history entries.                 | 10.1    |
| RET-16 | Implementations MUST validate retry policy at enqueue time.                                      | 11      |
| RET-17 | Implementations MUST support both `"discard"` and `"dead_letter"` exhaustion behaviors.          | 2.2     |
| RET-18 | Implementations MUST support exact matching for `non_retryable_errors`.                          | 6.2     |
| RET-19 | Implementations MUST reject invalid ISO 8601 duration strings.                                   | 4.2     |
| RET-20 | Implementations MUST validate retry policies against the schema (or equivalent constraints).     | 14      |

---

## 16. Relationship to Dead Letter Queue

When a job exhausts all retry attempts, it transitions to the `discarded` state (if `on_exhaustion` is `"discard"`) or is moved to a dead letter queue (if `on_exhaustion` is `"dead_letter"`). Dead letter queue handling, retention policies, replay mechanisms, and pruning are defined in [ojs-dead-letter.md](./ojs-dead-letter.md).

---

## Appendix A: Backoff Formula Quick Reference

```
Given:
  n = retry number (1-indexed; retry 1 = attempt 2)
  I = initial_interval (in seconds)
  C = backoff_coefficient
  M = max_interval (in seconds)

Strategy: none
  delay(n) = I

Strategy: linear
  delay(n) = I * n

Strategy: exponential (default)
  delay(n) = I * C^(n - 1)

Strategy: polynomial
  delay(n) = I * n^C

Cap:
  effective_delay(n) = min(delay(n), M)

Jitter (when enabled):
  jittered_delay(n) = effective_delay(n) * random(0.5, 1.5)
  final_delay(n) = min(jittered_delay(n), M)
```

---

## Appendix B: Comparison with Prior Art Field Mapping

| OJS Field             | Temporal              | Sidekiq                   | Celery                | BullMQ            |
|-----------------------|-----------------------|---------------------------|-----------------------|-------------------|
| `max_attempts`        | `maximumAttempts`     | `retry` (integer)         | `max_retries` (+1)   | `attempts`        |
| `initial_interval`    | `initialInterval`     | implicit (15s + rand)     | `retry_backoff` (s)  | `backoff.delay`   |
| `backoff_coefficient` | `backoffCoefficient`  | implicit (^4)             | `retry_backoff`       | `backoff.type`    |
| `max_interval`        | `maximumInterval`     | implicit (~21 days)       | `retry_backoff_max`   | N/A               |
| `jitter`              | internal              | implicit (rand component) | `retry_jitter`        | N/A               |
| `non_retryable_errors`| `nonRetryableErrorTypes`| N/A                     | `autoretry_for` (inverse) | N/A           |
| `on_exhaustion`       | N/A (always persists) | implicit (dead set)       | N/A                   | `removeOnFail`    |

---

*Open Job Spec v1.0.0-rc.1 -- Retry Policy Specification*
*https://openjobspec.org*
