# Open Job Spec: Disaster Recovery and High Availability Specification

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Disaster Recovery and High Availability Specification |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-15                                     |
| **Status**  | Release Candidate 1                            |
| **Tier**    | Official Extension                             |
| **URI**     | `urn:ojs:ext:disaster-recovery`                |
| **Requires**| OJS Core Specification (Layer 1), OJS Observability Specification |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Durability Guarantees](#4-durability-guarantees)
5. [High Availability Architecture](#5-high-availability-architecture)
6. [Replication](#6-replication)
7. [Failover Behavior](#7-failover-behavior)
8. [Split-Brain Prevention](#8-split-brain-prevention)
9. [Backup and Restore](#9-backup-and-restore)
10. [Disaster Recovery Procedures](#10-disaster-recovery-procedures)
11. [Graceful Degradation](#11-graceful-degradation)
12. [Observability for HA](#12-observability-for-ha)
13. [Conformance Requirements](#13-conformance-requirements)
14. [Prior Art](#14-prior-art)

---

## 1. Introduction

Background job systems hold critical application state: in-flight jobs that represent work in progress, scheduled jobs that represent future commitments, dead letter entries that require human investigation, and job history that supports auditing and debugging. Loss of any of this data has direct business impact -- failed payments, missed notifications, orphaned workflows, and broken SLAs.

Traditional approaches to high availability and disaster recovery are tightly coupled to specific backends (Redis Sentinel, PostgreSQL streaming replication, RabbitMQ mirrored queues). This creates a situation where HA/DR behavior is an implementation accident rather than a deliberate contract. Teams migrate from one backend to another and discover -- in production -- that durability guarantees they relied upon no longer hold.

This specification defines backend-agnostic behavioral contracts for durability, high availability, replication, failover, backup, and disaster recovery. It does not prescribe specific technologies or architectures. Instead, it defines the properties that ANY conformant OJS backend MUST, SHOULD, or MAY satisfy, and requires backends to declare which properties they provide through capability manifests.

### 1.1 Scope

This specification defines:

- Durability guarantees for enqueued jobs and state transitions.
- High availability architecture requirements and capability declarations.
- Replication consistency requirements for job delivery.
- Failover behavior contracts for in-flight jobs and client reconnection.
- Split-brain prevention requirements to avoid duplicate job execution.
- Backup and restore requirements including portable OJS JSON format.
- Disaster recovery procedures and RPO/RTO classification.
- Graceful degradation modes for partial availability scenarios.

This specification does **not** define:

- Specific replication protocols or consensus algorithms.
- Backend-specific configuration (e.g., Redis Sentinel settings, PostgreSQL replication slots).
- Network topology or infrastructure provisioning.

### 1.2 Data at Risk

The following data categories are subject to HA/DR requirements:

| Data Category      | Impact of Loss                                               | Typical Volume |
|--------------------|--------------------------------------------------------------|----------------|
| In-flight jobs     | Work in progress is abandoned; side effects may be partial.  | Low-medium     |
| Scheduled jobs     | Future work is silently dropped; SLAs are missed.            | Medium         |
| Dead letter queue  | Failed jobs requiring investigation are lost.                | Low            |
| Job history        | Audit trail and debugging capability are degraded.           | High           |
| Cron schedules     | Recurring jobs stop firing until manually recreated.         | Low            |
| Queue configuration| Rate limits, backpressure settings, routing rules are lost.  | Low            |

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term               | Definition                                                                                      |
|--------------------|-------------------------------------------------------------------------------------------------|
| availability       | The proportion of time a system is operational and able to accept and process jobs.              |
| durability         | The guarantee that a persisted job will not be lost due to infrastructure failure.               |
| Recovery Point Objective (RPO) | The maximum acceptable amount of data loss measured in time. An RPO of 5 minutes means up to 5 minutes of job data may be lost in a disaster. |
| Recovery Time Objective (RTO) | The maximum acceptable duration of a service outage. An RTO of 15 minutes means the system must be operational within 15 minutes of a failure. |
| failover           | The process of switching from a failed primary node to a standby node.                          |
| split-brain        | A condition where two or more nodes in a cluster each believe they are the primary, leading to conflicting writes and duplicate job execution. |
| quorum             | The minimum number of nodes that must agree on a write for it to be considered committed. Typically a majority (N/2 + 1). |
| replication lag    | The delay between a write on the primary node and its visibility on replica nodes.              |
| checkpoint         | A consistent snapshot of the system state from which recovery can proceed.                      |
| fencing token      | A monotonically increasing token used to prevent stale leaders from performing writes after a new leader has been elected. |

---

## 4. Durability Guarantees

### 4.1 Enqueue Durability

Once a PUSH operation returns a success response (HTTP 201 or gRPC OK), the enqueued job MUST survive a backend process restart. A client that receives a success response MUST be able to assume the job will eventually be delivered (subject to the configured durability level).

Backends MUST NOT return success before the job is persisted to the configured durability level.

### 4.2 State Transition Durability

State transitions (e.g., `available` → `active`, `active` → `completed`, `active` → `retryable`) MUST be durable before the backend acknowledges the transition to the worker or client. This prevents a scenario where a worker completes a job, receives acknowledgment, but a restart causes the job to reappear.

Specifically:
- A `complete` acknowledgment MUST be durable before the backend responds to the worker.
- A `fail` acknowledgment MUST be durable before the backend responds to the worker.
- A `retry` state transition MUST be durable before the backend releases the job for redelivery.

### 4.3 At-Least-Once Delivery

Jobs MUST NOT be permanently lost except through explicit discard operations (e.g., manual deletion via the Admin API, dead letter expiry with a configured TTL). Implicit data loss -- due to restart, failover, memory pressure, or replication failure -- violates this requirement.

If a backend cannot guarantee at-least-once delivery for a particular failure mode, it MUST declare this limitation in its capability manifest.

### 4.4 Durability Levels

Backends MUST declare their durability level in the capability manifest.

| Level | Name                   | Description                                                                 | Data Loss Risk              |
|-------|------------------------|-----------------------------------------------------------------------------|-----------------------------|
| 0     | Memory-only            | Jobs are held in memory. A process restart loses all jobs.                  | Full loss on restart.       |
| 1     | Single-node persistent | Jobs are persisted to disk on a single node. Survives process restart.      | Loss on disk/node failure.  |
| 2     | Replicated persistent  | Jobs are persisted and replicated to N nodes. Survives node failure.        | Loss only on quorum failure.|

- Level 0 backends MAY be used for development and non-critical workloads.
- Level 1 backends SHOULD be the minimum for production workloads.
- Level 2 backends SHOULD be used for mission-critical workloads with strict RPO requirements.

Capability manifest declaration:

```json
{
  "extensions": {
    "disaster_recovery": {
      "durability_level": 2,
      "replication_mode": "synchronous",
      "ha_mode": "active-passive",
      "backup_format": "ojs-json"
    }
  }
}
```

---

## 5. High Availability Architecture

### 5.1 Active-Passive Failover

In an active-passive configuration, a single primary node handles all reads and writes. One or more standby nodes replicate state from the primary and are ready to assume the primary role if the active node fails.

Requirements:
- The standby MUST replicate all job state from the primary.
- Failover MUST NOT require manual intervention for detection (though promotion MAY be manual).
- After failover, the new primary MUST serve all previously committed job state.
- The previous primary MUST be fenced (see [Section 8](#8-split-brain-prevention)) to prevent split-brain.

### 5.2 Active-Active (Multi-Primary)

In an active-active configuration, multiple nodes accept reads and writes simultaneously. This provides higher availability and write throughput but introduces conflict resolution complexity.

Requirements:
- Backends implementing active-active MUST define a conflict resolution strategy for concurrent writes to the same job.
- A job MUST NOT be delivered to two workers simultaneously as a result of multi-primary replication conflicts.
- Backends SHOULD use deterministic conflict resolution (e.g., last-write-wins with Lamport timestamps, or CRDTs) rather than requiring manual resolution.

### 5.3 Backend Capability Declaration

Backends MUST declare their supported HA mode in the capability manifest. Clients and orchestration tools use this declaration to configure appropriate failover behavior.

Valid `ha_mode` values:
- `"none"` -- No HA support. Single node only.
- `"active-passive"` -- Active-passive failover.
- `"active-active"` -- Multi-primary with conflict resolution.

### 5.4 Health Check Endpoint

Backends supporting HA MUST expose a health check endpoint as defined in [ojs-http-binding.md](./ojs-http-binding.md). The health response MUST include the node's HA role:

```json
{
  "status": "healthy",
  "ha": {
    "role": "primary",
    "mode": "active-passive",
    "replication_lag_ms": 12,
    "peers": 2
  }
}
```

Health check consumers (load balancers, orchestrators) use the `role` field to route traffic. A node transitioning from primary to standby MUST report `"status": "draining"` during the transition.

### 5.5 Graceful Degradation Minimum

At a minimum, all backends MUST support graceful degradation: when a backend becomes partially unavailable, it SHOULD continue serving requests that do not depend on the unavailable component. See [Section 11](#11-graceful-degradation) for details.

---

## 6. Replication

### 6.1 Synchronous vs Asynchronous Replication

| Property              | Synchronous Replication                     | Asynchronous Replication                        |
|-----------------------|---------------------------------------------|-------------------------------------------------|
| Write latency         | Higher (waits for replica acknowledgment).  | Lower (returns after local write).              |
| Data loss on failover | None (RPO = 0).                             | Possible (RPO > 0, bounded by lag).             |
| Availability impact   | Reduced if replica is slow or unreachable.  | Primary availability unaffected by replica.     |
| Consistency           | Strong (all replicas consistent on read).   | Eventual (replicas may lag behind primary).     |

Backends MUST declare their replication mode (`"synchronous"` or `"asynchronous"`) in the capability manifest.

### 6.2 Replication Lag and Job Visibility

Asynchronous replication introduces a window during which a job committed on the primary is not yet visible on replicas. This has critical implications for job delivery:

- A job MUST NOT be delivered to two workers simultaneously due to replication lag. If a failover occurs during the replication lag window, the new primary MAY redeliver jobs that were in-flight on the old primary, but MUST use visibility timeouts to prevent duplicate active processing.
- Backends using asynchronous replication SHOULD expose `replication_lag_ms` in the health check response and as a metric (see [Section 12](#12-observability-for-ha)).
- If replication lag exceeds a configured threshold, the backend SHOULD emit a warning event and MAY pause accepting new writes until the replica catches up.

### 6.3 Consistency Requirements

Regardless of replication mode:
- A job that has been acknowledged as `completed` MUST NOT be redelivered after failover.
- A job that has been acknowledged as `failed` (terminal) MUST NOT be redelivered after failover.
- A job in `active` state (checked out by a worker) MAY be redelivered after failover, but only after its visibility timeout expires.

Backends MUST declare their replication mode in the capability manifest so that operators can make informed decisions about RPO tradeoffs.

---

## 7. Failover Behavior

### 7.1 Automatic vs Manual Failover

Backends MAY support automatic failover (the system detects failure and promotes a standby without human intervention) or manual failover (an operator triggers promotion). Backends MUST declare which mode they support.

For automatic failover:
- Detection SHOULD use heartbeat-based failure detection with a configurable timeout.
- The default heartbeat interval SHOULD be 1 second, with a failure threshold of 3 missed heartbeats.
- Promotion MUST NOT occur due to transient network partitions alone. Backends SHOULD require quorum agreement before promoting a standby.

### 7.2 State Recovery After Failover

After failover, the new primary MUST:
1. Recover all committed job state from its replica of the data.
2. Identify in-flight jobs whose visibility timeout has not yet expired and leave them in `active` state.
3. Identify in-flight jobs whose visibility timeout has expired and transition them back to `available` for redelivery.
4. Resume cron schedule evaluation from the last known checkpoint.
5. Resume dead letter queue processing.

### 7.3 In-Flight Job Handling During Failover

The visibility timeout mechanism (defined in OJS Core) provides natural protection for in-flight jobs during failover. Jobs checked out by a worker have a visibility timeout -- if the backend fails before the worker completes, the job's visibility timeout eventually expires and the new primary redelivers the job.

- Workers SHOULD use heartbeats to extend visibility timeouts for long-running jobs.
- After failover, the new primary MUST honor existing visibility timeouts.
- Workers connected to the old primary MUST detect the failover and reconnect to the new primary.

### 7.4 Client Reconnection Behavior

SDKs and clients MUST implement reconnection logic for failover scenarios:

- Clients MUST retry failed operations with exponential backoff after detecting a backend failure.
- Clients SHOULD use a configurable list of backend endpoints and attempt each in order.
- Clients MUST NOT assume a reconnected backend has the same in-memory state. Stateful operations (e.g., long-polling) MUST be re-established after reconnection.
- The RECOMMENDED maximum reconnection backoff is 30 seconds.

---

## 8. Split-Brain Prevention

### 8.1 The Split-Brain Problem

Split-brain occurs when a network partition causes two nodes to each believe they are the primary. Both nodes may deliver the same job to different workers, resulting in duplicate execution. For non-idempotent jobs (e.g., payment processing, email sending), this causes data corruption or duplicate side effects.

### 8.2 Fencing Tokens

Backends supporting HA SHOULD implement fencing tokens for leader election:

- Each primary election generates a monotonically increasing fencing token (epoch number).
- All write operations include the fencing token.
- The storage layer rejects writes with a stale fencing token.
- After failover, the new primary's fencing token is strictly greater than the old primary's token.

This ensures that even if the old primary is still running (zombie leader), its writes are rejected by the storage layer.

### 8.3 Distributed Locking or Consensus

Backends SHOULD implement one of the following mechanisms to prevent split-brain:

- **Distributed consensus** (e.g., Raft, Paxos): Nodes agree on a single leader through a consensus protocol.
- **External lock service** (e.g., etcd, ZooKeeper, Consul): An external system provides leader election and fencing.
- **Quorum writes**: Writes must be acknowledged by a majority of nodes to be committed.

The choice of mechanism is a backend implementation detail. This specification does not prescribe a specific approach.

### 8.4 Prefer Unavailability Over Duplicate Processing

When a backend detects a potential split-brain condition, it SHOULD prefer becoming unavailable (rejecting new requests) over risking duplicate job processing. This follows the principle that it is better to temporarily stop processing than to process jobs incorrectly.

Backends MUST document their split-brain behavior so that operators can assess the risk for their workloads.

---

## 9. Backup and Restore

### 9.1 Backup Scope

Backends supporting the disaster recovery extension MUST be capable of backing up the following data:

| Data                 | MUST Back Up | Notes                                           |
|----------------------|--------------|--------------------------------------------------|
| Job queue state      | Yes          | All non-terminal jobs (available, scheduled, retryable, active). |
| Dead letter queue    | Yes          | All jobs in the dead letter queue.               |
| Cron schedules       | Yes          | All registered cron schedules and last-run timestamps. |
| Queue configuration  | RECOMMENDED  | Rate limits, backpressure settings, routing rules. |
| Completed job history| OPTIONAL     | May be large; operators MAY choose to exclude.   |

### 9.2 Point-in-Time Recovery

Backends SHOULD support point-in-time recovery (PITR), allowing restoration to any point within a configured retention window. PITR enables recovery from logical errors (e.g., a bug that corrupts job state) in addition to physical failures.

- The retention window SHOULD be configurable with a minimum of 24 hours.
- PITR MAY be implemented via write-ahead log (WAL) archiving, change data capture (CDC), or periodic snapshots with incremental backups.

### 9.3 Backup Verification

Backups that are not tested are not backups. Backends SHOULD provide a mechanism to verify backup integrity, including a restore-to-temporary-instance operation that validates job counts, queue state consistency, and cron schedule completeness. Operators SHOULD run backup verification on a regular schedule (RECOMMENDED: weekly).

### 9.4 Portable Backup Format

Backends SHOULD support export and import in OJS JSON format for portable backup and cross-backend migration. The format follows the OJS JSON specification ([ojs-json-format.md](./ojs-json-format.md)):

```json
{
  "ojs_backup": {
    "version": "1.0.0",
    "created_at": "2026-02-15T10:30:00Z",
    "backend": "example-backend",
    "contents": {
      "jobs": [
        { "id": "job_abc123", "queue": "email", "kind": "welcome_email", "state": "available", "payload": { "user_id": 42 } }
      ],
      "cron_schedules": [
        { "name": "daily_digest", "cron": "0 9 * * *", "queue": "email", "kind": "daily_digest", "last_run_at": "2026-02-15T09:00:00Z" }
      ],
      "dead_letter": []
    }
  }
}
```

---

## 10. Disaster Recovery Procedures

### 10.1 RPO/RTO Classification

Job systems should establish RPO/RTO targets based on workload criticality:

| Tier     | RPO           | RTO            | Example Workloads                                |
|----------|---------------|----------------|--------------------------------------------------|
| Critical | 0 (no loss)   | < 1 minute     | Payment processing, financial transactions.      |
| High     | < 1 minute    | < 5 minutes    | Order fulfillment, user notifications.           |
| Standard | < 15 minutes  | < 30 minutes   | Report generation, analytics aggregation.        |
| Low      | < 1 hour      | < 4 hours      | Log processing, batch data imports.              |

Backends MUST document their achievable RPO/RTO for each durability level and HA mode combination.

### 10.2 Cross-Region Recovery

For cross-region or cross-datacenter disaster recovery:

- Backends SHOULD support cross-region replication for critical workloads.
- Cross-region replication is inherently asynchronous. Backends MUST document the expected replication lag.
- After a regional failover, the recovery region MUST serve the full job processing workload.
- DNS-based failover or load balancer reconfiguration SHOULD redirect clients to the recovery region.

### 10.3 Recovery Priority

When recovering from a disaster, systems SHOULD prioritize data in the following order:

1. **Cron schedules** -- Missing a scheduled run has compounding effects.
2. **Scheduled jobs** -- Jobs with a future `run_at` represent committed work.
3. **Available jobs** -- Jobs ready for immediate processing.
4. **In-flight jobs** -- MAY be duplicated on recovery (at-least-once).
5. **Dead letter queue** -- Failed jobs awaiting investigation.
6. **Completed job history** -- MAY be recovered last or from a separate backup.

### 10.4 Runbook Template

Backends SHOULD provide a disaster recovery runbook covering the following scenarios:

| Scenario                    | Detection                          | Response                                              |
|-----------------------------|------------------------------------|-------------------------------------------------------|
| Single node failure         | Health check failure, heartbeat timeout. | Automatic failover to standby.                  |
| Full datacenter outage      | Multiple health check failures.    | DNS failover to recovery region. Verify replication state. |
| Data corruption             | Integrity check failure, anomalous job counts. | Point-in-time recovery to last known good state. |
| Split-brain detected        | Fencing token conflict, dual-primary alert. | Fence old primary. Verify job state consistency. |
| Backup restore required     | Total data loss.                   | Restore from latest verified backup. Reconcile with producers. |

---

## 11. Graceful Degradation

### 11.1 Partial Availability

When a backend is partially available, it SHOULD continue serving requests that do not depend on the unavailable component:

- If the replication target is unavailable but the primary is healthy, the backend MAY continue accepting writes with reduced durability (Level 1 instead of Level 2). The backend MUST log a warning when operating in degraded durability mode.
- If a single queue's storage is unavailable, the backend SHOULD continue serving healthy queues and return errors only for the affected queue.

### 11.2 Read-Only Mode

Backends SHOULD support a read-only degradation mode:

- In read-only mode, clients MAY query job state, list queues, and read dead letter entries.
- Enqueue operations MUST return HTTP 503 (Service Unavailable) with a `Retry-After` header.
- State transitions (complete, fail, retry) MUST be rejected with HTTP 503.
- Read-only mode SHOULD be entered automatically when the backend detects it cannot safely persist writes (e.g., disk full, replication quorum lost).

### 11.3 Queue-Level Degradation

Backends MAY support per-queue degradation, where individual queues are marked as unavailable while others continue operating:

- Enqueue to an unavailable queue MUST return HTTP 503 with the `X-OJS-Queue-Status: unavailable` header.
- Workers polling an unavailable queue MUST receive an empty response (not an error), allowing them to continue processing jobs from other queues.
- The Admin API (see [ojs-admin-api.md](./ojs-admin-api.md)) SHOULD expose per-queue status.

### 11.4 Circuit Breaker Pattern for Producers

SDKs SHOULD implement a circuit breaker pattern for enqueue operations:

- **Closed** (normal): Requests flow through normally.
- **Open** (tripped): After N consecutive failures or an error rate exceeding a threshold, the circuit opens. Enqueue attempts fail immediately without contacting the backend.
- **Half-open** (probing): After a cooldown period, the circuit allows a single probe request. If it succeeds, the circuit closes. If it fails, the circuit reopens.

The RECOMMENDED defaults are:
- Failure threshold: 5 consecutive failures or 50% error rate over 10 seconds.
- Open duration: 30 seconds.
- Half-open probe interval: 5 seconds.

---

## 12. Observability for HA

HA/DR observability builds upon the OJS Observability specification ([ojs-observability.md](./ojs-observability.md)). The following additional metrics and alerts are REQUIRED or RECOMMENDED for backends implementing this extension.

### 12.1 Metrics

| Metric Name                         | Type      | Labels               | Requirement  | Description                                              |
|-------------------------------------|-----------|-----------------------|--------------|----------------------------------------------------------|
| `ojs.ha.replication_lag_ms`         | Gauge     | `source`, `target`   | REQUIRED     | Current replication lag in milliseconds.                 |
| `ojs.ha.failover_total`             | Counter   | `mode`, `result`     | REQUIRED     | Number of failover events (`automatic`/`manual`, `success`/`failure`). |
| `ojs.ha.backup_age_seconds`         | Gauge     | `backup_type`        | REQUIRED     | Age of the most recent backup in seconds.                |
| `ojs.ha.recovery_time_seconds`      | Histogram | `scenario`           | RECOMMENDED  | Time taken to complete recovery operations.              |
| `ojs.ha.node_role`                  | Gauge     | `node_id`            | RECOMMENDED  | Current role of the node (1=primary, 0=standby).        |
| `ojs.ha.quorum_size`               | Gauge     | --                   | RECOMMENDED  | Current number of nodes in quorum.                       |

### 12.2 Alerts

Backends SHOULD emit or support the following alert conditions:

| Alert Name                          | Condition                                           | Severity  |
|-------------------------------------|-----------------------------------------------------|-----------|
| `backend_unavailable`               | Health check fails for > RTO threshold.             | Critical  |
| `replication_lag_exceeded`          | `replication_lag_ms` > configured threshold.        | Warning   |
| `backup_stale`                      | `backup_age_seconds` > configured max age.          | Warning   |
| `split_brain_detected`              | Multiple nodes report `role=primary` simultaneously.| Critical  |
| `durability_degraded`               | Operating at lower durability level than configured. | Warning   |
| `failover_failed`                   | Automatic failover attempted but did not succeed.   | Critical  |

### 12.3 Events

The following lifecycle events (per [ojs-events.md](./ojs-events.md)) SHOULD be emitted for HA/DR operations:

- `ha.failover.started` -- A failover has been initiated.
- `ha.failover.completed` -- A failover has completed successfully.
- `ha.failover.failed` -- A failover attempt failed.
- `ha.degraded.entered` -- The backend entered a degraded mode.
- `ha.degraded.exited` -- The backend returned to normal operation.
- `ha.backup.completed` -- A backup completed successfully.
- `ha.backup.failed` -- A backup attempt failed.

---

## 13. Conformance Requirements

An implementation declaring support for the disaster recovery extension MUST support:

| ID       | Requirement                                                                                  |
|----------|----------------------------------------------------------------------------------------------|
| DR-001   | Enqueue durability: successful PUSH response guarantees job survives backend restart.        |
| DR-002   | State transition durability: state changes are durable before acknowledgment.                |
| DR-003   | At-least-once delivery: jobs are not permanently lost except by explicit discard.            |
| DR-004   | Durability level declared in capability manifest.                                            |
| DR-005   | HA mode declared in capability manifest (`none`, `active-passive`, or `active-active`).     |
| DR-006   | Health check includes HA role and replication lag when HA is enabled.                        |
| DR-007   | Replication mode declared in capability manifest (`synchronous` or `asynchronous`).          |
| DR-008   | No duplicate active delivery due to replication lag (visibility timeout enforced).           |
| DR-009   | Completed/failed jobs not redelivered after failover.                                        |
| DR-010   | Backup support for job queue state, dead letter queue, and cron schedules.                   |
| DR-011   | `ojs.ha.replication_lag_ms` metric exposed when replication is enabled.                     |
| DR-012   | `ojs.ha.failover_total` metric exposed when HA is enabled.                                  |
| DR-013   | `ojs.ha.backup_age_seconds` metric exposed when backup is configured.                       |

Recommended:

| ID       | Requirement                                                                                  |
|----------|----------------------------------------------------------------------------------------------|
| DR-R001  | Automatic failover with heartbeat-based detection.                                           |
| DR-R002  | Fencing tokens for leader election to prevent split-brain.                                   |
| DR-R003  | Point-in-time recovery support.                                                              |
| DR-R004  | Portable backup in OJS JSON format.                                                          |
| DR-R005  | Read-only degradation mode with HTTP 503 responses.                                          |
| DR-R006  | Queue-level degradation (per-queue availability).                                            |
| DR-R007  | Circuit breaker pattern in SDKs for enqueue operations.                                      |
| DR-R008  | Cross-region replication for critical workloads.                                              |
| DR-R009  | Backup verification mechanism (restore testing).                                             |
| DR-R010  | Disaster recovery runbook provided with backend documentation.                               |

---

## 14. Prior Art

| System                         | HA/DR Approach                                                                                   |
|--------------------------------|--------------------------------------------------------------------------------------------------|
| **Redis Sentinel / Cluster**   | Sentinel provides automatic failover for active-passive. Cluster provides sharding with replicas per shard. Asynchronous replication; data loss possible on failover. |
| **PostgreSQL Streaming Replication** | Synchronous or asynchronous streaming replication. PITR via WAL archiving. Strong consistency with synchronous mode. |
| **RabbitMQ Quorum Queues**     | Raft-based consensus for replicated, durable queues with automatic leader election. Replaced mirrored queues. |
| **Temporal Multi-Cluster**     | Multi-cluster replication for cross-region DR. Namespace-level failover. Asynchronous replication with conflict resolution. |
| **AWS SQS**                    | Fully managed durability. Messages replicated across multiple AZs. 99.999999999% (11 9s) durability by design. |
| **Kafka ISR (In-Sync Replicas)** | Configurable replication factor. ISR ensures writes are acknowledged by in-sync replicas. `min.insync.replicas` prevents writes when quorum is lost. |

OJS does not prescribe any specific approach but requires backends to clearly declare their durability, replication, and failover characteristics so that operators can make informed deployment decisions.

---
