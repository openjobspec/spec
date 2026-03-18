# Open Job Spec: Verifiable Compute Attestation Extension

| Field        | Value                                                    |
|-------------|----------------------------------------------------------|
| **Title**   | OJS Verifiable Compute Attestation Extension              |
| **Version** | 0.1.0-draft                                              |
| **Date**    | 2026-04-17                                               |
| **Status**  | Draft                                                    |
| **Maturity** | Alpha                                                   |
| **Layer**   | Extension                                                |
| **URI**     | `urn:ojs:ext:attest`                                     |
| **Requires**| OJS Core Specification (Layer 1)                         |
| **RFC**     | [RFC-0010](../rfcs/RFC-0010-ext-attest.md)               |
| **License** | Apache 2.0                                               |

---

## Abstract

This extension defines `ext_attest`, an envelope extension that binds job inputs and
outputs to a verifiable attestation of the executing runtime. By attaching hardware
attestation quotes, jurisdiction metadata, model fingerprints, and cryptographic
signatures to the OJS job envelope, consumers gain cryptographic proof that a job
ran in the claimed environment, on the claimed hardware, with the claimed model — without
trusting the worker. No competitor in the background-job space (Sidekiq, BullMQ,
Celery, Faktory, Temporal, Oban) offers attested execution. This extension brings
Sigstore-grade provenance to job processing.

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Extension Fields](#4-extension-fields)
5. [VERIFY Operation](#5-verify-operation)
6. [Attestation Flow](#6-attestation-flow)
7. [Cluster Policy](#7-cluster-policy)
8. [Receipt Format](#8-receipt-format)
9. [Size Limits](#9-size-limits)
10. [Conformance Requirements](#10-conformance-requirements)
11. [Non-Requirements](#11-non-requirements)
12. [Security Considerations](#12-security-considerations)
13. [Examples](#13-examples)

---

## 1. Introduction

OJS is currently a "trust the worker" system. An enqueuer has no cryptographic way to
prove that a job ran in the environment claimed, that the inputs were not tampered with,
or that the outputs were not fabricated. This blocks high-trust use cases:

- **Regulated workloads** (HIPAA, PCI, GDPR processor obligations) that require
  auditable proof of execution environment.
- **Multi-tenant SaaS** where the platform must prove isolation to each tenant.
- **Cross-organization workflows** where parties need mutual attestation.
- **AI model provenance** where consumers need proof that inference ran on a
  specific model version in a specific enclave.

This extension introduces `ext_attest` — a single envelope key that carries a
verifiable attestation receipt binding job inputs, outputs, and execution environment
into a cryptographically signed document.

### 1.1 Scope

This specification defines:

- Sub-fields for attestation quotes, jurisdiction, model fingerprints, and signatures.
- A `VERIFY` logical operation for offline receipt verification.
- A cluster policy language for per-job-type attestation requirements.
- A receipt format that proves execution environment properties.
- Size limits for attestation data in the envelope.

### 1.2 Prior Art

- **Sigstore / in-toto** — signed build provenance for software artifacts. Same trust
  model, different artifact type.
- **AWS Nitro Attestation Documents** — hardware-rooted enclave attestation.
- **Intel TDX** and **AMD SEV-SNP** — confidential VM attestation.
- **Temporal** — has signed workflow histories, but no executor attestation.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD",
"SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this
document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14)
[[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)]
[[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear
in ALL CAPITALS, as shown here.

All JSON examples in this document are normative unless explicitly marked otherwise.

All timestamps use ISO 8601 / RFC 3339 format in UTC with `Z` suffix.

All digests use lowercase hexadecimal encoding prefixed with `sha256:`.

---

## 3. Terminology

| Term                  | Definition                                                                                |
|-----------------------|-------------------------------------------------------------------------------------------|
| **Attestation**       | A cryptographic document proving properties of the execution environment.                 |
| **Quote**             | A hardware-generated attestation evidence blob (e.g., AWS Nitro document, TDX report).   |
| **Receipt**           | The signed document that combines input digest, output digest, and attestation evidence.  |
| **TEE**               | Trusted Execution Environment — a hardware-isolated enclave.                              |
| **Prover**            | The worker that generates the attestation and signs the receipt.                          |
| **Verifier**          | Any party that validates the receipt against trusted roots.                               |
| **PQC**               | Post-Quantum Cryptography — algorithms resistant to quantum computer attacks.             |
| **Model fingerprint** | A SHA-256 hash of the model weights used for inference.                                   |
| **Jurisdiction**      | The legal and physical location where computation occurred.                               |
| **Cluster policy**    | A set of predicates that constrain where and how a job may execute.                       |

---

## 4. Extension Fields

The `ext_attest` envelope key contains a single JSON object with the following
sub-fields. Implementations that support this extension MUST recognize all fields
defined in this section. Unrecognized sub-fields MUST be preserved but MAY be ignored.

### 4.1 Top-Level Structure

```json
{
  "ext_attest": {
    "v": 1,
    "quote": { },
    "jurisdiction": { },
    "model_fingerprint": { },
    "signature": { },
    "input_digest": "sha256:...",
    "output_digest": "sha256:...",
    "receipt_id": "019034ab-receipt-uuid"
  }
}
```

| Field               | Type   | Required | Description                                              |
|----------------------|--------|----------|----------------------------------------------------------|
| `v`                  | integer| Yes      | Schema version. MUST be `1`.                             |
| `quote`              | object | Yes      | Hardware attestation evidence (Section 4.2).             |
| `jurisdiction`       | object | No       | Execution location metadata (Section 4.3).               |
| `model_fingerprint`  | object | No       | Model identity for AI workloads (Section 4.4).           |
| `signature`          | object | Yes      | Cryptographic signature over the receipt (Section 4.5).  |
| `input_digest`       | string | Yes      | SHA-256 digest of job inputs (args + meta).              |
| `output_digest`      | string | No       | SHA-256 digest of job outputs. Present after completion. |
| `receipt_id`         | string | Yes      | Unique identifier for this receipt (UUIDv7).             |

### 4.2 Quote

The `quote` sub-field carries hardware attestation evidence from the execution
environment.

```json
{
  "quote": {
    "type": "aws-nitro-v1",
    "evidence": "base64-encoded-attestation-document...",
    "nonce": "random-challenge-value",
    "issued_at": "2026-04-17T12:00:00Z"
  }
}
```

| Field       | Type   | Required | Description                                              |
|-------------|--------|----------|----------------------------------------------------------|
| `type`      | string | Yes      | Attestation type (see Section 4.2.1).                    |
| `evidence`  | string | Yes      | Base64-encoded attestation evidence blob.                |
| `nonce`     | string | Yes      | Challenge nonce for replay protection.                   |
| `issued_at` | string | Yes      | RFC 3339 timestamp when the quote was generated.         |

#### 4.2.1 Attestation Types

| Type              | Description                                                      |
|-------------------|------------------------------------------------------------------|
| `aws-nitro-v1`    | AWS Nitro Enclave attestation document (COSE Sign1 format).      |
| `intel-tdx-v4`    | Intel TDX v4 attestation report.                                 |
| `amd-sev-snp-v2`  | AMD SEV-SNP v2 attestation report.                               |
| `pqc-only`        | No hardware attestation; signature-only with PQC algorithms.     |

Implementations MUST support `pqc-only` as the minimum attestation type. Hardware
attestation types (`aws-nitro-v1`, `intel-tdx-v4`, `amd-sev-snp-v2`) are OPTIONAL
and depend on the execution environment.

**Rationale for MUST support pqc-only**: Not all workers run in hardware enclaves.
The `pqc-only` type enables signature-based attestation without hardware dependencies,
providing a migration path from no attestation to full hardware attestation.

#### 4.2.2 Nonce Requirements

The `nonce` MUST be a cryptographically random value of at least 16 bytes, encoded as
a hex string. Verifiers MUST reject quotes where the `nonce` does not match the
expected challenge.

**Rationale for MUST random nonce**: Without a fresh nonce, an attacker could replay
a previously valid attestation document from a different execution context.

### 4.3 Jurisdiction

The `jurisdiction` sub-field records the physical and legal location where computation
occurred.

```json
{
  "jurisdiction": {
    "region": "us-east-1",
    "datacenter": "use1-az1",
    "prover": "worker-enclave-07.prod.example.com"
  }
}
```

| Field        | Type   | Required | Description                                              |
|--------------|--------|----------|----------------------------------------------------------|
| `region`     | string | Yes      | Cloud region or geographic region identifier.            |
| `datacenter` | string | No       | Specific datacenter or availability zone.                |
| `prover`     | string | Yes      | Identity of the worker that generated the attestation.   |

Implementations MUST populate `region` and `prover` when `ext_attest` is present.
The `prover` value SHOULD be a stable worker identity (hostname, instance ID, or
DID) that can be correlated with the attestation quote.

### 4.4 Model Fingerprint

The `model_fingerprint` sub-field identifies the specific model used for AI workloads.
This field is OPTIONAL and only applicable to jobs that perform model inference.

```json
{
  "model_fingerprint": {
    "sha256": "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456",
    "registry_url": "https://registry.example.com/models/llama-3.1-70b@sha256:a1b2c3d4..."
  }
}
```

| Field          | Type   | Required | Description                                              |
|----------------|--------|----------|----------------------------------------------------------|
| `sha256`       | string | Yes      | SHA-256 hash of the model weights file.                  |
| `registry_url` | string | No       | URL to the model in a registry for verification.         |

When present, verifiers SHOULD check that the `sha256` value matches a known-good
model hash from a trusted registry.

### 4.5 Signature

The `signature` sub-field carries the cryptographic signature over the attestation
receipt.

```json
{
  "signature": {
    "alg": "hybrid:Ed25519+ML-DSA-65",
    "value": "base64-encoded-signature...",
    "key_id": "did:web:example.com:keys:worker-2026-q2"
  }
}
```

| Field    | Type   | Required | Description                                              |
|----------|--------|----------|----------------------------------------------------------|
| `alg`    | string | Yes      | Signature algorithm (see Section 4.5.1).                 |
| `value`  | string | Yes      | Base64-encoded signature bytes.                          |
| `key_id` | string | Yes      | Identifier for the signing key (DID or URI).             |

#### 4.5.1 Signature Algorithms

| Algorithm                   | Description                                              |
|-----------------------------|----------------------------------------------------------|
| `ed25519`                   | Ed25519 (RFC 8032). Classical, widely supported.         |
| `ml-dsa-65`                | ML-DSA-65 (FIPS 204). Post-quantum, NIST standardized.   |
| `hybrid:Ed25519+ML-DSA-65` | Hybrid scheme: both signatures concatenated.              |

Implementations MUST support `ed25519`. Implementations SHOULD support `ml-dsa-65`
and `hybrid:Ed25519+ML-DSA-65` for post-quantum readiness.

**Rationale for hybrid**: The hybrid scheme provides protection against both classical
and quantum attacks. If either algorithm is broken, the other still provides security.
NIST and BSI recommend hybrid schemes during the PQC transition period.

#### 4.5.2 Signature Input

The signature MUST be computed over the following canonical byte string:

```
sign_input = canonical_json(input_digest) || "|" ||
             canonical_json(output_digest) || "|" ||
             canonical_json(quote)
```

Where `canonical_json` follows [RFC 8785 (JSON Canonicalization Scheme)](https://www.rfc-editor.org/rfc/rfc8785).
If `output_digest` is not yet available (pre-completion), it MUST be replaced with
the empty string `""`.

### 4.6 Input and Output Digests

**`input_digest`** (string): The SHA-256 hash of the job's input fields, computed as:

```
input_digest = "sha256:" + hex(SHA-256(canonical_json({"args": args, "meta": meta})))
```

Implementations MUST compute `input_digest` at job dequeue time before execution
begins.

**`output_digest`** (string): The SHA-256 hash of the job's output, computed at
completion. The exact fields included in the digest are implementation-defined but
MUST be documented.

---

## 5. VERIFY Operation

The `VERIFY` operation is a new logical operation for offline verification of a job's
attestation receipt. Unlike other OJS operations that modify job state, `VERIFY` is
a read-only operation that validates the cryptographic integrity of an existing receipt.

### 5.1 Verification Steps

A verifier MUST perform the following steps in order:

1. **Schema validation.** Verify that `ext_attest` conforms to the schema in Section 4.
2. **Nonce check.** Verify that `quote.nonce` matches the expected challenge value.
3. **Freshness check.** Verify that `quote.issued_at` is within an acceptable time
   window (implementation-defined, RECOMMENDED ≤1 hour).
4. **Input digest check.** Recompute `input_digest` from the job's `args` and `meta`
   fields. The recomputed value MUST match `ext_attest.input_digest`.
5. **Output digest check.** If `output_digest` is present, recompute and verify.
6. **Quote verification.** Validate the hardware attestation evidence against the
   appropriate trust root (e.g., AWS Nitro root certificate, Intel TDX collateral).
   For `pqc-only` type, skip this step.
7. **Signature verification.** Verify `signature.value` against the signing key
   identified by `signature.key_id` using the algorithm specified by `signature.alg`.
8. **Policy evaluation.** If a cluster policy is configured for this job type
   (Section 7), verify that the receipt satisfies all policy predicates.

### 5.2 Verification Result

The `VERIFY` operation MUST return a structured result:

```json
{
  "verified": true,
  "checks": {
    "schema": "pass",
    "nonce": "pass",
    "freshness": "pass",
    "input_digest": "pass",
    "output_digest": "pass",
    "quote": "pass",
    "signature": "pass",
    "policy": "pass"
  },
  "verified_at": "2026-04-17T13:00:00Z"
}
```

If any check fails, `verified` MUST be `false` and the failing check MUST include
an `error` field describing the failure.

### 5.3 HTTP Binding

Backends that support `ext_attest` SHOULD expose a verification endpoint:

```
POST /v1/jobs/{id}/verify
```

**Request body**: Empty or `{"nonce": "expected-nonce-value"}`.

**Response**: The verification result (Section 5.2).

---

## 6. Attestation Flow

The following sequence shows the attestation lifecycle for a single job.

### 6.1 Sequence Diagram

```
  Enqueuer              Backend              Worker (TEE)           Verifier
     │                     │                     │                     │
     │  enqueue(job)       │                     │                     │
     │────────────────────►│                     │                     │
     │                     │  dequeue             │                     │
     │                     │────────────────────►│                     │
     │                     │                     │                     │
     │                     │                     │ 1. Generate nonce    │
     │                     │                     │ 2. Obtain HW quote   │
     │                     │                     │ 3. Compute           │
     │                     │                     │    input_digest      │
     │                     │                     │                     │
     │                     │                     │ 4. Execute job       │
     │                     │                     │                     │
     │                     │                     │ 5. Compute           │
     │                     │                     │    output_digest     │
     │                     │                     │ 6. Sign receipt      │
     │                     │                     │ 7. Attach ext_attest │
     │                     │                     │                     │
     │                     │  complete(job +      │                     │
     │                     │  ext_attest)         │                     │
     │                     │◄────────────────────│                     │
     │                     │                     │                     │
     │                     │                     │                     │
     │  get_job(id)        │                     │                     │
     │────────────────────►│                     │                     │
     │◄────────────────────│                     │                     │
     │                     │                     │                     │
     │  forward receipt    │                     │                     │
     │─────────────────────────────────────────────────────────────────►
     │                     │                     │                     │
     │                     │                     │           VERIFY     │
     │                     │                     │          receipt     │
     │◄─────────────────────────────────────────────────────────────────
     │  verification       │                     │                     │
     │  result             │                     │                     │
```

### 6.2 Lifecycle Steps

1. **Worker startup** — The worker produces an attestation document from the TEE
   hardware (or generates a signing key for `pqc-only` mode).
2. **Job dequeue** — The worker computes `input_digest` from the job's `args` and
   `meta` fields using RFC 8785 canonical JSON and SHA-256.
3. **Job execution** — The worker executes the job handler.
4. **Job completion** — The worker computes `output_digest`, assembles the receipt,
   signs it, and attaches `ext_attest` to the job envelope.
5. **Verification** — Any party with the worker's public key and a trusted root
   can invoke `VERIFY` to validate the receipt.

---

## 7. Cluster Policy

A cluster policy defines per-job-type predicates that constrain attestation
requirements. Policies are configured at the cluster or queue level and evaluated
at dequeue time.

### 7.1 Policy Schema

```json
{
  "policies": {
    "ai.inference.*": {
      "hardware": "required",
      "hardware_types": ["aws-nitro-v1", "intel-tdx-v4"],
      "regions": {"allowed": ["us-east-1", "eu-west-1"], "forbidden": ["cn-*"]},
      "signature_alg": "preferred:hybrid:Ed25519+ML-DSA-65",
      "model_fingerprint": "required"
    },
    "billing.*": {
      "hardware": "required",
      "hardware_types": ["aws-nitro-v1"],
      "regions": {"allowed": ["us-east-1"]},
      "signature_alg": "required:ed25519"
    },
    "analytics.*": {
      "hardware": "forbidden",
      "signature_alg": "preferred:ed25519"
    }
  }
}
```

### 7.2 Predicate Levels

| Level       | Behavior                                                              |
|-------------|-----------------------------------------------------------------------|
| `required`  | The predicate MUST be satisfied. Jobs that fail are rejected.         |
| `preferred` | The predicate SHOULD be satisfied. A warning is emitted on failure.   |
| `forbidden` | The predicate MUST NOT be satisfied. Jobs that match are rejected.    |

### 7.3 Policy Evaluation

Implementations MUST evaluate cluster policies at dequeue time. If a worker cannot
satisfy a `required` predicate, it MUST NOT execute the job and MUST return it to
the queue for a capable worker.

**Rationale for dequeue-time evaluation**: Evaluating at enqueue time is insufficient
because attestation depends on the executing worker's hardware and location, which
are unknown until dequeue.

---

## 8. Receipt Format

The attestation receipt is the complete `ext_attest` object attached to a completed
job. It serves as a self-contained proof of execution.

### 8.1 Receipt Properties

A valid receipt MUST satisfy the following properties:

1. **Binding.** The receipt binds inputs (`input_digest`) to outputs (`output_digest`)
   to execution environment (`quote`) via a single signature.
2. **Non-repudiation.** The prover cannot deny having generated the receipt (the
   signing key is bound to the attestation quote).
3. **Freshness.** The `nonce` and `issued_at` fields prevent replay of stale receipts.
4. **Offline verifiability.** Verification requires only the receipt, the prover's
   public key, and the hardware trust root — no network access to the prover.

### 8.2 Complete Receipt Example

```json
{
  "ext_attest": {
    "v": 1,
    "quote": {
      "type": "aws-nitro-v1",
      "evidence": "hEShATgioFkRH6lpbW9kdWxlX2lkeCdpLTBhYmNkZWYx...",
      "nonce": "a3f8b2c1d4e5f67890123456789abcde",
      "issued_at": "2026-04-17T12:00:01Z"
    },
    "jurisdiction": {
      "region": "us-east-1",
      "datacenter": "use1-az1",
      "prover": "i-0abcdef1234567890"
    },
    "model_fingerprint": {
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "registry_url": "https://models.example.com/llama-3.1-70b@sha256:e3b0c442..."
    },
    "signature": {
      "alg": "hybrid:Ed25519+ML-DSA-65",
      "value": "MEUCIQC7y2Ln1vEMwOz8aG...",
      "key_id": "did:web:example.com:keys:enclave-2026-q2"
    },
    "input_digest": "sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    "output_digest": "sha256:2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae",
    "receipt_id": "019034ab-rcpt-7def-0000-aaaaaaaaaaaa"
  }
}
```

---

## 9. Size Limits

Attestation data adds to the job envelope size. To prevent envelope bloat:

| Field         | Typical Size | Hard Cap | Notes                                       |
|---------------|-------------|----------|----------------------------------------------|
| `quote`       | 2–4 KB      | 16 KB    | Hardware attestation documents vary by TEE.  |
| `jurisdiction`| 100–200 B   | 1 KB     | Short string fields.                         |
| `model_fingerprint` | 150 B | 1 KB     | SHA-256 hash + URL.                          |
| `signature`   | 200–800 B   | 4 KB     | Hybrid signatures are larger.                |
| **Total `ext_attest`** | **≤8 KB typical** | **≤32 KB** | Hard cap enforced by backends. |

Implementations MUST reject `ext_attest` payloads exceeding 32 KB with error code
`ATTEST_PAYLOAD_TOO_LARGE`.

**Rationale for 32 KB cap**: Attestation data transits every backend operation
(enqueue, dequeue, complete, query). A 32 KB cap ensures that attestation overhead
remains negligible relative to the typical job payload budget (≤1 MB per OJS core).

---

## 10. Conformance Requirements

### 10.1 Preservation (All Backends, L0–L4)

All OJS-conformant backends MUST preserve `ext_attest` byte-for-byte across
enqueue → dequeue → result, per the existing extension preservation contract.
L0–L4 conformance is unaffected by this extension.

### 10.2 L5 Verifiable (Optional)

Backends that opt into verifiable compute conformance (L5) MUST:

- Preserve `ext_attest` byte-for-byte (same as L0–L4).
- Reject jobs whose `input_digest` does not match the recomputed digest when
  verification is enabled.
- Expose a `/v1/jobs/{id}/verify` endpoint (Section 5.3).
- Enforce cluster policies at dequeue time (Section 7.3).
- Validate `ext_attest` size limits (Section 9).

### 10.3 SDK Requirements

SDKs that support `ext_attest` MUST:

- Provide builder APIs for constructing `ext_attest` envelopes.
- Implement `input_digest` computation using RFC 8785 canonical JSON.
- Provide a `verify()` function for offline receipt verification.
- Support at least `ed25519` signature verification.

---

## 11. Non-Requirements

The following are explicitly **out of scope** for this extension:

1. **OJS is NOT a KMS.** Key generation, rotation, and distribution are outside
   the scope of `ext_attest`. The extension references keys by `key_id`; key
   management is delegated to external systems (AWS KMS, HashiCorp Vault, etc.).

2. **OJS is NOT a model registry.** While `model_fingerprint` records a hash and
   optional registry URL, OJS does not host, index, or distribute model weights.

3. **OJS is NOT a TEE vendor.** This extension defines the envelope format for
   attestation data but does not specify how hardware attestation is obtained.
   That is the responsibility of the TEE SDK (AWS Nitro SDK, Intel TDX SDK, etc.).

4. **OJS is NOT a certificate authority.** The `key_id` field references an
   existing key identity (DID, URI). OJS does not issue, sign, or revoke
   certificates.

5. **OJS is NOT a compliance engine.** Cluster policies express attestation
   requirements, but compliance determination (e.g., "is this HIPAA-compliant?")
   is an application-level concern.

---

## 12. Security Considerations

1. **Key compromise.** If a worker's signing key is compromised, all receipts
   signed by that key become untrustworthy. Implementations SHOULD support key
   rotation and SHOULD publish key revocation lists.

2. **Replay attacks.** The `nonce` field provides replay protection. Verifiers
   MUST check nonce freshness. Implementations SHOULD reject quotes older than
   1 hour.

3. **Side-channel attacks.** Hardware attestation (Nitro, TDX, SEV-SNP) provides
   protection against certain side-channel attacks, but this is a property of the
   TEE, not of this extension. The `pqc-only` type provides no side-channel
   protection.

4. **Quantum readiness.** The `hybrid:Ed25519+ML-DSA-65` algorithm provides
   protection during the post-quantum transition. Implementations SHOULD migrate
   to hybrid signatures before quantum-capable adversaries emerge.

5. **Digest manipulation.** The `input_digest` MUST be computed by the worker
   after dequeue, not provided by the enqueuer. If the enqueuer controlled the
   digest, a malicious enqueuer could submit a pre-computed digest that does not
   match the actual inputs.

6. **Envelope integrity.** The `ext_attest` object MUST NOT be modified after
   signing. Backends that transform job envelopes (e.g., middleware) MUST
   preserve `ext_attest` byte-for-byte.

---

## 13. Examples

### 13.1 Minimal Attestation (pqc-only)

```json
{
  "id": "019034ab-7c8d-7def-abcd-1234567890ab",
  "type": "billing.invoice.generate",
  "queue": "billing",
  "args": [{"customer_id": "cust-001", "period": "2026-Q1"}],
  "ext_attest": {
    "v": 1,
    "quote": {
      "type": "pqc-only",
      "evidence": "",
      "nonce": "b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9",
      "issued_at": "2026-04-17T12:00:00Z"
    },
    "jurisdiction": {
      "region": "us-east-1",
      "prover": "billing-worker-03.prod.example.com"
    },
    "signature": {
      "alg": "ed25519",
      "value": "MEUCIQC7y2Ln1vEMwOz8aG...",
      "key_id": "did:web:example.com:keys:billing-2026"
    },
    "input_digest": "sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    "output_digest": "sha256:2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae",
    "receipt_id": "019034ab-rcpt-min-0000-aaaaaaaaaaaa"
  }
}
```

### 13.2 Full Hardware Attestation with Model Fingerprint

```json
{
  "id": "019034ab-ai00-7def-abcd-1234567890ab",
  "type": "ai.inference.summarize",
  "queue": "ai-workers",
  "args": [{"document_url": "s3://docs/report.pdf", "max_length": 500}],
  "ext_attest": {
    "v": 1,
    "quote": {
      "type": "aws-nitro-v1",
      "evidence": "hEShATgioFkRH6lpbW9kdWxlX2lkeCdpLTBhYmNkZWYx...",
      "nonce": "a3f8b2c1d4e5f67890123456789abcde",
      "issued_at": "2026-04-17T12:00:01Z"
    },
    "jurisdiction": {
      "region": "us-east-1",
      "datacenter": "use1-az1",
      "prover": "i-0abcdef1234567890"
    },
    "model_fingerprint": {
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "registry_url": "https://models.example.com/llama-3.1-70b@sha256:e3b0c442..."
    },
    "signature": {
      "alg": "hybrid:Ed25519+ML-DSA-65",
      "value": "MEUCIQC7y2Ln1vEMwOz8aG...",
      "key_id": "did:web:example.com:keys:enclave-2026-q2"
    },
    "input_digest": "sha256:d7a8fbb307d7809469ca9abcb0082e4f8d5651e46d3cdb762d02d0bf37c9e592",
    "output_digest": "sha256:ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d",
    "receipt_id": "019034ab-rcpt-full-0000-bbbbbbbbbbbb"
  }
}
```

### 13.3 Verification Failure Response

```json
{
  "verified": false,
  "checks": {
    "schema": "pass",
    "nonce": "pass",
    "freshness": "pass",
    "input_digest": "fail",
    "output_digest": "skip",
    "quote": "skip",
    "signature": "skip",
    "policy": "skip"
  },
  "errors": [
    {
      "check": "input_digest",
      "expected": "sha256:9f86d081884c7d659a2feaa0c55ad015...",
      "actual": "sha256:e3b0c44298fc1c149afbf4c8996fb924...",
      "message": "Recomputed input digest does not match ext_attest.input_digest"
    }
  ],
  "verified_at": "2026-04-17T13:05:00Z"
}
```
