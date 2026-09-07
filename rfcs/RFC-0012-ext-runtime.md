# RFC-0012: ext_runtime — Runtime Capability Envelope

- **Stage**: 2 (Draft)
- **Champion**: TBD
- **Created**: 2026-04-17
- **Last Updated**: 2026-04-17
- **Target Spec Version**: 1.2.0
- **Reserved in registry**: `spec/spec/registry/extensions.json` → `ext_runtime`
- **Related moonshot**: M2 Universal Worker Runtime
- **Stability tier**: ![labs](https://img.shields.io/badge/OJS-Labs-blueviolet) (see [STABILITY.md](https://github.com/openjobspec/openjobspec/blob/main/STABILITY.md#ojs-labs))

## Summary

Reserve and define `ext_runtime` for declaring **what runtime a job needs**
(language, version, resources, GPU, network policy, sandbox profile).
Companion to M2 (Universal Worker Runtime), which lets a single binary
execute jobs from any language by spinning up the declared runtime.

## Motivation

Today every OJS worker is a same-language process: a Go worker only runs
Go handlers, a Python worker only runs Python. This forces ops teams to
maintain N worker fleets for N languages — a major operational tax.

`ext_runtime` lets a single "universal worker" choose the runtime per job:
- Wasm sandboxes for fast, untrusted handlers
- Containerized Python for ML workloads
- Native Node for I/O-bound work
- GPU-bound runtime for inference jobs

## Prior Art

- **Knative** — runtime-on-demand via container cold start. Heavy.
- **wasmCloud / Spin** — Wasm-first runtime selector. Compelling latency.
- **AWS Lambda runtime API** — closed, vendor-specific.
- **Temporal worker SDK** — language-bound; no cross-runtime story.

## Detailed Design

```jsonc
{
  "ext_runtime": {
    "v": 1,
    "kind": "wasm" | "container" | "native",
    "language": "python" | "go" | "node" | "rust" | "ruby" | "java" | "wasm",
    "version": "3.12",
    "image": "ghcr.io/example/handler@sha256:...",   // for kind=container
    "module": "ipfs://Qm...",                         // for kind=wasm
    "entrypoint": "handlers.process",
    "resources": {
      "cpu_millis": 500,
      "memory_mib": 256,
      "gpu": "nvidia-a100",
      "timeout_seconds": 300
    },
    "sandbox": {
      "filesystem": "readonly" | "tmpfs" | "none",
      "network": "egress-allow-list",
      "egress_hosts": ["api.openai.com:443"]
    }
  }
}
```

The universal worker (M2 deliverable) reads `ext_runtime`, pulls/loads the
runtime, executes the job, and returns the result. Workers MAY advertise
their supported runtimes via `/v1/capabilities`.

## Examples

See `ojs-universal-worker/` (M2 P1 deliverable, repo TBD).

## Conformance Impact

- New optional capability list `runtimes` in `/v1/capabilities`.
- L0–L4 unchanged.
- A new "Runtime Conformance" test pack (M2) verifies that a worker
  advertising `runtimes: [wasm, python:3.12]` actually executes those.

## Backward Compatibility

Fully backward compatible. Workers without `ext_runtime` support treat it
as opaque metadata.

## Implementation Requirements

- [ ] Go: M2 worker reference impl
- [ ] One sandbox runtime: Wasm via wazero (no CGo)

## Alternatives Considered

1. **Encode runtime in queue name** (e.g., `ml-jobs`, `web-jobs`) —
   industry's current approach. Rejected: no portability, no introspection.
2. **Separate "runtime" service** — adds infrastructure; defeats the
   simplification goal.

## Open Questions

1. Image pull authentication: re-use codec-server `KeyProvider` or new
   contract?
2. Should resource limits be MUST-honor or SHOULD-best-effort?
3. Do we need a `pre_pull_at` hint so workers can warm caches?
