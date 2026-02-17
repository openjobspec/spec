# RFC-0006: ML Resource Extensions

- **Stage**: 0 (Strawman)
- **Champion**: TBD
- **Created**: 2025-07-25
- **Last Updated**: 2025-07-25
- **Target Spec Version**: 0.3.0

## Summary

This RFC proposes an extension to the OJS job envelope for specifying GPU/TPU resource requirements, model versioning, and ML-specific scheduling constraints. It enables ML workloads to declare hardware needs, model dependencies, and resource budgets as part of the job specification, allowing OJS backends to make intelligent scheduling decisions for compute-intensive AI/ML jobs.

## Motivation

AI/ML workloads are the fastest-growing category of background job processing. Training runs, inference serving, data preprocessing, and model evaluation all involve long-running, resource-intensive tasks that require specific hardware. Today, OJS provides no way to express these requirements:

1. **No resource specification**: A job that requires a GPU cannot declare this in the OJS envelope. Operators resort to queue-based partitioning (e.g., a `gpu` queue) which is inflexible — it cannot distinguish between a job needing one A100 GPU and one needing eight H100 GPUs.

2. **No model versioning**: ML jobs frequently reference specific model versions. Without a standardized way to declare model dependencies, teams embed version strings in `args` or `meta` with no consistency, making it impossible to track which model versions are in use or enforce version pinning.

3. **No cost awareness**: GPU compute is expensive. There is no mechanism for operators to set resource budgets, track GPU-hours consumed per job type, or enforce quotas per team or tenant.

4. **No scheduling hints**: ML workloads benefit from hardware-aware scheduling — co-locating jobs that share a model (to reuse GPU memory), preferring nodes with NVLink for multi-GPU training, or scheduling during off-peak hours for cost savings. OJS has no vocabulary for expressing these preferences.

The v0.3 roadmap identifies "AI/ML job extensions — GPU affinity, model versioning, resource requirements" as a future direction. This RFC provides a concrete design.

### Use Cases

1. **Inference pipeline**: An image classification service enqueues inference jobs that each require one GPU with at least 16 GB VRAM and the `resnet50-v2.3` model loaded. The backend routes these jobs to workers on nodes with matching GPUs and pre-loaded models.

2. **Distributed training**: A training job requires 8 A100 GPUs with NVLink interconnect on a single node. The OJS scheduler holds the job until a node with sufficient resources becomes available.

3. **Cost-aware batch processing**: A data science team has a monthly GPU budget of 10,000 GPU-hours. The backend tracks resource consumption per team and rejects new jobs when the budget is exhausted.

4. **Model A/B testing**: Two model versions (`v2.3` and `v2.4`) are deployed simultaneously. The backend routes inference jobs to workers with the appropriate model version loaded, enabling gradual rollout with traffic splitting.

## Prior Art

### Kubernetes Resource Requests/Limits

Kubernetes allows pods to declare CPU and memory requests/limits, with extended resources for GPUs (`nvidia.com/gpu: 1`). The scheduler places pods on nodes with sufficient available resources. Resource quotas enforce per-namespace limits.

**Lesson**: The request/limit model is well-understood by operators. OJS should adopt similar vocabulary. However, Kubernetes resource management is node-level, while OJS operates at the job/worker level.

### Ray (Anyscale)

Ray allows tasks to declare resource requirements (`@ray.remote(num_gpus=1, num_cpus=4)`). The Ray scheduler bin-packs tasks onto available workers. Ray supports custom resources (e.g., `TPU`, `special_hardware`) and placement groups for co-location.

**Lesson**: Custom resource types are essential for ML workloads beyond GPU/CPU. OJS should support an extensible resource vocabulary.

### Celery (Python)

Celery has no built-in resource management. GPU allocation is typically handled by queue routing (`-Q gpu`) and manual worker placement. The `celery-resource-manager` third-party package adds basic resource tracking but is not widely adopted.

**Lesson**: Leaving resource management to ad-hoc solutions leads to fragmentation. A standardized extension is valuable.

### MLflow / Kubeflow

MLflow tracks model versions, parameters, and artifacts. Kubeflow Pipelines supports GPU resource requests through Kubernetes integration. Neither operates at the job queue level.

**Lesson**: Model versioning metadata should be declarative and queryable. OJS can provide the scheduling layer that connects to model registries.

## Detailed Design

### 1. Resource Requirements

Resource requirements are specified in the job's `meta` object with the `ojs.ml.` prefix:

#### Resource Specification Format

```json
{
  "type": "inference.classify",
  "queue": "ml-inference",
  "args": ["s3://bucket/image-001.jpg"],
  "meta": {
    "ojs.ml.resources": {
      "gpu": {
        "count": 1,
        "type": "nvidia-a100",
        "memory_gb": 40
      },
      "cpu": {
        "cores": 4
      },
      "memory_gb": 32
    }
  }
}
```

#### Resource Attributes

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `ojs.ml.resources` | object | No | Resource requirements object |
| `ojs.ml.resources.gpu` | object | No | GPU requirements |
| `ojs.ml.resources.gpu.count` | integer | MUST (if gpu present) | Number of GPUs required (≥ 1) |
| `ojs.ml.resources.gpu.type` | string | MAY | GPU type identifier (e.g., `nvidia-a100`, `nvidia-h100`, `google-tpu-v4`) |
| `ojs.ml.resources.gpu.memory_gb` | number | MAY | Minimum GPU memory in GB |
| `ojs.ml.resources.gpu.interconnect` | string | MAY | Required interconnect (e.g., `nvlink`, `pcie`) |
| `ojs.ml.resources.cpu` | object | No | CPU requirements |
| `ojs.ml.resources.cpu.cores` | integer | MUST (if cpu present) | Number of CPU cores required |
| `ojs.ml.resources.memory_gb` | number | No | Minimum system memory in GB |
| `ojs.ml.resources.custom` | object | No | Custom resource key-value pairs (e.g., `{"fpga": 2}`) |

#### GPU Type Registry

Implementations SHOULD recognize the following standard GPU type identifiers:

| Identifier | Hardware | Typical VRAM |
|------------|----------|--------------|
| `nvidia-a100` | NVIDIA A100 | 40 GB / 80 GB |
| `nvidia-h100` | NVIDIA H100 | 80 GB |
| `nvidia-l4` | NVIDIA L4 | 24 GB |
| `nvidia-t4` | NVIDIA T4 | 16 GB |
| `nvidia-a10g` | NVIDIA A10G | 24 GB |
| `google-tpu-v4` | Google TPU v4 | 32 GB HBM |
| `google-tpu-v5e` | Google TPU v5e | 16 GB HBM |
| `amd-mi300x` | AMD Instinct MI300X | 192 GB HBM |

Custom GPU types MAY be used. Implementations MUST NOT reject unknown GPU type identifiers. *Rationale: New GPU types are released frequently; the registry should be extensible without spec changes.*

### 2. Model Versioning

Jobs can declare model dependencies in the `meta` object:

```json
{
  "type": "inference.classify",
  "queue": "ml-inference",
  "args": ["s3://bucket/image-001.jpg"],
  "meta": {
    "ojs.ml.model": {
      "name": "resnet50",
      "version": "2.3.0",
      "registry": "s3://models/resnet50/v2.3.0",
      "checksum": "sha256:a1b2c3d4e5f6..."
    }
  }
}
```

#### Model Attributes

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `ojs.ml.model` | object | No | Model dependency declaration |
| `ojs.ml.model.name` | string | MUST (if model present) | Model name identifier |
| `ojs.ml.model.version` | string | MUST (if model present) | Semantic version string |
| `ojs.ml.model.registry` | string (URI) | MAY | URI to model artifact |
| `ojs.ml.model.checksum` | string | MAY | Content hash for integrity verification (format: `algorithm:hex`) |
| `ojs.ml.model.framework` | string | MAY | ML framework (e.g., `pytorch`, `tensorflow`, `onnx`, `jax`) |

### 3. Scheduling Hints

Scheduling hints allow producers to express preferences without mandating them:

```json
{
  "type": "training.finetune",
  "queue": "ml-training",
  "args": ["dataset-v3", "config.yaml"],
  "meta": {
    "ojs.ml.resources": {
      "gpu": {"count": 8, "type": "nvidia-h100", "interconnect": "nvlink"}
    },
    "ojs.ml.scheduling": {
      "affinity": "colocate-model",
      "preemptible": true,
      "max_wait_seconds": 3600,
      "cost_tier": "spot"
    }
  }
}
```

#### Scheduling Attributes

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `ojs.ml.scheduling` | object | No | Scheduling preference object |
| `ojs.ml.scheduling.affinity` | string | MAY | `colocate-model` (prefer nodes with model loaded), `spread` (distribute across nodes), `pack` (bin-pack onto fewest nodes) |
| `ojs.ml.scheduling.preemptible` | boolean | MAY | Whether the job can be preempted by higher-priority work |
| `ojs.ml.scheduling.max_wait_seconds` | integer | MAY | Maximum time to wait for resources before discarding |
| `ojs.ml.scheduling.cost_tier` | string | MAY | `on-demand`, `spot`, `reserved` — maps to cloud pricing tiers |

### 4. Resource Monitoring

Backends that support ML resources SHOULD expose resource utilization metrics:

| Metric Name | Unit | Description |
|-------------|------|-------------|
| `ojs.ml.gpu.utilization` | `ratio` | GPU utilization (0.0–1.0) per worker |
| `ojs.ml.gpu.memory_used` | `GB` | GPU memory in use per worker |
| `ojs.ml.gpu.hours` | `hours` | Cumulative GPU-hours consumed |
| `ojs.ml.resource.wait_time` | `ms` | Time job waited for resource availability |
| `ojs.ml.resource.queue_depth` | `{job}` | Jobs waiting for specific resource types |

### 5. Validation Rules

Backends MUST validate ML resource specifications at enqueue time:

| Rule | Error Code | Description |
|------|------------|-------------|
| `gpu.count` ≥ 1 when gpu object is present | `INVALID_RESOURCE_COUNT` | GPU count must be positive |
| `gpu.memory_gb` > 0 when specified | `INVALID_RESOURCE_MEMORY` | GPU memory must be positive |
| `cpu.cores` ≥ 1 when cpu object is present | `INVALID_RESOURCE_COUNT` | CPU core count must be positive |
| `memory_gb` > 0 when specified | `INVALID_RESOURCE_MEMORY` | System memory must be positive |
| `model.version` matches semver pattern | `INVALID_MODEL_VERSION` | Model version must be valid semver |
| `model.checksum` matches `algorithm:hex` pattern | `INVALID_MODEL_CHECKSUM` | Checksum must have a recognized format |

### 6. Worker Resource Advertisement

Workers MUST advertise their available resources during registration or heartbeat:

```json
{
  "worker_id": "worker-gpu-001",
  "resources": {
    "gpu": {
      "count": 4,
      "type": "nvidia-a100",
      "memory_gb": 80,
      "interconnect": "nvlink"
    },
    "cpu": {
      "cores": 64
    },
    "memory_gb": 512
  },
  "loaded_models": [
    {"name": "resnet50", "version": "2.3.0"},
    {"name": "bert-base", "version": "1.0.0"}
  ]
}
```

The backend uses advertised resources to match jobs to workers. When multiple workers satisfy a job's resource requirements, the backend SHOULD prefer the worker with the most specific match (e.g., a worker with the exact GPU type over one with a more powerful GPU). *Rationale: Specific matching reduces resource waste and enables model affinity optimizations.*

## Examples

### Single-GPU Inference Job

```json
{
  "type": "inference.classify",
  "queue": "ml-inference",
  "args": ["s3://data/images/batch-001.tar.gz"],
  "meta": {
    "ojs.ml.resources": {
      "gpu": {"count": 1, "type": "nvidia-t4", "memory_gb": 16},
      "memory_gb": 8
    },
    "ojs.ml.model": {
      "name": "efficientnet-b4",
      "version": "1.2.0",
      "framework": "pytorch"
    }
  }
}
```

### Multi-GPU Training Job

```json
{
  "type": "training.finetune",
  "queue": "ml-training",
  "args": ["s3://datasets/squad-v2", "configs/bert-finetune.yaml"],
  "meta": {
    "ojs.ml.resources": {
      "gpu": {"count": 8, "type": "nvidia-h100", "memory_gb": 80, "interconnect": "nvlink"},
      "cpu": {"cores": 32},
      "memory_gb": 256
    },
    "ojs.ml.model": {
      "name": "llama-3-70b",
      "version": "3.0.0",
      "registry": "s3://models/llama-3-70b/v3.0.0",
      "checksum": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "framework": "pytorch"
    },
    "ojs.ml.scheduling": {
      "affinity": "pack",
      "preemptible": false,
      "max_wait_seconds": 7200,
      "cost_tier": "on-demand"
    }
  }
}
```

### TPU Inference with Model A/B Test

```json
{
  "type": "inference.generate",
  "queue": "ml-inference",
  "args": ["Generate a summary of the following article..."],
  "meta": {
    "ojs.ml.resources": {
      "gpu": {"count": 1, "type": "google-tpu-v5e"}
    },
    "ojs.ml.model": {
      "name": "gemma-7b",
      "version": "2.0.0",
      "framework": "jax"
    },
    "ojs.ml.scheduling": {
      "affinity": "colocate-model",
      "cost_tier": "spot"
    }
  }
}
```

## Conformance Impact

ML resource extensions are an OPTIONAL extension. They do not affect conformance levels 0–4.

New requirements introduced:

- **MUST**: Backends MUST validate `ojs.ml.resources` at enqueue time and reject invalid specifications with the appropriate error code. *Rationale: Early validation prevents jobs from being queued that can never be scheduled.*
- **MUST**: Backends MUST NOT reject jobs with unknown GPU type identifiers. *Rationale: New hardware types should not require spec or backend updates.*
- **MUST**: Workers advertising resources MUST include accurate GPU type and memory information. *Rationale: Inaccurate resource advertisement leads to scheduling failures and OOM errors.*
- **SHOULD**: Backends SHOULD match jobs to workers based on declared resource requirements. *Rationale: Resource-aware scheduling is the primary value proposition of this extension.*
- **SHOULD**: Backends SHOULD track GPU-hours consumed per job for cost attribution. *Rationale: Cost visibility is critical for ML workload management.*
- **MAY**: Backends MAY implement preemption for jobs marked as `preemptible`. *Rationale: Preemption adds complexity but enables better resource utilization.*

## Backward Compatibility

This proposal is fully backward compatible. All ML resource attributes use the `ojs.ml.` prefix in the `meta` object. Backends that do not support ML resources will pass these attributes through as opaque metadata. Jobs without ML resource specifications are unaffected.

## Implementation Requirements

Per the OJS RFC process, proposals at Stage 2+ MUST include working prototypes in at least two languages:

- [ ] Go: ML resource scheduling in `ojs-backend-redis/internal/core/ml/`
- [ ] Python: ML resource client extensions in `ojs-python-sdk/src/ojs/ml/`

## Alternatives Considered

### Queue-Based Resource Partitioning

Continuing to use queues for resource partitioning (e.g., `gpu-a100` queue, `gpu-t4` queue) was considered. This was rejected because:

- Queue proliferation makes management unwieldy (N GPU types × M model versions = many queues)
- It does not support multi-dimensional resource matching (GPU + memory + interconnect)
- It conflates workload routing with resource scheduling

### Kubernetes-Native Scheduling

Delegating all resource scheduling to Kubernetes (OJS creates pods per job) was considered. This was rejected because:

- Not all OJS deployments run on Kubernetes
- Pod startup latency (cold start) is too high for latency-sensitive inference
- Long-running workers with pre-loaded models are more efficient than per-job pods

### External Scheduler Integration

Integrating with external schedulers (Slurm, Ray) was considered. This was rejected as the primary approach because:

- It creates a hard dependency on external infrastructure
- OJS should provide basic resource-aware scheduling natively
- Integration with external schedulers MAY be supported as an additional feature

## Open Questions

1. **Resource fragmentation**: How should the backend handle resource fragmentation? (e.g., 4 workers each have 2 free GPUs, but a job needs 8 GPUs on one node). Should the spec define placement constraints?

2. **Model pre-loading**: Should there be a mechanism for workers to declare which models they can load on demand (not just what is currently loaded)?

3. **Resource quotas**: Should quotas be part of this RFC or a separate extension? Quotas interact with multi-tenancy (ADR-008) and need careful design.

4. **Heterogeneous clusters**: How should the backend handle clusters with mixed GPU types? Should it support "equivalent" resource matching (e.g., an H100 satisfies an A100 request)?

5. **Resource accounting granularity**: Should GPU-hour tracking be per-job or per-tenant? Both are useful but have different implementation costs.
