# OJS Execution-History 0.1 — Cross-SDK Trace Schema

- **Stage**: 0 (Strawman)
- **Version**: `ojs-exec-history/0.1`
- **Validator**: [`ojs-conformance/lib/exechistory.go`](../ojs-conformance/lib/exechistory.go)
- **Related moonshot**: M6 Replay Studio + Learned Scheduler (`files/MOONSHOT_BRIEF.md`)
- **Status**: M6/P0 spike artifact

## Goals

A wire format every OJS SDK can write so that the Replay Studio (M6/P1) and
the contextual-bandit scheduler (M6/P2 shadow / P3 champion-challenger) can
ingest cross-language execution traces without per-SDK adapters. Format is
JSONL: one self-describing event per line, append-only, gzip-friendly.

## Goals

- **Polyglot.** Same wire shape from Go, Python, JS, Java, Rust, Ruby,
  .NET, PHP, WASM SDKs. No language-specific extensions in 0.1.
- **Append-only.** A trace file is a partition; rotation is the host's
  problem.
- **Forward-compatible.** Unknown attrs MUST be preserved when re-emitted.

## Non-Goals (0.1)

- Distributed-trace correlation (OpenTelemetry interop is a 0.2 concern).
- Schema evolution beyond an explicit `schema_version` bump.
- Server-side aggregation API; that's the Studio's job.

## Event Schema

Each line is a JSON object with the following fields:

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | string | yes | Must be `ojs-exec-history/0.1` for 0.1 emitters. |
| `envelope_id` | string | yes | The OJS envelope ID this span belongs to. |
| `sdk` | string | yes | Concrete SDK identifier (`ojs-go-sdk`, `ojs-py-sdk`, …). |
| `lang` | string | yes | Short language code (`go`, `python`, `ts`, …). |
| `span_kind` | string | yes | Closed set: `job.attempt`, `job.retry`, `job.middleware`, `workflow.fanout`, `workflow.gather`, `queue.dequeue`, `queue.enqueue`. |
| `started_at` | string | yes | RFC 3339 with nanoseconds. |
| `duration_ms` | number | yes | Must be ≥ 0. For in-flight spans, write 0 and `outcome=in_flight`. |
| `outcome` | string | yes | Closed set: `success`, `retryable`, `discarded`, `cancelled`, `in_flight`. |
| `attempt` | int | yes | 1-indexed retry counter. |
| `span_id` | string | yes | Unique within the trace file. |
| `parent_span_id` | string | no | Empty for top-level spans. |
| `worker_id` | string | no | Whatever the host considers stable identity. |
| `attrs` | object | no | Arbitrary key/value attributes. Validators MUST preserve unknown keys. |

## Validation Rules

The reference Go validator [`Replay`](../ojs-conformance/lib/exechistory.go)
enforces:

1. `schema_version` is in `AcceptedSchemaVersions`.
2. `span_kind` is in `KnownSpanKinds`.
3. `outcome` is in `KnownOutcomes`.
4. `started_at` parses as RFC 3339 with optional nanosecond precision.
5. `duration_ms ≥ 0`, `attempt ≥ 1`.
6. `envelope_id`, `span_id`, `sdk`, `lang` are non-empty.

`Replay` supports `strict=true` (first error stops the scan) and
`strict=false` (invalid lines are counted and skipped).

## Examples

```jsonl
{"schema_version":"ojs-exec-history/0.1","envelope_id":"01HRX...","sdk":"ojs-go-sdk","lang":"go","span_kind":"queue.dequeue","started_at":"2026-04-17T12:00:00.000000001Z","duration_ms":1.4,"outcome":"success","attempt":1,"span_id":"sp-001","worker_id":"go-pool-7"}
{"schema_version":"ojs-exec-history/0.1","envelope_id":"01HRX...","sdk":"ojs-go-sdk","lang":"go","span_kind":"job.attempt","started_at":"2026-04-17T12:00:00.001500000Z","duration_ms":248.7,"outcome":"success","attempt":1,"span_id":"sp-002","parent_span_id":"sp-001","worker_id":"go-pool-7","attrs":{"queue":"emails","kind":"send_invoice"}}
```

## Open Questions (P0 → P1)

1. Should we make `attrs` typed (e.g., separate `string_attrs` /
   `int_attrs`) for column-store ingestion?
2. Do we want a separate `error_message` field or stuff it under `attrs`?
3. Should `worker_id` be required? Trade-off: kills anonymous workers but
   makes scheduler features more reliable.

These resolve in M6/P1 — see ADRs under `spec/adrs/` once recorded.
