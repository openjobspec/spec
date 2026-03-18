# OJS-WASI 0.1.0 — `wasi:ojs/worker` Specification

- **Stage**: 0 (Strawman)
- **Version**: 0.1.0
- **WIT file**: [`spec/wit/wasi-ojs-0.1.0.wit`](./wit/wasi-ojs-0.1.0.wit)
- **Related moonshot**: M3 wasi:ojs Workers (`files/MOONSHOT_BRIEF.md`)
- **Status**: M3/P0 spike artifact — surface area frozen for prototype

## Goals

A polyglot, sandboxed, portable worker ABI for Open Job Spec. A worker
binary compiled to a `wasm32-wasi` component MUST be runnable, unmodified,
on:

- A native CLI host (`wasmtime` + ojs-go-sdk worker pool — M3/P1)
- A browser host (`wasm-rs` in a Web Worker — M3/P2)
- A mobile host (iOS WKWebView / Android WebView wrappers — M3/P3)

The wire envelope MUST be byte-identical to the JSON envelope defined by
`ojs-core.md`; transport is opaque to the guest.

## Non-Goals (P0)

- No streaming results (single-shot `complete` / `fail` only)
- No host-side persistent storage exposed (use `enqueue` for any side effect)
- No cross-job synchronization primitives
- No async/await — guests are expected to drive event loops themselves

## Lease Lifecycle

```
   guest.run()
      │
      ▼
   jobs.fetch(queue, wait_seconds)  ──► returns (envelope, lease_token)
      │
      ├─► loop while job not done:
      │       lease.heartbeat(token, extra=lease_duration/2)
      │
      ├─► success path: jobs.complete(token, completion)
      └─► failure path: jobs.fail(token, job_error)
```

### Invariants

1. **Token uniqueness.** A `lease-token` is single-use across `complete`
   and `fail`. Calling either with an already-finalized token MUST return
   `host-error::lease-not-found`.
2. **Heartbeat clamp.** Host MAY clamp `extra-seconds` to a configured
   maximum (e.g. 300s). Guest MUST handle the returned expiry being
   smaller than what it asked for.
3. **Lease expiry.** If wall-clock time exceeds the expiry, the host
   MUST treat the job as abandoned and re-issue with a new token. The
   guest's stale token MUST be rejected as `lease-expired`.
4. **No host time-travel.** Host MUST NOT decrement a previously-issued
   expiry. New expiries are monotonically non-decreasing per token.
5. **Crash safety.** Guest panics, traps, or process death MUST be
   indistinguishable from lease expiry (the host has no other recourse).

## Wire Format

The `envelope.args` field carries canonical-JSON-encoded arg arrays. Same
canonicalization rule as RFC-0010: P0 uses `encoding/json` deterministic
key ordering; the WIT version will move to RFC 8785 JCS in P1.

The `envelope.ext` list of `(key, value)` tuples carries reserved
extension keys (`ext_attest`, `ext_agent`, `ext_runtime`, `ext_mirror`,
`ext_sourcemap`) per the registry in `spec/spec/registry/extensions.json`.

## Versioning

The package version `wasi:ojs@0.1.0` follows WASI's component-model
versioning: any breaking change bumps the minor (pre-1.0) or major
(post-1.0). Hosts MUST refuse to instantiate guests targeting an
incompatible version.

## Open Questions (P0 → P1)

1. Should `jobs.fetch` accept multiple queues for fairness?
2. How does the guest discover its own worker identity for `ext_attest`?
3. Should we expose `wasi:clocks/monotonic-clock` directly or wrap it?
4. Is `enqueue` synchronous-ack or fire-and-forget?

These resolve in the M3/P1 prototype, recorded as ADRs under
`spec/adrs/`.
