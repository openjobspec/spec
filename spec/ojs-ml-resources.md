# OJS ML/AI Resource Extension Specification

**Open Job Spec v1.0.0-rc.1 — Experimental Extension**

| Field       | Value                  |
|-------------|------------------------|
| Version     | 0.1.0                  |
| Date        | 2026-02-16             |
| Status      | Experimental           |
| Layer       | 1 (Core Extension)     |
| Level       | Extension              |

---

## 1. Overview

Machine learning and AI workloads have unique requirements that general-purpose job queues do not address: GPU affinity, memory-intensive processing, checkpoint/resume for long-running training jobs, and resource-aware scheduling. This extension defines how OJS jobs can declare compute resource requirements, enabling backends to match jobs with capable workers.

This extension uses the OJS `meta` field for resource declarations, requiring no changes to the core specification. Backends that do not understand resource requirements MUST ignore them and process jobs normally.

### 1.1 Relationship to Other Specifications

- **ojs-core.md**: Resource requirements are carried in the standard `meta` field. The job lifecycle is unchanged.
- **ojs-extension-lifecycle.md**: This is an Experimental tier extension following the extension governance process.
- **ojs-retry.md**: Checkpointed jobs interact with retry policy — a resumed job preserves its attempt count.
- **ojs-events.md**: Checkpoint events extend the standard event vocabulary.

### 1.2 Terminology

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

| Term | Definition |
|------|-----------|
| **Resource requirement** | A declaration of compute resources a job needs (GPU, memory, CPU) |
| **Capability label** | A key-value pair describing a worker's available resources |
| **Checkpoint** | A saved snapshot of job progress that enables resume after interruption |
| **Affinity** | A preference for scheduling a job on specific workers or hardware classes |
| **Preemption** | Interrupting a running job to free resources for higher-priority work |

---

## 2. Resource Requirements

### 2.1 Resource Schema

Jobs MAY declare resource requirements in `meta.resources`:

```json
{
  "type": "ml.train",
  "args": [{"model": "resnet50", "epochs": 100}],
  "meta": {
    "resources": {
      "gpu": {
        "count": 2,
        "type": "nvidia-a100",
        "memory_gb": 40
      },
      "cpu": {
        "cores": 8
      },
      "memory_gb": 64,
      "storage_gb": 200
    }
  }
}
```

### 2.2 Resource Fields

| Field | Type | Description |
|-------|------|-------------|
| `resources.gpu.count` | integer | Number of GPUs required (default: 0) |
| `resources.gpu.type` | string | GPU model identifier (e.g., `nvidia-a100`, `nvidia-h100`, `nvidia-t4`) |
| `resources.gpu.memory_gb` | number | Minimum GPU memory per device in GB |
| `resources.cpu.cores` | integer | Minimum CPU cores required |
| `resources.memory_gb` | number | Minimum system memory in GB |
| `resources.storage_gb` | number | Minimum scratch storage in GB |

### 2.3 Worker Capability Registration

Workers declare their capabilities via labels during heartbeat or registration:

```json
{
  "worker_id": "gpu-worker-01",
  "labels": [
    "gpu:nvidia-a100",
    "gpu_count:4",
    "gpu_memory_gb:80",
    "cpu_cores:32",
    "memory_gb:256",
    "region:us-east-1",
    "spot:true"
  ]
}
```

---

## 3. Affinity and Anti-Affinity

### 3.1 Affinity Rules

Jobs MAY declare scheduling preferences in `meta.affinity`:

```json
{
  "type": "ml.inference",
  "args": [{"prompt": "Hello"}],
  "meta": {
    "resources": {"gpu": {"count": 1, "type": "nvidia-t4"}},
    "affinity": {
      "required": [
        {"key": "region", "operator": "In", "values": ["us-east-1", "us-west-2"]}
      ],
      "preferred": [
        {"key": "spot", "operator": "NotIn", "values": ["true"]}
      ]
    }
  }
}
```

### 3.2 Affinity Operators

| Operator | Description |
|----------|-------------|
| `In` | Worker label value MUST be in the specified values |
| `NotIn` | Worker label value MUST NOT be in the specified values |
| `Exists` | Worker MUST have the specified label key |
| `DoesNotExist` | Worker MUST NOT have the specified label key |

### 3.3 Scheduling Semantics

- **Required** affinity rules are hard constraints: a job MUST NOT be dispatched to a worker that violates any required rule.
- **Preferred** affinity rules are soft constraints: the scheduler SHOULD prefer workers matching preferred rules but MAY dispatch to non-matching workers if no matching workers are available.

---

## 4. Checkpointing

### 4.1 Overview

Long-running ML training jobs benefit from periodic checkpointing, allowing them to resume from the last saved state after interruption (preemption, timeout, crash).

### 4.2 Checkpoint Schema

```json
{
  "type": "ml.train",
  "args": [{"model": "resnet50", "epochs": 100}],
  "meta": {
    "checkpoint": {
      "enabled": true,
      "interval_s": 300,
      "storage_uri": "s3://my-bucket/checkpoints/",
      "max_checkpoints": 3
    }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `checkpoint.enabled` | boolean | Whether checkpointing is enabled |
| `checkpoint.interval_s` | integer | Checkpoint interval in seconds |
| `checkpoint.storage_uri` | string | URI prefix for checkpoint storage (s3://, gs://, file://) |
| `checkpoint.max_checkpoints` | integer | Maximum checkpoints to retain (FIFO eviction) |

### 4.3 Checkpoint API

Workers save checkpoints by including checkpoint data in the heartbeat:

```http
POST /ojs/v1/workers/heartbeat HTTP/1.1
Content-Type: application/json

{
  "worker_id": "gpu-worker-01",
  "active_jobs": ["job-123"],
  "checkpoint": {
    "job_id": "job-123",
    "epoch": 42,
    "loss": 0.0234,
    "storage_key": "s3://my-bucket/checkpoints/job-123/epoch-42.pt"
  }
}
```

### 4.4 Resume Semantics

When a checkpointed job is retried, the backend MUST include the last checkpoint in the job's `meta`:

```json
{
  "type": "ml.train",
  "args": [{"model": "resnet50", "epochs": 100}],
  "meta": {
    "last_checkpoint": {
      "epoch": 42,
      "loss": 0.0234,
      "storage_key": "s3://my-bucket/checkpoints/job-123/epoch-42.pt"
    }
  }
}
```

The worker SHOULD resume from the checkpoint rather than starting from scratch.

---

## 5. Preemption

### 5.1 Preemption Policy

Jobs MAY declare their preemption tolerance in `meta.preemption`:

```json
{
  "type": "ml.train",
  "meta": {
    "preemption": {
      "preemptible": true,
      "grace_period_s": 60,
      "checkpoint_on_preempt": true
    }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `preemptible` | boolean | Whether the job can be preempted (default: false) |
| `grace_period_s` | integer | Seconds of warning before preemption |
| `checkpoint_on_preempt` | boolean | Whether to checkpoint before preemption |

### 5.2 Preemption Flow

1. Backend decides to preempt a job (e.g., higher-priority job needs the GPU).
2. Backend sends `quiet` directive to the worker via heartbeat response.
3. Worker has `grace_period_s` seconds to checkpoint and clean up.
4. If `checkpoint_on_preempt` is true, worker MUST save a checkpoint.
5. Job returns to `retryable` state with checkpoint preserved.

---

## 6. Resource-Aware FETCH

### 6.1 Extended FETCH Request

Workers MAY include their capabilities in the FETCH request to enable server-side resource matching:

```json
{
  "queues": ["ml-training"],
  "count": 1,
  "worker_id": "gpu-worker-01",
  "capabilities": {
    "gpu": {"count": 4, "type": "nvidia-a100", "memory_gb": 80},
    "cpu": {"cores": 32},
    "memory_gb": 256
  }
}
```

### 6.2 Matching Semantics

When a FETCH request includes `capabilities`, the backend:

1. MUST only return jobs whose `meta.resources` requirements are satisfiable by the worker's capabilities.
2. MUST check all required affinity rules against the worker's labels.
3. SHOULD prefer jobs whose preferred affinity rules match the worker.
4. SHOULD prefer higher-priority jobs when multiple jobs match.

---

## 7. Events

This extension defines the following events:

| Event | Description |
|-------|-------------|
| `job.checkpoint.saved` | A checkpoint was saved for a running job |
| `job.checkpoint.loaded` | A checkpoint was loaded during job resume |
| `job.preempted` | A job was preempted to free resources |
| `job.resource.waiting` | A job is waiting for a capable worker |

---

## 8. Prior Art

| System | Resource Support |
|--------|-----------------|
| **Kubernetes Jobs** | Full resource requests/limits, affinity, tolerations |
| **Slurm** | GPU allocation, node affinity, checkpointing via DMTCP |
| **Ray** | GPU scheduling, object store for checkpoints |
| **MLflow** | Experiment tracking, model checkpointing (app-level) |
| **Temporal** | No native resource scheduling |
| **Celery** | Basic queue routing, no GPU support |

OJS takes a pragmatic approach: resource requirements are advisory metadata that backends MAY use for scheduling, rather than a mandatory resource management layer. This keeps the core spec simple while enabling sophisticated scheduling for ML workloads.
