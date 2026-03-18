# Open Job Spec — Extension Registry

| Field        | Value                                                  |
|--------------|--------------------------------------------------------|
| **Title**    | OJS Extension Registry                                 |
| **Version**  | 0.1.0-draft                                            |
| **Status**   | Draft (Stage 0 RFC)                                    |
| **Maturity** | Informational                                          |
| **Date**     | 2026-04-17                                             |
| **Layer**    | Meta (cross-cutting governance)                        |
| **URI**      | https://openjobspec.org/spec/v1/ojs-extension-registry |

---

## 1. Purpose

Provides a **single canonical list** of every reserved `ext_*` namespace in the
OJS envelope, the RFC that owns each, and its current lifecycle status under
[`ojs-extension-lifecycle.md`](./ojs-extension-lifecycle.md). This file MUST be
updated as part of any RFC that proposes a new top-level extension key.

The registry exists to:

1. Prevent name collisions across community extensions.
2. Give SDKs and backends a machine-checkable list of recognized keys (so
   unknown `ext_*` keys can be flagged or surfaced to operators).
3. Anchor the cross-references between extension RFCs and the conformance
   suite levels that exercise them.

## 2. Reservation Rules

- **R1.** Every top-level envelope key in the `ext_` namespace **MUST** appear in
  the table in §3 below before its specifying RFC reaches Stage 1.
- **R2.** Once reserved, a name **MUST NOT** be repurposed; deprecated extensions
  remain in the table with `Status: Retired` and a successor pointer.
- **R3.** A reservation **MAY** be filed at Stage 0 (draft) provided the proposing
  RFC PR is open and linked.
- **R4.** Backends and SDKs **SHOULD** preserve unknown `ext_*` keys verbatim
  (forward-compatibility); they **MUST NOT** strip them in normal operation.
- **R5.** `x-` prefixes are **RESERVED** for vendor / experimental extensions
  outside this registry; they have no portability guarantee.

## 3. Registry

### 3.1 Stable / Official Extensions

| Key             | RFC / Spec file                               | Status | Owner            | First introduced | Notes                                         |
|-----------------|-----------------------------------------------|--------|------------------|------------------|-----------------------------------------------|
| `ext_retry`     | [`ojs-retry.md`](./ojs-retry.md)              | Stable | spec WG          | v0.1             | Backoff, jitter, retry budgets.               |
| `ext_cron`      | [`ojs-cron.md`](./ojs-cron.md)                | Stable | spec WG          | v0.1             | Cron-style recurring schedules.               |
| `ext_unique`    | [`ojs-unique-jobs.md`](./ojs-unique-jobs.md)  | Stable | spec WG          | v0.1             | Unique-by-key deduplication.                  |
| `ext_workflow`  | [`ojs-workflows.md`](./ojs-workflows.md)      | Stable | spec WG          | v0.2             | chain / group / batch primitives.             |
| `ext_middleware`| [`ojs-middleware.md`](./ojs-middleware.md)    | Stable | spec WG          | v0.2             | Pre/post handlers, ordered chain.             |
| `ext_events`    | [`ojs-events.md`](./ojs-events.md)            | Stable | spec WG          | v0.2             | Lifecycle event emission.                     |

### 3.2 Experimental / Alpha Extensions

| Key          | RFC / Spec file                              | Status       | Owner    | Target promotion | Notes                                |
|--------------|----------------------------------------------|--------------|----------|------------------|--------------------------------------|
| `ext_agent`  | [`ojs-ai-agents.md`](./ojs-ai-agents.md)     | Experimental | agent WG | Official (v1)    | Alpha; superseded by `ext_agent_v2`. |

### 3.3 Reserved (Stage 0 — under active drafting)

These names are reserved by **moonshot RFCs** currently in draft. Each entry
points to the moonshot brief that motivates it. None has yet reached Stage 1;
schemas are illustrative and will firm up during the spike phase.

| Key             | Owning RFC (planned)         | Moonshot | Status     | Sketch                                                             |
|-----------------|------------------------------|----------|------------|--------------------------------------------------------------------|
| `ext_attest`    | `ojs-attest.md` (planned)    | M1       | Reserved   | TEE quote + jurisdiction proof + model fingerprint + PQC signature |
| `ext_agent_v2`  | `ojs-ai-agents-v2.md` (planned) | M2    | Reserved   | Successor to `ext_agent`; CAS-addressed memory; fork/merge ops     |
| `ext_runtime`   | `ojs-wasi-worker.md` (planned) | M3     | Reserved   | Worker runtime hints (server / edge / browser / mobile)            |
| `ext_mirror`    | `ojs-mirror.md` (planned)    | M4       | Reserved   | Source-system lineage when mirrored from Sidekiq/BullMQ/Celery/SQS |
| `ext_sourcemap` | `ojs-sourcemap.md` (planned) | M6       | Reserved   | Git SHA + source path for replay-studio step debugging             |

### 3.4 Retired

*(none yet)*

## 4. Reserved Operation Names

In addition to the seven core logical operations
(`PUSH`, `FETCH`, `ACK`, `FAIL`, `BEAT`, `CANCEL`, `INFO`), the following
operation names are reserved by moonshot RFCs and **MUST NOT** be used by
unrelated extensions:

| Operation              | Owning RFC          | Notes                                             |
|------------------------|---------------------|---------------------------------------------------|
| `VERIFY`               | `ojs-attest.md`     | Offline verification of a job's attestation chain |
| `PAUSE_HUMAN`          | `ojs-ai-agents-v2.md` | Mark job as awaiting human input                |
| `RESUME_HUMAN`         | `ojs-ai-agents-v2.md` | Resume from a human-paused state                |
| `FORK_AGENT`           | `ojs-ai-agents-v2.md` | Branch a conversation tree                      |
| `MERGE_AGENT`          | `ojs-ai-agents-v2.md` | Merge sibling branches                          |
| `TOOL_RETRY_ALTERNATE` | `ojs-ai-agents-v2.md` | Retry an agent tool call on an alternate provider |

## 5. Process to Reserve a New `ext_*` Key

1. Open an RFC draft PR in `spec/rfcs/`.
2. Add a row to §3.3 of this file in the same PR.
3. Choose a name that is:
   - Lowercase, snake-case.
   - Prefixed with `ext_`.
   - Distinctive (no overlap with existing entries; no two names that differ
     only by version suffix unless successors of one another).
4. After Stage-1 acceptance, move the row from §3.3 to §3.1 / §3.2 as
   appropriate and link the published spec file.

## 6. Machine-Readable Form

A normative, machine-readable copy of this registry MUST be maintained in
parallel at `spec/spec/registry/extensions.json`, with one object per row of
§3 and §4 keyed by `key` / `operation`. SDKs and conformance tooling SHOULD
consume the JSON form rather than parse this Markdown.

```json
{
  "version": "0.1.0-draft",
  "extensions": [
    {"key": "ext_retry",   "status": "stable",       "spec": "ojs-retry.md"},
    {"key": "ext_attest",  "status": "reserved",     "spec": "ojs-attest.md"}
  ],
  "operations": [
    {"name": "VERIFY", "status": "reserved", "spec": "ojs-attest.md"}
  ]
}
```

## 7. References

- [`ojs-extension-lifecycle.md`](./ojs-extension-lifecycle.md) — promotion model.
- [`ojs-extension-interactions.md`](./ojs-extension-interactions.md) — combination semantics.
- Moonshot Brief — `MOONSHOT_BRIEF.md` Parts 5 & 6.
