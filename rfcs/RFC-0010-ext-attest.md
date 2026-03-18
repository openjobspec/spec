# RFC-0010: ext_attest — Verifiable Compute Attestation Envelope

- **Stage**: 2 (Draft)
- **Champion**: TBD (crypto lead)
- **Created**: 2026-04-17
- **Last Updated**: 2026-04-17
- **Target Spec Version**: 1.2.0
- **Reserved in registry**: `spec/spec/registry/extensions.json` → `ext_attest`
- **Related moonshot**: M1 Verifiable Compute (`files/MOONSHOT_BRIEF.md`)
- **Stability tier**: ![labs](https://img.shields.io/badge/OJS-Labs-blueviolet) (see [STABILITY.md](../../STABILITY.md#ojs-labs))

## Summary

Reserve and define the `ext_attest` envelope key. It carries a verifiable
attestation document binding job inputs and outputs to a measurement of the
executing runtime (hardware enclave, trusted runtime, or signature-only).
This is the wire-format hook for OJS's "verifiable compute" moonshot — every
other piece (codec-server Signer/Attestor plugins, CTN witnessing) plugs in
behind this single envelope key.

## Motivation

OJS is currently a "trust the worker" system: an enqueuer has no
cryptographic way to prove that the job ran in the environment claimed,
that the inputs weren't tampered with, or that the outputs weren't
fabricated. This blocks high-trust use cases:

- Regulated workloads (HIPAA, PCI, GDPR processor obligations)
- Multi-tenant SaaS where the platform must prove isolation to each tenant
- Cross-organization workflows (M5 CTN scenarios)
- Supply-chain provenance for AI model training/inference jobs

No competitor in the background-job space (Sidekiq, BullMQ, Celery, Faktory,
Temporal, Oban, River, Asynq) offers attested execution. The closest analog
is Sigstore for build pipelines and AWS Nitro for confidential compute —
neither integrates at the job-system layer.

## Prior Art

- **Sigstore / in-toto** — signed build provenance for software artifacts.
  Same trust model, different artifact (`https://github.com/in-toto/attestation`).
- **AWS Nitro Attestation Documents** — hardware-rooted enclave attestation
  (`https://docs.aws.amazon.com/enclaves/latest/user/nitro-enclave.html`).
- **Intel TDX** + **AMD SEV-SNP** — confidential VM attestation.
- **Temporal** — has signed workflow histories, but no executor attestation.
- **Sidekiq / BullMQ / Celery** — no equivalent feature.

## Detailed Design

### Envelope key

```jsonc
{
  // ... standard OJS job envelope ...
  "ext_attest": {
    "v": 1,
    "alg": "ed25519",                  // signature algorithm; see registry
    "type": "aws-nitro",               // attestation type; see registry
    "key_id": "did:web:example.com:keys:worker-2026",
    "input_digest": "sha256:...",      // hex; covers args + meta as canonical JSON
    "output_digest": "sha256:...",     // present once result is sealed
    "document": "base64...",           // attestation document blob (opaque to OJS)
    "signature": "base64...",          // signature over (input_digest || output_digest || document)
    "signed_at": "2026-04-17T12:00:00Z"
  }
}
```

### Lifecycle

1. **Worker startup** — produces attestation document (`Attestor.Attest`
   from `ojs-codec-server/plugin.go`).
2. **Job dequeue** — worker computes `input_digest = SHA-256(canonical_json(args || meta))`.
3. **Job execution** — produces output.
4. **Job completion** — worker computes `output_digest`, signs the triple
   `(input_digest || output_digest || document)` with its key, attaches
   `ext_attest`.
5. **Verifier** (any party with the worker's public key + a trusted root)
   replays the digest and verifies signature + attestation freshness.

### Algorithm registry

Reuses identifiers already declared in
`ojs-codec-server/plugin.go`:

- Signature algs: `ed25519`, `ml-dsa-65`, `rsa-pss-sha256`
- Attestation types: `aws-nitro`, `intel-tdx`, `amd-sev-snp`, `pqc-only`

### Canonical JSON

`input_digest` and `output_digest` MUST be computed over the
**RFC 8785 (JSON Canonicalization Scheme) serialization** of the relevant
job fields. This ensures cross-language reproducibility.

## Examples

See `examples/verifiable-compute/` (P1 deliverable) for end-to-end Go and
Python reference implementations.

## Conformance Impact

- **New conformance level: L5 (Verifiable).** Optional; backends opt in.
- L5 introduces:
  - **MUST** preserve `ext_attest` byte-for-byte across enqueue → dequeue → result.
  - **MUST** reject jobs whose `input_digest` does not match the recomputed digest, when verification is enabled.
  - **SHOULD** expose a verification API (`/v1/jobs/{id}/verify`).

L0–L4 conformance is unaffected.

## Backward Compatibility

Fully backward compatible. `ext_attest` is an optional envelope key;
backends that don't understand it MUST preserve it as opaque bytes
(this is already the existing OJS extension contract, see
`spec/spec/ojs-extension-lifecycle.md`).

## Implementation Requirements

Stage 2+ requires working prototypes in two languages:

- [ ] Go — `ojs-go-sdk` + `ojs-codec-server` integration
- [ ] Python — `ojs-python-sdk` (M1 P1 deliverable)

## Alternatives Considered

1. **Per-operation signature header** — rejected: doesn't survive backend
   round-tripping without envelope-level treatment.
2. **Side-channel attestation log** — rejected: breaks the single-envelope
   contract that makes OJS portable.
3. **CloudEvents-style extension attribute** — partially adopted; `ext_attest`
   follows the same shape as existing OJS extensions for consistency.

## Open Questions

1. Should `document` be split into `document_format` + `document` to allow
   evolution (e.g., COSE → JWS → in-toto)?
2. Do we need an explicit `nonce` field for replay protection, or is the
   `signed_at` + `input_digest` pair sufficient?
3. Witness co-signatures: in-envelope or separate CTN entry only? (M5 dependency.)
