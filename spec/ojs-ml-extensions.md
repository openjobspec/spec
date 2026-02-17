# Open Job Spec: ML/AI Pipeline Extensions

| Field       | Value                          |
|-------------|--------------------------------|
| Version     | 0.1.0                          |
| Date        | 2026-02-19                     |
| Status      | Draft                          |
| Stage       | 1 (Proposal)                   |
| Maturity    | Alpha                          |
| Layer       | 1 -- Core (Extension)          |
| Spec URI    | `urn:ojs:spec:ml-extensions`   |
| Depends On  | ojs-core, ojs-ml-resources, ojs-workflows |

---

## Table of Contents

1. [Overview and Rationale](#1-overview-and-rationale)
2. [Terminology](#2-terminology)
3. [Relationship to ML Resources Extension](#3-relationship-to-ml-resources-extension)
4. [Model Metadata](#4-model-metadata)
5. [ML Pipeline Job Types](#5-ml-pipeline-job-types)
   - 5.1 [Training Jobs](#51-training-jobs)
   - 5.2 [Inference Jobs](#52-inference-jobs)
   - 5.3 [Data Preprocessing Jobs](#53-data-preprocessing-jobs)
   - 5.4 [Evaluation Jobs](#54-evaluation-jobs)
6. [Artifact Management](#6-artifact-management)
7. [Resource Scheduling Hints](#7-resource-scheduling-hints)
8. [Extension Attributes Summary](#8-extension-attributes-summary)
9. [Pipeline Composition with Workflows](#9-pipeline-composition-with-workflows)
10. [Job Envelope Examples](#10-job-envelope-examples)
11. [Interaction with Other Extensions](#11-interaction-with-other-extensions)
12. [Security Considerations](#12-security-considerations)

---

## 1. Overview and Rationale

This extension defines ML pipeline-specific attributes for OJS jobs, complementing the [ML/AI Resource Requirements Extension](ojs-ml-resources.md). While the ML Resources extension focuses on **compute infrastructure** (GPU type, VRAM, scheduling affinity), this extension addresses **ML workflow semantics**: model metadata, training hyperparameters, inference configuration, dataset references, evaluation metrics, and artifact management.

### 1.1 Motivation

Real-world ML systems are pipelines, not isolated jobs. A typical production ML workflow involves:

1. **Data preprocessing** — Clean, transform, and split raw data into training/validation/test sets
2. **Training** — Train or fine-tune a model with specific hyperparameters and checkpointing
3. **Evaluation** — Run the trained model against held-out test data and compute metrics
4. **Deployment** — Serve the model for batch or real-time inference

Each stage has domain-specific metadata that schedulers, monitoring systems, and lineage trackers need to understand. Without standardized attributes, every ML platform invents its own job metadata schema, breaking interoperability between training frameworks, serving systems, and experiment trackers.

### 1.2 Design Principles

1. **Complementary to ML Resources.** This extension does not duplicate resource attributes (`ext_ml_gpu_type`, etc.) defined in the ML Resources extension. It adds semantic metadata about the ML task itself.

2. **Framework-neutral.** Attributes describe *what* the ML task does, not *how* a specific framework implements it. Hyperparameters are passed as an opaque map; dataset URIs use standard URI schemes.

3. **Pipeline-first.** Attributes are designed to compose naturally with OJS workflow primitives (chain, group, batch) for expressing multi-stage ML pipelines.

4. **Observable.** Every attribute is designed to be useful for experiment tracking, model lineage, and audit logging.

### 1.3 Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt).

All JSON examples in this document are normative unless explicitly marked otherwise.

---

## 2. Terminology

| Term                  | Definition                                                                                               |
|-----------------------|----------------------------------------------------------------------------------------------------------|
| artifact              | A versioned file or collection produced or consumed by an ML job: model weights, datasets, checkpoints.   |
| hyperparameter        | A configuration value that controls the training process (learning rate, batch size, epochs).              |
| epoch                 | One complete pass through the entire training dataset.                                                     |
| inference             | Using a trained model to produce predictions on new input data.                                            |
| pipeline              | A sequence of ML jobs connected by data dependencies, typically: preprocess → train → evaluate → deploy.   |
| experiment            | A named collection of related training runs, used for comparison and tracking.                             |
| metric                | A quantitative measurement of model quality (accuracy, F1, loss, BLEU, etc.).                             |
| threshold             | A minimum or maximum metric value that a model must satisfy to pass evaluation.                           |
| model registry        | A system that stores versioned model artifacts with metadata (e.g., MLflow, Weights & Biases, S3).       |

---

## 3. Relationship to ML Resources Extension

This extension builds on and requires familiarity with [OJS ML/AI Resource Requirements](ojs-ml-resources.md). The division of responsibility is:

| Concern                        | ML Resources Extension (`ext_ml_*`)         | ML Extensions (`ext_mlx_*`)                     |
|--------------------------------|---------------------------------------------|--------------------------------------------------|
| GPU/TPU/CPU requirements       | ✓ `ext_ml_gpu_type`, `ext_ml_gpu_count`     |                                                  |
| Scheduling and affinity        | ✓ `ext_ml_node_selector`, `ext_ml_affinity` |                                                  |
| Preemption and checkpointing   | ✓ `ext_ml_priority_class`, `ext_ml_checkpoint_*` |                                              |
| Model identity and framework   |                                             | ✓ `ext_mlx_model_name`, `ext_mlx_model_framework` |
| Training hyperparameters       |                                             | ✓ `ext_mlx_training_*`                           |
| Inference configuration        |                                             | ✓ `ext_mlx_inference_*`                          |
| Dataset and artifact URIs      |                                             | ✓ `ext_mlx_artifact_*`                           |
| Evaluation metrics/thresholds  |                                             | ✓ `ext_mlx_eval_*`                               |
| Preprocessing configuration    |                                             | ✓ `ext_mlx_preprocess_*`                         |

Jobs that use ML Extensions attributes SHOULD also set appropriate ML Resources attributes for correct scheduling. ML Extensions attributes are informational and do not affect scheduling decisions.

---

## 4. Model Metadata

These attributes describe the model a job operates on. They complement the `ext_ml_model_id` and `ext_ml_model_version` attributes from the ML Resources extension with additional framework and schema information.

| Attribute                       | Type   | Required | Description                                                    |
|---------------------------------|--------|----------|----------------------------------------------------------------|
| `ext_mlx_model_name`            | string | No       | Human-readable model name (e.g., `"resnet50-imagenet"`)        |
| `ext_mlx_model_version`         | string | No       | Semantic version of the model artifact (e.g., `"2.1.0"`)      |
| `ext_mlx_model_framework`       | string | No       | ML framework: `pytorch`, `tensorflow`, `onnx`, `jax`, `sklearn`, `xgboost`, `custom` |
| `ext_mlx_model_input_schema`    | object | No       | JSON Schema describing expected model input format              |
| `ext_mlx_model_output_schema`   | object | No       | JSON Schema describing expected model output format             |
| `ext_mlx_experiment_id`         | string | No       | Experiment tracker ID (e.g., MLflow experiment ID)              |
| `ext_mlx_run_id`                | string | No       | Experiment run ID within the experiment                         |

### 4.1 `ext_mlx_model_framework` (string)

The ML framework required to load and execute the model. Well-known values:

| Value         | Framework           | Typical Use                                 |
|---------------|---------------------|---------------------------------------------|
| `pytorch`     | PyTorch             | Training, research, vLLM/TGI serving        |
| `tensorflow`  | TensorFlow          | Production serving, TPU workloads            |
| `onnx`        | ONNX Runtime        | Cross-framework inference, edge deployment   |
| `jax`         | JAX/Flax            | Research, TPU-native training                |
| `sklearn`     | scikit-learn        | Classical ML, CPU-only workloads             |
| `xgboost`     | XGBoost/LightGBM    | Tabular data, gradient boosting              |
| `custom`      | Custom framework     | Proprietary or specialized frameworks        |

**Rationale:** The framework determines which runtime libraries must be available on the worker. A worker with only PyTorch installed cannot execute a TensorFlow SavedModel. Declaring the framework enables workers to pre-validate compatibility before accepting a job.

### 4.2 Input/Output Schemas

`ext_mlx_model_input_schema` and `ext_mlx_model_output_schema` are JSON Schema objects that describe the expected structure of model inputs and outputs. These enable:

- **Validation**: Workers can validate job args against the input schema before running inference
- **Documentation**: Pipeline tools can display expected input/output formats
- **Type safety**: Downstream pipeline steps can verify data compatibility

Example:

```json
{
  "ext_mlx_model_input_schema": {
    "type": "object",
    "properties": {
      "text": { "type": "string", "maxLength": 4096 },
      "max_tokens": { "type": "integer", "minimum": 1, "maximum": 4096 }
    },
    "required": ["text"]
  },
  "ext_mlx_model_output_schema": {
    "type": "object",
    "properties": {
      "generated_text": { "type": "string" },
      "token_count": { "type": "integer" },
      "finish_reason": { "type": "string", "enum": ["stop", "length", "error"] }
    }
  }
}
```

---

## 5. ML Pipeline Job Types

This section defines extension attributes for the four canonical ML pipeline stages. These attributes are OPTIONAL and carry semantic meaning for experiment tracking, lineage, and monitoring. They do not alter scheduling behavior.

### 5.1 Training Jobs

Training job attributes describe the dataset, hyperparameters, and output locations for model training or fine-tuning.

| Attribute                            | Type    | Required | Description                                                   |
|--------------------------------------|---------|----------|---------------------------------------------------------------|
| `ext_mlx_training_dataset_uri`       | string  | No       | URI of the training dataset (S3, GCS, HDFS, local path)       |
| `ext_mlx_training_validation_uri`    | string  | No       | URI of the validation dataset                                  |
| `ext_mlx_training_hyperparameters`   | object  | No       | Key-value map of hyperparameters                               |
| `ext_mlx_training_epochs`            | integer | No       | Number of training epochs                                      |
| `ext_mlx_training_checkpoint_uri`    | string  | No       | URI for saving training checkpoints                            |
| `ext_mlx_training_resume_from`       | string  | No       | URI of a checkpoint to resume training from                    |
| `ext_mlx_training_output_model_uri`  | string  | No       | URI where the trained model artifact will be saved             |

#### `ext_mlx_training_hyperparameters` (object)

An opaque key-value map of training hyperparameters. Well-known keys include:

| Key               | Type   | Description                                |
|-------------------|--------|--------------------------------------------|
| `learning_rate`   | number | Optimizer learning rate                     |
| `batch_size`      | integer| Training batch size per device              |
| `weight_decay`    | number | L2 regularization coefficient               |
| `warmup_steps`    | integer| Learning rate warmup steps                  |
| `max_steps`       | integer| Maximum training steps (overrides epochs)   |
| `gradient_accumulation_steps` | integer | Steps to accumulate before optimizer step |
| `seed`            | integer| Random seed for reproducibility             |

Backends MUST preserve hyperparameters exactly as provided. Backends MUST NOT interpret, validate, or modify hyperparameter values.

**Rationale:** Hyperparameters are the single most important configuration for reproducibility. Storing them in the job envelope enables experiment trackers to compare runs without querying external systems.

#### `ext_mlx_training_resume_from` (string)

When set, the worker MUST load the referenced checkpoint and resume training from that state rather than starting from scratch. This attribute complements `ext_ml_checkpoint_storage_uri` from the ML Resources extension: the Resources extension defines *where* to write new checkpoints; this attribute defines *which* checkpoint to resume from.

**Rationale:** Training resumption after preemption or failure is critical for cost efficiency. A 24-hour training run interrupted at hour 20 should resume from the last checkpoint, not restart from epoch 0.

Example training job:

```json
{
  "type": "ml.train",
  "queue": "gpu-training",
  "args": [{"config": "fine-tune-llama"}],
  "ext_ml_gpu_type": "nvidia-h100",
  "ext_ml_gpu_count": 4,
  "ext_ml_runtime": "pytorch",
  "ext_ml_precision": "bf16",
  "ext_mlx_model_name": "llama-3.1-8b-custom",
  "ext_mlx_model_version": "1.0.0",
  "ext_mlx_model_framework": "pytorch",
  "ext_mlx_training_dataset_uri": "s3://datasets/customer-support-v3/train.parquet",
  "ext_mlx_training_validation_uri": "s3://datasets/customer-support-v3/val.parquet",
  "ext_mlx_training_hyperparameters": {
    "learning_rate": 2e-5,
    "batch_size": 32,
    "epochs": 3,
    "weight_decay": 0.01,
    "warmup_steps": 500,
    "seed": 42
  },
  "ext_mlx_training_epochs": 3,
  "ext_mlx_training_checkpoint_uri": "s3://checkpoints/llama-custom/run-001/",
  "ext_mlx_training_output_model_uri": "s3://models/llama-custom/v1.0.0/",
  "ext_mlx_experiment_id": "exp-llama-finetune-2024",
  "ext_mlx_run_id": "run-001"
}
```

### 5.2 Inference Jobs

Inference job attributes describe how a trained model should process input data.

| Attribute                          | Type    | Required | Description                                                  |
|------------------------------------|---------|----------|--------------------------------------------------------------|
| `ext_mlx_inference_model_uri`      | string  | No       | URI of the model artifact to load for inference               |
| `ext_mlx_inference_batch_size`     | integer | No       | Number of inputs to process per batch                         |
| `ext_mlx_inference_timeout_ms`     | integer | No       | Per-request timeout in milliseconds                           |
| `ext_mlx_inference_input_uri`      | string  | No       | URI of the input data for batch inference                     |
| `ext_mlx_inference_output_uri`     | string  | No       | URI where inference results will be written                   |
| `ext_mlx_inference_mode`           | string  | No       | Inference mode: `batch`, `streaming`, `realtime`              |

#### `ext_mlx_inference_mode` (string)

| Mode        | Description                                                        |
|-------------|--------------------------------------------------------------------|
| `batch`     | Process a fixed set of inputs from `ext_mlx_inference_input_uri`   |
| `streaming` | Process inputs as a continuous stream                               |
| `realtime`  | Single-request, low-latency inference                               |

**Rationale:** Batch inference processes millions of records from cloud storage; real-time inference serves individual API requests. Workers optimize differently for each mode (e.g., dynamic batching for real-time, large static batches for batch mode).

Example inference job:

```json
{
  "type": "ml.inference",
  "queue": "gpu-inference",
  "args": [{"task": "text-classification"}],
  "ext_ml_gpu_type": "nvidia-l4",
  "ext_ml_gpu_count": 1,
  "ext_ml_runtime": "vllm",
  "ext_mlx_model_name": "llama-3.1-8b-custom",
  "ext_mlx_model_version": "1.0.0",
  "ext_mlx_model_framework": "pytorch",
  "ext_mlx_inference_model_uri": "s3://models/llama-custom/v1.0.0/",
  "ext_mlx_inference_batch_size": 64,
  "ext_mlx_inference_timeout_ms": 5000,
  "ext_mlx_inference_input_uri": "s3://data/classify-input/batch-2024-01.jsonl",
  "ext_mlx_inference_output_uri": "s3://data/classify-output/batch-2024-01.jsonl",
  "ext_mlx_inference_mode": "batch"
}
```

### 5.3 Data Preprocessing Jobs

Preprocessing job attributes describe data transformation steps that prepare raw data for training or inference.

| Attribute                            | Type   | Required | Description                                                 |
|--------------------------------------|--------|----------|-------------------------------------------------------------|
| `ext_mlx_preprocess_input_uri`       | string | No       | URI of the raw input data                                    |
| `ext_mlx_preprocess_output_uri`      | string | No       | URI where processed data will be written                     |
| `ext_mlx_preprocess_input_format`    | string | No       | Input data format: `csv`, `parquet`, `json`, `jsonl`, `tfrecord`, `arrow`, `custom` |
| `ext_mlx_preprocess_output_format`   | string | No       | Output data format (same enum as input)                      |
| `ext_mlx_preprocess_transformations` | array  | No       | Ordered list of transformation descriptors                   |
| `ext_mlx_preprocess_split_ratios`    | object | No       | Train/validation/test split ratios                           |

#### `ext_mlx_preprocess_transformations` (array)

An ordered list of transformation descriptors. Each entry is an object with at minimum a `type` field. Well-known transformation types:

| Type           | Description                                         |
|----------------|-----------------------------------------------------|
| `tokenize`     | Text tokenization (specify tokenizer in `config`)   |
| `normalize`    | Feature normalization / scaling                      |
| `augment`      | Data augmentation (image flip, crop, noise, etc.)    |
| `filter`       | Row-level filtering by condition                     |
| `sample`       | Random sampling or downsampling                      |
| `deduplicate`  | Remove duplicate records                             |
| `encode`       | Categorical encoding (one-hot, label, etc.)          |

Example:

```json
{
  "ext_mlx_preprocess_transformations": [
    { "type": "filter", "config": { "column": "language", "value": "en" } },
    { "type": "deduplicate", "config": { "columns": ["text"] } },
    { "type": "tokenize", "config": { "tokenizer": "meta-llama/Llama-3.1-8B", "max_length": 2048 } },
    { "type": "sample", "config": { "fraction": 0.1, "seed": 42 } }
  ]
}
```

#### `ext_mlx_preprocess_split_ratios` (object)

Defines how to split the data into training, validation, and test sets:

```json
{
  "ext_mlx_preprocess_split_ratios": {
    "train": 0.8,
    "validation": 0.1,
    "test": 0.1
  }
}
```

The ratios MUST sum to 1.0. Backends SHOULD validate this constraint.

**Rationale:** Data preprocessing is the most time-consuming stage of many ML pipelines. Declaring transformations and split ratios in the job envelope enables reproducibility and makes preprocessing auditable.

### 5.4 Evaluation Jobs

Evaluation job attributes describe how a trained model should be assessed against a test dataset.

| Attribute                       | Type   | Required | Description                                                   |
|---------------------------------|--------|----------|---------------------------------------------------------------|
| `ext_mlx_eval_dataset_uri`      | string | No       | URI of the evaluation dataset                                  |
| `ext_mlx_eval_model_uri`        | string | No       | URI of the model to evaluate                                   |
| `ext_mlx_eval_metrics`          | array  | No       | List of metrics to compute                                     |
| `ext_mlx_eval_thresholds`       | object | No       | Minimum thresholds each metric must meet to pass               |
| `ext_mlx_eval_output_uri`       | string | No       | URI where evaluation results will be written                   |
| `ext_mlx_eval_baseline_run_id`  | string | No       | Run ID of a baseline model for comparison                      |

#### `ext_mlx_eval_metrics` (array)

A list of metric names to compute. Well-known metrics:

| Metric       | Domain                  | Description                                |
|--------------|-------------------------|--------------------------------------------|
| `accuracy`   | Classification          | Fraction of correct predictions             |
| `f1`         | Classification          | Harmonic mean of precision and recall        |
| `precision`  | Classification          | True positives / (true positives + false positives) |
| `recall`     | Classification          | True positives / (true positives + false negatives) |
| `auc_roc`    | Classification          | Area under the ROC curve                     |
| `loss`       | General                 | Evaluation loss value                        |
| `perplexity` | Language modeling        | Exponentiated average cross-entropy loss     |
| `bleu`       | Translation/generation   | BLEU score for text generation               |
| `rouge_l`    | Summarization           | ROUGE-L score for summarization quality      |
| `mae`        | Regression              | Mean absolute error                          |
| `rmse`       | Regression              | Root mean squared error                      |
| `latency_p50`| Performance             | Median inference latency                     |
| `latency_p99`| Performance             | 99th percentile inference latency            |
| `throughput` | Performance             | Inferences per second                        |

#### `ext_mlx_eval_thresholds` (object)

A map of metric names to threshold values. Each threshold defines the minimum (or maximum, for loss-type metrics) acceptable value. A worker SHOULD report whether each threshold was met in the job result.

```json
{
  "ext_mlx_eval_thresholds": {
    "accuracy": { "min": 0.92 },
    "f1": { "min": 0.88 },
    "latency_p99": { "max": 100 },
    "loss": { "max": 0.15 }
  }
}
```

**Rationale:** Automated evaluation with thresholds enables CI/CD for ML models. A training pipeline can automatically gate deployment on quality metrics: if the newly trained model doesn't meet the accuracy threshold, the pipeline stops before the model reaches production.

Example evaluation job:

```json
{
  "type": "ml.evaluate",
  "queue": "gpu-inference",
  "args": [{"task": "evaluate-classification"}],
  "ext_ml_gpu_type": "nvidia-a100",
  "ext_ml_gpu_count": 1,
  "ext_mlx_model_name": "llama-3.1-8b-custom",
  "ext_mlx_model_version": "1.0.0",
  "ext_mlx_model_framework": "pytorch",
  "ext_mlx_eval_dataset_uri": "s3://datasets/customer-support-v3/test.parquet",
  "ext_mlx_eval_model_uri": "s3://models/llama-custom/v1.0.0/",
  "ext_mlx_eval_metrics": ["accuracy", "f1", "precision", "recall", "latency_p99"],
  "ext_mlx_eval_thresholds": {
    "accuracy": { "min": 0.92 },
    "f1": { "min": 0.88 },
    "latency_p99": { "max": 100 }
  },
  "ext_mlx_eval_output_uri": "s3://eval-results/llama-custom/v1.0.0/",
  "ext_mlx_eval_baseline_run_id": "run-000",
  "ext_mlx_experiment_id": "exp-llama-finetune-2024",
  "ext_mlx_run_id": "run-001"
}
```

---

## 6. Artifact Management

Artifact attributes provide a unified way to reference ML artifacts (models, datasets, checkpoints) by URI. These complement the stage-specific URIs in Section 5 with cross-cutting artifact metadata.

| Attribute                     | Type   | Required | Description                                                |
|-------------------------------|--------|----------|------------------------------------------------------------|
| `ext_mlx_artifact_model_uri`  | string | No       | Primary model artifact URI                                  |
| `ext_mlx_artifact_dataset_uri`| string | No       | Primary dataset URI                                         |
| `ext_mlx_artifact_checkpoint_uri` | string | No   | Checkpoint artifact URI                                     |
| `ext_mlx_artifact_output_uri` | string | No       | Primary output artifact URI                                  |
| `ext_mlx_artifact_registry`   | string | No       | Artifact registry: `s3`, `gcs`, `azure_blob`, `mlflow`, `wandb`, `huggingface`, `local` |

### URI Schemes

Artifact URIs MUST use standard URI schemes. Well-known schemes:

| Scheme      | Example                                          | Description              |
|-------------|--------------------------------------------------|--------------------------|
| `s3://`     | `s3://bucket/models/v1.0/model.safetensors`      | Amazon S3                |
| `gs://`     | `gs://bucket/models/v1.0/model.safetensors`      | Google Cloud Storage     |
| `az://`     | `az://container/models/v1.0/model.safetensors`   | Azure Blob Storage       |
| `hdfs://`   | `hdfs://cluster/models/v1.0/`                    | Hadoop HDFS              |
| `mlflow://` | `mlflow://experiment-id/run-id/artifacts/model`  | MLflow Model Registry    |
| `wandb://`  | `wandb://entity/project/run-id/model`            | Weights & Biases         |
| `hf://`     | `hf://meta-llama/Llama-3.1-8B`                   | Hugging Face Hub         |
| `file://`   | `file:///data/models/v1.0/`                       | Local filesystem         |

**Rationale:** ML artifacts are the core data flowing through a pipeline. Standardizing URI references enables lineage tracking (which dataset trained which model), reproducibility (re-run a pipeline with the same artifacts), and garbage collection (identify orphaned artifacts).

---

## 7. Resource Scheduling Hints

These attributes provide additional scheduling hints beyond what the ML Resources extension offers. They are advisory — backends MAY use them to optimize placement but MUST NOT require them.

| Attribute                          | Type    | Required | Description                                              |
|------------------------------------|---------|----------|----------------------------------------------------------|
| `ext_mlx_scheduling_gpu_affinity`  | string  | No       | GPU affinity hint: `spread`, `pack`, `dedicated`         |
| `ext_mlx_scheduling_preemption_policy` | string | No   | Preemption behavior: `never`, `save_and_retry`, `immediate` |
| `ext_mlx_scheduling_spot_preference`   | string | No   | Spot/on-demand preference: `spot_preferred`, `on_demand_only`, `any` |
| `ext_mlx_scheduling_data_locality` | string  | No       | URI hint for data-local scheduling                       |

### 7.1 GPU Affinity

| Value       | Description                                                          |
|-------------|----------------------------------------------------------------------|
| `spread`    | Spread GPU allocation across nodes (fault tolerance for inference)    |
| `pack`      | Pack GPUs onto fewest nodes (minimize inter-node communication)      |
| `dedicated` | Require exclusive access to all GPUs on the allocated node(s)        |

**Rationale:** Training workloads benefit from `pack` affinity to minimize all-reduce communication overhead. Inference replicas benefit from `spread` to survive node failures. The ML Resources extension provides hard affinity rules; this attribute provides a simpler, intent-based hint.

### 7.2 Data Locality

When `ext_mlx_scheduling_data_locality` is set to a URI, the backend SHOULD prefer workers that are co-located with the referenced data (e.g., same cloud region, same HDFS rack). This avoids cross-region data transfer for large datasets.

---

## 8. Extension Attributes Summary

All attributes defined in this extension use the `ext_mlx_` prefix.

### Model Metadata

| Attribute                       | Type   | JSON Key                         |
|---------------------------------|--------|----------------------------------|
| Model name                      | string | `ext_mlx_model_name`             |
| Model version                   | string | `ext_mlx_model_version`          |
| ML framework                    | string | `ext_mlx_model_framework`        |
| Model input schema              | object | `ext_mlx_model_input_schema`     |
| Model output schema             | object | `ext_mlx_model_output_schema`    |
| Experiment ID                   | string | `ext_mlx_experiment_id`          |
| Run ID                          | string | `ext_mlx_run_id`                 |

### Training

| Attribute                       | Type    | JSON Key                               |
|---------------------------------|---------|----------------------------------------|
| Training dataset URI            | string  | `ext_mlx_training_dataset_uri`         |
| Validation dataset URI          | string  | `ext_mlx_training_validation_uri`      |
| Hyperparameters                 | object  | `ext_mlx_training_hyperparameters`     |
| Epochs                          | integer | `ext_mlx_training_epochs`              |
| Checkpoint URI                  | string  | `ext_mlx_training_checkpoint_uri`      |
| Resume from checkpoint          | string  | `ext_mlx_training_resume_from`         |
| Output model URI                | string  | `ext_mlx_training_output_model_uri`    |

### Inference

| Attribute                       | Type    | JSON Key                              |
|---------------------------------|---------|---------------------------------------|
| Model URI                       | string  | `ext_mlx_inference_model_uri`         |
| Batch size                      | integer | `ext_mlx_inference_batch_size`        |
| Per-request timeout (ms)        | integer | `ext_mlx_inference_timeout_ms`        |
| Input data URI                  | string  | `ext_mlx_inference_input_uri`         |
| Output data URI                 | string  | `ext_mlx_inference_output_uri`        |
| Inference mode                  | string  | `ext_mlx_inference_mode`              |

### Preprocessing

| Attribute                       | Type   | JSON Key                                |
|---------------------------------|--------|-----------------------------------------|
| Input URI                       | string | `ext_mlx_preprocess_input_uri`          |
| Output URI                      | string | `ext_mlx_preprocess_output_uri`         |
| Input format                    | string | `ext_mlx_preprocess_input_format`       |
| Output format                   | string | `ext_mlx_preprocess_output_format`      |
| Transformations                 | array  | `ext_mlx_preprocess_transformations`    |
| Split ratios                    | object | `ext_mlx_preprocess_split_ratios`       |

### Evaluation

| Attribute                       | Type   | JSON Key                           |
|---------------------------------|--------|------------------------------------|
| Evaluation dataset URI          | string | `ext_mlx_eval_dataset_uri`         |
| Model URI                       | string | `ext_mlx_eval_model_uri`           |
| Metrics                         | array  | `ext_mlx_eval_metrics`             |
| Thresholds                      | object | `ext_mlx_eval_thresholds`          |
| Output URI                      | string | `ext_mlx_eval_output_uri`          |
| Baseline run ID                 | string | `ext_mlx_eval_baseline_run_id`     |

### Artifacts

| Attribute                       | Type   | JSON Key                            |
|---------------------------------|--------|-------------------------------------|
| Model artifact URI              | string | `ext_mlx_artifact_model_uri`        |
| Dataset URI                     | string | `ext_mlx_artifact_dataset_uri`      |
| Checkpoint URI                  | string | `ext_mlx_artifact_checkpoint_uri`   |
| Output URI                      | string | `ext_mlx_artifact_output_uri`       |
| Artifact registry               | string | `ext_mlx_artifact_registry`         |

### Scheduling Hints

| Attribute                       | Type   | JSON Key                                |
|---------------------------------|--------|-----------------------------------------|
| GPU affinity                    | string | `ext_mlx_scheduling_gpu_affinity`       |
| Preemption policy               | string | `ext_mlx_scheduling_preemption_policy`  |
| Spot preference                 | string | `ext_mlx_scheduling_spot_preference`    |
| Data locality hint              | string | `ext_mlx_scheduling_data_locality`      |

---

## 9. Pipeline Composition with Workflows

ML Extensions attributes compose naturally with OJS workflow primitives. A complete ML pipeline is expressed as a workflow chain where each step declares both resource requirements (ML Resources) and semantic metadata (ML Extensions).

### 9.1 Complete Training Pipeline

```json
{
  "workflow_type": "chain",
  "id": "019539a4-ml-pipeline-001",
  "name": "customer-support-classifier-v1",
  "steps": [
    {
      "type": "ml.preprocess",
      "queue": "cpu-workers",
      "args": [{"task": "prepare-training-data"}],
      "ext_ml_accelerator": "cpu",
      "ext_ml_cpu_cores": 8,
      "ext_ml_memory_gb": 32,
      "ext_mlx_preprocess_input_uri": "s3://raw-data/customer-tickets-2024.jsonl",
      "ext_mlx_preprocess_output_uri": "s3://processed/customer-tickets-v3/",
      "ext_mlx_preprocess_input_format": "jsonl",
      "ext_mlx_preprocess_output_format": "parquet",
      "ext_mlx_preprocess_transformations": [
        { "type": "filter", "config": { "column": "language", "value": "en" } },
        { "type": "deduplicate", "config": { "columns": ["text"] } },
        { "type": "tokenize", "config": { "tokenizer": "meta-llama/Llama-3.1-8B" } }
      ],
      "ext_mlx_preprocess_split_ratios": { "train": 0.8, "validation": 0.1, "test": 0.1 }
    },
    {
      "type": "ml.train",
      "queue": "gpu-training",
      "args": [{"task": "fine-tune-classifier"}],
      "ext_ml_gpu_type": "nvidia-a100",
      "ext_ml_gpu_count": 4,
      "ext_ml_gpu_memory_gb": 80,
      "ext_ml_runtime": "pytorch",
      "ext_ml_precision": "bf16",
      "ext_ml_distributed_strategy": "fsdp",
      "ext_ml_checkpoint_enabled": true,
      "ext_ml_checkpoint_interval_s": 600,
      "ext_mlx_model_name": "llama-3.1-8b-classifier",
      "ext_mlx_model_framework": "pytorch",
      "ext_mlx_training_dataset_uri": "s3://processed/customer-tickets-v3/train.parquet",
      "ext_mlx_training_validation_uri": "s3://processed/customer-tickets-v3/val.parquet",
      "ext_mlx_training_hyperparameters": {
        "learning_rate": 2e-5,
        "batch_size": 16,
        "weight_decay": 0.01,
        "warmup_steps": 200,
        "seed": 42
      },
      "ext_mlx_training_epochs": 5,
      "ext_mlx_training_output_model_uri": "s3://models/classifier/v1.0.0/"
    },
    {
      "type": "ml.evaluate",
      "queue": "gpu-inference",
      "args": [{"task": "evaluate-classifier"}],
      "ext_ml_gpu_type": "nvidia-a100",
      "ext_ml_gpu_count": 1,
      "ext_mlx_eval_dataset_uri": "s3://processed/customer-tickets-v3/test.parquet",
      "ext_mlx_eval_model_uri": "s3://models/classifier/v1.0.0/",
      "ext_mlx_eval_metrics": ["accuracy", "f1", "precision", "recall"],
      "ext_mlx_eval_thresholds": {
        "accuracy": { "min": 0.92 },
        "f1": { "min": 0.88 }
      },
      "ext_mlx_eval_output_uri": "s3://eval-results/classifier/v1.0.0/"
    },
    {
      "type": "ml.deploy",
      "queue": "deployment",
      "args": [{"model_uri": "s3://models/classifier/v1.0.0/", "canary_percentage": 10}],
      "ext_ml_accelerator": "cpu",
      "ext_mlx_artifact_model_uri": "s3://models/classifier/v1.0.0/",
      "ext_mlx_artifact_registry": "s3"
    }
  ]
}
```

### 9.2 Parallel Evaluation (Group)

Evaluate a model against multiple test sets in parallel:

```json
{
  "workflow_type": "group",
  "id": "019539a4-eval-group-001",
  "jobs": [
    {
      "type": "ml.evaluate",
      "args": [{"eval_set": "english"}],
      "ext_mlx_eval_dataset_uri": "s3://eval/english-test.parquet",
      "ext_mlx_eval_model_uri": "s3://models/classifier/v1.0.0/",
      "ext_mlx_eval_metrics": ["accuracy", "f1"]
    },
    {
      "type": "ml.evaluate",
      "args": [{"eval_set": "spanish"}],
      "ext_mlx_eval_dataset_uri": "s3://eval/spanish-test.parquet",
      "ext_mlx_eval_model_uri": "s3://models/classifier/v1.0.0/",
      "ext_mlx_eval_metrics": ["accuracy", "f1"]
    },
    {
      "type": "ml.evaluate",
      "args": [{"eval_set": "adversarial"}],
      "ext_mlx_eval_dataset_uri": "s3://eval/adversarial-test.parquet",
      "ext_mlx_eval_model_uri": "s3://models/classifier/v1.0.0/",
      "ext_mlx_eval_metrics": ["accuracy", "f1", "latency_p99"]
    }
  ]
}
```

---

## 10. Job Envelope Examples

### 10.1 Fine-Tuning with Resume

A training job resuming from a previous checkpoint:

```json
{
  "id": "019539a4-ft-resume-001",
  "type": "ml.train",
  "queue": "gpu-training",
  "args": [{"task": "resume-fine-tune"}],
  "ext_ml_accelerator": "gpu",
  "ext_ml_gpu_type": "nvidia-h100",
  "ext_ml_gpu_count": 8,
  "ext_ml_gpu_interconnect": "nvlink",
  "ext_ml_precision": "bf16",
  "ext_ml_distributed_strategy": "fsdp",
  "ext_ml_priority_class": "reserved",
  "ext_mlx_model_name": "llama-3.1-70b-domain",
  "ext_mlx_model_version": "0.2.0",
  "ext_mlx_model_framework": "pytorch",
  "ext_mlx_training_dataset_uri": "s3://data/domain-corpus/train.parquet",
  "ext_mlx_training_hyperparameters": {
    "learning_rate": 1e-5,
    "batch_size": 8,
    "gradient_accumulation_steps": 4,
    "seed": 42
  },
  "ext_mlx_training_resume_from": "s3://checkpoints/llama-70b-domain/run-003/step-15000/",
  "ext_mlx_training_output_model_uri": "s3://models/llama-70b-domain/v0.2.0/",
  "ext_mlx_experiment_id": "exp-domain-adaptation",
  "ext_mlx_run_id": "run-003"
}
```

### 10.2 Batch Inference Pipeline

A real-time batch scoring job:

```json
{
  "id": "019539a4-batch-inf-001",
  "type": "ml.inference",
  "queue": "gpu-inference",
  "args": [{"task": "batch-classify"}],
  "ext_ml_accelerator": "gpu",
  "ext_ml_gpu_type": "nvidia-l4",
  "ext_ml_gpu_count": 1,
  "ext_ml_runtime": "onnx",
  "ext_mlx_model_name": "customer-intent-classifier",
  "ext_mlx_model_version": "3.1.0",
  "ext_mlx_model_framework": "onnx",
  "ext_mlx_inference_model_uri": "s3://models/intent-classifier/v3.1.0/model.onnx",
  "ext_mlx_inference_batch_size": 256,
  "ext_mlx_inference_timeout_ms": 30000,
  "ext_mlx_inference_input_uri": "s3://data/daily-tickets/2024-01-15.jsonl",
  "ext_mlx_inference_output_uri": "s3://data/daily-predictions/2024-01-15.jsonl",
  "ext_mlx_inference_mode": "batch"
}
```

---

## 11. Interaction with Other Extensions

| Extension           | Interaction                                                                     |
|---------------------|---------------------------------------------------------------------------------|
| ML Resources        | ML Extensions attributes complement resource attributes. Use both together.      |
| Retry               | Training jobs SHOULD use retry with `ext_mlx_training_resume_from` for checkpoint-based recovery. |
| Workflows           | ML pipelines map naturally to chain (sequential stages), group (parallel evaluation), and batch (fan-out inference). |
| Unique Jobs         | Use unique job keys with `ext_mlx_experiment_id` + `ext_mlx_run_id` to prevent duplicate training runs. |
| Events              | Backends SHOULD emit events with ML metadata for experiment tracking integration. |
| Cron                | Scheduled retraining pipelines combine cron triggers with ML pipeline workflows.  |
| Progress            | Training jobs SHOULD report progress as epoch/step completion percentage.         |

---

## 12. Security Considerations

1. **Artifact URI validation.** Backends MUST validate that artifact URIs use allowed schemes and MUST NOT allow arbitrary file system access. Backends SHOULD enforce allowlists for permitted URI prefixes per queue or tenant.

2. **Hyperparameter injection.** Hyperparameters are passed as opaque maps. Workers MUST NOT evaluate hyperparameter values as code. Workers SHOULD sanitize hyperparameter values before passing them to ML frameworks.

3. **Model integrity.** When `ext_ml_model_checksum` (from ML Resources) is set alongside `ext_mlx_inference_model_uri`, workers SHOULD verify model integrity before loading.

4. **Credential management.** Artifact URIs that reference cloud storage require credentials. Workers SHOULD use IAM roles or workload identity (not embedded credentials) to access artifact storage. Credentials MUST NOT appear in job envelope attributes.

5. **Data privacy.** Dataset URIs may reference sensitive data. Backends SHOULD enforce access control policies that ensure only authorized workers can access job attributes containing dataset URIs.
