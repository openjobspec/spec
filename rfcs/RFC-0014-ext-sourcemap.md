# RFC-0014: ext_sourcemap — Job → Source Code Provenance

- **Stage**: 2 (Draft)
- **Champion**: TBD
- **Created**: 2026-04-17
- **Last Updated**: 2026-04-17
- **Target Spec Version**: 1.2.0
- **Reserved in registry**: `spec/spec/registry/extensions.json` → `ext_sourcemap`
- **Related moonshot**: M6 Time-Travel Debugger
- **Stability tier**: ![labs](https://img.shields.io/badge/OJS-Labs-blueviolet) (see [STABILITY.md](https://github.com/openjobspec/openjobspec/blob/main/STABILITY.md#ojs-labs))

## Summary

Reserve and define `ext_sourcemap`, an envelope key that pins a job to the
exact source-code revision and handler symbol that produced and will
process it. Foundation for M6's "click any historical job, jump to the
code that ran it" experience and a precondition for any reliable
post-mortem of a long-running job.

## Motivation

When a 6-month-old job fails to retry, no operator can answer "what code
ran this?" without manual archeology. `ext_sourcemap` makes that lookup
O(1):

- Producer-side: handler module + symbol + git SHA at enqueue time.
- Worker-side: same fields at dequeue, plus binary build ID.
- Combined: a verifiable chain from enqueue → execution → result, pinned
  to source.

This is the substrate the Time-Travel Debugger (M6) lights up on top of.

## Prior Art

- **Sentry release tracking** — runtime errors → source SHA; not job-system aware.
- **Datadog APM source maps** — same, for distributed traces.
- **Temporal workflow versioning** — closest analog; vendor-locked.
- No background-job competitor exposes this.

## Detailed Design

```jsonc
{
  "ext_sourcemap": {
    "v": 1,
    "producer": {
      "git_sha": "deadbeef...",
      "git_repo": "github.com/example/app",
      "handler_module": "com.example.jobs.ProcessOrder",
      "handler_symbol": "ProcessOrder.handle",
      "build_id": "abc123",
      "language": "java",
      "enqueued_at_revision_url": "https://github.com/example/app/blob/deadbeef.../jobs/ProcessOrder.java#L42"
    },
    "worker": {
      "git_sha": "deadbeef...",        // populated at dequeue
      "build_id": "xyz789",
      "started_at_revision_url": "..."
    }
  }
}
```

The `worker` block is populated when the worker leases the job. Mismatch
between producer and worker `git_sha` is allowed (it's normal during
deploys) but recorded for debugging.

## Examples

```bash
ojs jobs inspect <job-id> --show-source
# Opens the handler URL at the producer git SHA in your default browser.
```

## Conformance Impact

L0–L4 unchanged. `ext_sourcemap` is opaque-preserved like all extensions.
M6 introduces optional tooling that consumes it (CLI, web UI).

## Backward Compatibility

Fully backward compatible.

## Implementation Requirements

- [ ] Go SDK: auto-populate `producer` block via `runtime.Caller` + `debug.ReadBuildInfo`
- [ ] Python SDK: auto-populate via `inspect` + git introspection
- [ ] CLI: `ojs jobs inspect --show-source` (M6 P1)

## Alternatives Considered

1. **Stuff into `meta`** — rejected: meta is producer-defined, not standardized.
2. **Auto-derive at runtime per query** — rejected: source SHA at query
   time is not the SHA at enqueue time; you lose the historical view.

## Open Questions

1. Should `git_sha` be required or best-effort? (Recommend best-effort —
   not all environments have git introspection.)
2. URL templating: hard-code GitHub/GitLab patterns or take a template
   string per repo?
