# ADR-017: ML/AI Resource Requirement Extensions

## Status

Accepted (Updated)

## Context

AI and ML workloads have fundamentally different resource requirements from traditional background jobs. They need GPU acceleration, specific model versions, large memory allocations, compute budgets, TPU scheduling, specific GPU interconnects, and preemption-aware execution. The existing OJS extension mechanism (`ext_*` attributes) provides a natural way to express these requirements without modifying the core specification.

The ML/AI market is growing rapidly, and background job systems are increasingly used for inference, training, and data processing pipelines. Production ML teams need:

- **GPU type and VRAM constraints**: Training a 70B-parameter LLM requires 8x NVIDIA H100 GPUs with 80 GB VRAM each; inference of a small classifier needs a single T4 with 16 GB. Without precise VRAM declarations, schedulers cannot prevent CUDA OOM failures.
- **Compute capability constraints**: BF16 training requires Ampere (8.0+), FP8 training requires Hopper (9.0+). Jobs compiled for a newer architecture crash on older GPUs.
- **GPU interconnect requirements**: Tensor parallelism over PCIe (32 GB/s) is 20-30x slower than NVLink (900 GB/s), making NVLink essential for large model training.
- **TPU scheduling**: Google TPU v5e pods require specific topology declarations (e.g., 2x4 chip layout) that have no analog in traditional job systems.
- **Model locality routing**: Loading a 70B model from disk takes 60-120 seconds. Routing to a worker that already has the model loaded reduces p99 latency from minutes to milliseconds.
- **Preemption and checkpointing**: Spot GPU instances cost 60-90% less but can be interrupted. Without checkpoint-on-preempt semantics, interrupted training loses all progress.
- **Queue-level resource governance**: Without aggregate GPU limits, a burst of training jobs can starve inference traffic.

Standardizing these requirements enables portable ML job definitions across backends, intelligent worker routing, and cost optimization.

## Decision

We add the ML Resource Extension (`ojs-ml-resources`) with seven attribute groups, all using the `ext_ml_` prefix:

1. **Resource requirements** -- Accelerator type, GPU type/count/VRAM/compute capability/interconnect, TPU type/topology/chip count, CPU cores, system memory, storage, shared memory
2. **Model versioning** -- Model ID, version, provider, checksum, format
3. **Compute constraints** -- Token limits, batch sizes, timeouts, runtime, precision, distributed strategy
4. **Node affinity and scheduling** -- Node selectors (equality constraints), affinity rules (In/NotIn/Exists/DoesNotExist/Gt/Gte/Lt/Lte operators with required/preferred split), anti-affinity
5. **Preemption semantics** -- Priority classes (spot/on-demand/reserved), preemptible flag, grace period, checkpoint-on-preempt
6. **Checkpointing** -- Enabled flag, interval, storage URI, max checkpoint count
7. **Queue-level resource constraints** -- Defaults, limits, GPU budgets

Workers advertise their capabilities (hardware, loaded models, runtimes, labels) during FETCH requests. Backends match job requirements to worker capabilities, using hard constraints for mandatory requirements and soft constraints for preferences.

### Key Design Decisions

- **`ext_ml_gpu_compute_capability` as a string**: Compute capability versions like "8.0" and "9.0" are not simple integers. A string representation preserves the original NVIDIA versioning scheme and avoids lossy float comparisons.
- **Separate interconnect field**: Rather than inferring interconnect from GPU type, we make it explicit. The same GPU model (A100) can be deployed with NVLink or PCIe depending on the server configuration.
- **TPU as a first-class accelerator**: TPU topology constraints are fundamentally different from GPU constraints (2D mesh vs. independent devices). A separate `ext_ml_tpu_*` namespace avoids overloading GPU fields.
- **Required vs. preferred affinity**: Mirroring Kubernetes semantics, which are well-understood by ML infrastructure teams and proven at scale.
- **Preemption does not count against retry budget**: Spot preemption is a scheduling event, not a job failure. Counting it against `max_attempts` would exhaust retry budgets for jobs that would otherwise succeed.

## Consequences

### Positive
- Enables standardized ML workload scheduling across any OJS backend
- Workers can self-describe their hardware for automatic job routing
- Priority classes enable cost optimization with spot/preemptible instances
- Model versioning prevents production incidents from model updates
- Compute capability and VRAM constraints prevent runtime CUDA OOM errors at scheduling time
- TPU topology constraints enable correct placement on TPU pod slices
- GPU interconnect constraints prevent performance degradation in multi-GPU training
- Queue-level limits provide resource governance for multi-tenant GPU clusters
- Checkpointing prevents loss of expensive training compute on preemption or failure

### Negative
- Adds complexity to job validation for backends that support this extension
- GPU type and TPU type enumerations require maintenance as new hardware is released
- Worker capability matching adds routing complexity
- Queue-level GPU budget tracking adds state management burden to backends

### Risks
- Rapid hardware evolution may outpace spec updates (mitigated by allowing custom `{vendor}-{model}` identifiers)
- Complex affinity rules may be difficult to debug when jobs are not being scheduled (mitigated by requiring backends to expose unschedulable job reasons)
