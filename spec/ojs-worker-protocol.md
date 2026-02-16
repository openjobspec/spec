# Open Job Spec -- Worker Lifecycle and Coordination Protocol

**OJS Layer 3: Worker Protocol**

| Field        | Value                                    |
|--------------|------------------------------------------|
| **Version**  | 1.0.0-rc.1                               |
| **Date**     | 2025-06-01                               |
| **Status**   | Release Candidate                        |
| **Maturity** | Beta                                     |
| **Layer**    | 3 (Worker Protocol)                      |
| **Requires** | OJS Core Specification (Layer 1), OJS JSON Wire Format (Layer 2) |
| **License**  | Apache 2.0                               |

---

## 1. Introduction

This document defines the **worker lifecycle and coordination protocol** for Open Job
Spec (OJS). It specifies how workers register with a backend, receive and process jobs,
report health via heartbeats, and shut down gracefully without losing work.

This specification is part of the OJS three-tier architecture:

- **Layer 1 -- Core Specification**: Defines what a job IS (attributes, lifecycle, operations).
- **Layer 2 -- Wire Format Encodings**: Defines how a job is SERIALIZED (JSON, etc.).
- **Layer 3 -- Protocol Bindings and Worker Protocol**: Defines how jobs are TRANSMITTED and how workers COORDINATE with the backend (this document).

### 1.1 Scope

This specification covers:

- Worker lifecycle states and transitions
- Worker registration and deregistration
- Heartbeat protocol for health monitoring and server-initiated state changes
- Visibility timeout and reservation semantics for crash recovery
- Job claiming (FETCH) semantics
- Graceful shutdown procedures
- Concurrency model
- Signal handling conventions
- Dead worker detection and job recovery

This specification does NOT cover:

- Transport-level details (HTTP, gRPC, WebSocket) -- those are defined in transport-specific protocol binding documents.
- Job envelope format -- that is defined in the OJS JSON Wire Format (Layer 2).
- Job lifecycle states (available, active, completed, etc.) -- those are defined in the Core Specification (Layer 1).

### 1.2 Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD",
"SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this
document are to be interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt)
and [RFC 8174](https://www.ietf.org/rfc/rfc8174.txt).

### 1.3 Terminology

| Term                  | Definition                                                                       |
|-----------------------|----------------------------------------------------------------------------------|
| **Worker**            | A process that fetches and executes jobs from one or more queues.                |
| **Backend**           | The server-side component that stores jobs, manages queues, and coordinates workers. |
| **Heartbeat**         | A periodic message from a worker to the backend indicating liveness.             |
| **Visibility timeout**| The duration a job remains reserved for a worker before being automatically requeued. |
| **Grace period**      | The maximum time a worker waits for active jobs to complete during shutdown.      |
| **Reservation**       | The exclusive claim a worker holds on a job while processing it.                 |

---

## 2. Worker Lifecycle States

### 2.1 State Definitions

A worker process exists in exactly one of three operational states at any given time:

| State         | Description                                                                                               |
|---------------|-----------------------------------------------------------------------------------------------------------|
| **running**   | The worker is actively fetching new jobs from the backend and processing them. This is the normal operating state. |
| **quiet**     | The worker has stopped fetching new jobs but continues processing any jobs currently active. Used during graceful shutdown or rolling deployments. |
| **terminate** | The worker is finishing active jobs within a bounded grace period and will exit when the grace period expires or all active jobs complete, whichever comes first. |

After the worker process exits, its final state is **terminated** (process no longer exists).

Workers MUST track their current lifecycle state and report it in every heartbeat
request.

**Rationale**: A worker MUST track its state because the backend relies on accurate
state reporting to make scheduling decisions. If the backend believes a worker is
`running` when it is actually `quiet`, it may route jobs to a worker that will never
fetch them, causing increased latency and potential starvation of queued work.

### 2.2 State Transition Diagram

```
                  +---------+
                  | running |
                  +----+----+
                       |
          +------------+------------+
          |                         |
   SIGTSTP / heartbeat       SIGTERM / heartbeat
   response "quiet"          response "terminate"
          |                         |
          v                         v
     +----+----+              +-----+-----+
     |  quiet  +------------->| terminate |
     +---------+  SIGTERM /   +-----+-----+
                  heartbeat         |
                  response          | grace period expires
                  "terminate"       | or all jobs complete
                                    v
                              +-----+------+
                              | terminated |
                              | (exited)   |
                              +------------+
```

### 2.3 State Transitions

The following table enumerates all valid state transitions:

| From        | To          | Trigger                                                   |
|-------------|-------------|-----------------------------------------------------------|
| running     | quiet       | Server sends `"quiet"` in heartbeat response, or worker receives `SIGTSTP` |
| running     | terminate   | Server sends `"terminate"` in heartbeat response, or worker receives `SIGTERM` |
| quiet       | terminate   | Server sends `"terminate"` in heartbeat response, or worker receives `SIGTERM` |
| quiet       | running     | Worker receives `SIGCONT` signal (resume after quiet)     |
| terminate   | terminated  | All active jobs complete, or grace period expires         |

Workers MUST NOT transition backward from `terminate` to `quiet` or `running`.

**Rationale**: Allowing backward transitions from `terminate` would create race
conditions between shutdown logic already in progress and resumed fetch loops.
Once a worker has committed to shutting down, the only safe direction is forward
to process exit. Faktory and Sidekiq enforce this same irreversibility.

Workers MUST NOT transition directly from `terminated` to any other state. A new
worker process MUST be started instead.

**Rationale**: Process-level state (file descriptors, thread pools, database
connections) cannot be reliably restored after shutdown. Requiring a fresh process
avoids an entire category of resource-leak bugs.

---

## 3. Worker Registration

### 3.1 Registration on Startup

Workers SHOULD register with the backend on startup, before beginning to fetch jobs.

**Rationale**: Registration is SHOULD (not MUST) because lightweight implementations
may rely solely on heartbeats for worker discovery. However, explicit registration
enables the backend to immediately track the worker in its UI and to pre-validate
the worker's queue subscriptions and labels.

Registration MUST include the following fields:

| Field          | Type            | Required | Description                                          |
|----------------|-----------------|----------|------------------------------------------------------|
| `worker_id`    | string          | Yes      | Globally unique worker identifier (UUIDv7 RECOMMENDED) |
| `hostname`     | string          | Yes      | Machine hostname where the worker is running         |
| `pid`          | integer         | Yes      | Operating system process ID                          |
| `queues`       | array of string | Yes      | Ordered list of queues this worker subscribes to     |
| `concurrency`  | integer         | Yes      | Maximum number of jobs this worker processes in parallel |
| `labels`       | array of string | No       | Arbitrary labels for filtering and grouping (e.g., `["canary", "v2.1"]`) |
| `started_at`   | string          | No       | ISO 8601 / RFC 3339 timestamp of worker process start |

Workers MUST generate a unique `worker_id` for each process instance.

**Rationale**: A unique `worker_id` per process is essential for the backend to
distinguish between different incarnations of a worker on the same host. If a
worker crashes and restarts, reusing the same ID would cause the backend to
conflate the old (dead) worker's state with the new worker's state, potentially
leading to incorrect job requeue decisions and phantom heartbeat failures.

### 3.2 Registration Example

```json
{
  "worker_id": "worker_019539a4-b68c-7def",
  "hostname": "web-server-1",
  "pid": 12345,
  "queues": ["email", "default"],
  "concurrency": 10,
  "labels": ["canary", "v2.1"],
  "started_at": "2025-06-01T08:00:00Z"
}
```

### 3.3 Registration Response

The backend SHOULD respond to a successful registration with:

```json
{
  "ok": true,
  "server_time": "2025-06-01T08:00:00.123Z",
  "heartbeat_interval": 5,
  "heartbeat_timeout": 30,
  "visibility_timeout_default": 1800
}
```

| Field                       | Type    | Description                                                |
|-----------------------------|---------|------------------------------------------------------------|
| `ok`                        | boolean | Whether registration was accepted                          |
| `server_time`               | string  | Current server time (RFC 3339) for clock drift detection   |
| `heartbeat_interval`        | integer | Recommended heartbeat interval in seconds                  |
| `heartbeat_timeout`         | integer | Seconds after which a missing heartbeat marks worker dead  |
| `visibility_timeout_default`| integer | Default visibility timeout in seconds for reserved jobs    |

### 3.4 Deregistration

Workers SHOULD deregister from the backend during graceful shutdown, after all
active jobs have completed or been failed.

**Rationale**: Explicit deregistration allows the backend to immediately remove
the worker from its active set rather than waiting for heartbeat timeout. This
reduces the window during which the backend might attempt to route work to a
worker that will never claim it.

---

## 4. Heartbeat Protocol (BEAT)

### 4.1 Purpose

The heartbeat protocol serves two critical functions:

1. **Liveness detection**: The backend uses heartbeats to determine which workers are
   alive and capable of processing jobs.
2. **Server-initiated state changes**: The heartbeat response is the mechanism by which
   the backend instructs workers to transition to `quiet` or `terminate` states.

### 4.2 Heartbeat Request

Workers MUST send heartbeats to the backend at regular intervals.

**Rationale**: Heartbeats are the only reliable mechanism for the backend to distinguish
between a slow worker and a dead worker. Without heartbeats, the backend cannot
determine whether a worker holding reserved jobs has crashed (requiring requeue) or
is simply taking a long time to process. Every production job system -- Faktory, Sidekiq,
Temporal, Oban -- requires heartbeats for exactly this reason.

The default heartbeat interval is **5 seconds**. Implementations MAY use a different
interval but MUST document it.

**Rationale**: 5 seconds balances detection speed against overhead. Faktory uses 15
seconds; Temporal uses 5-60 seconds depending on activity type. A 5-second default
means the backend can detect a dead worker within 30 seconds (6 missed beats), which
is fast enough for most workloads without creating excessive network traffic. At 5
seconds per beat, a fleet of 1,000 workers generates only 200 requests per second --
negligible for any backend.

A heartbeat request MUST include the following fields:

| Field             | Type            | Required | Description                                         |
|-------------------|-----------------|----------|-----------------------------------------------------|
| `worker_id`       | string          | Yes      | The worker's unique identifier                      |
| `state`           | string          | Yes      | Current lifecycle state: `"running"`, `"quiet"`, or `"terminate"` |
| `active_jobs`     | integer         | Yes      | Number of jobs currently being processed            |
| `active_job_ids`  | array of string | Yes      | IDs of all jobs currently being processed           |
| `started_at`      | string          | No       | Worker start time (RFC 3339)                        |
| `hostname`        | string          | No       | Machine hostname                                    |
| `pid`             | integer         | No       | Operating system process ID                         |
| `queues`          | array of string | No       | Queues this worker is subscribed to                 |
| `concurrency`     | integer         | No       | Worker's concurrency setting                        |
| `labels`          | array of string | No       | Worker labels                                       |

Workers MUST include `active_job_ids` in every heartbeat.

**Rationale**: Reporting active job IDs is essential for the backend to perform
accurate dead-worker recovery. When a worker dies without deregistering, the backend
must know exactly which jobs were in-flight so it can requeue them. Without this
information, the backend would need to scan all active jobs and cross-reference
reservation ownership -- a significantly more expensive operation, especially under
the high-load conditions that often accompany worker failures.

### 4.3 Heartbeat Request Example

```json
{
  "worker_id": "worker_019539a4-b68c-7def",
  "state": "running",
  "active_jobs": 5,
  "active_job_ids": ["job_1", "job_2", "job_3", "job_4", "job_5"],
  "started_at": "2025-06-01T08:00:00Z",
  "hostname": "web-server-1",
  "pid": 12345,
  "queues": ["email", "default"],
  "concurrency": 10,
  "labels": ["canary", "v2.1"]
}
```

### 4.4 Heartbeat Response

The backend MUST respond to every heartbeat with a JSON object containing at minimum
a `state` field.

**Rationale**: The heartbeat response is the server's only reliable channel for
instructing a worker to change state. Unlike signals (which require SSH access or
orchestrator integration), heartbeat responses work across network boundaries, through
load balancers, and in containerized environments where direct signal delivery is
impractical. Faktory's BEAT command uses this exact pattern -- the server responds
with a state string that the worker must honor.

| Field         | Type   | Required | Description                                          |
|---------------|--------|----------|------------------------------------------------------|
| `state`       | string | Yes      | Desired worker state: `"running"`, `"quiet"`, or `"terminate"` |
| `server_time` | string | No       | Current server time (RFC 3339) for clock synchronization |

Workers MUST transition to the state specified in the heartbeat response if it
differs from their current state, subject to the valid transitions defined in
Section 2.3.

**Rationale**: Workers MUST honor server-directed state changes because the backend
has a global view of the system that individual workers lack. During a rolling
deployment, the backend can selectively quiet workers in a controlled sequence. If
workers could ignore state directives, the backend would lose the ability to
orchestrate fleet-wide operations, forcing operators to rely on external tooling
(SSH, Kubernetes signals) for what should be a first-class protocol capability.

### 4.5 Heartbeat Response Examples

Normal operation -- server confirms the worker should keep running:

```json
{
  "state": "running",
  "server_time": "2025-06-01T10:30:00Z"
}
```

Server requests the worker to stop fetching new jobs:

```json
{
  "state": "quiet"
}
```

Server requests the worker to begin termination:

```json
{
  "state": "terminate"
}
```

### 4.6 Heartbeat Failure Handling

If a heartbeat request fails (network error, server error), the worker MUST continue
operating in its current state and retry the heartbeat at the next interval.

**Rationale**: A transient network partition or server restart should not cause a
healthy worker to stop processing jobs. The heartbeat is a best-effort signal; the
worker's local state is authoritative until the backend explicitly overrides it. This
resilience is critical in production environments where brief network disruptions are
common.

Workers SHOULD log heartbeat failures at a warning level.

Workers SHOULD NOT change their lifecycle state based on heartbeat failures alone.
Only explicit server directives (heartbeat responses) or OS signals trigger state
transitions.

---

## 5. Visibility Timeout and Reservation Semantics

### 5.1 Reservation Model

When a worker claims a job via FETCH (Section 6), the job transitions from the
`available` state to the `active` state. At this point, the job is **reserved**
for the claiming worker with a **visibility timeout**.

The visibility timeout defines the maximum duration a job may remain in the `active`
state without being acknowledged (ACK) or failed (FAIL). If the timeout expires before
the worker reports an outcome, the backend MUST automatically return the job to the
`available` state for another worker to claim.

**Rationale**: Visibility timeout is the fundamental mechanism for preventing job loss
when workers crash. Without it, a job claimed by a crashed worker would remain in the
`active` state indefinitely -- effectively lost. Every production-grade job system
implements some form of reservation timeout: SQS calls it "visibility timeout," Faktory
calls it "reserve_for," and Oban uses a "rescue" mechanism. The term "visibility timeout"
is used here because it is the most widely recognized term, originating from Amazon SQS.

### 5.2 Default Visibility Timeout

The default visibility timeout is **1800 seconds** (30 minutes).

**Rationale**: 30 minutes matches Faktory's default `reserve_for` and is long enough
for the vast majority of background jobs (email sending, image processing, data exports)
while short enough that crashed-worker recovery happens within a reasonable timeframe.
Jobs that require longer execution times can specify a custom `visibility_timeout`
in their envelope.

### 5.3 Per-Job Visibility Timeout

Jobs MAY specify a custom visibility timeout via the `visibility_timeout` field in the
job envelope (defined in OJS JSON Wire Format, Section 3.1):

```json
{
  "specversion": "1.0",
  "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
  "type": "video.transcode",
  "queue": "media",
  "args": ["video_abc123", "1080p"],
  "visibility_timeout": 7200
}
```

This job has a 2-hour visibility timeout, overriding the default 30 minutes.

### 5.4 Visibility Timeout Extension (Heartbeat from Handler)

Workers MAY extend the visibility timeout for a job that is still being processed.
This is accomplished by reporting the job's ID in the `active_job_ids` field of the
heartbeat request.

When the backend receives a heartbeat that includes a job ID in `active_job_ids`, it
SHOULD reset that job's visibility timeout to the full configured duration (default
or per-job), counted from the time the heartbeat is received.

**Rationale**: Long-running jobs (video transcoding, large data exports, ML inference)
may legitimately exceed the default visibility timeout. Rather than requiring producers
to predict the exact execution time and set an enormous timeout (which delays crash
recovery), workers can extend the timeout incrementally. This is the same pattern
Temporal uses for activity heartbeats -- long-running activities call
`ctx.heartbeat()` periodically to signal liveness without committing to a fixed
maximum duration.

Implementations SHOULD provide a mechanism in the job handler context for explicitly
extending the visibility timeout. For example:

```python
# Python example
async def handle_video_transcode(ctx, video_id, resolution):
    for chunk in video.chunks():
        process(chunk)
        await ctx.heartbeat()  # extends visibility timeout
```

```go
// Go example
func HandleVideoTranscode(ctx ojs.Context, videoID string, resolution string) error {
    for chunk := range video.Chunks() {
        process(chunk)
        ctx.Heartbeat()  // extends visibility timeout
    }
    return nil
}
```

### 5.5 Visibility Timeout Expiration

When a job's visibility timeout expires:

1. The backend MUST transition the job from `active` back to `available`.
2. The backend MUST increment the job's `attempt` counter.
3. The backend MUST record an error in the job's `errors` array with type
   `"visibility_timeout"`.
4. The backend MUST respect the job's retry policy -- if the maximum number of
   attempts has been reached, the job transitions to `discarded` instead of
   `available`.

**Rationale**: Each of these steps is MUST because they collectively maintain the
invariants that (a) no job is silently lost, (b) the attempt counter accurately
reflects reality, (c) operators have visibility into timeout events via the error
log, and (d) jobs are not retried beyond their configured limits. Omitting any one
of these steps creates a correctness gap: without (1), jobs are lost; without (2),
retry limits are not enforced; without (3), timeouts are invisible to operators;
without (4), jobs retry infinitely.

### 5.6 Reservation Ownership

A job's reservation is bound to a specific `worker_id`. Only the worker that claimed
the job MAY acknowledge (ACK) or fail (FAIL) it.

The backend MUST reject ACK or FAIL requests from a worker that does not hold the
reservation.

**Rationale**: Reservation ownership prevents a race condition where a crashed
worker's job is requeued and claimed by Worker B, and then the original (recovered)
Worker A attempts to ACK the same job. Without ownership checks, Worker A's ACK
would incorrectly mark Worker B's in-progress execution as complete.

---

## 6. Job Claiming (FETCH) Semantics

### 6.1 FETCH Operation

FETCH is the operation by which a worker claims one or more jobs from the backend.
Implementations MAY realize FETCH as a blocking long-poll, a non-blocking poll, or
a server-push mechanism, depending on the transport binding.

### 6.2 FETCH Request

A FETCH request MUST include:

| Field    | Type            | Required | Description                                          |
|----------|-----------------|----------|------------------------------------------------------|
| `queues` | array of string | Yes      | Ordered list of queues to fetch from (highest priority first) |
| `count`  | integer         | No       | Number of jobs to fetch (default: 1)                 |

Workers MUST specify at least one queue in the `queues` field.

**Rationale**: Explicit queue specification prevents a worker from accidentally
consuming jobs it is not configured to handle. This is especially important in
multi-tenant or multi-service environments where different workers are responsible
for different job types, and a misconfigured worker draining the wrong queue could
cause cascading failures.

### 6.3 Queue Priority

Queues in the `queues` array are ordered by priority: the first queue has the highest
priority. The backend SHOULD attempt to fetch jobs from higher-priority queues first.

**Rationale**: Queue-level priority ordering gives operators a simple, declarative
way to express processing preferences. A worker configured with `["critical", "default",
"bulk"]` will naturally drain the `critical` queue before servicing `default` or `bulk`,
without requiring job-level priority fields on every envelope.

### 6.4 Atomic Claiming

The backend MUST atomically transition jobs from `available` to `active` during a
FETCH operation. No two workers may claim the same job.

**Rationale**: Atomic claiming is the foundation of exactly-once delivery semantics
(more precisely, at-least-once with deduplication). If two workers could claim the
same job, the system would silently produce duplicate work -- a correctness violation
that is extremely difficult to detect and debug in production. The MUST requirement
reflects the severity of this failure mode.

Recommended implementation strategies:

- **PostgreSQL**: `SELECT ... FOR UPDATE SKIP LOCKED` within a transaction. The
  `SKIP LOCKED` clause ensures that concurrent FETCH requests do not block each other;
  each worker gets a different set of jobs. This is the approach used by Oban, GoodJob,
  and Solid Queue.

- **Redis**: `BLMOVE` (blocking list move) from the queue list to a worker-specific
  processing list. This provides atomic pop-and-push semantics. Sidekiq and Faktory
  use Redis list operations for job claiming.

- **MySQL**: `SELECT ... FOR UPDATE SKIP LOCKED` (available since MySQL 8.0). Similar
  to PostgreSQL but with MySQL-specific transaction semantics.

### 6.5 FETCH Response

A successful FETCH response MUST return an array of job envelopes as defined in the
OJS JSON Wire Format (Layer 2). Each returned job MUST have:

- `state` set to `"active"`
- A visibility timeout countdown started by the backend

```json
{
  "jobs": [
    {
      "specversion": "1.0",
      "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
      "type": "email.send",
      "queue": "email",
      "args": ["user@example.com", "welcome"],
      "state": "active",
      "attempt": 1,
      "created_at": "2025-06-01T08:55:00.000Z",
      "enqueued_at": "2025-06-01T09:00:00.123Z",
      "started_at": "2025-06-01T09:00:01.456Z"
    }
  ]
}
```

If no jobs are available, the backend MUST return an empty array (not an error):

```json
{
  "jobs": []
}
```

### 6.6 FETCH Behavior by Worker State

| Worker State | FETCH Behavior                                                    |
|--------------|-------------------------------------------------------------------|
| running      | Worker actively fetches jobs at its configured polling interval.  |
| quiet        | Worker MUST NOT issue new FETCH requests.                         |
| terminate    | Worker MUST NOT issue new FETCH requests.                         |

Workers MUST stop fetching when transitioning out of the `running` state.

**Rationale**: A `quiet` or `terminate` worker that continues to fetch jobs would
accumulate work it may not be able to complete, increasing the volume of jobs that
must be requeued during shutdown and degrading overall system throughput.

---

## 7. Graceful Shutdown Sequence

### 7.1 Overview

Graceful shutdown ensures that active jobs are not lost when a worker process exits.
The sequence is designed to complete as much in-flight work as possible before the
process terminates.

### 7.2 Shutdown Steps

The graceful shutdown sequence proceeds as follows:

1. **Trigger received**: The worker receives a shutdown signal (`SIGTERM`) or a
   heartbeat response with `state: "terminate"`.

2. **Stop fetching**: The worker MUST immediately stop issuing FETCH requests.

   **Rationale**: Stopping fetch is MUST because every new job claimed after the
   shutdown signal increases the risk of incomplete work and forced requeue. The
   sooner fetching stops, the more time remains for completing already-active jobs.

3. **Transition to `terminate` state**: The worker MUST update its internal state
   and report `"terminate"` in subsequent heartbeats.

4. **Wait for active jobs**: The worker MUST wait for currently active jobs to
   complete, up to the configured grace period.

   **Rationale**: Waiting is MUST (not SHOULD) because prematurely killing active
   jobs causes work to be wasted and repeated. In systems processing expensive
   operations (video transcoding, large data exports), abandoned partial work
   represents significant resource waste.

5. **Grace period expiration**: If any jobs remain active after the grace period:

   a. The worker SHOULD send a FAIL for each remaining job with error type
      `"shutdown"` and a descriptive message.

      **Rationale**: Explicit FAIL is SHOULD (not MUST) because the worker may
      not be able to communicate with the backend if the grace period was triggered
      by a network partition. However, when communication is possible, an explicit
      FAIL enables the backend to immediately requeue the job rather than waiting
      for the full visibility timeout to expire.

   b. Jobs that are not explicitly failed will be recovered by the backend when
      their visibility timeout expires (Section 5.5).

6. **Deregister**: The worker SHOULD send a deregistration request to the backend
   (Section 3.4).

7. **Exit**: The worker process exits with exit code 0 (clean shutdown).

### 7.3 Grace Period

The default grace period is **25 seconds**.

**Rationale**: 25 seconds aligns with Kubernetes' default `terminationGracePeriodSeconds`
of 30 seconds, leaving 5 seconds of margin for shutdown overhead (deregistration,
connection teardown, signal propagation). Sidekiq uses 25 seconds for the same reason.
This default ensures that OJS workers work correctly out of the box in Kubernetes
environments without requiring configuration changes.

Implementations MUST support configurable grace periods.

**Rationale**: The default of 25 seconds is appropriate for typical web-application
background jobs, but workloads vary dramatically. A worker processing 100ms webhook
deliveries needs only a few seconds; a worker running multi-hour data pipelines may
need minutes. Making the grace period configurable is MUST because a hardcoded default
would force operators into one of two bad choices: abandoning long jobs or delaying
deployments.

### 7.4 Shutdown Sequence Diagram

```
    Trigger                Stop          Wait for         Grace period      Deregister
  (SIGTERM or           fetching      active jobs          expiration         & exit
   heartbeat)
      |                    |               |                   |                |
      v                    v               v                   v                v
  +--------+         +---------+     +-----------+      +-----------+     +--------+
  | Signal |-------->| No more |---->| Active    |----->| FAIL      |---->| Exit   |
  | recv'd |         | FETCH   |     | jobs run  |      | remaining |     | (0)    |
  +--------+         +---------+     | to finish |      | jobs      |     +--------+
                                     +-----------+      +-----------+
                                          |
                                          | all jobs complete
                                          | before grace period
                                          v
                                     +--------+
                                     | Exit   |
                                     | (0)    |
                                     +--------+
```

### 7.5 Two-Phase Shutdown (Quiet then Terminate)

For zero-downtime deployments, operators SHOULD use a two-phase shutdown:

1. **Phase 1 -- Quiet**: Send a `"quiet"` directive via heartbeat response. The worker
   stops fetching but continues processing active jobs. New worker instances can be
   started to take over fetching.

2. **Phase 2 -- Terminate**: After a deployment-specific delay (allowing active jobs
   to drain), send a `"terminate"` directive via heartbeat response. The worker begins
   the grace period countdown.

This two-phase approach minimizes job disruption because:

- Active jobs are given the full duration between quiet and terminate to complete
  naturally, rather than being constrained to the grace period alone.
- New workers begin fetching immediately after the old workers are quieted, so queue
  throughput is maintained.

---

## 8. Concurrency Model

### 8.1 Worker Concurrency

Workers MUST support configurable concurrency -- the maximum number of jobs processed
in parallel by a single worker process.

**Rationale**: Concurrency is MUST because it is the primary mechanism for tuning
worker throughput. A worker with concurrency 1 processes jobs serially (safe but slow);
a worker with concurrency 50 processes jobs in parallel (fast but resource-intensive).
Without configurable concurrency, operators cannot match worker behavior to their
workload characteristics and resource constraints.

The default concurrency is **10**.

**Rationale**: 10 is the default used by Faktory and is a reasonable starting point
for I/O-bound workloads (HTTP calls, database queries, email sending). CPU-bound
workloads typically require lower concurrency (matching core count), while I/O-heavy
workloads may benefit from higher concurrency.

### 8.2 Concurrency Enforcement

Workers MUST NOT have more active jobs than their configured concurrency limit at
any point in time.

**Rationale**: Exceeding the concurrency limit causes resource exhaustion (memory,
CPU, file descriptors, database connections) that degrades not only the worker but
potentially the entire host and dependent services. This is MUST because the failure
mode is severe and non-obvious -- an over-concurrent worker may appear to function
normally under light load but collapse catastrophically under peak traffic.

Workers MUST NOT issue a FETCH request when the number of active jobs equals the
configured concurrency.

### 8.3 Queue-Level Concurrency

Backends MAY support queue-level concurrency limits, which cap the total number of
active jobs across all workers for a given queue.

When a backend enforces queue-level concurrency, the FETCH response SHOULD return
fewer jobs than requested (or an empty set) rather than exceeding the queue's
concurrency limit.

Workers SHOULD respect queue-level concurrency limits communicated by the backend.

---

## 9. Signal Handling

### 9.1 Signal Definitions

Workers MUST handle the following POSIX signals:

| Signal    | Action                                                                      |
|-----------|-----------------------------------------------------------------------------|
| `SIGTERM` | Begin graceful shutdown: transition to `terminate` state (Section 7).       |
| `SIGTSTP` | Stop fetching new jobs: transition to `quiet` state.                        |
| `SIGCONT` | Resume fetching: transition from `quiet` back to `running` state.           |
| `SIGINT`  | Immediate shutdown: best-effort cleanup and process exit.                   |

**Rationale**: Signal handling is MUST because POSIX signals are the universal process
lifecycle mechanism on Unix-like systems. `SIGTERM` is sent by `kill`, Docker, Kubernetes,
systemd, and every major process manager. `SIGTSTP` and `SIGCONT` are the standard
job-control signals. A worker that does not handle these signals will be killed
ungracefully by the operating system, losing all in-flight work. Sidekiq, Faktory
workers, and Oban all handle these exact signals with these exact semantics.

### 9.2 SIGTERM Handling

On receiving `SIGTERM`:

1. The worker MUST transition to the `terminate` state.
2. The worker MUST stop fetching new jobs.
3. The worker MUST begin the graceful shutdown sequence (Section 7).

Workers MUST NOT immediately exit on `SIGTERM`.

**Rationale**: `SIGTERM` is a request to terminate, not a demand to die immediately.
The default handler for `SIGTERM` kills the process, which is why workers MUST install
a custom handler. Kubernetes sends `SIGTERM` and then waits for the
`terminationGracePeriodSeconds` before sending `SIGKILL`. A worker that exits
immediately on `SIGTERM` wastes this grace period.

### 9.3 SIGTSTP Handling

On receiving `SIGTSTP`:

1. The worker MUST transition to the `quiet` state.
2. The worker MUST stop fetching new jobs.
3. The worker MUST continue processing active jobs.

### 9.4 SIGCONT Handling

On receiving `SIGCONT`:

1. If the worker is in the `quiet` state, it SHOULD transition back to `running`
   and resume fetching.
2. If the worker is in the `terminate` state, the signal MUST be ignored.

### 9.5 SIGINT Handling

On receiving `SIGINT` (typically from Ctrl+C in a terminal):

1. The worker SHOULD attempt best-effort cleanup of active jobs.
2. The worker MAY exit immediately without waiting for active jobs to complete.
3. Active jobs will be recovered by the visibility timeout mechanism (Section 5.5).

**Rationale**: `SIGINT` is the interactive interrupt signal, typically sent by a
developer pressing Ctrl+C. In development, fast shutdown is more important than
graceful completion. In production, `SIGTERM` (not `SIGINT`) is the standard
shutdown signal.

### 9.6 Platform Considerations

On platforms that do not support POSIX signals (e.g., Windows), workers SHOULD
implement equivalent behavior using platform-native mechanisms:

- Windows: `CTRL_CLOSE_EVENT`, `CTRL_SHUTDOWN_EVENT`, or named events
- Containers without signal support: Rely on heartbeat-based state transitions

---

## 10. Dead Worker Detection and Job Recovery

### 10.1 Heartbeat-Based Detection

The backend MUST track the timestamp of each worker's most recent heartbeat.

**Rationale**: Tracking heartbeat timestamps is the backend's only mechanism for
detecting worker death in the absence of explicit deregistration. A worker that crashes,
loses network connectivity, or is killed with `SIGKILL` cannot deregister; the backend
must infer death from silence.

If a worker has not sent a heartbeat within the configured heartbeat timeout (default:
**30 seconds**), the backend SHOULD consider the worker dead.

**Rationale**: The default timeout of 30 seconds (6 missed heartbeats at 5-second
intervals) provides tolerance for transient network issues and brief garbage collection
pauses while still detecting true failures promptly. Faktory uses a similar heuristic.

### 10.2 Job Recovery Process

When the backend determines that a worker is dead:

1. The backend MUST identify all jobs reserved by the dead worker (using the last
   reported `active_job_ids`).

   **Rationale**: Using `active_job_ids` from the last heartbeat is MUST because
   this is the most accurate record of what the worker was processing. The alternative
   -- scanning all active jobs for the worker's reservation -- is both slower and less
   reliable, as it depends on the backend's reservation tracking implementation.

2. For each identified job, the backend MUST perform one of the following:

   a. If the job's visibility timeout has already expired, it will have been
      automatically requeued per Section 5.5. No further action is needed.

   b. If the job's visibility timeout has NOT expired, the backend SHOULD immediately
      return the job to the `available` state (preemptive recovery) rather than
      waiting for the visibility timeout to expire.

      **Rationale**: Preemptive recovery reduces the latency between worker death
      and job re-execution. Without it, a job with a 30-minute visibility timeout
      on a worker that died 1 minute after claiming it would wait 29 minutes before
      being retried. Preemptive recovery makes the wait time equal to the heartbeat
      timeout (30 seconds) instead.

3. The backend MUST increment the `attempt` counter for each recovered job.

4. The backend MUST record an error in the job's `errors` array with type
   `"worker_death"`.

5. The backend MUST remove the dead worker from its active worker registry.

### 10.3 Avoiding Premature Recovery

The backend MUST NOT recover jobs from a worker that has merely experienced a brief
heartbeat delay. To avoid premature recovery:

- The heartbeat timeout SHOULD be at least 3 times the heartbeat interval.
- Backends SHOULD use monotonically increasing heartbeat sequence numbers to
  distinguish delayed heartbeats from missing heartbeats.
- Backends SHOULD consider network conditions and clock drift when evaluating
  heartbeat timeliness.

### 10.4 Split-Brain Prevention

In rare cases, a worker may recover after the backend has declared it dead and
requeued its jobs. When this occurs:

- The recovered worker MAY attempt to ACK or FAIL jobs it was processing.
- The backend MUST reject these requests because the reservation has been
  invalidated (Section 5.6).
- The worker SHOULD log the rejection and continue operating normally (or
  re-register if it detects its registration has been removed).

---

## 11. Complete Examples

### 11.1 Normal Heartbeat Flow

The following example shows a worker's heartbeat lifecycle during normal operation:

```
Time   Worker                          Backend
----   ------                          -------
T+0s   Register                  --->  Store worker record
       {worker_id, hostname,           {ok: true,
        pid, queues, concurrency}       heartbeat_interval: 5}

T+0s   FETCH {queues: ["email"]} --->  Return job_1
       Begin processing job_1

T+5s   BEAT                      --->  Record heartbeat
       {state: "running",              {state: "running",
        active_jobs: 1,                 server_time: "..."}
        active_job_ids: ["job_1"]}

T+8s   ACK {job_id: "job_1"}    --->  Mark job_1 completed

T+10s  BEAT                      --->  Record heartbeat
       {state: "running",              {state: "running"}
        active_jobs: 0,
        active_job_ids: []}

T+10s  FETCH {queues: ["email"]} --->  Return job_2
       Begin processing job_2

T+15s  BEAT                      --->  Record heartbeat
       {state: "running",              {state: "running"}
        active_jobs: 1,
        active_job_ids: ["job_2"]}
```

### 11.2 Server-Initiated Quiet and Terminate

The following example shows the backend directing a worker through the two-phase
shutdown sequence during a rolling deployment:

```
Time   Worker                          Backend
----   ------                          -------
T+0s   BEAT                      --->  Deployment initiated;
       {state: "running",              respond with quiet
        active_jobs: 3,                {state: "quiet"}
        active_job_ids:
         ["j1","j2","j3"]}

       Worker transitions to
       "quiet" state.
       Stops fetching.

T+5s   BEAT                      --->  Worker is draining;
       {state: "quiet",                keep quiet
        active_jobs: 3,                {state: "quiet"}
        active_job_ids:
         ["j1","j2","j3"]}

T+8s   ACK {job_id: "j1"}       --->  Mark j1 completed

T+10s  BEAT                      --->  Worker still draining
       {state: "quiet",                {state: "quiet"}
        active_jobs: 2,
        active_job_ids: ["j2","j3"]}

T+12s  ACK {job_id: "j2"}       --->  Mark j2 completed

T+15s  BEAT                      --->  All old workers quiet;
       {state: "quiet",                send terminate
        active_jobs: 1,                {state: "terminate"}
        active_job_ids: ["j3"]}

       Worker transitions to
       "terminate" state.
       Grace period starts (25s).

T+18s  ACK {job_id: "j3"}       --->  Mark j3 completed

T+20s  BEAT                      --->  Acknowledge
       {state: "terminate",            {state: "terminate"}
        active_jobs: 0,
        active_job_ids: []}

       All jobs complete.
       Worker deregisters.

T+20s  Deregister               --->  Remove worker record

       Worker exits (code 0).
```

### 11.3 Worker Crash and Recovery

The following example shows what happens when a worker crashes while processing jobs:

```
Time    Worker                          Backend
----    ------                          -------
T+0s    BEAT                      --->  Record heartbeat
        {state: "running",              {state: "running"}
         active_jobs: 2,
         active_job_ids: ["j1","j2"]}

T+3s    --- WORKER CRASHES ---          (no heartbeat received)
        (SIGKILL, OOM, hardware
         failure, etc.)

T+5s    (expected heartbeat)            (not received)

T+10s   (expected heartbeat)            (not received)

T+15s   (expected heartbeat)            (not received)

T+20s   (expected heartbeat)            (not received)

T+25s   (expected heartbeat)            (not received)

T+30s   (expected heartbeat)            (not received)
                                        Backend declares worker dead
                                        (30s since last heartbeat).

                                        Recovery:
                                        - j1: returned to "available"
                                          attempt incremented
                                          error recorded: "worker_death"
                                        - j2: returned to "available"
                                          attempt incremented
                                          error recorded: "worker_death"
                                        - Worker record removed
```

### 11.4 Visibility Timeout Extension for Long-Running Job

```
Time     Worker                          Backend
----     ------                          -------
T+0s     FETCH                     --->  Return job_1
         Begin processing job_1          (visibility_timeout: 1800s)

T+5s     BEAT                      --->  Record heartbeat;
         {active_job_ids: ["job_1"]}     reset job_1 visibility
                                         timeout to T+1805s

T+10s    BEAT                      --->  Record heartbeat;
         {active_job_ids: ["job_1"]}     reset job_1 visibility
                                         timeout to T+1810s

  ...    (job continues processing)      (timeout keeps resetting)

T+2400s  BEAT                      --->  Record heartbeat;
         {active_job_ids: ["job_1"]}     reset job_1 visibility
                                         timeout to T+4200s

T+2500s  ACK {job_id: "job_1"}    --->   Mark job_1 completed
         (job completed after 41 min,
          well beyond the 30-min default
          visibility timeout, but kept
          alive by heartbeats)
```

### 11.5 SIGTERM Graceful Shutdown

```
Time    Worker                          Backend
----    ------                          -------
T+0s    Processing jobs j1, j2, j3

T+1s    --- SIGTERM received ---
        Transition to "terminate".
        Stop fetching.
        Grace period = 25s.

T+5s    BEAT                      --->  Record heartbeat
        {state: "terminate",            {state: "terminate"}
         active_jobs: 3,
         active_job_ids:
          ["j1","j2","j3"]}

T+8s    j1 completes.
        ACK {job_id: "j1"}       --->  Mark j1 completed

T+12s   j2 completes.
        ACK {job_id: "j2"}       --->  Mark j2 completed

T+15s   BEAT                      --->  Record heartbeat
        {state: "terminate",            {state: "terminate"}
         active_jobs: 1,
         active_job_ids: ["j3"]}

T+26s   Grace period expires.
        j3 still running.

        FAIL {job_id: "j3",      --->  Mark j3 failed
         error: {type: "shutdown",      (will be retried per
          message: "worker               retry policy)
           shutting down"}}

T+26s   Deregister               --->  Remove worker record

        Worker exits (code 0).
```

---

## 12. Prior Art

This specification draws from the following prior art:

| System / Standard | Contribution to This Specification                                               |
|-------------------|----------------------------------------------------------------------------------|
| **Faktory**       | Three-state worker lifecycle (Running/Quiet/Terminate), BEAT command with server-directed state changes, `reserve_for` visibility timeout, heartbeat protocol design |
| **Sidekiq**       | TSTP/TERM signal handling conventions, 25-second grace period aligned with Kubernetes defaults, quiet/busy worker states, graceful shutdown sequence |
| **Temporal**      | Activity heartbeat pattern for long-running tasks (`ctx.heartbeat()`), visibility timeout extension via heartbeat, structured worker identity |
| **Oban**          | `SELECT FOR UPDATE SKIP LOCKED` for atomic job claiming in PostgreSQL, `LISTEN/NOTIFY` for real-time job notification, dead-worker rescue mechanism |
| **Amazon SQS**    | Visibility timeout terminology and semantics, message reservation model, automatic requeue on timeout expiration |
| **GoodJob**       | PostgreSQL-based `SKIP LOCKED` claiming, process-level concurrency control       |
| **Solid Queue**   | Database-backed claiming semantics, graceful shutdown with `SIGTERM`              |

---

## Appendix A: Configuration Reference

The following table summarizes all configurable parameters defined in this specification:

| Parameter                | Default      | Unit    | Description                                              |
|--------------------------|--------------|---------|----------------------------------------------------------|
| `heartbeat_interval`     | 5            | seconds | Interval between heartbeat requests                      |
| `heartbeat_timeout`      | 30           | seconds | Duration after which a missing worker is declared dead   |
| `visibility_timeout`     | 1800         | seconds | Default reservation period for claimed jobs              |
| `concurrency`            | 10           | jobs    | Maximum parallel jobs per worker process                 |
| `grace_period`           | 25           | seconds | Time to wait for active jobs during shutdown             |
| `queues`                 | `["default"]`| --      | Ordered list of queues to subscribe to                   |
| `labels`                 | `[]`         | --      | Worker labels for filtering and grouping                 |

---

## Appendix B: Error Types Defined by This Specification

This specification defines the following error types that backends and workers
MUST use when recording errors related to worker coordination:

| Error Type             | Description                                                       |
|------------------------|-------------------------------------------------------------------|
| `visibility_timeout`   | Job's visibility timeout expired before ACK or FAIL               |
| `worker_death`         | Worker was declared dead; job recovered by backend                |
| `shutdown`             | Worker shut down before job completed; job failed during grace period |

These error types appear in the `type` field of error objects in the job's `errors`
array (as defined in OJS JSON Wire Format, Section 12).

---

## Appendix C: Changelog

### 1.0.0-rc.1 (2025-06-01)

- Initial release candidate.
- Defined three-state worker lifecycle: running, quiet, terminate.
- Defined heartbeat protocol (BEAT) with server-initiated state transitions.
- Defined visibility timeout and reservation semantics (default 1800s).
- Defined FETCH semantics with atomic claiming.
- Defined graceful shutdown sequence with configurable grace period (default 25s).
- Defined concurrency model (default 10).
- Defined signal handling conventions (SIGTERM, SIGTSTP, SIGCONT, SIGINT).
- Defined dead worker detection and job recovery procedures.
- Adopted Faktory's three-state model and Temporal's activity heartbeat pattern.

---

*Open Job Spec v1.0.0-rc.1 -- Worker Lifecycle and Coordination Protocol*
*https://openjobspec.org*
