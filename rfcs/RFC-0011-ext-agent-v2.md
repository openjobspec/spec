# RFC-0011: ext_agent_v2 — First-Class Agent Workflow Envelope

- **Stage**: 2 (Draft)
- **Champion**: TBD
- **Created**: 2026-04-17
- **Last Updated**: 2026-04-17
- **Target Spec Version**: 1.2.0
- **Reserved in registry**: `spec/spec/registry/extensions.json` → `ext_agent_v2`
- **Supersedes**: `ext_agent` (v1, marked Experimental)
- **Related moonshot**: M3 Agent-Native Job System
- **Stability tier**: ![labs](https://img.shields.io/badge/OJS-Labs-blueviolet) (see [STABILITY.md](https://github.com/openjobspec/openjobspec/blob/main/STABILITY.md#ojs-labs))

## Summary

Define `ext_agent_v2` as the second-generation agent workflow envelope
key. It models LLM-agent job patterns that v1 didn't: human-in-the-loop
pauses (`PAUSE_HUMAN`/`RESUME_HUMAN`), agent forking and merging
(`FORK_AGENT`/`MERGE_AGENT`), and tool-retry-with-alternate
(`TOOL_RETRY_ALTERNATE`). All four operations are pre-reserved in the
extension registry.

## Motivation

`ext_agent` (v1) treated agent calls as opaque single-shot jobs. Real
agent workflows in 2026 need:

- **Human checkpoints.** Approval gates between tool calls (e.g., "before
  executing this SQL, get human sign-off"). v1 forces external coordination.
- **Speculative branching.** Run two prompts in parallel, take the winner.
- **Tool fallback.** When `search_web` fails, retry with `search_archive`
  preserving the original conversation context.

Today this lives in app code (LangGraph state machines, Temporal workflows
with bespoke wrappers). Bringing it into the OJS envelope makes it
backend-portable and observable in the same lens as every other job.

## Prior Art

- **LangGraph** — state-machine orchestration for LLM agents
  (`https://langchain-ai.github.io/langgraph/`). No portability layer.
- **Temporal AI SDK** — agent workflows on top of Temporal primitives.
  Vendor-locked.
- **OpenAI Assistants API** — closed runtime; no extraction path.
- **OJS `ext_agent` v1** — `spec/spec/ojs-agent.md`. Tool-call recording
  only; no lifecycle ops.

## Detailed Design

### Envelope shape

```jsonc
{
  "ext_agent_v2": {
    "v": 2,
    "agent_id": "uuidv7",
    "parent_agent_id": "uuidv7",       // for forks
    "state": "running" | "paused_human" | "forked" | "merged" | "completed",
    "checkpoints": [
      {
        "id": "ckpt-1",
        "kind": "human_approval",
        "prompt": "Approve SQL execution?",
        "data": { "sql": "DELETE FROM ..." },
        "decided_at": "2026-04-17T12:00:00Z",
        "decision": "approve" | "reject" | null,
        "decided_by": "user@example.com"
      }
    ],
    "tool_attempts": [
      {
        "tool": "search_web",
        "status": "failed",
        "alternate": "search_archive",  // for TOOL_RETRY_ALTERNATE
        "attempt": 1
      }
    ]
  }
}
```

### New operations (already reserved)

| Operation | Purpose | State precondition |
|---|---|---|
| `PAUSE_HUMAN` | Suspend job awaiting human decision | `active` → `paused_human` |
| `RESUME_HUMAN` | Resume after decision recorded | `paused_human` → `active` |
| `FORK_AGENT` | Spawn N child agent jobs sharing parent context | `active` → `forked` |
| `MERGE_AGENT` | Reduce N child results into parent | child `completed` → parent `active` |
| `TOOL_RETRY_ALTERNATE` | Retry tool call with named alternate | retry attempt |

### State machine extension

`paused_human` is a new pseudo-state layered on top of `active`. Workers
hold the lease but emit no progress until `RESUME_HUMAN` is invoked or
the lease expires (configurable, default 24h).

### Backend support

L0–L4 backends MUST preserve the envelope opaquely. A new optional
capability flag `agent_v2` is added to `/v1/capabilities` for backends
that natively implement the new operations.

## Examples

See `examples/agent-workflows/` (M3 P1 deliverable).

## Conformance Impact

- New optional capability `agent_v2` reported via `/v1/capabilities`.
- New conformance test pack (M3 deliverable, ~30 tests) covering each new operation.
- L0–L4 unchanged for non-agent backends.

## Backward Compatibility

`ext_agent` v1 envelopes remain valid indefinitely. v1 → v2 migration is
a no-op for jobs that don't use the new operations. Producers MAY emit
both keys during transition; consumers MUST prefer v2 if both present.

## Implementation Requirements

- [ ] Go SDK: `ojs-go-sdk/agent`
- [ ] Python SDK: `ojs-python-sdk/agent`
- [ ] One backend with native checkpoint storage (likely `ojs-backend-postgres`)

## Alternatives Considered

1. **Bolt onto `ext_workflow`** — rejected; agent state has fundamentally
   different semantics (non-deterministic, human-pausable).
2. **Out-of-band agent service** — rejected; defeats OJS's portability promise.
3. **In-place evolution of `ext_agent` v1** — rejected; breaking change to
   semantics warrants a new key.

## Open Questions

1. Should checkpoint data have a size cap (e.g., 64 KB) and require
   blob-store offload above that?
2. `decided_by` — opaque string or did:web identifier?
3. How do we model **streaming** agent output in the envelope without
   bloating it? Likely separate `ext_runtime` integration (RFC-0012).
