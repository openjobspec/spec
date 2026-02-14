# Open Job Spec: Graceful Shutdown Specification

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Graceful Shutdown Specification            |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-13                                     |
| **Status**  | Release Candidate                              |
| **Tier**    | Official Extension                             |
| **URI**     | `urn:ojs:ext:graceful-shutdown`                |
| **Requires**| OJS Core Specification (Layer 1), OJS Worker Protocol |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Signal Handling Protocol](#4-signal-handling-protocol)
5. [Shutdown Phases](#5-shutdown-phases)
6. [Grace Period Configuration](#6-grace-period-configuration)
7. [In-Flight Job Handling](#7-in-flight-job-handling)
8. [Container Orchestrator Integration](#8-container-orchestrator-integration)
   - 8.1 [Kubernetes](#81-kubernetes)
   - 8.2 [Docker / Docker Compose](#82-docker--docker-compose)
9. [Backend Server Shutdown](#9-backend-server-shutdown)
10. [Conformance Requirements](#10-conformance-requirements)
11. [Prior Art](#11-prior-art)
12. [Examples](#12-examples)

---

## 1. Introduction

Graceful shutdown is the difference between a clean deployment and job loss. Every production system that processes background jobs MUST handle three scenarios correctly: planned deployments (rolling restarts), scaling events (pod termination), and crash recovery (process killed by OOM or hardware failure).

The OJS Worker Protocol (ojs-worker-protocol.md) defines worker lifecycle states (running → quiet → terminate) and heartbeat semantics. This specification extends that foundation with detailed guidance on signal handling, drain behavior, in-flight job handling, and integration with container orchestrators (Kubernetes, Docker).

The Docker PID 1 problem -- where shell processes do not forward signals to child processes -- catches virtually every team deploying containerized workers. Kubernetes' `terminationGracePeriodSeconds`, `preStop` hooks, and the interaction between SIGTERM timing and readiness probes are consistently misconfigured. This specification provides concrete, copy-pasteable configurations that eliminate these failure modes.

### 1.1 Scope

This specification defines:

- Signal handling protocol for OJS workers and backends.
- The three shutdown phases (quiet, drain, force-stop).
- Grace period configuration and semantics.
- In-flight job handling during shutdown.
- Kubernetes and Docker integration patterns.
- Backend server shutdown behavior.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term                  | Definition                                                                                     |
|-----------------------|------------------------------------------------------------------------------------------------|
| graceful shutdown     | An orderly process of stopping a worker or server while preserving in-flight job integrity.    |
| quiet phase           | The worker stops fetching new jobs but continues processing active jobs.                       |
| drain phase           | The worker waits for all active jobs to complete, up to the grace period.                      |
| force-stop            | The worker terminates immediately. Active jobs are abandoned.                                  |
| grace period          | Maximum time allowed for active jobs to complete during shutdown.                              |
| PID 1 problem         | When a shell process (bash, sh) is PID 1 in a container, it does not forward signals to children. |

---

## 4. Signal Handling Protocol

### 4.1 Worker Signal Handling

OJS workers MUST handle the following POSIX signals:

| Signal    | Action                                                                      |
|-----------|-----------------------------------------------------------------------------|
| `SIGTERM` | Begin graceful shutdown: enter quiet phase, then drain, then stop.          |
| `SIGINT`  | Same as `SIGTERM`. Enables Ctrl+C in development.                           |
| `SIGTSTP` | Enter quiet phase only (stop fetching, continue active jobs). Do NOT stop.  |

**Rationale**: The two-signal protocol (SIGTSTP to quiet, SIGTERM to stop) originates from Sidekiq and is now the industry standard. SIGTSTP allows operators to quiet a worker during an investigation without losing it, then either resume (SIGCONT) or terminate (SIGTERM).

### 4.2 Signal Handling Priority

When both SIGTSTP and SIGTERM are received:
- SIGTSTP while running → Enter quiet phase.
- SIGTERM while running → Begin graceful shutdown (quiet + drain + stop).
- SIGTERM while quiet → Begin drain phase immediately.
- Second SIGTERM while draining → Force-stop immediately.

**Rationale**: The "double SIGTERM = force stop" convention provides an escape hatch when the drain phase takes too long. Kubernetes sends SIGTERM and then SIGKILL after `terminationGracePeriodSeconds`; the second SIGTERM gives the operator a manual force-stop option.

### 4.3 The PID 1 Problem

When a process runs as PID 1 inside a container, the kernel does NOT deliver default signal handlers. A shell script (`#!/bin/sh`) as PID 1 will not forward SIGTERM to child processes.

OJS workers MUST be started as PID 1 directly (not via a shell wrapper), OR must use an init system that forwards signals.

**Correct Dockerfile**:
```dockerfile
# CORRECT: Go binary is PID 1, receives signals directly
CMD ["/app/ojs-worker"]
```

**Incorrect Dockerfile**:
```dockerfile
# INCORRECT: /bin/sh is PID 1, does not forward SIGTERM to ojs-worker
CMD /app/ojs-worker
```

**Alternative with shell**:
```dockerfile
# CORRECT: exec replaces the shell, making ojs-worker PID 1
CMD ["sh", "-c", "exec /app/ojs-worker"]
```

SDKs SHOULD detect when running as a non-PID-1 process inside a container and log a warning.

---

## 5. Shutdown Phases

Graceful shutdown proceeds through three sequential phases:

```
Signal received (SIGTERM/SIGINT)
    │
    ▼
┌──────────────────────────┐
│ Phase 1: QUIET           │  Stop fetching new jobs.
│ Duration: immediate      │  Deregister from backend.
│                          │  Reject new FETCH assignments.
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ Phase 2: DRAIN           │  Wait for active jobs to complete.
│ Duration: up to grace    │  Continue heartbeats.
│ period                   │  Monitor progress.
└──────────┬───────────────┘
           │ grace period expired OR all jobs complete
           ▼
┌──────────────────────────┐
│ Phase 3: STOP            │  Cancel remaining active jobs.
│ Duration: immediate      │  Release resources.
│                          │  Exit process.
└──────────────────────────┘
```

### 5.1 Phase 1: Quiet

- The worker MUST immediately stop fetching new jobs (no more FETCH requests).
- The worker MUST send a heartbeat with `state: "quiet"` to inform the backend.
- The backend MUST NOT assign new jobs to a quiet worker.
- Active jobs continue executing normally.

### 5.2 Phase 2: Drain

- The worker waits for all active jobs to complete.
- The worker MUST continue sending heartbeats during drain (so the backend knows the worker is alive, not crashed).
- The worker SHOULD log the number of remaining active jobs periodically (every 5 seconds).

### 5.3 Phase 3: Stop

If the grace period expires with jobs still active:

- The worker MUST attempt to cancel active jobs by calling FAIL with a `ShutdownError` error type.
- The backend SHOULD treat `ShutdownError` as retryable (the job did not fail due to a logic error; it was interrupted).
- The worker MUST send a final heartbeat with `state: "terminate"`.
- The worker exits.

---

## 6. Grace Period Configuration

### 6.1 Worker-Side Configuration

Workers MUST support a configurable grace period:

| Configuration           | Type     | Default | Description                                          |
|-------------------------|----------|---------|------------------------------------------------------|
| `shutdown_grace_period` | duration | `30s`   | Maximum time to wait for active jobs during drain.   |

### 6.2 Choosing the Grace Period

The grace period SHOULD be greater than the maximum expected job execution time. A formula:

```
grace_period = max_job_duration + heartbeat_interval + safety_margin
```

Example: If the longest job takes 60 seconds, heartbeat interval is 10 seconds, and safety margin is 10 seconds:

```
grace_period = 60 + 10 + 10 = 80 seconds
```

### 6.3 Interaction with Container Grace Period

When running in Kubernetes, the worker's grace period MUST be less than `terminationGracePeriodSeconds`:

```
worker.shutdown_grace_period < pod.terminationGracePeriodSeconds
```

If the worker's grace period equals or exceeds the container's, Kubernetes will SIGKILL the worker before it finishes draining, defeating the purpose of graceful shutdown.

**Recommended**: Set `terminationGracePeriodSeconds` to `worker.shutdown_grace_period + 10`.

---

## 7. In-Flight Job Handling

### 7.1 Job Requeue on Crash

If a worker crashes (process killed, OOM, hardware failure) without completing the shutdown protocol:

- The backend detects the missing heartbeat after the heartbeat timeout.
- The backend requeues all jobs that were assigned to the crashed worker.
- This relies on the visibility timeout mechanism defined in ojs-worker-protocol.md.

No special crash handling is needed from the worker -- the backend's dead worker detection handles it.

### 7.2 Long-Running Jobs

For jobs that take longer than the grace period:

1. The worker SHOULD send a FAIL with error type `ShutdownTimeout` and a message explaining the interruption.
2. The backend SHOULD schedule a retry for the interrupted job.
3. The retried job SHOULD resume from where it left off IF the handler supports checkpointing.

Handlers that support checkpointing SHOULD store progress in the job's `meta` field:

```json
{
  "meta": {
    "checkpoint": { "processed_rows": 50000, "total_rows": 100000 }
  }
}
```

---

## 8. Container Orchestrator Integration

### 8.1 Kubernetes

#### Recommended Pod Spec

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ojs-worker
spec:
  replicas: 3
  template:
    spec:
      terminationGracePeriodSeconds: 90  # > worker grace period (80s)
      containers:
        - name: worker
          image: myapp/ojs-worker:latest
          command: ["/app/ojs-worker"]  # NOT via shell (PID 1 issue)
          env:
            - name: OJS_SHUTDOWN_GRACE_PERIOD
              value: "80s"
          lifecycle:
            preStop:
              exec:
                command: ["sh", "-c", "kill -TSTP 1 && sleep 5"]
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8081
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8081
            periodSeconds: 10
            failureThreshold: 3
```

#### PreStop Hook

The `preStop` hook sends SIGTSTP to quiet the worker before Kubernetes sends SIGTERM. This gives the worker a head start on draining:

1. `preStop` sends SIGTSTP → worker enters quiet phase.
2. Kubernetes removes the pod from the Service (takes 1-5 seconds for endpoint propagation).
3. Kubernetes sends SIGTERM → worker begins drain phase.
4. Worker drains within `shutdown_grace_period`.
5. Worker exits cleanly before `terminationGracePeriodSeconds`.

#### Readiness Probe

The readiness probe SHOULD return unhealthy when the worker is in quiet or terminate state. This causes Kubernetes to stop routing traffic to the pod (for workers that also serve HTTP).

### 8.2 Docker / Docker Compose

#### Recommended Configuration

```yaml
# docker-compose.yml
services:
  worker:
    image: myapp/ojs-worker:latest
    command: ["/app/ojs-worker"]  # Array form, not string
    stop_grace_period: 90s
    stop_signal: SIGTERM
```

#### Docker Stop Behavior

`docker stop` sends SIGTERM, waits for `stop_grace_period` (default: 10s), then sends SIGKILL. The `stop_grace_period` MUST be set to at least `worker.shutdown_grace_period + 10`.

---

## 9. Backend Server Shutdown

OJS backend servers (not just workers) also require graceful shutdown:

### 9.1 Server Shutdown Sequence

1. Stop accepting new HTTP connections.
2. Finish in-flight HTTP requests (up to server grace period).
3. Stop scheduler goroutines (cron, reaper, promoter).
4. Close backend connections (Redis, Postgres).
5. Exit.

### 9.2 Server Shutdown Configuration

| Configuration           | Type     | Default | Description                                            |
|-------------------------|----------|---------|--------------------------------------------------------|
| `server_shutdown_timeout` | duration | `30s` | Maximum time to finish in-flight HTTP requests.        |

---

## 10. Conformance Requirements

An implementation declaring support for the graceful-shutdown extension MUST support:

| ID           | Requirement                                                                    |
|--------------|--------------------------------------------------------------------------------|
| GS-001       | Handle SIGTERM: quiet → drain → stop sequence.                                 |
| GS-002       | Handle SIGINT: same as SIGTERM.                                                |
| GS-003       | Configurable grace period with default of 30 seconds.                          |
| GS-004       | Continue heartbeats during drain phase.                                        |
| GS-005       | FAIL active jobs with `ShutdownError` when grace period expires.               |

Recommended:

| ID           | Requirement                                                                    |
|--------------|--------------------------------------------------------------------------------|
| GS-R001      | Handle SIGTSTP: enter quiet phase without stopping.                            |
| GS-R002      | Double SIGTERM: force-stop immediately.                                        |
| GS-R003      | Log remaining active job count during drain.                                   |
| GS-R004      | Readiness probe returns unhealthy when quiet.                                  |

---

## 11. Prior Art

| System           | Shutdown Approach                                                                           |
|------------------|---------------------------------------------------------------------------------------------|
| **Sidekiq**      | SIGTSTP to quiet (stop fetching), SIGTERM to shutdown. Configurable `:timeout` (default 25s). Rolling restart with SIGTSTP → wait → SIGTERM. |
| **Oban**         | `Oban.drain_queue/2` for testing. Graceful shutdown via GenServer termination. Lifeline plugin rescues orphans. |
| **BullMQ**       | `worker.close()` waits for active jobs. No signal handling built-in.                        |
| **Faktory**      | BEAT response can signal `quiet` or `terminate`. Worker-side handling is client library responsibility. |
| **Temporal**     | Worker shutdown via `Worker.shutdown()`. SDK handles activity heartbeat timeout.             |
| **Kubernetes**   | SIGTERM → `terminationGracePeriodSeconds` → SIGKILL. PreStop hooks for pre-shutdown logic.  |

The Sidekiq two-signal protocol (SIGTSTP + SIGTERM) is the most battle-tested and widely understood. OJS adopts it as the standard.

---

## 12. Examples

### 12.1 Go Worker with Graceful Shutdown

```go
func main() {
    worker := ojs.NewWorker("http://localhost:8080",
        ojs.WithQueues("default", "email"),
        ojs.WithConcurrency(10),
        ojs.WithShutdownGracePeriod(80 * time.Second),
    )

    worker.Register("email.send", handleEmailSend)

    ctx, cancel := signal.NotifyContext(context.Background(),
        syscall.SIGTERM, syscall.SIGINT,
    )
    defer cancel()

    if err := worker.Start(ctx); err != nil {
        slog.Error("worker error", "error", err)
        os.Exit(1)
    }

    slog.Info("worker stopped gracefully")
}
```

### 12.2 Node.js Worker with Graceful Shutdown

```javascript
const worker = new OJSWorker({
  url: 'http://localhost:8080',
  queues: ['default', 'email'],
  concurrency: 10,
  shutdownGracePeriod: 80_000, // 80 seconds
});

worker.register('email.send', handleEmailSend);

await worker.start();

process.on('SIGTERM', async () => {
  console.log('SIGTERM received, shutting down...');
  await worker.stop(); // Quiet → drain → stop
  process.exit(0);
});
```

### 12.3 Shutdown Timeline

```
t=0s   SIGTERM received
       → Worker enters QUIET phase
       → Stops calling FETCH
       → Sends heartbeat: state=quiet
       → Active jobs: 7

t=5s   → Active jobs: 5 (2 completed)
t=10s  → Active jobs: 3 (2 more completed)
t=15s  → Active jobs: 1 (2 more completed)
t=22s  → Active jobs: 0 (last job completed!)
       → Worker sends heartbeat: state=terminate
       → Worker exits cleanly

Total shutdown time: 22 seconds (within 80s grace period ✓)
```

---

## Appendix A: Changelog

| Date       | Change                        |
|------------|-------------------------------|
| 2026-02-13 | Initial release candidate.    |
