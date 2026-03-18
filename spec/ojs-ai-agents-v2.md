# Open Job Spec: Agent Substrate Protocol (ext_agent_v2)

| Field        | Value                                                    |
|-------------|----------------------------------------------------------|
| **Title**   | OJS Agent Substrate Protocol (ASP) Extension             |
| **Version** | 0.1.0-draft                                              |
| **Date**    | 2026-04-17                                               |
| **Status**  | Draft                                                    |
| **Maturity** | Alpha                                                   |
| **Layer**   | Extension                                                |
| **URI**     | `urn:ojs:ext:agent-v2`                                   |
| **Requires**| OJS Core Specification (Layer 1)                         |
| **Supersedes** | `ext_agent` (v1, Alpha)                               |
| **RFC**     | [RFC-0011](../rfcs/RFC-0011-ext-agent-v2.md)             |
| **License** | Apache 2.0                                               |

---

## Abstract

This extension defines `ext_agent_v2`, the second-generation envelope extension for
durable AI agent workflows. Where v1 (`ext_agent`) treated agent calls as opaque
single-shot jobs with tool-call recording, v2 introduces first-class lifecycle
operations for human-in-the-loop approval gates, speculative agent forking and merging,
tool-call fallback to alternate providers, a content-addressed memory DAG for
conversation history, and provider-portable replay semantics. By encoding these
capabilities into the OJS job envelope, agent workflows gain the same reliability,
observability, and backend portability guarantees that OJS provides for conventional
background jobs.

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Extension Fields](#4-extension-fields)
5. [Envelope Operations](#5-envelope-operations)
6. [State Machine](#6-state-machine)
7. [Memory DAG](#7-memory-dag)
8. [Tool-Call Schema](#8-tool-call-schema)
9. [Replay Semantics](#9-replay-semantics)
10. [Provider Portability](#10-provider-portability)
11. [Backward Compatibility](#11-backward-compatibility)
12. [Conformance Requirements](#12-conformance-requirements)
13. [Non-Requirements](#13-non-requirements)
14. [Security Considerations](#14-security-considerations)
15. [Examples](#15-examples)
16. [Versioning](#16-versioning)

---

## 1. Introduction

Real-world AI agent workflows in 2026 demand capabilities that v1 (`ext_agent`) cannot
express. An agent composing a complex report may need human approval before executing a
destructive database query. A coding agent may speculatively fork two solution approaches,
evaluate both, and merge the winner. When a web-search tool fails, the agent may need to
retry with an alternate archive-search provider while preserving conversational context.

Today, these patterns live in application code — LangGraph state machines, Temporal
workflows with bespoke wrappers, or vendor-locked platforms. Bringing them into the OJS
envelope makes them backend-portable and observable through the same lens as every other
OJS job.

### 1.1 Scope

This specification defines:

- Five new envelope operations for agent lifecycle management.
- A content-addressed Merkle DAG schema for durable conversation memory.
- A standardized tool-call schema compatible with MCP and A2A.
- Replay semantics for deterministic and non-deterministic agent steps.
- A provider portability envelope for resuming jobs across model providers.
- State machine extensions layered on top of the OJS core lifecycle.

### 1.2 Relationship to ext_agent (v1)

`ext_agent_v2` supersedes `ext_agent` (v1). All v1 fields (`ext_agent_model`,
`ext_agent_tools`, `ext_agent_tool_results`, etc.) remain valid. Consumers that only
read v1 fields continue to work without modification. Producers MAY emit both `ext_agent_*`
and `ext_agent_v2` fields during transition; consumers MUST prefer `ext_agent_v2` fields
when both are present.

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

All identifiers (job IDs, agent IDs) SHOULD use UUIDv7 for time-sortability.

---

## 3. Terminology

| Term                  | Definition                                                                                |
|-----------------------|-------------------------------------------------------------------------------------------|
| **Agent**             | A worker process that performs LLM inference and optionally invokes tools.                 |
| **Memory DAG**        | A content-addressed Merkle DAG recording the full conversation and tool-call history.     |
| **Checkpoint**        | A named point in the memory DAG from which execution can be paused, forked, or resumed.   |
| **Fork**              | Creating a new branch of agent execution from an existing checkpoint node.                |
| **Merge**             | Combining two or more branches of agent execution into a single continuation.             |
| **Human gate**        | A pause point where agent execution awaits human approval or rejection.                   |
| **Tool attempt**      | A single invocation of a tool, possibly one of several attempts with alternate providers. |
| **Provider**          | An LLM inference service (e.g., OpenAI, Anthropic, local vLLM).                          |
| **Replay**            | Re-executing an agent workflow from the memory DAG for debugging or auditing.             |
| **Content ID**        | A SHA-256 hash uniquely identifying a node in the memory DAG.                             |
| **ASP**               | Agent Substrate Protocol — the informal name for this extension.                          |

---

## 4. Extension Fields

All fields use the `ext_agent_v2` namespace. The top-level field is a single JSON object
attached to the job envelope. Implementations that support this extension MUST recognize
all fields defined in this section. Unrecognized sub-fields within `ext_agent_v2` MUST
be preserved but MAY be ignored.

**Rationale for MUST preserve**: Agent envelopes may traverse middleware, gateways, and
backend implementations that do not understand every sub-field. Silently dropping
unrecognized fields would corrupt the envelope and break downstream consumers.

### 4.1 Top-Level Structure

| Field               | Type     | Required | Default       | Description                                              |
|----------------------|----------|----------|---------------|----------------------------------------------------------|
| `v`                  | integer  | Yes      | —             | Schema version. MUST be `2`.                             |
| `agent_id`           | string   | Yes      | —             | Unique identifier for this agent instance (UUIDv7).      |
| `parent_agent_id`    | string   | No       | `null`        | Agent ID of the parent, set when forked.                 |
| `state`              | string   | Yes      | `"running"`   | Current agent state (see Section 6).                     |
| `memory_root`        | string   | No       | `null`        | Content ID of the current head of the memory DAG.        |
| `memory_nodes`       | object[] | No       | `[]`          | Inline memory DAG nodes (see Section 7).                 |
| `tool_attempts`      | object[] | No       | `[]`          | Tool invocation history (see Section 8).                 |
| `checkpoints`        | object[] | No       | `[]`          | Named checkpoints for human gates and forks.             |
| `provider_envelope`  | object   | No       | `null`        | Provider portability metadata (see Section 10).          |

#### `v` (integer)

Implementations MUST reject envelopes where `ext_agent_v2.v` is not `2` with error
code `AGENT_V2_UNSUPPORTED_VERSION`.

**Rationale for MUST reject**: Forward-incompatible schema changes would cause silent
data corruption if processed by a v2 consumer.

#### `state` (string)

The agent state. Valid values: `"running"`, `"paused_human"`, `"forked"`, `"merged"`,
`"completed"`. See Section 6 for the full state machine.

#### `checkpoints` (object[])

Each checkpoint records a named point in the agent's execution:

```json
{
  "id": "ckpt-001",
  "kind": "human_approval",
  "prompt": "Approve SQL execution: DELETE FROM users WHERE inactive = true?",
  "data": {"sql": "DELETE FROM users WHERE inactive = true", "row_estimate": 14200},
  "created_at": "2026-04-17T12:00:00Z",
  "decided_at": null,
  "decision": null,
  "decided_by": null,
  "memory_node": "sha256:abc123..."
}
```

| Field         | Type   | Required | Description                                               |
|---------------|--------|----------|-----------------------------------------------------------|
| `id`          | string | Yes      | Unique checkpoint identifier within this agent.           |
| `kind`        | string | Yes      | `"human_approval"`, `"fork_point"`, or `"save"`.          |
| `prompt`      | string | No       | Human-readable description of what is being requested.    |
| `data`        | object | No       | Arbitrary checkpoint payload (≤64 KB).                    |
| `created_at`  | string | Yes      | RFC 3339 timestamp of checkpoint creation.                |
| `decided_at`  | string | No       | RFC 3339 timestamp of human decision.                     |
| `decision`    | string | No       | `"approve"`, `"reject"`, or `null` (pending).             |
| `decided_by`  | string | No       | Identifier of the human who made the decision.            |
| `memory_node` | string | No       | Content ID of the memory DAG node at this checkpoint.     |

---

## 5. Envelope Operations

This extension defines five new logical operations. These operations are layered on top
of the OJS core lifecycle and do not replace existing operations.

### 5.1 PAUSE_HUMAN

Pause agent execution to await human approval.

**Precondition**: Agent state MUST be `"running"`.

**Effect**: Agent state transitions to `"paused_human"`. A new checkpoint of kind
`"human_approval"` is appended to `checkpoints`. The worker MUST hold its lease but
MUST NOT emit progress or invoke tools until `RESUME_HUMAN` is received or the lease
expires.

**Rationale for MUST hold lease**: Releasing the lease would allow another worker to
dequeue the job and potentially resume execution without the required human approval.

**Lease timeout**: Implementations SHOULD support a configurable lease timeout for
human-paused jobs. The default SHOULD be 24 hours. When the lease expires without a
`RESUME_HUMAN`, the implementation MUST transition the job to `"retryable"` per the
core lifecycle.

**Envelope after PAUSE_HUMAN**:

```json
{
  "id": "019034ab-7c8d-7def-abcd-1234567890ab",
  "type": "ai.agent.report",
  "queue": "agents",
  "args": ["Generate quarterly sales report"],
  "ext_agent_v2": {
    "v": 2,
    "agent_id": "019034ab-0000-7def-0000-aaaaaaaaaaaa",
    "state": "paused_human",
    "checkpoints": [
      {
        "id": "ckpt-001",
        "kind": "human_approval",
        "prompt": "Agent wants to query production database. Approve?",
        "data": {"sql": "SELECT * FROM orders WHERE total > 10000"},
        "created_at": "2026-04-17T12:30:00Z",
        "decision": null,
        "decided_by": null
      }
    ],
    "memory_root": "sha256:e3b0c44298fc1c149afbf4c8996fb924..."
  }
}
```

### 5.2 RESUME_HUMAN

Resume agent execution after a human decision has been recorded.

**Precondition**: Agent state MUST be `"paused_human"`. The most recent pending
checkpoint MUST have its `decision` field set before invoking this operation.

**Effect**: Agent state transitions to `"running"`. The checkpoint's `decided_at` and
`decided_by` fields are populated. If `decision` is `"reject"`, the implementation
MUST transition the job to `"cancelled"` rather than `"running"`.

**Rationale for MUST cancel on reject**: A rejected human gate means the agent's
proposed action was explicitly denied. Continuing execution would violate the human's
intent.

**Envelope after RESUME_HUMAN (approved)**:

```json
{
  "ext_agent_v2": {
    "v": 2,
    "agent_id": "019034ab-0000-7def-0000-aaaaaaaaaaaa",
    "state": "running",
    "checkpoints": [
      {
        "id": "ckpt-001",
        "kind": "human_approval",
        "prompt": "Agent wants to query production database. Approve?",
        "data": {"sql": "SELECT * FROM orders WHERE total > 10000"},
        "created_at": "2026-04-17T12:30:00Z",
        "decided_at": "2026-04-17T12:35:00Z",
        "decision": "approve",
        "decided_by": "ops-lead@example.com"
      }
    ]
  }
}
```

### 5.3 FORK_AGENT

Create a branch of agent execution from an existing checkpoint.

**Precondition**: Agent state MUST be `"running"`. A valid `memory_node` content ID
MUST be specified as the fork point.

**Effect**: A new child job is created with its own `agent_id`, `parent_agent_id` set
to the forking agent's ID, and the memory DAG branched from the specified node. The
parent agent's state transitions to `"forked"`. The child starts in state `"running"`.

Implementations MUST create the child job atomically — either both the child is
created and the parent transitions to `"forked"`, or neither occurs.

**Rationale for MUST atomic**: A fork that creates the child but fails to update the
parent would leave the system in an inconsistent state where the parent continues
executing alongside its fork.

**Fork request**:

```json
{
  "operation": "FORK_AGENT",
  "parent_agent_id": "019034ab-0000-7def-0000-aaaaaaaaaaaa",
  "fork_point": "sha256:a1b2c3d4...",
  "child_overrides": {
    "ext_agent_model": "claude-sonnet-4",
    "ext_agent_temperature": 0.3
  }
}
```

### 5.4 MERGE_AGENT

Merge two or more branches of agent execution back into a single continuation.

**Precondition**: All child agent jobs referenced in the merge MUST be in state
`"completed"`. The parent agent MUST be in state `"forked"`.

**Effect**: The parent agent transitions back to `"running"`. The child branches'
memory DAG nodes are merged according to the specified strategy. A new merge node
is appended to the parent's memory DAG.

**Merge strategies**:

| Strategy  | Behavior                                                              |
|-----------|-----------------------------------------------------------------------|
| `ours`    | Parent's context wins. Child results are recorded but not injected.   |
| `theirs`  | Child's context replaces the parent's from the fork point forward.    |
| `union`   | Both contexts are concatenated chronologically into the merged DAG.   |

Implementations MUST support all three strategies. The default strategy is `"theirs"`
when merging a single child. For multiple children, the default is `"union"`.

**Merge request**:

```json
{
  "operation": "MERGE_AGENT",
  "parent_agent_id": "019034ab-0000-7def-0000-aaaaaaaaaaaa",
  "children": [
    "019034ab-1111-7def-0000-bbbbbbbbbbbb",
    "019034ab-2222-7def-0000-cccccccccccc"
  ],
  "strategy": "union"
}
```

### 5.5 TOOL_RETRY_ALTERNATE

Retry a failed tool call with an alternate provider while preserving the conversation
context.

**Precondition**: A tool attempt MUST exist in `tool_attempts` with status `"failed"`.
The specified alternate tool MUST be declared in the agent's tool definitions or in
a provider-registered tool catalog.

**Effect**: A new tool attempt is appended with the alternate tool, referencing the
original attempt. The conversation context (memory DAG) is preserved; only the tool
invocation is replaced.

**Rationale for preserving context**: The LLM's decision to invoke a tool was correct;
only the tool execution failed. Replaying the entire conversation to reach the same
tool-call decision would be wasteful and non-deterministic.

**Envelope after TOOL_RETRY_ALTERNATE**:

```json
{
  "ext_agent_v2": {
    "v": 2,
    "state": "running",
    "tool_attempts": [
      {
        "attempt_id": "ta-001",
        "tool_id": "search_web",
        "tool_name": "Web Search",
        "provider": "tavily",
        "args": {"query": "OJS specification latest version"},
        "result": null,
        "error": {"code": "PROVIDER_TIMEOUT", "message": "Request timed out after 30s"},
        "duration_ms": 30000,
        "status": "failed",
        "timestamp": "2026-04-17T12:40:00Z"
      },
      {
        "attempt_id": "ta-002",
        "tool_id": "search_archive",
        "tool_name": "Archive Search",
        "provider": "archive_org",
        "args": {"query": "OJS specification latest version"},
        "result": {"snippets": ["..."]},
        "error": null,
        "duration_ms": 1200,
        "status": "succeeded",
        "retries_from": "ta-001",
        "timestamp": "2026-04-17T12:40:02Z"
      }
    ]
  }
}
```

---

## 6. State Machine

The `ext_agent_v2` state machine extends the OJS core job lifecycle. Agent states are
layered on top of the `active` core state — from the backend's perspective, the job
remains `active` while agent-level state transitions occur.

### 6.1 State Diagram

```
                        ┌──────────────────────────────────────────┐
                        │          OJS Core: active                │
                        │                                          │
                        │  ┌─────────┐   PAUSE_HUMAN   ┌────────────────┐
                        │  │         │ ───────────────► │                │
                        │  │ running │                  │ paused_human   │
                        │  │         │ ◄─────────────── │                │
                        │  └────┬────┘   RESUME_HUMAN   └────────────────┘
                        │       │          (approve)                │
                        │       │                           RESUME_HUMAN
                        │       │ FORK_AGENT                (reject)
                        │       │                                  │
                        │       ▼                                  ▼
                        │  ┌─────────┐                    OJS Core: cancelled
                        │  │         │
                        │  │ forked  │
                        │  │         │
                        │  └────┬────┘
                        │       │
                        │       │ MERGE_AGENT
                        │       │ (all children completed)
                        │       │
                        │       ▼
                        │  ┌─────────┐
                        │  │         │
                        │  │ running │ ──────────► OJS Core: completed
                        │  │         │
                        │  └─────────┘
                        │                                          │
                        └──────────────────────────────────────────┘
```

### 6.2 State Transition Rules

| From             | Operation       | To              | Condition                          |
|------------------|-----------------|-----------------|-------------------------------------|
| `running`        | `PAUSE_HUMAN`   | `paused_human`  | Checkpoint created                  |
| `paused_human`   | `RESUME_HUMAN`  | `running`       | Decision is `"approve"`             |
| `paused_human`   | `RESUME_HUMAN`  | (cancelled)     | Decision is `"reject"`              |
| `running`        | `FORK_AGENT`    | `forked`        | Child job created atomically        |
| `forked`         | `MERGE_AGENT`   | `running`       | All children in `"completed"`       |
| `running`        | (job completes) | `completed`     | Normal OJS completion               |

Implementations MUST reject operations that violate these preconditions with error
code `AGENT_V2_INVALID_STATE_TRANSITION`.

---

## 7. Memory DAG

The memory DAG is a content-addressed Merkle DAG that records the full conversation
and tool-call history of an agent workflow. Each node is immutable and identified by
its content hash.

### 7.1 Node Schema

```json
{
  "content_id": "sha256:e3b0c44298fc1c149afbf4c8996fb924...",
  "parents": ["sha256:a1b2c3d4..."],
  "type": "message",
  "payload": {
    "role": "assistant",
    "content": "I'll search for the latest sales figures."
  },
  "created_at": "2026-04-17T12:30:00Z"
}
```

| Field        | Type     | Required | Description                                              |
|--------------|----------|----------|----------------------------------------------------------|
| `content_id` | string   | Yes      | SHA-256 hash of `(parents + type + payload)`.            |
| `parents`    | string[] | Yes      | Content IDs of parent nodes. Empty for root nodes.       |
| `type`       | string   | Yes      | `"message"`, `"tool_call"`, `"tool_result"`, or `"checkpoint"`. |
| `payload`    | object   | Yes      | Type-specific content (see Section 7.2).                 |
| `created_at` | string   | Yes      | RFC 3339 timestamp.                                      |

#### `content_id` computation

Implementations MUST compute `content_id` as follows:

```
content_id = "sha256:" + hex(SHA-256(canonical_json(parents) + "|" + type + "|" + canonical_json(payload)))
```

Where `canonical_json` is [RFC 8785 JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785).

**Rationale for content-addressing**: Content-addressed nodes enable efficient
deduplication, integrity verification, and branch detection. Two nodes with the same
content ID are guaranteed to have identical content regardless of which branch produced
them.

### 7.2 Node Types

**`message`**: An LLM message (user, assistant, or system).

```json
{"role": "user", "content": "What were Q3 sales?"}
```

**`tool_call`**: A tool invocation request from the LLM.

```json
{"tool_id": "query_db", "args": {"sql": "SELECT SUM(total) FROM orders WHERE quarter = 'Q3'"}}
```

**`tool_result`**: The result of a tool invocation.

```json
{"tool_id": "query_db", "result": {"total": 4250000}, "duration_ms": 120}
```

**`checkpoint`**: A named checkpoint (human gate or fork point).

```json
{"checkpoint_id": "ckpt-001", "kind": "human_approval", "prompt": "Approve DB access?"}
```

### 7.3 Branching and Merging

A **fork** creates a new branch by appending a node with the fork-point node as its
parent. Both the original and forked branches can independently append new nodes.

A **merge** creates a new node with multiple parents — one from each branch being
merged. The merge node's payload records the merge strategy and which branch
contributions were accepted.

```json
{
  "content_id": "sha256:merged...",
  "parents": ["sha256:branch_a_head...", "sha256:branch_b_head..."],
  "type": "checkpoint",
  "payload": {
    "checkpoint_id": "ckpt-merge-001",
    "kind": "merge",
    "strategy": "union",
    "source_branches": ["branch_a", "branch_b"]
  }
}
```

### 7.4 Storage Considerations

Implementations MAY store memory DAG nodes inline in the envelope (`memory_nodes`
array) or externally in a content-addressable store referenced by `memory_root`.
Inline storage SHOULD be used only for small DAGs (≤50 nodes). For larger DAGs,
implementations SHOULD use external storage and include only the root reference.

---

## 8. Tool-Call Schema

The tool-call schema provides a standardized format for tool invocations that is
compatible with both the [Model Context Protocol (MCP)](https://modelcontextprotocol.io)
and the [Agent-to-Agent (A2A) Protocol](https://github.com/google/A2A).

### 8.1 Tool Attempt Structure

| Field         | Type    | Required | Description                                              |
|---------------|---------|----------|----------------------------------------------------------|
| `attempt_id`  | string  | Yes      | Unique identifier for this attempt.                      |
| `tool_id`     | string  | Yes      | Tool identifier (MUST match an MCP tool name or A2A skill ID). |
| `tool_name`   | string  | Yes      | Human-readable tool name.                                |
| `provider`    | string  | No       | Provider of the tool (e.g., `"tavily"`, `"local"`).      |
| `args`        | object  | Yes      | Arguments passed to the tool.                            |
| `result`      | any     | No       | Tool execution result (`null` if failed or pending).     |
| `error`       | object  | No       | Error details if the tool call failed.                   |
| `duration_ms` | integer | No       | Execution time in milliseconds.                          |
| `status`      | string  | Yes      | `"pending"`, `"succeeded"`, or `"failed"`.               |
| `retries_from`| string  | No       | `attempt_id` of the original attempt (for TOOL_RETRY_ALTERNATE). |
| `timestamp`   | string  | Yes      | RFC 3339 timestamp of the attempt.                       |

### 8.2 MCP Compatibility

When a tool is provided by an MCP server, the `tool_id` MUST match the MCP tool name
as returned by `tools/list`. The `args` object MUST conform to the tool's
`inputSchema`. The `result` field MUST contain the MCP `content` array from the tool
response.

### 8.3 A2A Compatibility

When a tool invocation delegates to an A2A agent, the `tool_id` SHOULD be set to the
A2A agent's `agentCard.url`. The `args` object MUST be a valid A2A `Message`. The
`result` field MUST contain the A2A response `Artifact`.

---

## 9. Replay Semantics

Agent workflows involve both deterministic operations (OJS-controlled state transitions,
tool routing) and non-deterministic operations (LLM inference). The replay model
distinguishes between these.

### 9.1 Deterministic Replay

The following steps MUST produce identical results when replayed from the same
memory DAG state:

- State machine transitions (Section 6)
- Tool routing decisions (which tool to invoke based on the LLM's request)
- Checkpoint creation and evaluation
- Merge strategy application

### 9.2 Non-Deterministic Steps

LLM inference is inherently non-deterministic. When replaying a workflow:

- Implementations MUST record the original LLM response in the memory DAG.
- During replay, implementations MUST use the recorded response rather than
  re-invoking the LLM.
- If re-inference is required (e.g., the recorded response is unavailable),
  implementations MUST annotate the replayed node with provenance metadata:

```json
{
  "type": "message",
  "payload": {
    "role": "assistant",
    "content": "Re-inferred response...",
    "_replay": {
      "original_content_id": "sha256:original...",
      "re_inferred": true,
      "model": "claude-sonnet-4",
      "reason": "original_unavailable"
    }
  }
}
```

### 9.3 Replay Guarantee Level

Implementations SHOULD document their replay guarantee level:

| Level   | Guarantee                                                        |
|---------|------------------------------------------------------------------|
| `exact` | Byte-identical replay of all recorded steps.                     |
| `semantic` | Logically equivalent replay; LLM outputs may differ in wording. |
| `best_effort` | Replay attempted but not guaranteed for provider-dependent steps. |

---

## 10. Provider Portability

A job MAY be resumed with a different model provider than the one that started it.
The `provider_envelope` field documents the compatibility context.

### 10.1 Provider Envelope Structure

```json
{
  "ext_agent_v2": {
    "provider_envelope": {
      "original_provider": "openai",
      "original_model": "gpt-4o",
      "current_provider": "anthropic",
      "current_model": "claude-sonnet-4",
      "switched_at": "2026-04-17T13:00:00Z",
      "reason": "provider_outage",
      "context_format": "chatml",
      "token_mapping": {
        "original_tokens_used": 4200,
        "estimated_equivalent_tokens": 3800
      }
    }
  }
}
```

| Field                         | Type    | Required | Description                                  |
|-------------------------------|---------|----------|----------------------------------------------|
| `original_provider`           | string  | Yes      | Provider that started the workflow.           |
| `original_model`              | string  | Yes      | Model that started the workflow.              |
| `current_provider`            | string  | Yes      | Provider currently executing.                |
| `current_model`               | string  | Yes      | Model currently executing.                   |
| `switched_at`                 | string  | Yes      | RFC 3339 timestamp of the switch.            |
| `reason`                      | string  | No       | Reason for the switch.                       |
| `context_format`              | string  | No       | Conversation format used for portability.    |
| `token_mapping`               | object  | No       | Token count mapping between providers.       |

### 10.2 Context Conversion

When switching providers, the memory DAG content MUST be converted to the target
provider's expected format. Implementations SHOULD support at least the `chatml`
format as a common interchange representation. Provider-specific features (e.g.,
system prompts, tool-use syntax) SHOULD be mapped on a best-effort basis.

Implementations MUST NOT silently drop conversation history during provider switches.
If a message cannot be represented in the target format, it MUST be preserved as a
`system` message with a `[PORTABILITY_NOTE]` prefix.

---

## 11. Backward Compatibility

### 11.1 Coexistence with ext_agent (v1)

- `ext_agent` v1 envelopes remain valid indefinitely.
- Producers MAY include both `ext_agent_*` fields and an `ext_agent_v2` object.
- When both are present, consumers MUST prefer `ext_agent_v2`.
- v1-only consumers continue to function; they see v1 fields and ignore the
  `ext_agent_v2` object per the OJS extension preservation contract.

### 11.2 Migration Path

The v1 → v2 migration is a no-op for jobs that do not use the new operations
(PAUSE_HUMAN, RESUME_HUMAN, FORK_AGENT, MERGE_AGENT, TOOL_RETRY_ALTERNATE).
Existing v1 tool results can be embedded in the v2 `tool_attempts` array without
loss of information.

---

## 12. Conformance Requirements

### 12.1 Preservation (All Backends)

All OJS-conformant backends (L0–L4) MUST preserve `ext_agent_v2` byte-for-byte
across enqueue → dequeue → result, per the existing extension preservation contract.

### 12.2 Native Support (Optional Capability)

Backends that natively implement the ext_agent_v2 operations MUST report the
`agent_v2` capability via `/v1/capabilities`. Native support requires:

- MUST implement all five operations (Section 5).
- MUST enforce state transition rules (Section 6.2).
- MUST validate checkpoint data size ≤64 KB.
- MUST support all three merge strategies.
- SHOULD support external memory DAG storage for workflows exceeding 50 nodes.

### 12.3 SDK Requirements

SDKs that support ext_agent_v2 MUST:

- Provide builder APIs for constructing `ext_agent_v2` envelopes.
- Validate `content_id` computation (Section 7.1).
- Support the human gate workflow (pause → wait → resume).
- Provide a replay API that respects the semantics in Section 9.

---

## 13. Non-Requirements

The Agent Substrate Protocol is deliberately scoped. The following are explicitly
**out of scope** for this extension:

1. **ASP is NOT a model gateway.** OJS does not proxy LLM inference calls. The
   agent worker is responsible for calling its configured provider.

2. **ASP is NOT a prompt registry.** System prompts, prompt templates, and prompt
   versioning are application concerns, not envelope concerns.

3. **ASP is NOT an evals platform.** Quality evaluation of agent outputs is outside
   the scope of this extension. The memory DAG provides the raw data that external
   eval tools can consume.

4. **ASP is NOT a model router.** While `ext_agent_v2` records provider switches
   and supports fallback, the routing decision logic is application-level. OJS
   provides the envelope; the application provides the brain.

5. **ASP is NOT an agent framework.** LangChain, CrewAI, AutoGen, and similar
   frameworks provide agent orchestration logic. ASP provides the portable
   persistence and lifecycle layer underneath any framework.

---

## 14. Security Considerations

1. **Checkpoint data sensitivity.** Checkpoint `data` fields may contain sensitive
   information (SQL queries, PII). Implementations SHOULD encrypt checkpoint data
   using the `ext_encryption` codec when the job handles sensitive data.

2. **Human gate spoofing.** The `RESUME_HUMAN` operation MUST be authenticated.
   Implementations MUST verify that the `decided_by` identity has authorization
   to approve or reject the checkpoint.

3. **Memory DAG integrity.** Content-addressed nodes provide tamper detection.
   Implementations SHOULD verify `content_id` hashes when loading DAG nodes from
   external storage.

4. **Provider credential isolation.** When switching providers via `provider_envelope`,
   implementations MUST NOT include provider credentials in the envelope. Credentials
   MUST be resolved from the worker's runtime configuration.

---

## 15. Examples

### 15.1 Full Human-in-the-Loop Workflow

```json
{
  "id": "019034ab-7c8d-7def-abcd-1234567890ab",
  "type": "ai.agent.data_cleanup",
  "queue": "agents",
  "args": ["Clean up inactive user accounts older than 2 years"],
  "ext_agent_v2": {
    "v": 2,
    "agent_id": "019034ab-0000-7def-0000-aaaaaaaaaaaa",
    "state": "paused_human",
    "memory_root": "sha256:f4a3b2c1...",
    "memory_nodes": [
      {
        "content_id": "sha256:00000001...",
        "parents": [],
        "type": "message",
        "payload": {"role": "user", "content": "Clean up inactive user accounts older than 2 years"},
        "created_at": "2026-04-17T12:00:00Z"
      },
      {
        "content_id": "sha256:00000002...",
        "parents": ["sha256:00000001..."],
        "type": "message",
        "payload": {"role": "assistant", "content": "I'll identify and remove inactive accounts. Let me first query the database."},
        "created_at": "2026-04-17T12:00:01Z"
      },
      {
        "content_id": "sha256:00000003...",
        "parents": ["sha256:00000002..."],
        "type": "tool_call",
        "payload": {"tool_id": "query_db", "args": {"sql": "SELECT COUNT(*) FROM users WHERE last_active < '2024-04-17'"}},
        "created_at": "2026-04-17T12:00:02Z"
      },
      {
        "content_id": "sha256:00000004...",
        "parents": ["sha256:00000003..."],
        "type": "tool_result",
        "payload": {"tool_id": "query_db", "result": {"count": 14200}, "duration_ms": 85},
        "created_at": "2026-04-17T12:00:02Z"
      },
      {
        "content_id": "sha256:f4a3b2c1...",
        "parents": ["sha256:00000004..."],
        "type": "checkpoint",
        "payload": {"checkpoint_id": "ckpt-001", "kind": "human_approval", "prompt": "Delete 14,200 inactive accounts?"},
        "created_at": "2026-04-17T12:00:03Z"
      }
    ],
    "checkpoints": [
      {
        "id": "ckpt-001",
        "kind": "human_approval",
        "prompt": "Delete 14,200 inactive accounts?",
        "data": {"sql": "DELETE FROM users WHERE last_active < '2024-04-17'", "row_count": 14200},
        "created_at": "2026-04-17T12:00:03Z",
        "decision": null,
        "decided_by": null,
        "memory_node": "sha256:f4a3b2c1..."
      }
    ],
    "tool_attempts": [
      {
        "attempt_id": "ta-001",
        "tool_id": "query_db",
        "tool_name": "Database Query",
        "provider": "postgres",
        "args": {"sql": "SELECT COUNT(*) FROM users WHERE last_active < '2024-04-17'"},
        "result": {"count": 14200},
        "error": null,
        "duration_ms": 85,
        "status": "succeeded",
        "timestamp": "2026-04-17T12:00:02Z"
      }
    ]
  }
}
```

### 15.2 Fork-and-Merge Workflow

```json
{
  "ext_agent_v2": {
    "v": 2,
    "agent_id": "019034ab-0000-7def-0000-parent000000",
    "state": "forked",
    "memory_root": "sha256:fork_point...",
    "checkpoints": [
      {
        "id": "ckpt-fork-001",
        "kind": "fork_point",
        "data": {
          "children": [
            {"agent_id": "019034ab-0000-7def-0000-child_a00000", "model": "gpt-4o"},
            {"agent_id": "019034ab-0000-7def-0000-child_b00000", "model": "claude-sonnet-4"}
          ]
        },
        "created_at": "2026-04-17T13:00:00Z",
        "memory_node": "sha256:fork_point..."
      }
    ]
  }
}
```

---

## 16. Versioning

### 16.1 Additive-Only Evolution

Within the v2 schema (`ext_agent_v2.v == 2`), changes MUST be additive only:

- New optional fields MAY be added.
- Existing fields MUST NOT be removed or have their type changed.
- New node types MAY be added to the memory DAG.
- New checkpoint kinds MAY be added.
- New merge strategies MAY be added.

### 16.2 Breaking Changes

Any change that would break an existing v2 consumer requires a new major version
(`ext_agent_v3`) and a new RFC. The `v` field enables consumers to detect and reject
unsupported versions.

### 16.3 Extension Registry

The following identifiers are reserved in `spec/spec/registry/extensions.json`:

- `ext_agent_v2` — this extension
- Operations: `PAUSE_HUMAN`, `RESUME_HUMAN`, `FORK_AGENT`, `MERGE_AGENT`, `TOOL_RETRY_ALTERNATE`
