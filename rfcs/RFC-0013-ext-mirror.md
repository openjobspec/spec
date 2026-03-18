# RFC-0013: ext_mirror — Dual-Run Migration Envelope

- **Stage**: 2 (Draft)
- **Champion**: TBD
- **Created**: 2026-04-17
- **Last Updated**: 2026-04-17
- **Target Spec Version**: 1.2.0
- **Reserved in registry**: `spec/spec/registry/extensions.json` → `ext_mirror`
- **Related moonshot**: M4 Live Shadow Migration (`ojs-mirror/`)
- **Stability tier**: ![labs](https://img.shields.io/badge/OJS-Labs-blueviolet) (see [STABILITY.md](../../STABILITY.md#ojs-labs))

## Summary

Reserve and define `ext_mirror`, an envelope key that marks a job as part
of a dual-run migration (`ojs-mirror`). It carries the correlation ID
linking the LHS (legacy) and RHS (OJS) execution, and the diff-policy
decisions.

## Motivation

`ojs-mirror` (M4) runs every job on both a legacy job system and an
OJS-compliant backend in parallel until teams trust the new side. The diff
engine needs a way to **pair** the LHS and RHS executions reliably, even
across retries and re-enqueues. A queue-name convention isn't enough —
correlation must survive backend round-trips.

## Prior Art

- **Stripe's online migrations**
  (`https://stripe.com/blog/online-migrations`). Same dual-write pattern,
  no spec.
- **Linkerd's traffic shifting** — analog at the HTTP layer.
- No background-job competitor offers this pattern as a first-class feature.

## Detailed Design

```jsonc
{
  "ext_mirror": {
    "v": 1,
    "correlation_id": "uuidv7",
    "side": "lhs" | "rhs",
    "source_system": "sidekiq" | "bullmq" | "celery" | "rabbitmq" | "custom",
    "diff_policy": {
      "fields_allowed_to_differ": ["completed_at", "result.processing_ms"],
      "side_effect_mode": "execute" | "sandbox" | "idempotent",
      "sample_rate": 1.0
    },
    "authoritative": "lhs" | "rhs",     // who's results count for downstream
    "started_at": "2026-04-17T12:00:00Z"
  }
}
```

The diff engine uses `correlation_id` to pair entries; `authoritative`
tells downstream consumers which side's results to use.

## Examples

See `ojs-mirror/docs/design.md` and `ojs-mirror/cmd/ojs-mirror/main.go`.

## Conformance Impact

L0–L4 backends MUST preserve `ext_mirror` opaquely. No new MUST/SHOULD
otherwise.

## Backward Compatibility

Fully backward compatible.

## Implementation Requirements

- [ ] Go: `ojs-mirror` reference implementation
- [ ] One source adapter (Sidekiq) + one sink adapter (`ojs-backend-postgres`)

## Alternatives Considered

1. **Out-of-band correlation table** — rejected: pairing breaks under
   retries that change job IDs.
2. **Reuse `ext_workflow`** — rejected: semantically different.

## Open Questions

1. Should `diff_policy` live in the envelope or be referenced by ID?
   (Inline lets each job carry its own policy; reference saves bytes.)
2. Do we need a `cutover_phase` field for staged % migrations?
