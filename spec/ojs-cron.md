# OJS Cron / Periodic Job Specification

**Open Job Spec v1.0.0-rc.1**

| Field       | Value                  |
|-------------|------------------------|
| Version     | 1.0.0-rc.1             |
| Date        | 2026-02-19             |
| Status      | Release Candidate      |
| Maturity    | Beta                   |
| Layer       | 1 (Core Specification) |
| Level       | 2 (Scheduled)          |

---

## 1. Overview

Cron jobs (also called periodic jobs, recurring jobs, or scheduled jobs) are jobs that execute on a repeating schedule. Every background job system surveyed during the design of OJS -- Sidekiq, BullMQ, Celery, Oban, Faktory, Asynq, River, Graphile Worker, Temporal, Inngest, Machinery, and Taskiq -- supports some form of cron or periodic scheduling. This universality makes cron a core capability rather than an optional extension.

This document defines the `CronJob` data structure, the cron expression syntax, timezone handling, overlap prevention policies, lifecycle management operations, leader election requirements for distributed deployments, and the events emitted by the cron subsystem.

### 1.1 Relationship to Other Specifications

- **ojs-core.md**: CronJobs produce standard OJS jobs. Each triggered occurrence creates a job that follows the standard job lifecycle (available, active, completed, retryable, discarded, etc.).
- **ojs-retry.md**: The `options.retry` field within a CronJob uses the standard OJS retry policy format.
- **ojs-http-binding.md**: Registration, listing, and removal endpoints are defined here and mapped to HTTP in the HTTP binding.
- **ojs-events.md**: This document defines cron-specific events (`cron.triggered`, `cron.skipped`) that extend the standard event vocabulary.

### 1.2 Terminology

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

---

## 2. CronJob Structure

A **CronJob** is a named, persistent registration that instructs the system to enqueue a job on a repeating schedule.

### 2.1 Complete CronJob Object

```json
{
  "name": "daily-report",
  "cron": "0 9 * * *",
  "timezone": "America/New_York",
  "type": "report.generate",
  "args": [{"report": "daily_summary"}],
  "options": {
    "queue": "reports",
    "timeout": 300,
    "retry": {
      "max_attempts": 3,
      "initial_interval": "PT30S",
      "backoff_coefficient": 2.0
    }
  },
  "overlap_policy": "skip",
  "enabled": true,
  "description": "Generate daily summary report at 9 AM ET"
}
```

### 2.2 Field Definitions

#### Required Fields

| Field  | Type   | Description |
|--------|--------|-------------|
| `name` | string | Unique identifier for this cron job registration. Used as the primary key for updates and removal. |
| `cron` | string | Cron expression defining the schedule. See Section 3 for syntax. |
| `type` | string | The OJS job type to enqueue on each occurrence. Dot-namespaced (e.g., `report.generate`, `cache.warm`). |

**`name` MUST be unique** across all registered cron jobs within an OJS deployment.

> **Rationale**: Without a unique name, there is no stable identifier for updating, toggling, or removing a cron registration. Every surveyed system (Oban's `@cron`, Sidekiq Enterprise's periodic jobs, Asynq's scheduler) uses a unique name or key for cron registrations. Duplicate names would create ambiguity about which schedule is authoritative.

**`name` MUST match the pattern `[a-z0-9][a-z0-9\-\.]*`** (lowercase alphanumeric, hyphens, and dots; must start with an alphanumeric character). Maximum length: 255 characters.

> **Rationale**: Consistent naming constraints prevent encoding issues across backends, allow names to be used safely in URLs (e.g., `DELETE /ojs/v1/cron/:name`), and match the queue naming convention already defined in ojs-core.md. Restricting to lowercase avoids case-sensitivity ambiguities across operating systems and databases.

**`cron` MUST be a valid cron expression** as defined in Section 3, or one of the special expressions defined in Section 4.

> **Rationale**: An invalid cron expression would result in a cron job that never fires or fires at unexpected times. Rejecting invalid expressions at registration time (fail-fast) prevents silent misconfiguration. Every surveyed system validates cron expressions at registration.

**`type` MUST be a valid OJS job type** following the dot-namespaced convention defined in ojs-core.md.

> **Rationale**: The `type` field is used to route triggered jobs to the correct handler. An invalid or unregistered type would produce jobs that no worker can process, silently filling queues with unprocessable work.

#### Optional Fields

| Field            | Type    | Default     | Description |
|------------------|---------|-------------|-------------|
| `args`           | array   | `[]`        | Arguments passed to each triggered job. JSON-native types only. |
| `timezone`       | string  | `"UTC"`     | IANA timezone name for schedule evaluation. See Section 5. |
| `options`        | object  | `{}`        | Job options applied to each triggered job (queue, timeout, retry, tags, etc.). |
| `overlap_policy` | string  | `"skip"`    | Behavior when a new occurrence fires while the previous run is still active. See Section 6. |
| `enabled`        | boolean | `true`      | Whether this cron job is active. Disabled cron jobs remain registered but do not fire. |
| `description`    | string  | `null`      | Human-readable description of what this cron job does. For documentation and dashboards. |

**`args` MUST be a JSON array** containing only JSON-native types (string, number, boolean, null, array, object).

> **Rationale**: OJS uses `args` (array) rather than `payload` (object) based on the research finding that Sidekiq's "simple types only" constraint is universally validated across all surveyed systems. The array format matches the standard job envelope defined in ojs-core.md. Using a different argument format for cron-triggered jobs versus directly-enqueued jobs would create inconsistency and require special handling in workers.

**`options` fields** are applied to each job created by the cron trigger. They follow the same schema as the `options` field in the standard `POST /ojs/v1/jobs` enqueue request. Supported fields include:

| Option Field | Type    | Description |
|-------------|---------|-------------|
| `queue`     | string  | Target queue for triggered jobs. Default: `"default"`. |
| `timeout`   | integer | Maximum execution time in seconds. |
| `retry`     | object  | Retry policy (see ojs-retry.md). |
| `tags`      | array   | String tags for filtering and observability. |
| `meta`      | object  | Extensible key-value metadata passed to each triggered job. |

#### System-Managed Fields (Read-Only)

These fields are set and maintained by the implementation. Clients MUST NOT set these fields during registration; implementations MUST ignore them if provided.

| Field         | Type      | Description |
|---------------|-----------|-------------|
| `last_run_at` | ISO 8601  | Timestamp of the most recent trigger. `null` if the cron job has never fired. |
| `next_run_at` | ISO 8601  | Timestamp of the next scheduled trigger, computed from the cron expression and timezone. `null` if the cron job is disabled. |
| `run_count`   | integer   | Total number of times this cron job has been triggered since registration. |
| `created_at`  | ISO 8601  | Timestamp of when the cron job was registered. |

> **Rationale**: System-managed fields provide essential observability. `next_run_at` lets operators verify schedules are correct without waiting for the next occurrence. `last_run_at` and `run_count` enable monitoring for missed triggers (if `last_run_at` is significantly before `next_run_at` minus the interval, something is wrong). `created_at` supports auditing.

Implementations MUST compute `next_run_at` on registration and update it after every trigger.

> **Rationale**: Without `next_run_at`, operators have no way to verify that a cron expression is interpreted correctly. Temporal and Oban both expose next-run information, and it is the most commonly requested feature for cron job observability.

---

## 3. Cron Expression Syntax

OJS uses the standard 5-field cron expression format with an optional 6th field for second-level precision.

### 3.1 Standard 5-Field Format

```
┌───────────── minute (0-59)
│ ┌───────────── hour (0-23)
│ │ ┌───────────── day of month (1-31)
│ │ │ ┌───────────── month (1-12 or JAN-DEC)
│ │ │ │ ┌───────────── day of week (0-7 or SUN-SAT, where both 0 and 7 represent Sunday)
│ │ │ │ │
* * * * *
```

| Field        | Allowed Values     | Allowed Special Characters |
|--------------|--------------------|---------------------------|
| Minute       | 0-59               | `*` `,` `-` `/`          |
| Hour         | 0-23               | `*` `,` `-` `/`          |
| Day of Month | 1-31               | `*` `,` `-` `/` `L` `W`  |
| Month        | 1-12 or JAN-DEC    | `*` `,` `-` `/`          |
| Day of Week  | 0-7 or SUN-SAT     | `*` `,` `-` `/` `L` `#`  |

### 3.2 Extended 6-Field Format (Optional Seconds)

Implementations MAY support a 6-field format where the first field represents seconds:

```
┌───────────── second (0-59)
│ ┌───────────── minute (0-59)
│ │ ┌───────────── hour (0-23)
│ │ │ ┌───────────── day of month (1-31)
│ │ │ │ ┌───────────── month (1-12 or JAN-DEC)
│ │ │ │ │ ┌───────────── day of week (0-7 or SUN-SAT)
│ │ │ │ │ │
* * * * * *
```

Implementations MUST distinguish between 5-field and 6-field expressions by counting the number of whitespace-separated tokens.

> **Rationale**: The 5-field format is the de facto standard used by POSIX cron, Oban, Sidekiq, and the vast majority of job systems. The 6-field extension for seconds is supported by Quartz (Java), Spring, and Asynq, and is necessary for sub-minute scheduling. Requiring implementations to distinguish by field count avoids ambiguity and matches existing practice.

When a 5-field expression is used, the seconds field is implicitly `0` (the job triggers at second 0 of the matching minute).

### 3.3 Special Characters

| Character | Name       | Description | Example |
|-----------|------------|-------------|---------|
| `*`       | Wildcard   | Matches every value in the field. | `* * * * *` = every minute |
| `,`       | List       | Specifies multiple values. | `1,15 * * * *` = minute 1 and 15 |
| `-`       | Range      | Specifies a range of values (inclusive). | `1-5 * * * *` = minutes 1 through 5 |
| `/`       | Step       | Specifies increments. | `*/15 * * * *` = every 15 minutes |
| `L`       | Last       | Last day of month (day-of-month field) or last specific weekday (day-of-week field). | `0 0 L * *` = midnight on last day of month |
| `W`       | Weekday    | Nearest weekday to the given day of month. | `0 0 15W * *` = nearest weekday to the 15th |
| `#`       | Nth        | Nth occurrence of a weekday in the month. | `0 0 * * 5#3` = third Friday of every month |

**Implementations MUST support** `*`, `,`, `-`, and `/` in all fields.

> **Rationale**: These four characters constitute the minimal cron syntax understood by every cron implementation surveyed. Without them, basic scheduling patterns (every N minutes, specific hours, ranges) are impossible. This aligns with POSIX cron syntax.

**Implementations SHOULD support** `L`, `W`, and `#` for day-of-month and day-of-week fields.

> **Rationale**: These extensions (from Quartz/Spring) enable common business scheduling patterns (last day of month, nearest weekday, third Friday) that are otherwise cumbersome to express. They are widely supported but not universal, making SHOULD appropriate.

### 3.4 Month and Day-of-Week Names

Implementations MUST accept both numeric values and three-letter English abbreviations (case-insensitive) for months and days of week.

> **Rationale**: Named values (`JAN`, `MON`) improve readability and reduce off-by-one errors. Both numeric and named forms are supported by POSIX cron and every surveyed implementation. Case-insensitivity prevents frustrating errors from capitalization differences.

**Month names**: JAN, FEB, MAR, APR, MAY, JUN, JUL, AUG, SEP, OCT, NOV, DEC

**Day-of-week names**: SUN, MON, TUE, WED, THU, FRI, SAT

Both `0` and `7` represent Sunday in the day-of-week field.

> **Rationale**: POSIX cron defines Sunday as 0, while some systems (Quartz, Vixie cron) also accept 7 as Sunday. Accepting both prevents a common source of misconfiguration.

### 3.5 Expression Validation

Implementations MUST validate cron expressions at registration time and reject invalid expressions with a `400 Bad Request` response and an `invalid_request` error code.

> **Rationale**: Deferring validation to trigger time would allow invalid cron jobs to persist silently, never firing, with no feedback to the operator. Fail-fast at registration is a principle followed by every surveyed system and prevents wasted operational cycles debugging why a cron job never runs.

The following MUST be treated as validation errors:

- Values outside the allowed range for a field (e.g., minute 60, month 13)
- Day-of-month values that are never valid (e.g., 32)
- Syntactically malformed expressions (unmatched ranges, invalid step values)
- Step value of 0 (e.g., `*/0`)
- Empty expression string

Implementations SHOULD warn (but MUST NOT reject) day-of-month values that are valid only in some months (e.g., 31 is valid for January but not February). The job simply does not fire in months where the day does not exist.

---

## 4. Special Expressions

In addition to standard cron syntax, implementations MUST support the following special expressions as aliases for common schedules:

| Expression                | Equivalent Cron | Description |
|--------------------------|-----------------|-------------|
| `@yearly` or `@annually` | `0 0 1 1 *`    | Once a year, midnight on January 1st |
| `@monthly`               | `0 0 1 * *`    | Once a month, midnight on the 1st |
| `@weekly`                | `0 0 * * 0`    | Once a week, midnight on Sunday |
| `@daily` or `@midnight`  | `0 0 * * *`    | Once a day, at midnight |
| `@hourly`                | `0 * * * *`    | Once an hour, at minute 0 |

> **Rationale**: These aliases are supported by Vixie cron, Go's `robfig/cron`, Oban, and most modern cron libraries. They eliminate common errors in writing expressions for standard intervals and improve readability. Mandating support (MUST) ensures portability -- a cron job registered with `@daily` on one implementation will work on any other.

### 4.1 Interval Expression: `@every <duration>`

Implementations SHOULD support the `@every <duration>` syntax for simple interval-based scheduling:

```
@every 30m       -- every 30 minutes
@every 2h        -- every 2 hours
@every 1h30m     -- every 1 hour and 30 minutes
@every 45s       -- every 45 seconds
@every 500ms     -- every 500 milliseconds
```

The duration format follows Go's `time.Duration` string representation:

| Unit | Suffix | Example |
|------|--------|---------|
| Milliseconds | `ms` | `500ms` |
| Seconds | `s` | `45s` |
| Minutes | `m` | `30m` |
| Hours | `h` | `2h` |

Durations can be combined: `1h30m`, `2h45m30s`.

> **Rationale**: Interval-based scheduling is fundamentally different from calendar-based cron expressions. It means "every N duration from the time of registration (or last trigger)," not "at specific clock times." Go's `robfig/cron` and Asynq support this syntax. It is particularly useful for health checks, cache warming, and sync operations where the exact clock time does not matter.

**Important distinction**: `@every 30m` fires every 30 minutes from the time the cron job was registered or last triggered. `*/30 * * * *` fires at minutes 0 and 30 of every hour regardless of when the cron job was registered. These are different behaviors.

Implementations that support `@every` MUST track the anchor time (registration time or last trigger time) and compute the next occurrence relative to it.

> **Rationale**: Without a defined anchor, the behavior of `@every` is ambiguous. Anchoring to registration/last-trigger time matches the behavior of Go's `robfig/cron` and Asynq, and produces the most intuitive result for operators expecting "every N time units."

---

## 5. Timezone Handling

### 5.1 IANA Timezone Names

The `timezone` field MUST use IANA timezone database names (also known as the tz database or Olson database).

> **Rationale**: IANA timezone names (e.g., `"America/New_York"`, `"Europe/London"`, `"Asia/Tokyo"`) are the only timezone representation that correctly encodes daylight saving time (DST) rules, historical timezone changes, and leap second handling. Every major programming language and operating system ships the IANA timezone database. Fixed UTC offsets like `"+05:00"` or abbreviations like `"EST"` do not encode DST transitions, leading to jobs firing at the wrong time twice a year. Every surveyed system that supports timezones (Oban, Sidekiq Enterprise, BullMQ, Asynq) uses IANA names.

Examples of valid timezone values:

```
"UTC"
"America/New_York"
"America/Los_Angeles"
"Europe/London"
"Europe/Berlin"
"Asia/Tokyo"
"Asia/Kolkata"
"Australia/Sydney"
"Pacific/Auckland"
```

Implementations MUST NOT accept:
- Fixed UTC offsets as timezone values (e.g., `"+05:00"`, `"-08:00"`, `"UTC+5"`)
- Ambiguous timezone abbreviations (e.g., `"EST"`, `"PST"`, `"CST"`)
- Non-IANA timezone names

> **Rationale for MUST NOT on offsets**: Fixed offsets are a frequent source of bugs. `"UTC-5"` does not account for Eastern Daylight Time. A cron job intended to fire at 9 AM Eastern would fire at 9 AM EST year-round, which is 10 AM EDT during summer. The IANA name `"America/New_York"` correctly handles this transition. By rejecting offsets at registration time, implementations force users to specify their intent correctly.

When `timezone` is omitted, implementations MUST default to `"UTC"`.

> **Rationale**: UTC is the only timezone with no DST transitions and no historical rule changes. It is the safest default and the most widely expected behavior for server-side scheduling.

### 5.2 Daylight Saving Time Transitions

Implementations MUST correctly handle DST transitions. This introduces two edge cases:

#### Spring Forward (Clock Jumps Ahead)

When clocks spring forward (e.g., 2:00 AM becomes 3:00 AM in `America/New_York` on the second Sunday of March), any cron job scheduled during the skipped hour MUST NOT fire during that transition.

For example, a cron job with expression `30 2 * * *` (2:30 AM daily) in `America/New_York`:
- On the spring-forward day, 2:30 AM does not exist. The job MUST NOT fire.
- On all other days, the job fires at 2:30 AM local time as expected.

> **Rationale**: Attempting to fire a job at a time that does not exist would require either inventing a substitute time (ambiguous) or firing at the UTC equivalent (violates the timezone intent). Skipping the non-existent occurrence is the behavior of POSIX cron, Oban, and Sidekiq Enterprise, and is the least surprising option.

#### Fall Back (Clock Falls Behind)

When clocks fall back (e.g., 2:00 AM becomes 1:00 AM in `America/New_York` on the first Sunday of November), any cron job scheduled during the repeated hour MUST fire exactly once.

For example, a cron job with expression `30 1 * * *` (1:30 AM daily) in `America/New_York`:
- On the fall-back day, 1:30 AM occurs twice (once in EDT, once in EST). The job MUST fire exactly once, during the first occurrence.

> **Rationale**: Firing twice would cause duplicate work. Firing during the first occurrence (the earlier wall-clock time) is the conventional behavior of POSIX cron and matches the principle of least surprise. Oban and Go's `robfig/cron` both adopt this approach.

### 5.3 Timezone Database Updates

Implementations SHOULD use the latest available IANA timezone database and SHOULD provide a mechanism to update the timezone database without restarting the service.

> **Rationale**: Governments change timezone rules with sometimes very little notice. An outdated timezone database can cause cron jobs to fire at incorrect times. Most operating systems and language runtimes update the tz database through system package updates.

---

## 6. Overlap Policies

An overlap occurs when a cron job's next scheduled occurrence arrives while the previous occurrence is still executing (state `active`). The `overlap_policy` field controls how the implementation handles this situation.

### 6.1 Policy Definitions

Implementations MUST support the following overlap policies:

#### `skip`

If the previous run is still active when the next occurrence is due, skip the new occurrence entirely. The cron job's `next_run_at` advances to the following scheduled time. A `cron.skipped` event MUST be emitted.

```json
{
  "overlap_policy": "skip"
}
```

**Behavior**: No new job is enqueued. The skipped occurrence is lost (not deferred). This is the safest default for idempotent operations where running twice would waste resources but not cause harm.

> **Rationale**: `skip` is the default because it prevents unbounded concurrency and resource exhaustion for long-running jobs. If a daily report takes 25 hours, `skip` prevents the system from launching a new report every day while the previous one is still running, which would compound the overload. Oban, Asynq, and Sidekiq Enterprise all default to skip behavior.

#### `allow`

Start a new run regardless of whether the previous run is still active. This permits concurrent executions of the same cron job.

```json
{
  "overlap_policy": "allow"
}
```

**Behavior**: A new job is enqueued unconditionally. Multiple instances of the same cron job may be executing simultaneously. Use this only when concurrent runs are safe and intended (e.g., stateless health checks, independent data pulls for different time windows).

#### `cancel_previous`

Cancel the currently active run and start a new one. The previous job transitions to the `cancelled` state.

```json
{
  "overlap_policy": "cancel_previous"
}
```

**Behavior**: The implementation MUST attempt to cancel the active job before (or concurrently with) enqueueing the new one. If the active job completes before the cancellation takes effect, the cancellation is a no-op and the new job proceeds normally. This policy is useful for "latest data wins" scenarios (e.g., a sync job where only the most recent run matters).

> **Rationale**: Some workloads are invalidated by newer data. A cache rebuild triggered every hour should cancel the previous rebuild if it is still running, because the new rebuild will produce fresher results. Temporal's `TERMINATE_IF_RUNNING` and BullMQ's `removeOnComplete` with re-enqueue pattern serve similar purposes.

#### `enqueue`

Enqueue the new run even if the previous run is still active, but do not allow concurrent execution. The new job waits in the queue and will be picked up by a worker after the previous run completes.

```json
{
  "overlap_policy": "enqueue"
}
```

**Behavior**: The new job enters the `available` state and waits for a worker. If the overlap persists across multiple occurrences, multiple jobs may accumulate in the queue. Implementations SHOULD log a warning when more than 2 queued occurrences of the same cron job exist.

> **Rationale**: This policy is appropriate for jobs where every occurrence must be processed but concurrent execution is unsafe (e.g., sequential database migrations, ordered report generation). The warning threshold prevents silent queue buildup.

### 6.2 Default Policy

When `overlap_policy` is omitted, implementations MUST default to `"skip"`.

> **Rationale**: `skip` is the safest default. It prevents resource exhaustion, avoids concurrent execution bugs, and matches the default behavior of Oban, Asynq, and Sidekiq Enterprise. A more permissive default would expose users to subtle concurrency issues in the common case.

### 6.3 Overlap Detection

To implement overlap policies other than `allow`, the implementation MUST track whether a cron-triggered job is currently in the `active` state.

Implementations MUST use the cron job `name` as the correlation key for overlap detection. When a cron job fires, the triggered job MUST include the cron job name in its metadata:

```json
{
  "metadata": {
    "cron_name": "daily-report",
    "cron_triggered_at": "2026-02-12T14:00:00Z"
  }
}
```

> **Rationale**: Without a correlation key, there is no way to determine which active jobs were triggered by a specific cron job. Using the cron job name (which is unique by definition) provides a stable, human-readable correlation. Including the trigger timestamp enables debugging of timing issues.

---

## 7. Leader Election

In distributed deployments where multiple OJS server instances are running, only one instance MUST be responsible for evaluating cron schedules and triggering jobs at any given time. This is the **cron leader**.

> **Rationale**: Without leader election, every server instance would independently evaluate cron expressions and trigger jobs, resulting in duplicate executions proportional to the number of instances. For a deployment with 5 server instances, a `@daily` cron job would fire 5 times per day. This is the most common cron-related bug in distributed systems.

### 7.1 Requirements

Implementations MUST ensure that at most one instance evaluates cron schedules at any given time.

> **Rationale**: The "at most one" guarantee is stronger than "exactly one." In the event of leader failure, it is acceptable (and safer) for no instance to evaluate cron schedules briefly, rather than risk two instances evaluating simultaneously. A short gap in cron evaluation is recoverable (the next tick will fire); duplicate firings are harder to detect and may cause data corruption.

Implementations MUST support automatic leader failover. If the current leader becomes unavailable, another instance MUST acquire leadership within a reasonable time bound (RECOMMENDED: within 30 seconds).

> **Rationale**: Without automatic failover, a leader crash would silently stop all cron jobs until manual intervention. The 30-second recommendation balances fast recovery against election chatter. Oban uses a 30-second leadership interval; River uses advisory locks with automatic re-acquisition.

### 7.2 Implementation Strategies

The spec does not mandate a specific leader election mechanism. Implementations MAY use any of the following:

- **Database advisory locks** (Postgres): `pg_advisory_lock` or `pg_try_advisory_lock`. Used by Oban and River.
- **Redis distributed locks**: `SET NX EX` with periodic renewal. Used by Sidekiq Enterprise and Asynq.
- **Consensus protocols**: Raft, etcd leases, or ZooKeeper ephemeral nodes. Appropriate for large-scale deployments.
- **External coordination**: Kubernetes leader election, HashiCorp Consul, etc.

Regardless of mechanism, the leader MUST periodically renew its leadership claim. If renewal fails (e.g., network partition, process pause), the leader MUST stop evaluating cron schedules and allow another instance to take over.

> **Rationale**: A leader that holds its claim indefinitely without renewal can become a "zombie leader" -- a process that believes it is the leader but is actually partitioned from the cluster. Periodic renewal with expiry is the standard pattern across all distributed lock implementations.

### 7.3 Cron Evaluation Loop

The cron leader MUST run an evaluation loop that:

1. Computes the next occurrence for each enabled cron job based on the current time and the cron expression.
2. For any cron job whose `next_run_at` is at or before the current time, evaluates the overlap policy and (if appropriate) enqueues a new job.
3. Updates `last_run_at`, `next_run_at`, and `run_count` for triggered cron jobs.
4. Sleeps until the next earliest `next_run_at` across all enabled cron jobs (or a maximum sleep interval, RECOMMENDED: 60 seconds).

Implementations MUST NOT evaluate cron schedules more frequently than once per second.

> **Rationale**: Sub-second cron evaluation is unnecessary (the finest granularity supported is 1 second with 6-field expressions) and wastes CPU. The maximum sleep interval of 60 seconds ensures that newly registered cron jobs are picked up within a reasonable time.

Implementations MUST handle clock skew and process pauses gracefully. If the evaluation loop wakes up and finds that multiple occurrences were missed (e.g., the leader was paused for 10 minutes), it MUST fire at most one catch-up occurrence per cron job and advance `next_run_at` to the next future occurrence.

> **Rationale**: Firing all missed occurrences after a pause would create a burst of jobs that could overwhelm workers. Firing exactly one catch-up occurrence ensures that the cron job "recovers" without creating a thundering herd. This matches the behavior of Vixie cron and systemd timers.

---

## 8. Registration, Listing, and Removal

### 8.1 Register a CronJob

**Operation**: Register a new cron job or update an existing one.

**HTTP Binding**: `POST /ojs/v1/cron`

**Request Body**:

```json
{
  "name": "daily-report",
  "cron": "0 9 * * *",
  "timezone": "America/New_York",
  "type": "report.generate",
  "args": [{"report": "daily_summary"}],
  "options": {
    "queue": "reports",
    "timeout": 300,
    "retry": {
      "max_attempts": 3,
      "initial_interval": "PT30S",
      "backoff_coefficient": 2.0
    }
  },
  "overlap_policy": "skip",
  "enabled": true,
  "description": "Generate daily summary report at 9 AM ET"
}
```

**Response** (`201 Created` for new registration, `200 OK` for update):

```json
{
  "cron_job": {
    "name": "daily-report",
    "cron": "0 9 * * *",
    "timezone": "America/New_York",
    "type": "report.generate",
    "args": [{"report": "daily_summary"}],
    "options": {
      "queue": "reports",
      "timeout": 300,
      "retry": {
        "max_attempts": 3,
        "initial_interval": "PT30S",
        "backoff_coefficient": 2.0
      }
    },
    "overlap_policy": "skip",
    "enabled": true,
    "description": "Generate daily summary report at 9 AM ET",
    "last_run_at": null,
    "next_run_at": "2026-02-13T14:00:00Z",
    "run_count": 0,
    "created_at": "2026-02-12T20:15:00Z"
  }
}
```

Implementations MUST use upsert semantics for registration: if a cron job with the given `name` already exists, its fields are updated. This enables declarative cron job management (register all cron jobs on application startup).

> **Rationale**: Upsert semantics match the pattern used by Oban (`@cron` module attribute), Sidekiq Enterprise (configuration hash), and Asynq (scheduler registration). Declarative registration -- where the application defines its full set of cron jobs on startup -- is the most robust pattern because it ensures cron jobs stay in sync with application code. Without upsert, implementations would need separate create/update endpoints, and application startup code would need to handle "already exists" errors.

### 8.2 List CronJobs

**Operation**: List all registered cron jobs.

**HTTP Binding**: `GET /ojs/v1/cron`

**Response** (`200 OK`):

```json
{
  "cron_jobs": [
    {
      "name": "daily-report",
      "cron": "0 9 * * *",
      "timezone": "America/New_York",
      "type": "report.generate",
      "args": [{"report": "daily_summary"}],
      "options": {
        "queue": "reports",
        "timeout": 300
      },
      "overlap_policy": "skip",
      "enabled": true,
      "description": "Generate daily summary report at 9 AM ET",
      "last_run_at": "2026-02-12T14:00:00Z",
      "next_run_at": "2026-02-13T14:00:00Z",
      "run_count": 42,
      "created_at": "2026-01-01T00:00:00Z"
    },
    {
      "name": "hourly-cleanup",
      "cron": "@hourly",
      "timezone": "UTC",
      "type": "maintenance.cleanup",
      "args": [],
      "options": {
        "queue": "maintenance",
        "timeout": 120
      },
      "overlap_policy": "skip",
      "enabled": true,
      "description": "Clean up expired sessions and temp files",
      "last_run_at": "2026-02-12T20:00:00Z",
      "next_run_at": "2026-02-12T21:00:00Z",
      "run_count": 1008,
      "created_at": "2026-01-01T00:00:00Z"
    }
  ],
  "count": 2
}
```

Implementations SHOULD support filtering by `enabled` status via query parameter: `GET /ojs/v1/cron?enabled=true`.

### 8.3 Get a CronJob

**Operation**: Retrieve a single cron job by name.

**HTTP Binding**: `GET /ojs/v1/cron/:name`

**Response** (`200 OK`):

```json
{
  "cron_job": {
    "name": "daily-report",
    "cron": "0 9 * * *",
    "timezone": "America/New_York",
    "type": "report.generate",
    "args": [{"report": "daily_summary"}],
    "options": {
      "queue": "reports",
      "timeout": 300
    },
    "overlap_policy": "skip",
    "enabled": true,
    "description": "Generate daily summary report at 9 AM ET",
    "last_run_at": "2026-02-12T14:00:00Z",
    "next_run_at": "2026-02-13T14:00:00Z",
    "run_count": 42,
    "created_at": "2026-01-01T00:00:00Z"
  }
}
```

If the cron job does not exist, implementations MUST return `404 Not Found` with a `not_found` error code.

### 8.4 Remove a CronJob

**Operation**: Unregister a cron job. Does not affect any currently active or queued jobs that were previously triggered by this cron job.

**HTTP Binding**: `DELETE /ojs/v1/cron/:name`

**Response** (`200 OK`):

```json
{
  "deleted": true,
  "name": "daily-report"
}
```

If the cron job does not exist, implementations MUST return `404 Not Found` with a `not_found` error code.

> **Rationale**: Returning 404 for a non-existent cron job (rather than 200) makes the operation non-idempotent, which some argue is wrong for DELETE. However, the 404 response provides valuable feedback: if an operator deletes a cron job that does not exist, they likely have a misconfiguration or are targeting the wrong deployment. Silent success would mask this error.

### 8.5 Toggle a CronJob

**Operation**: Enable or disable a cron job without removing its registration.

**HTTP Binding**: `PATCH /ojs/v1/cron/:name`

**Request Body**:

```json
{
  "enabled": false
}
```

**Response** (`200 OK`):

```json
{
  "cron_job": {
    "name": "daily-report",
    "enabled": false,
    "next_run_at": null
  }
}
```

When a cron job is disabled, `next_run_at` MUST be set to `null`.

> **Rationale**: Toggling is a common operational need: temporarily disabling a cron job during maintenance, debugging, or incident response, without losing the registration. A separate toggle operation (rather than requiring a full re-registration) is a UX improvement. Setting `next_run_at` to `null` provides clear signal that the cron job will not fire.

---

## 9. Events

The cron subsystem emits the following events. These events extend the standard OJS event vocabulary defined in ojs-events.md.

### 9.1 `cron.triggered`

Emitted when a cron job fires and a new job is enqueued.

```json
{
  "event": "cron.triggered",
  "timestamp": "2026-02-12T14:00:00.123Z",
  "data": {
    "cron_name": "daily-report",
    "cron_expression": "0 9 * * *",
    "timezone": "America/New_York",
    "job_id": "019501a2-3b4c-7d5e-8f6a-1b2c3d4e5f6a",
    "job_type": "report.generate",
    "run_count": 43,
    "scheduled_time": "2026-02-12T14:00:00Z",
    "actual_time": "2026-02-12T14:00:00.123Z"
  }
}
```

Implementations MUST emit a `cron.triggered` event every time a cron job successfully enqueues a new job.

> **Rationale**: This event is the primary observability signal for cron jobs. Without it, operators have no way to confirm that a cron job is firing as expected, short of checking the job queue. The `scheduled_time` vs. `actual_time` delta reveals evaluation lag. The `run_count` enables monitoring for missed triggers.

### 9.2 `cron.skipped`

Emitted when a cron job's occurrence is skipped due to overlap policy.

```json
{
  "event": "cron.skipped",
  "timestamp": "2026-02-12T14:00:00.456Z",
  "data": {
    "cron_name": "daily-report",
    "cron_expression": "0 9 * * *",
    "timezone": "America/New_York",
    "reason": "overlap_skip",
    "active_job_id": "019501a2-1111-2222-3333-444455556666",
    "scheduled_time": "2026-02-12T14:00:00Z"
  }
}
```

The `reason` field MUST be one of:

| Reason          | Description |
|-----------------|-------------|
| `overlap_skip`  | Previous run still active, overlap policy is `skip`. |
| `disabled`      | Cron job was disabled at evaluation time. |
| `dst_skip`      | Scheduled time does not exist due to DST spring-forward. |

Implementations MUST emit a `cron.skipped` event whenever a scheduled occurrence does not result in a new job being enqueued.

> **Rationale**: Skipped occurrences are invisible by default -- no job is created, no handler runs, no completion event fires. Without a skip event, operators cannot distinguish between "the cron job is working correctly and skipping overlaps" and "the cron job is broken and not firing." This is the most commonly requested observability improvement in cron systems.

---

## 10. Complete Examples

### 10.1 Daily Report at 9 AM Eastern

A report that generates every weekday morning, with retry on failure.

```json
{
  "name": "weekday-morning-report",
  "cron": "0 9 * * MON-FRI",
  "timezone": "America/New_York",
  "type": "report.generate",
  "args": [{"report": "daily_summary", "format": "pdf"}],
  "options": {
    "queue": "reports",
    "timeout": 600,
    "retry": {
      "max_attempts": 3,
      "initial_interval": "PT1M",
      "backoff_coefficient": 2.0,
      "max_interval": "PT10M"
    },
    "tags": ["reporting", "daily"]
  },
  "overlap_policy": "skip",
  "enabled": true,
  "description": "Generate PDF daily summary report at 9 AM ET on weekdays"
}
```

**Schedule interpretation**: Fires at 9:00 AM Eastern Time, Monday through Friday. During Eastern Daylight Time (March-November), this is 13:00 UTC. During Eastern Standard Time (November-March), this is 14:00 UTC. The implementation handles this transition automatically because the timezone is specified as `America/New_York`.

### 10.2 Hourly Cache Cleanup

A maintenance job that cleans up expired cache entries every hour.

```json
{
  "name": "cache-cleanup",
  "cron": "@hourly",
  "timezone": "UTC",
  "type": "maintenance.cache_cleanup",
  "args": [{"max_age_hours": 24, "batch_size": 1000}],
  "options": {
    "queue": "maintenance",
    "timeout": 120,
    "retry": {
      "max_attempts": 2,
      "initial_interval": "PT10S"
    }
  },
  "overlap_policy": "skip",
  "enabled": true,
  "description": "Remove expired cache entries older than 24 hours"
}
```

**Schedule interpretation**: Fires at minute 0 of every hour (equivalent to `0 * * * *`). Uses UTC because the operation is timezone-independent. The `skip` overlap policy ensures that if a cleanup takes longer than an hour, the next occurrence is skipped rather than piling up.

### 10.3 Every-30-Minutes Data Sync

A synchronization job that pulls data from an external API every 30 minutes.

```json
{
  "name": "external-data-sync",
  "cron": "*/30 * * * *",
  "timezone": "UTC",
  "type": "integration.sync",
  "args": [{"source": "api.partner.com", "endpoint": "/v2/orders"}],
  "options": {
    "queue": "integrations",
    "timeout": 900,
    "retry": {
      "max_attempts": 5,
      "initial_interval": "PT30S",
      "backoff_coefficient": 2.0,
      "max_interval": "PT5M"
    },
    "tags": ["integration", "partner-api"],
    "meta": {
      "partner_id": "partner_001",
      "sync_version": "2"
    }
  },
  "overlap_policy": "enqueue",
  "enabled": true,
  "description": "Sync order data from partner API every 30 minutes"
}
```

**Schedule interpretation**: Fires at minutes 0 and 30 of every hour. Uses the `enqueue` overlap policy because every sync run is important (to avoid data gaps), but concurrent runs could cause race conditions with the external API. If a sync takes longer than 30 minutes, the next occurrence waits in the queue.

### 10.4 Interval-Based Health Check

A health check that runs every 5 minutes, independent of clock alignment.

```json
{
  "name": "upstream-health-check",
  "cron": "@every 5m",
  "timezone": "UTC",
  "type": "monitoring.health_check",
  "args": [{"targets": ["db", "cache", "search", "storage"]}],
  "options": {
    "queue": "monitoring",
    "timeout": 30,
    "retry": {
      "max_attempts": 1
    }
  },
  "overlap_policy": "allow",
  "enabled": true,
  "description": "Check health of upstream dependencies every 5 minutes"
}
```

**Schedule interpretation**: Fires every 5 minutes from the time of registration. Unlike `*/5 * * * *` (which fires at minutes 0, 5, 10, ...), `@every 5m` fires at registration_time, registration_time + 5m, registration_time + 10m, etc. Uses `allow` overlap policy because health checks are stateless and concurrent execution is safe.

### 10.5 Last Day of Month Report

A billing report that runs on the last day of every month.

```json
{
  "name": "monthly-billing",
  "cron": "0 23 L * *",
  "timezone": "America/Chicago",
  "type": "billing.monthly_report",
  "args": [{"include_pending": true}],
  "options": {
    "queue": "billing",
    "timeout": 3600,
    "retry": {
      "max_attempts": 3,
      "initial_interval": "PT5M",
      "backoff_coefficient": 2.0
    },
    "tags": ["billing", "monthly"]
  },
  "overlap_policy": "cancel_previous",
  "enabled": true,
  "description": "Generate monthly billing report at 11 PM CT on the last day of each month"
}
```

**Schedule interpretation**: Fires at 11:00 PM Central Time on the last day of each month (the `L` special character). Uses `cancel_previous` because if the report is still running when the next month's deadline arrives (this should never happen, but defensive programming), the old run should be abandoned in favor of the new one.

---

## 11. Prior Art

The cron specification draws from the following systems and standards:

| System / Standard | Key Influence |
|-------------------|---------------|
| **POSIX cron / Vixie cron** | 5-field expression format, DST handling behavior (skip on spring-forward, fire once on fall-back), special expressions (`@daily`, `@hourly`, etc.). |
| **Oban (Elixir)** | Cron plugin architecture, overlap policies (`unique` option for cron jobs), leader election via advisory locks, declarative cron registration on application startup. |
| **Sidekiq Enterprise (Ruby)** | Periodic job configuration hash, leader-based scheduling, IANA timezone support, smart handling of DST transitions. |
| **Asynq (Go)** | `@every` interval syntax, scheduler with Redis-based leader election, cron job registration API, seconds-level cron expressions. |
| **BullMQ (JavaScript)** | Repeatable jobs with cron expressions, timezone support, overlap prevention via unique job keys. |
| **Quartz (Java)** | 6-field (with seconds) and 7-field (with year) cron expressions, `L`, `W`, `#` special characters, extensive timezone handling. |
| **Spring Framework** | `@Scheduled` annotation, cron expression parsing with seconds field, timezone parameter. |
| **Go robfig/cron** | `@every` duration syntax, 5/6-field auto-detection, parser options for seconds and descriptors. |
| **Temporal (Polyglot)** | Schedule concept with overlap policies (skip, buffer_one, buffer_all, cancel_other, terminate_other, allow_all), jitter, pause/unpause. |
| **systemd timers** | Calendar event expressions, catch-up behavior after missed triggers (fire at most once), persistent timer state across reboots. |

Every system surveyed supports cron or periodic job scheduling, confirming its status as a universal requirement for background job processing. The OJS cron specification standardizes the common patterns while explicitly defining the edge cases (DST, overlap, leader election) that most systems handle inconsistently or leave unspecified.

---

## 12. Conformance Requirements Summary

This section summarizes all normative requirements for quick reference.

### MUST Requirements

| ID | Requirement | Section |
|----|-------------|---------|
| CRON-01 | CronJob `name` MUST be unique within a deployment | 2.2 |
| CRON-02 | CronJob `name` MUST match `[a-z0-9][a-z0-9\-\.]*` | 2.2 |
| CRON-03 | `cron` field MUST be a valid expression or special expression | 2.2 |
| CRON-04 | `type` MUST follow OJS dot-namespaced convention | 2.2 |
| CRON-05 | `args` MUST be a JSON array | 2.2 |
| CRON-06 | System-managed fields MUST be ignored if provided by client | 2.2 |
| CRON-07 | `next_run_at` MUST be computed on registration and after every trigger | 2.2 |
| CRON-08 | Implementations MUST distinguish 5-field from 6-field by token count | 3.2 |
| CRON-09 | `*`, `,`, `-`, `/` MUST be supported in all cron fields | 3.3 |
| CRON-10 | Month and day-of-week names MUST be accepted (case-insensitive) | 3.4 |
| CRON-11 | Invalid cron expressions MUST be rejected at registration time | 3.5 |
| CRON-12 | Standard special expressions (`@daily`, etc.) MUST be supported | 4 |
| CRON-13 | `timezone` MUST use IANA timezone database names | 5.1 |
| CRON-14 | Fixed UTC offsets and abbreviations MUST NOT be accepted as timezone | 5.1 |
| CRON-15 | Default timezone MUST be `"UTC"` | 5.1 |
| CRON-16 | DST spring-forward: jobs in skipped hours MUST NOT fire | 5.2 |
| CRON-17 | DST fall-back: jobs in repeated hours MUST fire exactly once | 5.2 |
| CRON-18 | All four overlap policies MUST be supported | 6.1 |
| CRON-19 | Default overlap policy MUST be `"skip"` | 6.2 |
| CRON-20 | Cron-triggered jobs MUST include `cron_name` in metadata | 6.3 |
| CRON-21 | At most one instance MUST evaluate cron schedules at a time | 7.1 |
| CRON-22 | Automatic leader failover MUST be supported | 7.1 |
| CRON-23 | Leader MUST periodically renew its leadership claim | 7.2 |
| CRON-24 | Cron evaluation MUST NOT occur more than once per second | 7.3 |
| CRON-25 | Missed occurrences MUST fire at most once on catch-up | 7.3 |
| CRON-26 | Registration MUST use upsert semantics | 8.1 |
| CRON-27 | Removal of non-existent cron job MUST return 404 | 8.4 |
| CRON-28 | Disabled cron job `next_run_at` MUST be `null` | 8.5 |
| CRON-29 | `cron.triggered` event MUST be emitted on successful trigger | 9.1 |
| CRON-30 | `cron.skipped` event MUST be emitted on skipped occurrence | 9.2 |

### SHOULD Requirements

| ID | Requirement | Section |
|----|-------------|---------|
| CRON-S01 | `L`, `W`, `#` special characters SHOULD be supported | 3.3 |
| CRON-S02 | `@every <duration>` SHOULD be supported | 4.1 |
| CRON-S03 | Latest IANA timezone database SHOULD be used | 5.3 |
| CRON-S04 | Warning when >2 queued occurrences exist (enqueue policy) | 6.1 |
| CRON-S05 | Leader failover SHOULD complete within 30 seconds | 7.1 |
| CRON-S06 | Filtering by `enabled` status SHOULD be supported in list | 8.2 |

---

*Open Job Spec v1.0.0-rc.1 -- Cron / Periodic Job Specification*
*https://openjobspec.org*
