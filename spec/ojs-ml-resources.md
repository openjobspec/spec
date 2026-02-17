# Open Job Spec: ML/AI Resource Requirements Extension

| Field       | Value                        |
|-------------|------------------------------|
| Version     | 0.3.0                        |
| Date        | 2026-02-19                   |
| Status      | Draft                        |
| Stage       | 2 (Draft)                    |
| Maturity    | Alpha                        |
| Layer       | 1 -- Core (Extension)        |
| Spec URI    | `urn:ojs:spec:ml-resources`  |

---

## Table of Contents

1. [Overview and Rationale](#1-overview-and-rationale)
2. [Terminology](#2-terminology)
3. [Resource Requirements](#3-resource-requirements)
   - 3.1 [Accelerator Types](#31-accelerator-types)
   - 3.2 [GPU Requirements](#32-gpu-requirements)
   - 3.3 [TPU Requirements](#33-tpu-requirements)
   - 3.4 [Memory and Storage](#34-memory-and-storage)
   - 3.5 [CPU Requirements](#35-cpu-requirements)
4. [Model Versioning](#4-model-versioning)
5. [Model Registry Integration](#5-model-registry-integration)
   - 5.1 [Registry Providers](#51-registry-providers)
   - 5.2 [Registry URI Scheme](#52-registry-uri-scheme)
   - 5.3 [Model Resolution](#53-model-resolution)
6. [Compute Constraints](#6-compute-constraints)
7. [Node Affinity and Scheduling](#7-node-affinity-and-scheduling)
   - 7.1 [Node Selectors](#71-node-selectors)
   - 7.2 [Affinity Rules](#72-affinity-rules)
   - 7.3 [Anti-Affinity](#73-anti-affinity)
8. [Resource Priority and Preemption](#8-resource-priority-and-preemption)
   - 8.1 [Priority Classes](#81-priority-classes)
   - 8.2 [Preemption Semantics](#82-preemption-semantics)
   - 8.3 [Resource Reservation](#83-resource-reservation)
   - 8.4 [Priority Escalation](#84-priority-escalation)
9. [Checkpoint and Resume Semantics](#9-checkpoint-and-resume-semantics)
   - 9.1 [Checkpoint Configuration](#91-checkpoint-configuration)
   - 9.2 [Checkpoint Lifecycle](#92-checkpoint-lifecycle)
   - 9.3 [Resume Protocol](#93-resume-protocol)
   - 9.4 [Checkpoint Storage Backends](#94-checkpoint-storage-backends)
10. [Queue-Level Resource Constraints](#10-queue-level-resource-constraints)
11. [Worker Capability Advertisement](#11-worker-capability-advertisement)
12. [Workflow Integration](#12-workflow-integration)
    - 12.1 [Training Pipeline Example](#121-training-pipeline-example)
    - 12.2 [Multi-Model Inference Example](#122-multi-model-inference-example)
    - 12.3 [Resource Propagation in Workflows](#123-resource-propagation-in-workflows)
13. [Job Envelope Examples](#13-job-envelope-examples)
14. [Interaction with Other Extensions](#14-interaction-with-other-extensions)
15. [Security Considerations](#15-security-considerations)
16. [Prior Art](#16-prior-art)

---

## 1. Overview and Rationale

This extension defines attributes for expressing machine learning and AI workload resource requirements in OJS jobs. It enables job producers to specify GPU, TPU, and CPU requirements, model versions, memory needs, compute constraints, node affinity rules, and preemption policies. Backends use these attributes to route jobs to workers with appropriate hardware and software capabilities.

### 1.1 Motivation

AI/ML workloads have fundamentally different infrastructure requirements from traditional background jobs:

- **GPU type and count**: Training a 70B-parameter LLM requires 8x NVIDIA H100 GPUs with NVLink interconnect; serving a small classification model needs a single T4. Without standardized resource declarations, schedulers cannot make correct placement decisions.
- **TPU scheduling**: Google Cloud TPU v5e pods require specific topology declarations (e.g., 2x4 chip layout) that have no analog in traditional job systems.
- **Memory requirements**: A Llama 3.1 405B model in FP16 needs approximately 810 GB of GPU VRAM across devices, plus significant system RAM for KV cache. Schedulers MUST understand both GPU VRAM and system memory to avoid OOM kills.
- **Compute capability constraints**: CUDA compute capability 8.0+ is required for BF16 tensor cores; FP8 training requires compute capability 8.9+ (Hopper architecture). Jobs that require specific instruction sets MUST declare these constraints.
- **Model versioning**: Deploying model version v2.1 to a subset of inference workers while v2.0 handles remaining traffic requires precise version routing.
- **Cost optimization**: A hyperparameter sweep that can tolerate interruption should run on spot/preemptible instances at 60-90% cost savings, with automatic checkpointing and resume.

Without a standard way to express these requirements, every ML job framework invents its own resource specification, preventing interoperability between schedulers, backends, and SDKs.

### 1.2 Design Principles

1. **Declarative, not imperative.** Jobs declare what resources they need; backends decide how to satisfy those requirements. This separation enables backend-specific optimizations (e.g., bin-packing, topology-aware placement) without changing job definitions.

2. **Minimum viable constraints.** All resource attributes are OPTIONAL. A job that specifies only `ext_ml_gpu_count: 1` is valid and schedulable. Jobs MAY progressively add constraints (GPU type, VRAM, compute capability) as their requirements become more specific.

3. **Wire-format neutral.** Resource requirements are expressed as `ext_ml_*` extension attributes in the job envelope, following the OJS extension convention. They serialize identically in JSON and Protobuf wire formats.

4. **Backward compatible.** Backends that do not implement this extension MUST ignore `ext_ml_*` attributes without error, per the OJS extension contract.

### 1.3 Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt).

All JSON examples in this document are normative unless explicitly marked otherwise.

---

## 2. Terminology

| Term                    | Definition                                                                                                  |
|-------------------------|-------------------------------------------------------------------------------------------------------------|
| accelerator             | A hardware device that accelerates computation: GPU, TPU, FPGA, or CPU (when no accelerator is needed).     |
| GPU VRAM                | Video RAM on a GPU device, measured in gigabytes. Distinct from system (host) memory.                       |
| compute capability      | NVIDIA's versioning scheme for GPU instruction set features (e.g., 7.0 = Volta, 8.0 = Ampere, 9.0 = Hopper). |
| node selector           | A set of key-value labels that a worker node MUST match for job placement.                                   |
| affinity rule           | A scheduling constraint that influences (but may not strictly require) job placement on matching workers.    |
| preemption              | The act of interrupting a running job to free resources for a higher-priority job.                            |
| checkpoint              | A serialized snapshot of job progress that enables resumption after interruption.                             |
| resource reservation    | A pre-allocated capacity guarantee that ensures resources are available when a job becomes schedulable.       |
| priority class          | A classification that determines a job's access to resources: `spot`, `on-demand`, or `reserved`.            |
| topology                | The physical or logical arrangement of accelerator devices (e.g., TPU pod slice shape, GPU NVLink domain).   |
| worker capability       | A self-reported description of the hardware and software resources available on a worker node.                |

---

## 3. Resource Requirements

All ML resource attributes use the `ext_ml_` prefix. Backends that support this extension MUST validate these attributes against the constraints defined in this section. Backends that do not support this extension MUST ignore all `ext_ml_*` attributes without returning an error.

**Rationale:** The `ext_ml_` prefix ensures ML resource attributes never collide with core OJS attributes or other extensions. The ignore-if-unsupported rule ensures backward compatibility with non-ML backends.

### 3.1 Accelerator Types

| Attribute           | Type   | Required | Description                                                            |
|---------------------|--------|----------|------------------------------------------------------------------------|
| `ext_ml_accelerator`| string | No       | Required accelerator type: `gpu`, `tpu`, `fpga`, `cpu`                 |

When `ext_ml_accelerator` is `gpu` or `tpu`, the backend MUST NOT dispatch the job to a CPU-only worker.

**Rationale:** Dispatching a GPU job to a CPU-only node causes immediate failure. The accelerator type acts as a hard scheduling gate.

When `ext_ml_accelerator` is `cpu`, the backend MAY dispatch the job to a worker with accelerators, but the job does not require them.

When `ext_ml_accelerator` is omitted, the backend SHOULD infer the accelerator requirement from other attributes: if `ext_ml_gpu_count` or `ext_ml_gpu_type` is set, the accelerator is implicitly `gpu`; if `ext_ml_tpu_type` is set, the accelerator is implicitly `tpu`.

**Rationale:** Requiring explicit `ext_ml_accelerator` when GPU fields are already present would be redundant and error-prone. Implicit inference reduces boilerplate.

### 3.2 GPU Requirements

| Attribute                     | Type    | Required | Description                                                          |
|-------------------------------|---------|----------|----------------------------------------------------------------------|
| `ext_ml_gpu_type`             | string  | No       | GPU model identifier (see table below)                               |
| `ext_ml_gpu_count`            | integer | No       | Number of GPUs required (default: 1 when any GPU attribute is set)   |
| `ext_ml_gpu_memory_gb`        | number  | No       | Minimum GPU VRAM per device in GB                                     |
| `ext_ml_gpu_compute_capability` | string | No      | Minimum NVIDIA compute capability (e.g., `"8.0"`)                   |
| `ext_ml_gpu_interconnect`     | string  | No       | Required GPU interconnect: `nvlink`, `pcie`, `any`                   |

#### Well-Known GPU Types

Implementations SHOULD recognize the following GPU type identifiers. Implementations MAY accept additional identifiers following the pattern `{vendor}-{model}`.

| Identifier      | Vendor  | Model            | VRAM  | Compute Capability | Common Use Case                |
|-----------------|---------|------------------|-------|--------------------|---------------------------------|
| `nvidia-a100`   | NVIDIA  | A100 (40/80 GB)  | 40/80 | 8.0                | Training, large inference       |
| `nvidia-h100`   | NVIDIA  | H100 (80 GB)     | 80    | 9.0                | LLM training, FP8 inference     |
| `nvidia-h200`   | NVIDIA  | H200 (141 GB)    | 141   | 9.0                | LLM training, extended context  |
| `nvidia-l4`     | NVIDIA  | L4 (24 GB)       | 24    | 8.9                | Inference, video processing     |
| `nvidia-l40s`   | NVIDIA  | L40S (48 GB)     | 48    | 8.9                | Inference, fine-tuning          |
| `nvidia-t4`     | NVIDIA  | T4 (16 GB)       | 16    | 7.5                | Inference, cost-optimized       |
| `nvidia-v100`   | NVIDIA  | V100 (16/32 GB)  | 16/32 | 7.0                | Legacy training                 |
| `nvidia-a10g`   | NVIDIA  | A10G (24 GB)     | 24    | 8.6                | Inference (AWS)                 |
| `nvidia-b200`   | NVIDIA  | B200 (192 GB)    | 192   | 10.0               | Next-gen LLM training           |
| `amd-mi250`     | AMD     | MI250 (128 GB)   | 128   | --                 | HPC, training                   |
| `amd-mi300x`    | AMD     | MI300X (192 GB)  | 192   | --                 | LLM training, inference         |

**Rationale:** Well-known GPU type identifiers prevent string fragmentation. Without a canonical list, one team might use `"a100"`, another `"A100"`, and a third `"nvidia-a100-80gb"`. The `{vendor}-{model}` convention is extensible while remaining human-readable.

#### `ext_ml_gpu_count` (integer)

The number of GPU devices required. When any GPU-related attribute is set but `ext_ml_gpu_count` is omitted, the default is `1`.

A backend MUST reject a job with `ext_ml_gpu_count` set to `0` if other GPU attributes (`ext_ml_gpu_type`, `ext_ml_gpu_memory_gb`, `ext_ml_gpu_compute_capability`) are also set.

**Rationale:** Requesting 0 GPUs with a GPU type constraint is contradictory and indicates a client bug. Failing fast prevents silent scheduling errors.

#### `ext_ml_gpu_memory_gb` (number)

Minimum GPU VRAM per device in gigabytes. When set, the backend MUST only dispatch the job to workers where every allocated GPU has at least this much VRAM.

Common VRAM requirements by workload:

| Workload                        | Model Size | Precision | VRAM per GPU | GPU Count |
|---------------------------------|------------|-----------|-------------|-----------|
| Llama 3.1 8B inference          | 8B params  | FP16      | 16 GB       | 1         |
| Llama 3.1 70B inference (vLLM)  | 70B params | FP16      | 40 GB       | 4         |
| Llama 3.1 405B inference        | 405B params| FP8       | 80 GB       | 8         |
| Stable Diffusion XL             | 6.6B params| FP16      | 24 GB       | 1         |
| GPT-NeoX 20B fine-tuning        | 20B params | BF16      | 80 GB       | 4         |
| BERT-large inference             | 340M params| FP32      | 4 GB        | 1         |

**Rationale:** VRAM is the most common bottleneck for ML workloads. Models that exceed available VRAM crash with CUDA OOM errors. Declarative VRAM requirements allow schedulers to prevent these failures.

#### `ext_ml_gpu_compute_capability` (string)

Minimum NVIDIA compute capability version, expressed as a `"major.minor"` string. When set, the backend MUST only dispatch the job to workers whose GPUs meet or exceed this version.

| Compute Capability | Architecture | Key Features                              |
|--------------------|--------------|--------------------------------------------|
| `7.0`              | Volta        | Tensor Cores (FP16)                        |
| `7.5`              | Turing       | INT8 Tensor Cores, RT Cores                |
| `8.0`              | Ampere       | BF16 Tensor Cores, TF32, sparsity          |
| `8.6`              | Ampere (GA10x)| Same as 8.0, lower core count             |
| `8.9`              | Ada Lovelace | FP8 Tensor Cores, Transformer Engine       |
| `9.0`              | Hopper       | FP8 training, Transformer Engine v2, NVLink4 |
| `10.0`             | Blackwell    | FP4 support, 5th-gen Tensor Cores          |

Example: A job using PyTorch's `torch.bfloat16` data type MUST set `ext_ml_gpu_compute_capability` to at least `"8.0"`, because BF16 tensor core acceleration requires Ampere or later.

**Rationale:** Compute capability determines which GPU instruction sets are available. A job compiled for Hopper FP8 will fail on a Turing GPU. Declarative compute capability constraints prevent these failures at scheduling time rather than at runtime.

#### `ext_ml_gpu_interconnect` (string)

Required interconnect between GPU devices. Valid values:

- `nvlink` -- Requires NVLink interconnect between all allocated GPUs. NVLink provides 600-900 GB/s bidirectional bandwidth, critical for tensor parallelism in large model training.
- `pcie` -- PCIe interconnect is acceptable. Suitable for data parallelism and smaller models.
- `any` -- No interconnect preference (default).

When `ext_ml_gpu_count` is `1`, this attribute SHOULD be ignored.

**Rationale:** Multi-GPU training performance is dominated by interconnect bandwidth. Tensor parallelism across PCIe (32 GB/s) is 20-30x slower than NVLink (900 GB/s), making NVLink-connected GPUs essential for large model training. Without this constraint, a scheduler might place a training job on PCIe-connected GPUs, causing training to be impractically slow.

### 3.3 TPU Requirements

| Attribute                | Type    | Required | Description                                           |
|--------------------------|---------|----------|-------------------------------------------------------|
| `ext_ml_tpu_type`        | string  | No       | TPU version: `v4`, `v5e`, `v5p`, `v6e`               |
| `ext_ml_tpu_topology`    | string  | No       | TPU pod slice topology (e.g., `"2x4"`, `"4x4"`)      |
| `ext_ml_tpu_chip_count`  | integer | No       | Number of TPU chips required                           |

#### Well-Known TPU Types

| Identifier | Vendor | Model            | HBM per Chip | Common Use Case               |
|------------|--------|------------------|--------------|-------------------------------|
| `v4`       | Google | TPU v4           | 32 GB        | Training, general inference    |
| `v5e`      | Google | TPU v5e          | 16 GB        | Cost-efficient inference       |
| `v5p`      | Google | TPU v5p          | 95 GB        | Large model training           |
| `v6e`      | Google | TPU v6e (Trillium)| 32 GB       | Next-gen training              |

#### TPU Topology

TPU pod slices are arranged in a 2D or 3D mesh topology. The `ext_ml_tpu_topology` attribute specifies the required shape. Examples:

- `"2x2"` -- 4 chips (single host)
- `"2x4"` -- 8 chips (suitable for Llama 3.1 8B training on v5e)
- `"4x4"` -- 16 chips (suitable for Llama 3.1 70B training on v5e)
- `"4x8"` -- 32 chips (large-scale training)

When `ext_ml_tpu_topology` is set, the backend MUST allocate a contiguous pod slice of the specified shape. Backends that cannot satisfy the topology requirement MUST reject the job.

**Rationale:** TPU interconnect topology directly affects training performance. A fragmented allocation of 8 TPU chips spread across non-adjacent hosts will have significantly higher inter-chip latency than a contiguous 2x4 slice. The topology constraint ensures the scheduler respects the physical layout requirements of the TPU mesh.

### 3.4 Memory and Storage

| Attribute             | Type   | Required | Description                                             |
|-----------------------|--------|----------|---------------------------------------------------------|
| `ext_ml_memory_gb`    | number | No       | Minimum system (host) memory in GB                       |
| `ext_ml_storage_gb`   | number | No       | Minimum scratch storage in GB                            |
| `ext_ml_shm_size_gb`  | number | No       | Minimum shared memory (`/dev/shm`) size in GB            |

#### `ext_ml_memory_gb` (number)

Minimum system memory required, independent of GPU VRAM. ML workloads often need substantial host memory for:
- Data loading and preprocessing pipelines
- KV cache for inference servers (vLLM, TGI)
- Gradient accumulation buffers during training
- Dataset caching (HuggingFace `datasets` library)

Example: Running vLLM with Llama 3.1 70B typically requires 64-128 GB of system RAM for the KV cache, even though the model weights reside in GPU VRAM.

**Rationale:** System memory exhaustion causes Linux OOM killer to terminate the process, losing all in-progress work. Declaring memory requirements enables schedulers to prevent OOM kills.

#### `ext_ml_shm_size_gb` (number)

Minimum shared memory size in gigabytes. PyTorch DataLoader with `num_workers > 0` uses `/dev/shm` for IPC. Docker containers default to 64 MB of shared memory, which is insufficient for most ML workloads.

When set, the backend SHOULD ensure the worker's shared memory allocation meets or exceeds this value. This is particularly important in containerized environments.

**Rationale:** The default 64 MB `/dev/shm` in Docker causes `Bus error` crashes in PyTorch DataLoader when using multiprocessing. This is one of the most common ML container deployment failures, and it is entirely preventable with a declarative constraint.

### 3.5 CPU Requirements

| Attribute           | Type    | Required | Description                          |
|---------------------|---------|----------|--------------------------------------|
| `ext_ml_cpu_cores`  | integer | No       | Minimum CPU cores required            |

CPU-only ML workloads (e.g., scikit-learn training, ONNX Runtime CPU inference, data preprocessing) SHOULD set `ext_ml_accelerator` to `cpu` and declare CPU cores and memory requirements.

---

## 4. Model Versioning

| Attribute                | Type   | Required | Description                                                  |
|--------------------------|--------|----------|--------------------------------------------------------------|
| `ext_ml_model_id`        | string | No       | Model identifier (e.g., `llama-3.1-70b`, `stable-diffusion-xl`) |
| `ext_ml_model_version`   | string | No       | Specific model version or tag                                 |
| `ext_ml_model_provider`  | string | No       | Model provider: `openai`, `anthropic`, `google`, `huggingface`, `replicate`, `local`, `custom` |
| `ext_ml_model_checksum`  | string | No       | Integrity checksum (e.g., `sha256:abc123def...`)              |
| `ext_ml_model_format`    | string | No       | Model format: `safetensors`, `gguf`, `onnx`, `torchscript`, `savedmodel`, `custom` |

#### `ext_ml_model_id` (string)

A human-readable identifier for the model. This is used for routing jobs to workers that have the model loaded, and for tracking which model version processed each job.

Workers SHOULD include a list of loaded model IDs in their capability advertisement. Backends SHOULD prefer dispatching jobs to workers that already have the requested model loaded, to avoid cold-start latency.

**Rationale:** Loading a 70B model from disk to GPU takes 60-120 seconds. Routing an inference request to a worker that already has the model loaded reduces p99 latency from minutes to milliseconds.

#### `ext_ml_model_version` (string)

A version tag for the model. Implementations SHOULD use semantic versioning (`1.0.0`, `2.1.0-beta`) but MAY use any string (e.g., Git SHA, date tag).

When both `ext_ml_model_id` and `ext_ml_model_version` are set, the backend MUST only dispatch the job to workers that have that specific model version loaded or accessible.

**Rationale:** Model version pinning prevents production incidents where a newly deployed model version causes quality regressions. Gradual rollout (sending 10% of traffic to v2.1, 90% to v2.0) requires precise version routing.

#### `ext_ml_model_checksum` (string)

An integrity checksum for the model weights file. Format: `{algorithm}:{hex-digest}` (e.g., `sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`).

Workers SHOULD verify the checksum of loaded model weights against this value. A checksum mismatch indicates model corruption or tampering and the worker MUST reject the job.

**Rationale:** Model weights are the largest and most critical artifacts in ML systems. Corrupted weights produce silently incorrect outputs. Checksum verification provides defense-in-depth against storage corruption and supply-chain attacks.

#### `ext_ml_model_format` (string)

The serialization format of the model weights. Valid values:

| Format         | Description                                      | Typical Use                |
|----------------|--------------------------------------------------|----------------------------|
| `safetensors`  | HuggingFace safe serialization                    | HuggingFace models         |
| `gguf`         | GGML Universal Format                             | llama.cpp, CPU inference   |
| `onnx`         | Open Neural Network Exchange                      | Cross-framework inference  |
| `torchscript`  | PyTorch JIT serialization                         | PyTorch production serving |
| `savedmodel`   | TensorFlow SavedModel                             | TensorFlow Serving         |
| `custom`       | Custom format                                     | Proprietary models         |

**Rationale:** Workers need to know the model format to select the appropriate runtime. A vLLM worker cannot load a GGUF model; a llama.cpp worker cannot load safetensors. Declaring the format enables correct routing.

---

## 5. Model Registry Integration

This section defines how OJS ML jobs reference models from external model registries. Registry integration enables reproducible deployments, model lineage tracking, and automated model pulling.

### 5.1 Registry Providers

| Attribute                    | Type   | Required | Description                                              |
|------------------------------|--------|----------|----------------------------------------------------------|
| `ext_ml_model_registry`      | string | No       | Registry provider: `huggingface`, `mlflow`, `wandb`, `s3`, `gcs`, `custom` |
| `ext_ml_model_registry_uri`  | string | No       | Full URI to the model artifact in the registry            |

#### Well-Known Registry Providers

| Provider       | Identifier    | URI Pattern                                          | Description                        |
|----------------|---------------|------------------------------------------------------|------------------------------------|
| HuggingFace    | `huggingface` | `hf://org/model-name@revision`                       | HuggingFace Hub models             |
| MLflow         | `mlflow`      | `mlflow://tracking-server/model-name/version`        | MLflow Model Registry              |
| Weights & Biases | `wandb`     | `wandb://entity/project/model:alias`                 | W&B Model Registry                 |
| Amazon S3      | `s3`          | `s3://bucket/path/to/model/`                         | S3-hosted model artifacts          |
| Google Cloud   | `gcs`         | `gs://bucket/path/to/model/`                         | GCS-hosted model artifacts         |
| Custom         | `custom`      | Implementation-defined                               | Private or proprietary registries  |

When `ext_ml_model_registry` is `huggingface`, backends SHOULD support automatic model resolution using the HuggingFace Hub API. When set to `mlflow`, backends SHOULD resolve models from the configured MLflow tracking server.

**Rationale:** ML teams use different model registries depending on their stack. HuggingFace Hub is the de facto standard for open-source models; MLflow is common in enterprise ML platforms; Weights & Biases is popular for experiment tracking. Supporting multiple registries enables OJS to integrate with existing ML infrastructure without requiring migration.

### 5.2 Registry URI Scheme

The `ext_ml_model_registry_uri` attribute provides a fully-qualified URI for fetching the model. The URI scheme depends on the registry provider:

```json
{
  "ext_ml_model_id": "meta-llama/Llama-3.1-70B-Instruct",
  "ext_ml_model_registry": "huggingface",
  "ext_ml_model_registry_uri": "hf://meta-llama/Llama-3.1-70B-Instruct@main",
  "ext_ml_model_format": "safetensors",
  "ext_ml_model_checksum": "sha256:e3b0c44298fc..."
}
```

Workers MUST resolve the model URI before loading. If the model is not already cached locally, the worker MUST fetch it from the registry. Workers SHOULD cache fetched models to avoid redundant downloads.

**Rationale:** A 70B model download (~140 GB) takes 10-30 minutes. Explicit registry URIs enable workers to pre-fetch models and maintain local caches, reducing cold-start latency from minutes to seconds.

### 5.3 Model Resolution

When both `ext_ml_model_id` and `ext_ml_model_version` are set without a `ext_ml_model_registry_uri`, the backend SHOULD resolve the model URI from the registry provider. Resolution order:

1. Check if the worker already has the model loaded (via `models_loaded` in worker capabilities).
2. Check the worker's local model cache.
3. Resolve from the configured registry using `ext_ml_model_id` + `ext_ml_model_version`.
4. If resolution fails, transition the job to `retryable` with a descriptive error.

When `ext_ml_model_checksum` is set, the worker MUST verify the checksum of the resolved model before loading. A checksum mismatch MUST cause the job to fail with a descriptive error.

**Rationale:** Automatic model resolution reduces boilerplate in job definitions. Teams should be able to say "run inference with Llama 3.1 70B" without constructing a full registry URI. The resolution chain ensures correctness while minimizing latency.

---

## 6. Compute Constraints

| Attribute                  | Type    | Required | Description                                               |
|----------------------------|---------|----------|-----------------------------------------------------------|
| `ext_ml_max_tokens`        | integer | No       | Maximum tokens for generation tasks                        |
| `ext_ml_max_batch_size`    | integer | No       | Maximum batch size for inference                           |
| `ext_ml_timeout_seconds`   | integer | No       | ML-specific timeout (overrides job timeout)                |
| `ext_ml_runtime`           | string  | No       | ML runtime: `pytorch`, `tensorflow`, `onnx`, `triton`, `vllm`, `tgi`, `custom` |
| `ext_ml_precision`         | string  | No       | Compute precision: `fp32`, `fp16`, `bf16`, `fp8`, `int8`, `int4` |
| `ext_ml_distributed_strategy` | string | No    | Distribution strategy: `none`, `data_parallel`, `tensor_parallel`, `pipeline_parallel`, `fsdp`, `deepspeed` |

#### `ext_ml_timeout_seconds` (integer)

When present, this timeout overrides the standard OJS job timeout for this job. ML workloads have highly variable execution times: a classification inference takes milliseconds, while a fine-tuning run may take hours.

**Rationale:** The standard OJS timeout is designed for typical background jobs (seconds to minutes). ML training jobs routinely run for hours or days. A separate ML-specific timeout prevents premature job termination while still allowing the standard timeout for non-ML jobs on the same backend.

#### `ext_ml_precision` (string)

The numerical precision for model computation. This affects both performance and memory usage:

| Precision | Bytes per Param | Typical Use                  | Min Compute Capability |
|-----------|----------------|------------------------------|------------------------|
| `fp32`    | 4              | Research, validation          | 7.0                    |
| `fp16`    | 2              | Standard inference            | 7.0                    |
| `bf16`    | 2              | Training (better range)       | 8.0                    |
| `fp8`     | 1              | Efficient training (Hopper+)  | 8.9                    |
| `int8`    | 1              | Quantized inference           | 7.5                    |
| `int4`    | 0.5            | Highly quantized inference    | 7.5                    |

When `ext_ml_precision` requires a minimum compute capability and `ext_ml_gpu_compute_capability` is not set, the backend SHOULD infer the minimum compute capability from the precision requirement.

**Rationale:** Precision determines VRAM usage (FP16 uses half the memory of FP32) and performance (FP8 on Hopper provides 2x throughput over FP16). Declaring precision allows schedulers to validate hardware compatibility and estimate VRAM requirements.

#### `ext_ml_distributed_strategy` (string)

The parallelism strategy for multi-GPU/multi-node training:

| Strategy            | Description                                               | When to Use                      |
|---------------------|-----------------------------------------------------------|----------------------------------|
| `none`              | Single-device execution                                    | Small models, inference          |
| `data_parallel`     | Replicate model, shard data                                | Model fits in single GPU VRAM    |
| `tensor_parallel`   | Shard model tensors across devices                         | Large models, low-latency        |
| `pipeline_parallel` | Shard model layers across devices                          | Very large models, throughput    |
| `fsdp`              | Fully Sharded Data Parallel                                | Large models, memory-efficient   |
| `deepspeed`         | DeepSpeed ZeRO stages                                     | Very large training runs         |

**Rationale:** The distribution strategy affects how GPU interconnect bandwidth is utilized and whether GPU-to-GPU communication is latency-sensitive. Tensor parallelism requires NVLink; data parallelism works over PCIe. Declaring the strategy enables the scheduler to enforce appropriate interconnect constraints.

---

## 7. Node Affinity and Scheduling

Node affinity enables fine-grained control over which worker nodes can execute a job. This is essential for ML workloads that have specific hardware, software, or locality requirements.

### 7.1 Node Selectors

| Attribute                  | Type   | Required | Description                                           |
|----------------------------|--------|----------|-------------------------------------------------------|
| `ext_ml_node_selector`     | object | No       | Key-value map of labels that worker nodes MUST match   |

A node selector is a set of equality constraints. A worker MUST match ALL key-value pairs to be eligible for the job.

```json
{
  "ext_ml_node_selector": {
    "gpu_type": "nvidia-a100",
    "region": "us-east-1",
    "gpu_memory": "80gb"
  }
}
```

**Rationale:** Node selectors provide the simplest and most predictable scheduling constraint. They are analogous to Kubernetes `nodeSelector` and are sufficient for the majority of ML scheduling use cases.

### 7.2 Affinity Rules

| Attribute              | Type   | Required | Description                                                  |
|------------------------|--------|----------|--------------------------------------------------------------|
| `ext_ml_affinity`      | object | No       | Scheduling affinity rules with required and preferred lists   |

Affinity rules provide more expressive scheduling constraints than node selectors:

```json
{
  "ext_ml_affinity": {
    "required": [
      {
        "key": "gpu_type",
        "operator": "In",
        "values": ["nvidia-a100", "nvidia-h100"]
      },
      {
        "key": "compute_capability",
        "operator": "Gte",
        "values": ["8.0"]
      }
    ],
    "preferred": [
      {
        "key": "gpu_interconnect",
        "operator": "In",
        "values": ["nvlink"],
        "weight": 80
      },
      {
        "key": "region",
        "operator": "In",
        "values": ["us-east-1"],
        "weight": 20
      }
    ]
  }
}
```

#### Operators

| Operator       | Semantics                                                       |
|----------------|-----------------------------------------------------------------|
| `In`           | Worker label value MUST be in the specified set                  |
| `NotIn`        | Worker label value MUST NOT be in the specified set              |
| `Exists`       | Worker MUST have the label key (value is irrelevant)             |
| `DoesNotExist` | Worker MUST NOT have the label key                               |
| `Gt`           | Worker label value MUST be greater than the specified value      |
| `Gte`          | Worker label value MUST be greater than or equal to              |
| `Lt`           | Worker label value MUST be less than the specified value         |
| `Lte`          | Worker label value MUST be less than or equal to                 |

#### Required vs. Preferred

- **Required** rules are hard constraints. A backend MUST NOT dispatch a job to a worker that violates any required rule. If no worker satisfies all required rules, the job MUST remain in the `available` state until a matching worker becomes available.
- **Preferred** rules are soft constraints with weights. A backend SHOULD prefer workers that satisfy more preferred rules, weighted by the `weight` field (0-100). Preferred rules MUST NOT prevent job dispatch if no worker satisfies them.

**Rationale:** The required/preferred split mirrors Kubernetes affinity semantics, which are well-understood by ML infrastructure teams. Required rules prevent hardware-incompatible placement; preferred rules enable optimization (e.g., data locality, cost preference) without blocking scheduling.

### 7.3 Anti-Affinity

Anti-affinity rules prevent co-location of specific jobs on the same worker. This is useful for:
- Fault isolation: ensure replicas of the same model run on different physical hosts
- Resource isolation: prevent memory-intensive jobs from competing on the same node

Anti-affinity rules use the same operator syntax as affinity rules but are specified under `ext_ml_anti_affinity`:

```json
{
  "ext_ml_anti_affinity": {
    "required": [
      {
        "key": "job_type",
        "operator": "In",
        "values": ["ml.train.large"]
      }
    ]
  }
}
```

**Rationale:** When serving a model with multiple replicas for high availability, all replicas should run on different physical machines. If all replicas share a host and that host fails, the service experiences total downtime. Anti-affinity rules enforce physical distribution.

---

## 8. Resource Priority and Preemption

### 8.1 Priority Classes

| Attribute                | Type   | Required | Description                                                |
|--------------------------|--------|----------|------------------------------------------------------------|
| `ext_ml_priority_class`  | string | No       | Resource priority: `spot`, `on-demand`, `reserved`          |

Priority classes determine how a job interacts with resource allocation and preemption:

| Priority Class | Preemptible | Cost     | SLA                                       |
|----------------|------------|----------|-------------------------------------------|
| `spot`         | Yes        | Lowest   | May be interrupted at any time              |
| `on-demand`    | No*        | Medium   | Runs to completion unless explicitly cancelled |
| `reserved`     | No         | Highest  | Guaranteed capacity, lowest queue wait time  |

\* `on-demand` jobs MAY be preempted by `reserved` jobs if the backend implements priority-based preemption.

A backend that supports preemption MUST implement the following priority ordering: `reserved` > `on-demand` > `spot`. A higher-priority job MAY preempt a lower-priority job when insufficient resources are available.

**Rationale:** Cloud GPU instances are expensive ($2-$32/hour per GPU). Spot/preemptible instances offer 60-90% cost savings for fault-tolerant workloads like hyperparameter sweeps. Priority classes enable cost optimization while ensuring production inference traffic gets guaranteed resources.

### 8.2 Preemption Semantics

| Attribute                         | Type    | Required | Description                                                     |
|-----------------------------------|---------|----------|-----------------------------------------------------------------|
| `ext_ml_preemptible`              | boolean | No       | Whether this job can be preempted (default: derived from priority class) |
| `ext_ml_preemption_grace_period_s`| integer | No       | Seconds of warning before preemption (default: 30)               |
| `ext_ml_checkpoint_on_preempt`    | boolean | No       | Whether to checkpoint before preemption (default: false)          |

When a job is preempted:

1. The backend MUST notify the worker at least `ext_ml_preemption_grace_period_s` seconds before forcibly terminating the job.
2. If `ext_ml_checkpoint_on_preempt` is `true`, the worker SHOULD save a checkpoint during the grace period.
3. After the grace period, if the worker has not voluntarily released the job, the backend MUST transition the job to `retryable` state.
4. When the preempted job is retried, it SHOULD resume from the last checkpoint if one exists.

**Rationale:** Ungraceful preemption loses all in-progress work. A training job that has run for 2 hours and is preempted without checkpointing must restart from scratch. The grace period and checkpoint-on-preempt mechanism minimize wasted compute.

### 8.3 Resource Reservation

| Attribute                    | Type    | Required | Description                                                    |
|------------------------------|---------|----------|----------------------------------------------------------------|
| `ext_ml_reservation_id`      | string  | No       | Identifier of a pre-allocated resource reservation              |
| `ext_ml_reservation_timeout_s`| integer| No       | Maximum seconds a reservation is held before release            |

Resource reservations allow jobs to claim GPU resources before they are ready to execute. This is useful for:
- **Workflow steps**: Reserve GPUs for the training step while the data preprocessing step is running
- **Scheduled training**: Reserve a GPU cluster for a nightly training run
- **SLA guarantees**: Ensure inference capacity is always available for production traffic

When `ext_ml_reservation_id` is set, the backend MUST verify that the referenced reservation exists and has sufficient unreleased capacity. The backend MUST NOT dispatch the job to a worker outside the reserved capacity pool.

**Rationale:** Without reservations, a multi-step ML pipeline risks GPU starvation: the data preprocessing completes, but by the time the training step is ready, all GPUs have been claimed by other jobs. Reservations provide capacity guarantees for pipelines.

### 8.4 Priority Escalation

| Attribute                          | Type    | Required | Description                                                      |
|------------------------------------|---------|----------|------------------------------------------------------------------|
| `ext_ml_priority_escalation`       | boolean | No       | Whether the job's priority can be escalated over time (default: false) |
| `ext_ml_escalation_after_s`        | integer | No       | Seconds in queue before priority escalation begins (default: 3600)   |
| `ext_ml_escalation_target_class`   | string  | No       | Target priority class after escalation (e.g., `on-demand`)           |

When a job with `ext_ml_priority_class` set to `spot` has been in the `available` state for longer than `ext_ml_escalation_after_s`, the backend MAY escalate its priority to `ext_ml_escalation_target_class`. This prevents starvation of low-priority jobs during sustained high-priority demand.

**Rationale:** A spot training job that waits indefinitely for GPU resources is worse than paying on-demand prices. Priority escalation provides a configurable safety valve that balances cost optimization with job completion guarantees. Without escalation, spot jobs can starve for days during GPU-constrained periods.

---

## 9. Checkpoint and Resume Semantics

### 9.1 Checkpoint Configuration

| Attribute                    | Type    | Required | Description                                                        |
|------------------------------|---------|----------|--------------------------------------------------------------------|
| `ext_ml_checkpoint_enabled`  | boolean | No       | Whether periodic checkpointing is enabled (default: false)          |
| `ext_ml_checkpoint_interval_s`| integer| No       | Checkpoint interval in seconds (default: 300)                       |
| `ext_ml_checkpoint_storage_uri`| string| No       | URI for checkpoint storage (e.g., `s3://bucket/checkpoints/`)       |
| `ext_ml_checkpoint_max_count`| integer | No       | Maximum checkpoints to retain (FIFO eviction, default: 3)           |

Checkpointing saves periodic snapshots of job progress, enabling:
- **Preemption recovery**: Resume from the last checkpoint after spot instance interruption
- **Failure recovery**: Resume training after hardware failure without losing hours of compute
- **Evaluation**: Inspect intermediate training results without waiting for completion

Checkpoint data MUST include:
- Job ID
- Epoch and/or global step number
- Model weights storage key (URI or path)
- Training metrics at checkpoint time (loss, accuracy, etc.)
- Timestamp

Workers MUST save checkpoints to the URI specified in `ext_ml_checkpoint_storage_uri`. Backends SHOULD store checkpoint metadata (epoch, step, loss, storage key) in the job's metadata for retrieval via the INFO operation.

### 9.2 Checkpoint Lifecycle

A checkpoint progresses through the following states:

1. **Initiated**: The worker begins serializing model state.
2. **Uploading**: Model weights and optimizer state are being written to checkpoint storage.
3. **Committed**: The checkpoint metadata has been recorded in the job's metadata. The backend MUST update the job's `last_checkpoint` metadata field atomically.
4. **Expired**: The checkpoint has been evicted by FIFO retention policy (`ext_ml_checkpoint_max_count`).

Checkpoint metadata stored in the job MUST use the following schema:

```json
{
  "last_checkpoint": {
    "job_id": "019502a4-5678-7abc-8000-000000000002",
    "epoch": 42,
    "step": 126000,
    "loss": 0.0234,
    "metrics": {"accuracy": 0.947, "learning_rate": 0.0001},
    "storage_key": "s3://checkpoints/train-70b/epoch-42/",
    "created_at": "2026-02-19T12:00:00Z"
  }
}
```

Workers MUST NOT consider a checkpoint committed until both the model weights have been fully written to storage AND the metadata has been recorded in the job. Partial checkpoints (weights written but metadata not recorded) MUST be treated as non-existent on resume.

**Rationale:** Atomic checkpoint commits prevent a failure during checkpoint upload from leaving the job in an inconsistent state. If a worker crashes after uploading weights but before recording metadata, the next run will resume from the previous valid checkpoint rather than attempting to load a partial one.

### 9.3 Resume Protocol

When a checkpointed job is resumed (due to preemption, failure, or manual retry), the worker MUST follow this protocol:

1. Read the job's `last_checkpoint` metadata field.
2. If `last_checkpoint` exists and contains a valid `storage_key`:
   a. Download the checkpoint from `storage_key`.
   b. Restore model weights, optimizer state, and training step counter.
   c. Resume training from `step + 1` (or `epoch + 1` for epoch-based training).
   d. Log the resume event with the checkpoint epoch/step for observability.
3. If `last_checkpoint` does not exist or the checkpoint is invalid:
   a. Start training from the beginning.
   b. Log a warning indicating no valid checkpoint was found.

Workers MUST NOT restart from epoch 0 if a valid checkpoint exists. Restarting from scratch wastes all compute invested in prior epochs.

**Rationale:** ML training runs are the most expensive computing workloads in existence. A single training run can cost $1-10M in GPU hours. Losing even a few hours of progress due to hardware failure or preemption is unacceptable. The resume protocol ensures that progress is never lost when checkpoints are available.

### 9.4 Checkpoint Storage Backends

Checkpoint storage URIs MUST follow standard URI schemes. Supported schemes:

| Scheme     | Example                                    | Description               |
|------------|--------------------------------------------|---------------------------|
| `s3://`    | `s3://bucket/checkpoints/run-id/`          | Amazon S3                 |
| `gs://`    | `gs://bucket/checkpoints/run-id/`          | Google Cloud Storage      |
| `az://`    | `az://container/checkpoints/run-id/`       | Azure Blob Storage        |
| `file://`  | `file:///mnt/nfs/checkpoints/run-id/`      | Local or NFS filesystem   |

Workers SHOULD support at least `s3://` and `file://` schemes. The checkpoint storage URI MUST include a trailing slash to indicate a directory prefix.

**Rationale:** Different organizations use different cloud storage providers. Supporting multiple schemes ensures OJS checkpointing works across cloud environments and on-premises deployments without requiring a storage abstraction layer.

---

## 10. Queue-Level Resource Constraints

Queues MAY be configured with default and maximum resource constraints. This enables cluster administrators to enforce resource policies without relying on job producers to set correct values.

### 10.1 Queue Resource Defaults

```json
{
  "queue": "gpu-inference",
  "config": {
    "ml_defaults": {
      "ext_ml_accelerator": "gpu",
      "ext_ml_gpu_count": 1,
      "ext_ml_timeout_seconds": 60,
      "ext_ml_priority_class": "on-demand"
    }
  }
}
```

When a job is enqueued to a queue with `ml_defaults`, any `ext_ml_*` attribute not explicitly set by the job producer MUST be filled with the queue's default value.

**Rationale:** Inference queues have predictable resource requirements. Setting defaults at the queue level reduces boilerplate and prevents misconfiguration (e.g., an inference job accidentally requesting 8 GPUs).

### 10.2 Queue Resource Limits

```json
{
  "queue": "gpu-inference",
  "config": {
    "ml_limits": {
      "max_gpu_count": 4,
      "max_gpu_memory_gb": 80,
      "max_memory_gb": 256,
      "max_timeout_seconds": 3600,
      "allowed_gpu_types": ["nvidia-a100", "nvidia-h100", "nvidia-l4"],
      "allowed_priority_classes": ["on-demand", "reserved"],
      "max_concurrent_gpu_jobs": 100,
      "max_total_gpus": 64
    }
  }
}
```

A backend MUST reject (with HTTP 422 or gRPC `INVALID_ARGUMENT`) any job whose `ext_ml_*` attributes exceed the queue's resource limits. Queue limits enforce Section 10 constraints.

**Rationale:** Without queue-level limits, a single misconfigured job requesting 64 GPUs could starve all other jobs. Queue limits provide a safety net that prevents resource exhaustion and enables multi-tenant resource governance.

### 10.3 Queue GPU Budget

Queues MAY enforce a total GPU budget that limits the aggregate number of GPUs used by all active jobs in the queue:

| Config Field             | Type    | Description                                              |
|--------------------------|---------|----------------------------------------------------------|
| `max_concurrent_gpu_jobs`| integer | Maximum number of GPU jobs that can be active simultaneously |
| `max_total_gpus`         | integer | Maximum aggregate GPU count across all active jobs         |

When the GPU budget is exhausted, new GPU jobs MUST remain in the `available` state until budget becomes available. The backend MUST NOT reject budget-exceeded jobs; it MUST queue them.

**Rationale:** GPU clusters are shared resources. Without aggregate limits, a burst of training jobs could consume all GPUs, starving inference traffic. Queue-level budgets ensure fair resource allocation across workload types.

---

## 11. Worker Capability Advertisement

Workers MUST advertise their compute capabilities when connecting to a backend that supports ML resource matching. Capabilities are included in FETCH requests and heartbeats.

```json
{
  "worker_id": "gpu-worker-01",
  "capabilities": {
    "accelerator": "gpu",
    "gpu": {
      "type": "nvidia-a100",
      "count": 8,
      "memory_gb": 80,
      "compute_capability": "8.0",
      "interconnect": "nvlink"
    },
    "cpu_cores": 96,
    "memory_gb": 1024,
    "storage_gb": 8000,
    "shm_size_gb": 256,
    "models_loaded": [
      {"model_id": "llama-3.1-70b", "model_version": "v2.1", "model_format": "safetensors"},
      {"model_id": "llama-3.1-8b", "model_version": "v2.1", "model_format": "safetensors"}
    ],
    "runtimes": ["vllm", "pytorch"],
    "labels": {
      "region": "us-east-1",
      "zone": "us-east-1a",
      "instance_type": "p4d.24xlarge",
      "cluster": "ml-training-prod"
    }
  }
}
```

Backends that support this extension MUST match job requirements to worker capabilities:

1. **Hard constraints**: `ext_ml_gpu_type`, `ext_ml_gpu_count`, `ext_ml_gpu_memory_gb`, `ext_ml_gpu_compute_capability`, `ext_ml_tpu_type`, and node selector labels are hard constraints. The backend MUST NOT dispatch a job to a worker that fails any hard constraint.

2. **Soft constraints**: Preferred affinity rules and model locality are soft constraints. The backend SHOULD prefer workers that satisfy soft constraints but MUST NOT block dispatch if no worker satisfies them.

3. **Model locality**: When `ext_ml_model_id` is set, the backend SHOULD prefer workers that have the model loaded (listed in `models_loaded`), to minimize cold-start latency.

**Rationale:** Resource-aware scheduling is the core value proposition of this extension. Without capability matching, ML jobs would be dispatched to incompatible workers, causing immediate failures or severe performance degradation.

---

## 12. Workflow Integration

ML workloads naturally form pipelines: data preparation feeds training, training feeds evaluation, evaluation feeds deployment. The OJS Workflow Primitives (chain, group, batch) compose with ML resource requirements to express these pipelines.

### 12.1 Training Pipeline Example

A typical ML training pipeline as an OJS workflow chain:

```json
{
  "workflow_type": "chain",
  "id": "019502a4-0001-7abc-8000-000000000001",
  "steps": [
    {
      "type": "ml.data_prep",
      "queue": "cpu-workers",
      "args": [{"dataset": "s3://data/training-v3.parquet", "output": "s3://data/processed/"}],
      "ext_ml_accelerator": "cpu",
      "ext_ml_cpu_cores": 16,
      "ext_ml_memory_gb": 64,
      "ext_ml_storage_gb": 500,
      "ext_ml_timeout_seconds": 3600
    },
    {
      "type": "ml.train",
      "queue": "gpu-training",
      "args": [{"dataset": "s3://data/processed/", "config": "s3://configs/llama-finetune.yaml"}],
      "ext_ml_accelerator": "gpu",
      "ext_ml_gpu_type": "nvidia-h100",
      "ext_ml_gpu_count": 8,
      "ext_ml_gpu_memory_gb": 80,
      "ext_ml_gpu_interconnect": "nvlink",
      "ext_ml_memory_gb": 512,
      "ext_ml_model_id": "llama-3.1-70b",
      "ext_ml_model_version": "v2.1-finetune",
      "ext_ml_precision": "bf16",
      "ext_ml_distributed_strategy": "fsdp",
      "ext_ml_runtime": "pytorch",
      "ext_ml_timeout_seconds": 86400,
      "ext_ml_priority_class": "reserved",
      "ext_ml_checkpoint_enabled": true,
      "ext_ml_checkpoint_interval_s": 600,
      "ext_ml_checkpoint_storage_uri": "s3://checkpoints/llama-finetune/"
    },
    {
      "type": "ml.evaluate",
      "queue": "gpu-inference",
      "args": [{"model": "s3://models/llama-finetune-latest/", "eval_set": "s3://data/eval/"}],
      "ext_ml_accelerator": "gpu",
      "ext_ml_gpu_type": "nvidia-a100",
      "ext_ml_gpu_count": 2,
      "ext_ml_gpu_memory_gb": 80,
      "ext_ml_model_id": "llama-3.1-70b",
      "ext_ml_model_version": "v2.1-finetune",
      "ext_ml_runtime": "vllm",
      "ext_ml_timeout_seconds": 7200
    },
    {
      "type": "ml.deploy",
      "queue": "deployment",
      "args": [{"model_uri": "s3://models/llama-finetune-latest/", "canary_percentage": 10}],
      "ext_ml_accelerator": "cpu",
      "ext_ml_timeout_seconds": 300
    }
  ]
}
```

This chain expresses: **data_prep** (CPU, 16 cores, 64 GB RAM) then **train** (8x H100, NVLink, FSDP, checkpointing) then **evaluate** (2x A100, vLLM) then **deploy** (CPU). Each step has independent resource requirements. The backend schedules each step on appropriate workers as the chain progresses.

### 12.2 Multi-Model Inference Example

A parallel inference pipeline using a workflow group:

```json
{
  "workflow_type": "group",
  "id": "019502a4-0002-7abc-8000-000000000002",
  "jobs": [
    {
      "type": "ml.inference",
      "queue": "gpu-inference",
      "args": [{"prompt": "Summarize this document", "document_id": "doc-456"}],
      "ext_ml_model_id": "llama-3.1-70b",
      "ext_ml_gpu_type": "nvidia-a100",
      "ext_ml_gpu_count": 4,
      "ext_ml_gpu_memory_gb": 80,
      "ext_ml_runtime": "vllm",
      "ext_ml_max_tokens": 4096,
      "ext_ml_precision": "fp16"
    },
    {
      "type": "ml.inference",
      "queue": "gpu-inference",
      "args": [{"image_prompt": "A photo of a sunset over mountains", "style": "photorealistic"}],
      "ext_ml_model_id": "stable-diffusion-xl",
      "ext_ml_gpu_type": "nvidia-l4",
      "ext_ml_gpu_count": 1,
      "ext_ml_gpu_memory_gb": 24,
      "ext_ml_runtime": "pytorch",
      "ext_ml_precision": "fp16"
    },
    {
      "type": "ml.inference",
      "queue": "gpu-inference",
      "args": [{"audio_file": "s3://audio/meeting-recording.wav"}],
      "ext_ml_model_id": "whisper-large-v3",
      "ext_ml_gpu_type": "nvidia-t4",
      "ext_ml_gpu_count": 1,
      "ext_ml_gpu_memory_gb": 16,
      "ext_ml_runtime": "pytorch",
      "ext_ml_precision": "fp16"
    }
  ]
}
```

All three inference jobs run in parallel on different GPU types matching their model requirements.

### 12.3 Resource Propagation in Workflows

When a workflow step does not specify `ext_ml_*` attributes, it MUST NOT inherit resource requirements from other steps. Each step in a workflow is an independent job with its own resource requirements.

**Rationale:** ML pipeline steps have wildly different resource profiles. A data preprocessing step needs CPUs and memory; a training step needs GPUs and NVLink; an evaluation step needs fewer GPUs. Inheriting the training step's 8x H100 requirement for a CPU-only preprocessing step would waste resources and delay scheduling.

However, workflows MAY define shared metadata (e.g., experiment ID, run ID) that propagates to all steps. This metadata is set at the workflow level and is distinct from resource requirements.

---

## 13. Job Envelope Examples

### 13.1 LLM Inference Job

```json
{
  "id": "019502a4-1234-7abc-8000-000000000001",
  "type": "ml.inference",
  "queue": "gpu-inference",
  "args": [{"prompt": "Summarize this document", "document_id": "doc-456"}],
  "ext_ml_accelerator": "gpu",
  "ext_ml_gpu_type": "nvidia-a100",
  "ext_ml_gpu_count": 2,
  "ext_ml_gpu_memory_gb": 80,
  "ext_ml_model_id": "llama-3.1-70b",
  "ext_ml_model_version": "v2.1",
  "ext_ml_model_provider": "huggingface",
  "ext_ml_model_format": "safetensors",
  "ext_ml_runtime": "vllm",
  "ext_ml_max_tokens": 4096,
  "ext_ml_precision": "fp16",
  "ext_ml_priority_class": "on-demand",
  "ext_ml_timeout_seconds": 60
}
```

### 13.2 Large-Scale Training Job

```json
{
  "id": "019502a4-5678-7abc-8000-000000000002",
  "type": "ml.train",
  "queue": "gpu-training",
  "args": [{"config_uri": "s3://configs/train-70b.yaml"}],
  "ext_ml_accelerator": "gpu",
  "ext_ml_gpu_type": "nvidia-h100",
  "ext_ml_gpu_count": 8,
  "ext_ml_gpu_memory_gb": 80,
  "ext_ml_gpu_compute_capability": "9.0",
  "ext_ml_gpu_interconnect": "nvlink",
  "ext_ml_memory_gb": 1024,
  "ext_ml_storage_gb": 2000,
  "ext_ml_shm_size_gb": 256,
  "ext_ml_model_id": "llama-3.1-70b",
  "ext_ml_model_version": "v2.1-finetune",
  "ext_ml_model_format": "safetensors",
  "ext_ml_runtime": "pytorch",
  "ext_ml_precision": "bf16",
  "ext_ml_distributed_strategy": "fsdp",
  "ext_ml_timeout_seconds": 172800,
  "ext_ml_priority_class": "reserved",
  "ext_ml_checkpoint_enabled": true,
  "ext_ml_checkpoint_interval_s": 600,
  "ext_ml_checkpoint_storage_uri": "s3://checkpoints/train-70b/",
  "ext_ml_checkpoint_max_count": 5,
  "ext_ml_preemptible": false,
  "ext_ml_node_selector": {
    "cluster": "ml-training-prod",
    "instance_type": "p5.48xlarge"
  }
}
```

### 13.3 TPU Training Job

```json
{
  "id": "019502a4-9abc-7abc-8000-000000000003",
  "type": "ml.train",
  "queue": "tpu-training",
  "args": [{"config_uri": "gs://configs/t5-xxl-tpu.yaml"}],
  "ext_ml_accelerator": "tpu",
  "ext_ml_tpu_type": "v5e",
  "ext_ml_tpu_topology": "4x4",
  "ext_ml_tpu_chip_count": 16,
  "ext_ml_memory_gb": 256,
  "ext_ml_model_id": "t5-xxl",
  "ext_ml_model_version": "v1.0",
  "ext_ml_runtime": "tensorflow",
  "ext_ml_precision": "bf16",
  "ext_ml_timeout_seconds": 86400,
  "ext_ml_priority_class": "reserved",
  "ext_ml_checkpoint_enabled": true,
  "ext_ml_checkpoint_interval_s": 900,
  "ext_ml_checkpoint_storage_uri": "gs://checkpoints/t5-xxl/"
}
```

### 13.4 Cost-Optimized Hyperparameter Sweep

```json
{
  "id": "019502a4-def0-7abc-8000-000000000004",
  "type": "ml.train",
  "queue": "gpu-spot",
  "args": [{"config_uri": "s3://configs/sweep-lr-0.001.yaml", "sweep_id": "sweep-42"}],
  "ext_ml_accelerator": "gpu",
  "ext_ml_gpu_type": "nvidia-a100",
  "ext_ml_gpu_count": 4,
  "ext_ml_gpu_memory_gb": 40,
  "ext_ml_memory_gb": 128,
  "ext_ml_model_id": "resnet50",
  "ext_ml_model_version": "v1.0",
  "ext_ml_runtime": "pytorch",
  "ext_ml_precision": "fp16",
  "ext_ml_distributed_strategy": "data_parallel",
  "ext_ml_timeout_seconds": 14400,
  "ext_ml_priority_class": "spot",
  "ext_ml_preemptible": true,
  "ext_ml_preemption_grace_period_s": 60,
  "ext_ml_checkpoint_on_preempt": true,
  "ext_ml_checkpoint_enabled": true,
  "ext_ml_checkpoint_interval_s": 300,
  "ext_ml_checkpoint_storage_uri": "s3://checkpoints/sweep-42/"
}
```

### 13.5 CPU-Only Inference Job

```json
{
  "id": "019502a4-1111-7abc-8000-000000000005",
  "type": "ml.inference",
  "queue": "cpu-inference",
  "args": [{"text": "Classify this customer support ticket", "ticket_id": "TK-12345"}],
  "ext_ml_accelerator": "cpu",
  "ext_ml_cpu_cores": 4,
  "ext_ml_memory_gb": 8,
  "ext_ml_model_id": "distilbert-base",
  "ext_ml_model_version": "v1.2",
  "ext_ml_model_format": "onnx",
  "ext_ml_runtime": "onnx",
  "ext_ml_max_batch_size": 32,
  "ext_ml_timeout_seconds": 10,
  "ext_ml_priority_class": "on-demand"
}
```

---

## 14. Interaction with Other Extensions

### 14.1 Priority Extension

The `ext_ml_priority_class` attribute MAY influence job priority scoring. Backends SHOULD map priority classes to priority scores: `reserved` > `on-demand` > `spot`. When the Priority Extension is also used, the `ext_ml_priority_class` SHOULD be combined with the job's numeric priority to determine final scheduling order.

### 14.2 Retry Extension

ML jobs have specific retry considerations:

- Jobs with `ext_ml_priority_class` set to `spot` SHOULD have retry policies that account for preemption. The preemption event is not a job failure -- it is a scheduling event. Backends MUST NOT count preemption-triggered retries against `max_attempts`.

**Rationale:** A spot job that is preempted 3 times and then succeeds on the 4th attempt has not "failed" 3 times. Counting preemptions as failures would exhaust retry budget and discard jobs that would otherwise complete successfully.

- Jobs with `ext_ml_checkpoint_enabled` set to `true` SHOULD have `on_exhaustion` set to `dead_letter` rather than `discard`, so that checkpoint data is preserved for manual recovery.

### 14.3 Timeout Extension

`ext_ml_timeout_seconds` overrides the standard job timeout when present. Backends MUST use `ext_ml_timeout_seconds` as the execution timeout for the job, ignoring the standard timeout field.

### 14.4 Queue Configuration Extension

Queue-level ML resource defaults and limits (Section 9) compose with the Queue Configuration Extension. When both are configured, ML-specific limits MUST be enforced in addition to general queue limits.

### 14.5 Workflow Extension

ML resource attributes on workflow steps are independent of each other (Section 12.3). Workflow-level metadata (experiment ID, run ID, dataset version) MAY be propagated to all steps via the workflow's `meta` field.

### 14.6 Unique Jobs Extension

ML inference jobs MAY use the Unique Jobs Extension for request deduplication. When two identical inference requests arrive within the uniqueness window, the second request SHOULD receive the result of the first rather than consuming additional GPU resources.

**Rationale:** GPU inference is expensive. Deduplicating identical requests (e.g., from retry storms or duplicate webhook deliveries) prevents wasted compute.

---

## 15. Security Considerations

### 15.1 Resource Exhaustion

- Resource requirements MUST be validated against configurable upper bounds to prevent resource exhaustion attacks. A malicious client requesting 1000 GPUs MUST be rejected.
- GPU count and memory values SHOULD have configurable maximum limits at the queue level (Section 9.2).
- Backends SHOULD implement rate limiting on job submissions to GPU queues.

### 15.2 Model Security

- Model IDs SHOULD be validated against an allow-list when configured. Permitting arbitrary model IDs could allow workers to load untrusted models.
- Model checksums (`ext_ml_model_checksum`) SHOULD be verified by workers before loading model weights. This prevents model substitution attacks.
- Model storage URIs MUST be validated to prevent path traversal and SSRF attacks.

### 15.3 Checkpoint Security

- Checkpoint storage URIs MUST be validated against an allow-list of permitted storage prefixes.
- Checkpoint data MAY contain model weights and training data. Backends SHOULD encrypt checkpoint storage at rest.
- Workers MUST NOT restore checkpoints from untrusted sources.

### 15.4 Node Selector Injection

- Node selector values MUST be sanitized. A malicious client MUST NOT be able to inject labels that bypass scheduling constraints.
- Backends SHOULD restrict which node selector keys are available to job producers. Administrative labels (e.g., `cost_center`, `security_zone`) SHOULD NOT be settable by job producers.

---

## 16. Prior Art

| System                      | Approach                                                                 |
|-----------------------------|--------------------------------------------------------------------------|
| Kubernetes Device Plugins   | `nvidia.com/gpu: 2` resource requests; topology-aware scheduling via GPU Operator |
| Slurm                       | `--gres=gpu:a100:4` for GPU scheduling; `--constraint` for node features |
| Ray Cluster                 | `num_gpus`, `num_cpus`, `resources={"TPU": 4}` per task/actor            |
| AWS SageMaker               | Instance type encapsulates GPU type and count (e.g., `ml.p4d.24xlarge`)  |
| Google Vertex AI            | `machineType` + `acceleratorType` + `acceleratorCount`                   |
| Azure ML                    | `compute_target` with `vm_size` (e.g., `Standard_NC96ads_A100_v4`)       |
| Modal                       | `@app.function(gpu="H100:8")` decorator syntax                          |
| RunPod                      | `gpu_type_id` + `cloud_type` (community/secure) in API                   |

OJS adopts an approach closest to Kubernetes resource requests, with explicit fields rather than opaque instance type identifiers. This enables portable job definitions that work across cloud providers and on-premises clusters.
