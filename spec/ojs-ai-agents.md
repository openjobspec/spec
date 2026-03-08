# Open Job Spec -- AI Agent Task Orchestration Extension

| Field        | Value                                    |
|--------------|------------------------------------------|
| **Title**    | OJS AI Agent Task Orchestration Extension |
| **Version**  | 0.1.0-draft                              |
| **Date**     | 2026-02-23                               |
| **Status**   | Draft                                    |
| **Maturity** | Alpha                                    |
| **Layer**    | Extension                                |
| **Requires** | OJS Core Specification (Layer 1)         |
| **License**  | Apache 2.0                               |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Extension Fields](#2-extension-fields)
3. [Agent Task Lifecycle](#3-agent-task-lifecycle)
4. [Tool Definition Schema](#4-tool-definition-schema)
5. [Tool Result Schema](#5-tool-result-schema)
6. [Error Handling](#6-error-handling)
7. [Conformance Requirements](#7-conformance-requirements)
8. [Examples](#8-examples)
9. [Security Considerations](#9-security-considerations)
10. [Prior Art](#10-prior-art)
11. [Extension Interactions](#11-extension-interactions)

---

## 1. Introduction

This extension defines how AI agent workloads -- including LLM inference, tool-calling
chains, multi-agent delegation, and RAG (Retrieval-Augmented Generation) pipelines --
are represented and orchestrated within the OJS job envelope.

### 1.1 Rationale

AI agent tasks have fundamentally different operational characteristics from traditional
background jobs. A conventional job executes a deterministic function with bounded resource
consumption. An AI agent task, by contrast, involves non-deterministic LLM inference with
variable token consumption, dynamic tool invocation that may spawn additional work, and
delegation patterns where one agent creates child jobs for other agents. These differences
demand specialized extension fields that traditional job systems cannot express.

Without a standardized envelope for agent orchestration, every framework invents its own
representation. LangChain encodes agent state in Python objects that are not serializable
across language boundaries. CrewAI couples agent definitions to its runtime. AutoGen uses
in-memory conversation threads that cannot survive process restarts. OpenAI's Assistants
API provides a vendor-locked REST interface. None of these approaches produce a portable,
transport-neutral, vendor-neutral job envelope that an OJS-conformant backend can route,
persist, retry, and observe using existing infrastructure.

This extension provides a standardized way to express agent requirements using the
`ext_agent_*` field namespace. By encoding model selection, token budgets, tool
declarations, delegation chains, RAG configuration, and multi-agent coordination into the
OJS job envelope, implementations gain the ability to orchestrate AI agent workloads with
the same reliability guarantees (exactly-once processing, retry policies, workflow
composition) that OJS provides for conventional jobs.

### 1.2 Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD",
"SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this
document are to be interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt)
and [RFC 8174](https://www.ietf.org/rfc/rfc8174.txt).

All JSON examples in this document are normative unless explicitly marked otherwise.

All timestamps use ISO 8601 / RFC 3339 format in UTC with `Z` suffix.

All identifiers (job IDs, team IDs) SHOULD use UUIDv7 for time-sortability.

### 1.3 Terminology

| Term                    | Definition                                                                                |
|-------------------------|-------------------------------------------------------------------------------------------|
| **Agent task**          | An OJS job that invokes one or more LLM inference calls, optionally with tool use.        |
| **Token budget**        | The maximum total tokens (input + output) an agent task and its descendants may consume.  |
| **Tool**                | An external function an agent may invoke during execution (web search, database query, API call). |
| **Delegation**          | The act of an agent creating a child agent job to handle a sub-task.                      |
| **Delegation depth**    | The number of ancestor agent jobs in the current delegation chain.                        |
| **RAG pipeline**        | A retrieval-augmented generation pattern where context is fetched from external sources before LLM inference. |
| **Multi-agent system**  | A coordinated set of agent tasks that collaborate toward a shared goal.                   |
| **Consensus**           | A decision-making pattern where multiple agents must agree before a result is accepted.   |
| **Model fallback**      | The process of attempting alternative LLM models when the primary model is unavailable.   |

---

## 2. Extension Fields

All fields use the `ext_agent_` prefix per the OJS extension naming convention.
Implementations that support this extension MUST recognize all fields defined in this
section. Unrecognized `ext_agent_*` fields MUST be preserved but MAY be ignored.

**Rationale for MUST preserve**: Agent tasks may pass through middleware, proxies, or
backend implementations that do not support every field in this extension. Silently
dropping unrecognized fields would corrupt the job envelope and break downstream
consumers that depend on those fields.

### 2.1 Agent Task Metadata

| Field                       | Type     | Required | Default | Description                                                  |
|-----------------------------|----------|----------|---------|--------------------------------------------------------------|
| `ext_agent_model`           | string   | No       | —       | Preferred model identifier (e.g., `gpt-4o`, `claude-sonnet-4`) |
| `ext_agent_fallback_models` | string[] | No       | `[]`    | Ordered list of fallback models if primary is unavailable    |
| `ext_agent_provider`        | string   | No       | —       | Provider identifier (e.g., `openai`, `anthropic`, `local`)  |
| `ext_agent_temperature`     | number   | No       | —       | Sampling temperature (0.0 -- 2.0)                            |
| `ext_agent_max_tokens`      | integer  | No       | —       | Maximum tokens for a single LLM response                     |
| `ext_agent_token_budget`    | integer  | No       | —       | Total token budget for the entire agent task chain            |
| `ext_agent_tokens_used`     | integer  | No       | `0`     | Tokens consumed so far (system-managed, read-only to clients)|
| `ext_agent_model_used`      | string   | No       | —       | Actual model used after fallback (system-managed)            |

#### Field Semantics

**`ext_agent_model`** (string): The preferred LLM model identifier. This is a hint to the
implementation, not a hard constraint. If the preferred model is unavailable, the
implementation SHOULD attempt fallback models before failing.

**`ext_agent_fallback_models`** (string[]): An ordered list of alternative models.
Implementations MUST attempt models in the declared order. An empty array means no
fallback is available; if the primary model fails, the job fails.

**Rationale for MUST ordered**: Fallback order encodes the job author's preference for
cost, quality, and latency trade-offs. A random or implementation-chosen order would
violate the author's intent and produce unpredictable behavior.

**`ext_agent_temperature`** (number): Sampling temperature for the LLM call.
Implementations MUST reject values outside the range `[0.0, 2.0]` with error code
`AGENT_INVALID_PARAMETER`.

**Rationale for MUST reject**: Temperature values outside the supported range produce
undefined behavior across providers. Rejecting early prevents silent quality degradation.

**`ext_agent_token_budget`** (integer): The total token budget (input + output) for the
entire agent task, including all tool calls, delegation chains, and retries within the
agent's scope. Implementations MUST NOT allow `ext_agent_tokens_used` to exceed this
value.

**Rationale for MUST NOT exceed**: Token consumption directly maps to cost. Without a hard
budget enforcement, a misbehaving agent (e.g., one stuck in a tool-calling loop) could
consume unbounded tokens and incur unbounded cost. Server-side enforcement is the only
reliable mechanism because client-side checks can be bypassed or skipped.

**`ext_agent_tokens_used`** (integer): A system-managed counter. Clients MUST NOT set this
field at enqueue time; implementations MUST ignore any client-provided value and
initialize it to `0`.

**Rationale for MUST ignore client value**: Allowing clients to set `tokens_used` would
enable budget bypass. The counter must be authoritative and system-managed.

**`ext_agent_model_used`** (string): Set by the implementation after LLM invocation to
record which model was actually used. This field MUST be populated when model fallback
occurs.

**Rationale for MUST populate on fallback**: Without recording the actual model used,
operators cannot debug quality issues, audit cost attribution, or understand why output
characteristics changed between runs.

### 2.2 Tool Calling

| Field                       | Type     | Required | Default  | Description                                            |
|-----------------------------|----------|----------|----------|--------------------------------------------------------|
| `ext_agent_tools`           | object[] | No       | `[]`     | Available tools for this agent task (see Section 4)    |
| `ext_agent_tool_choice`     | string   | No       | `"auto"` | Tool selection mode: `auto`, `required`, `none`        |
| `ext_agent_tool_results`    | object[] | No       | `[]`     | Results from tool invocations (system-managed, see Section 5) |
| `ext_agent_tool_timeout_ms` | integer  | No       | `30000`  | Timeout in milliseconds for individual tool executions |

#### Field Semantics

**`ext_agent_tools`** (object[]): Each element MUST conform to the Tool Definition Schema
(Section 4). Implementations MUST validate tool definitions at enqueue time and reject
jobs with malformed tool schemas.

**Rationale for MUST validate at enqueue**: Deferring validation to execution time wastes
queue capacity and worker cycles on jobs that will inevitably fail. Early rejection
provides immediate feedback to the client.

**`ext_agent_tool_choice`** (string): Controls whether the agent is allowed, required, or
forbidden from using tools.

| Value        | Behavior                                                                |
|--------------|-------------------------------------------------------------------------|
| `"auto"`     | The agent MAY use tools at its discretion.                              |
| `"required"` | The agent MUST invoke at least one tool before producing a final output. |
| `"none"`     | The agent MUST NOT invoke any tools; tool definitions are informational only. |

**`ext_agent_tool_timeout_ms`** (integer): The maximum time allowed for a single tool
execution. This timeout is independent of the overall job timeout. Implementations
SHOULD enforce this timeout per tool invocation.

**Rationale for independent timeout**: Tool executions (e.g., web searches, database
queries) have different latency profiles than LLM inference. A 120-second job timeout
should not be consumed by a single slow tool call. Independent tool timeouts enable
finer-grained resource control.

### 2.3 Agent Delegation

| Field                            | Type     | Required | Default | Description                                          |
|----------------------------------|----------|----------|---------|------------------------------------------------------|
| `ext_agent_parent_id`            | string   | No       | —       | Job ID of the parent agent that delegated this task  |
| `ext_agent_delegation_depth`     | integer  | No       | `0`     | Current depth in the delegation chain                |
| `ext_agent_max_delegation_depth` | integer  | No       | `10`    | Maximum allowed delegation depth                     |

#### Field Semantics

**`ext_agent_parent_id`** (string): When present, identifies the parent agent job that
created this task via delegation. Implementations MUST validate that the referenced
parent job exists and is in the `active` state.

**Rationale for MUST validate parent**: Orphaned delegation chains (where the parent has
already completed or been cancelled) create resource leaks and produce results that no
consumer will collect.

**`ext_agent_delegation_depth`** (integer): The current depth of this job in the
delegation chain. A root agent task has depth `0`. When an agent delegates to a child,
the child's depth MUST be set to `parent_depth + 1`.

**Rationale for MUST increment**: Incorrect depth tracking defeats the purpose of depth
limits. The implementation -- not the client -- must compute and set this value to prevent
bypass.

**`ext_agent_max_delegation_depth`** (integer): The maximum allowed depth. Implementations
MUST reject agent tasks where `ext_agent_delegation_depth` is greater than or equal to
`ext_agent_max_delegation_depth` with error code `AGENT_MAX_DELEGATION_DEPTH`.

**Rationale for MUST reject**: Without a hard depth limit, a poorly written agent could
create infinite delegation chains, exhausting queue capacity and potentially causing
cascading failures across the system.

### 2.4 Structured Output

| Field                         | Type   | Required | Default  | Description                                          |
|-------------------------------|--------|----------|----------|------------------------------------------------------|
| `ext_agent_output_schema`     | object | No       | —        | JSON Schema (draft 2020-12) for the expected output  |
| `ext_agent_output_format`     | string | No       | `"text"` | Output format: `json`, `text`, `markdown`            |

#### Field Semantics

**`ext_agent_output_schema`** (object): A JSON Schema document that the agent's final
output MUST conform to. When present, implementations SHOULD validate the output against
this schema before transitioning the job to `completed`.

**Rationale for SHOULD (not MUST)**: Output schema validation is valuable but adds latency.
Some implementations may choose to defer validation to the consumer for performance
reasons. However, implementations that do validate MUST reject non-conforming output with
error code `AGENT_OUTPUT_SCHEMA_VIOLATION`.

**`ext_agent_output_format`** (string): Declares the expected output format. When set to
`"json"`, the agent's output MUST be valid JSON. When set to `"text"` or `"markdown"`,
the output is treated as an opaque string.

### 2.5 RAG Pipeline Configuration

| Field                            | Type     | Required | Default        | Description                                                |
|----------------------------------|----------|----------|----------------|------------------------------------------------------------|
| `ext_agent_context_sources`      | object[] | No       | `[]`           | Context retrieval source configurations                    |
| `ext_agent_context_window`       | integer  | No       | —              | Maximum context tokens to include in the LLM prompt        |
| `ext_agent_retrieval_strategy`   | string   | No       | `"similarity"` | Retrieval strategy: `similarity`, `mmr`, `hybrid`          |

#### Field Semantics

**`ext_agent_context_sources`** (object[]): Each element describes a retrieval source.
The following source types are defined:

| Source Type      | Description                                                      |
|------------------|------------------------------------------------------------------|
| `"vector_db"`    | A vector database (e.g., Pinecone, Weaviate, pgvector).         |
| `"document_store"` | A document store (e.g., Elasticsearch, MongoDB Atlas Search). |
| `"api"`          | An external API that returns context documents.                  |

Each source object MUST include:

| Field        | Type   | Required | Description                                  |
|--------------|--------|----------|----------------------------------------------|
| `type`       | string | Yes      | Source type (one of the above).              |
| `name`       | string | Yes      | Human-readable name for the source.          |
| `endpoint`   | string | Yes      | Connection endpoint (URL, connection string). |
| `collection` | string | No       | Collection or index name within the source.  |
| `top_k`      | integer| No       | Maximum number of documents to retrieve.     |

**Rationale for MUST include type/name/endpoint**: These three fields are the minimum
information needed to connect to a retrieval source. Without them, the implementation
cannot execute the retrieval step of a RAG pipeline.

**`ext_agent_context_window`** (integer): The maximum number of context tokens to include
in the LLM prompt. This value MUST be less than or equal to `ext_agent_max_tokens` when
both are specified. Implementations MUST truncate retrieved context to fit within this
window.

**Rationale for MUST truncate**: LLM APIs have hard context length limits. Exceeding them
produces API errors that waste tokens already consumed during retrieval.

**`ext_agent_retrieval_strategy`** (string): The strategy for selecting context documents.

| Strategy       | Description                                                         |
|----------------|---------------------------------------------------------------------|
| `"similarity"` | Pure cosine/dot-product similarity ranking.                         |
| `"mmr"`        | Maximal Marginal Relevance -- balances relevance with diversity.    |
| `"hybrid"`     | Combination of keyword (BM25) and semantic similarity.              |

### 2.6 Multi-Agent Coordination

| Field                           | Type    | Required | Default | Description                                             |
|---------------------------------|---------|----------|---------|---------------------------------------------------------|
| `ext_agent_role`                | string  | No       | —       | Agent's role in a multi-agent system                    |
| `ext_agent_team_id`             | string  | No       | —       | Team identifier for coordinated agents                  |
| `ext_agent_consensus_required`  | boolean | No       | `false` | Whether results need consensus from multiple agents     |
| `ext_agent_voting_threshold`    | number  | No       | `0.5`   | Minimum agreement ratio for consensus (0.0 -- 1.0)     |

#### Field Semantics

**`ext_agent_role`** (string): A human-readable role descriptor (e.g., `"researcher"`,
`"critic"`, `"summarizer"`, `"code_reviewer"`). This field is informational and is used
for routing, logging, and display. Implementations MUST preserve this field but MAY
ignore it for execution purposes.

**`ext_agent_team_id`** (string): Groups related agent tasks into a logical team.
Implementations MAY use this field to co-schedule team members, share context between
them, or apply team-level resource limits.

**`ext_agent_consensus_required`** (boolean): When `true`, the team's result is not final
until a sufficient number of agents agree. Implementations that support consensus MUST
NOT mark the team's work as complete until the voting threshold is met or all agents have
reported results.

**Rationale for MUST NOT mark complete prematurely**: Consensus is a correctness
requirement, not an optimization hint. Marking a result as complete before consensus is
reached defeats the purpose of multi-agent verification and could propagate incorrect
results to downstream consumers.

**`ext_agent_voting_threshold`** (number): The minimum ratio of agreeing agents required
for consensus. A value of `0.5` means a simple majority. A value of `1.0` means
unanimous agreement. Implementations MUST reject values outside the range `(0.0, 1.0]`
with error code `AGENT_INVALID_PARAMETER`.

**Rationale for MUST reject out-of-range**: A threshold of `0.0` would mean no agreement
is needed, making consensus meaningless. A threshold above `1.0` is mathematically
impossible to satisfy.

---

## 3. Agent Task Lifecycle

Agent tasks follow the standard OJS 8-state lifecycle (`scheduled → available → pending →
active → completed | retryable | cancelled | discarded`) with additional semantics defined
by this extension. This section specifies how agent-specific behavior maps onto each
lifecycle transition.

### 3.1 Token Budget Enforcement

Implementations MUST check the token budget before each LLM API call. If
`ext_agent_tokens_used` plus the estimated tokens for the pending call would exceed
`ext_agent_token_budget`, the implementation MUST NOT make the LLM call and MUST
transition the job to `retryable` with error code `AGENT_TOKEN_BUDGET_EXCEEDED`.

**Rationale for MUST check before each call**: Checking only after a call completes allows
a single expensive call to exceed the budget by an unbounded amount. Pre-call checking
ensures that the budget is never exceeded by more than the estimation error of a single call.

Implementations MUST decrement the token budget atomically. In concurrent environments
(e.g., parallel tool executions within a single agent task), the decrement operation MUST
be serialized or use atomic compare-and-swap to prevent race conditions that could allow
budget overruns.

**Rationale for MUST atomic decrement**: Without atomicity, two concurrent tool calls
could each read the same remaining budget, both proceed, and together exceed the limit.
This is the classic check-then-act race condition.

After each LLM call completes, the implementation MUST update `ext_agent_tokens_used` with
the actual token count reported by the LLM provider.

Agent results SHOULD include token usage metadata in the job result envelope. This metadata
SHOULD contain at minimum:

| Field               | Type    | Description                                    |
|---------------------|---------|------------------------------------------------|
| `prompt_tokens`     | integer | Total input tokens consumed across all calls.  |
| `completion_tokens` | integer | Total output tokens consumed across all calls. |
| `total_tokens`      | integer | Sum of prompt and completion tokens.           |
| `llm_calls`         | integer | Number of LLM API calls made.                  |

### 3.2 Model Fallback

If the primary model specified in `ext_agent_model` is unavailable (HTTP 429, 503, or
connection error), implementations MUST attempt models from `ext_agent_fallback_models`
in the declared order before failing the job.

**Rationale for MUST attempt in order**: The fallback list encodes a deliberate priority
order reflecting cost, quality, and latency trade-offs chosen by the job author. Skipping
models or reordering them would violate the author's intent.

When a fallback model is used, the implementation MUST record the model identifier in
`ext_agent_model_used`. This applies even when the primary model succeeds -- in that case,
`ext_agent_model_used` MUST be set to the primary model identifier.

Model fallback is an internal mechanism of the agent execution. Model fallback attempts
MUST NOT count as job-level retries as defined by the OJS Retry Policy Specification. A
single job execution may attempt multiple models before succeeding or failing; this entire
sequence constitutes one job attempt.

**Rationale for MUST NOT count as job retry**: Model fallback addresses transient provider
unavailability, not handler errors. Conflating the two would prematurely exhaust the job's
retry budget and prevent retries of genuine handler failures.

### 3.3 Delegation Depth

Before creating a child agent job via delegation, the implementation MUST validate that the
current `ext_agent_delegation_depth` is strictly less than `ext_agent_max_delegation_depth`.
If the depth limit would be exceeded, the implementation MUST fail the delegation with error
code `AGENT_MAX_DELEGATION_DEPTH` and MUST NOT create the child job.

**Rationale for MUST validate before creation**: Creating the child job and then failing it
wastes queue capacity, generates spurious lifecycle events, and complicates cleanup.

When an agent delegates to a child, the child job MUST inherit the following fields from the
parent unless explicitly overridden:

- `ext_agent_token_budget` — remaining budget (parent budget minus parent tokens used)
- `ext_agent_max_delegation_depth` — same limit as parent
- `ext_agent_delegation_depth` — parent depth + 1
- `ext_agent_parent_id` — parent job ID

### 3.4 Tool Execution

When an agent invokes a tool, the implementation MUST validate that the tool name matches
an entry in `ext_agent_tools`. If the tool is not declared, the implementation MUST reject
the invocation with error code `AGENT_TOOL_NOT_FOUND`.

**Rationale for MUST validate against declared list**: Allowing undeclared tool invocations
opens a vector for prompt injection attacks where a malicious prompt tricks the agent into
calling arbitrary functions. The declared tool list serves as an allowlist.

Tool execution SHOULD have an independent timeout controlled by `ext_agent_tool_timeout_ms`.
This timeout SHOULD be enforced separately from the overall job timeout.

Tool results MUST be recorded in `ext_agent_tool_results` using the schema defined in
Section 5. Implementations MUST append results in invocation order.

**Rationale for MUST record results**: Tool result history is essential for debugging agent
behavior, auditing tool usage, and enabling retry logic that can skip previously successful
tool calls.

### 3.5 Multi-Agent Coordination

Multi-agent coordination MAY be implemented using the fields defined in Section 2.6.
Implementations that support multi-agent coordination MUST implement the following behavior:

1. All agents in a team (identified by `ext_agent_team_id`) MUST be tracked as a group.
2. When `ext_agent_consensus_required` is `true`, the team's result MUST NOT be finalized
   until the agreement ratio meets or exceeds `ext_agent_voting_threshold`.
3. If all agents in the team have completed and consensus has not been reached, the
   implementation MUST report error code `AGENT_CONSENSUS_FAILED`.

---

## 4. Tool Definition Schema

Each tool definition MUST be a JSON object conforming to the following schema. This schema
is intentionally compatible with the OpenAI function calling format to enable zero-cost
adoption for implementations already supporting that format.

```json
{
  "name": "web_search",
  "description": "Search the web for information",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Search query"
      }
    },
    "required": ["query"]
  }
}
```

| Field         | Type   | Required | Description                                            |
|---------------|--------|----------|--------------------------------------------------------|
| `name`        | string | Yes      | Unique tool name within the agent task's tool list.    |
| `description` | string | Yes      | Human-readable description of the tool's purpose.      |
| `parameters`  | object | Yes      | JSON Schema (draft 2020-12) defining the tool's input. |

Implementations MUST reject tool definitions where `name` is not unique within the
`ext_agent_tools` array.

**Rationale for MUST unique names**: Tool invocations reference tools by name. Duplicate
names create ambiguity about which tool to execute.

Tool names MUST match the pattern `^[a-z][a-z0-9_]{0,63}$` (lowercase letter, followed
by up to 63 lowercase letters, digits, or underscores).

**Rationale for MUST match pattern**: Consistent naming enables reliable matching, logging,
and allowlist management. The pattern is deliberately restrictive to prevent encoding
attacks or confusion with other identifiers.

---

## 5. Tool Result Schema

Each tool result MUST be a JSON object conforming to the following schema:

```json
{
  "tool_call_id": "call_019539a4-b6c7-7000-8000-abcdef123456",
  "name": "web_search",
  "result": {
    "snippets": [
      "Quantum computing breakthrough: new error correction method..."
    ]
  },
  "tokens_used": 150,
  "latency_ms": 1200,
  "error": null
}
```

| Field          | Type            | Required | Description                                            |
|----------------|-----------------|----------|--------------------------------------------------------|
| `tool_call_id` | string          | Yes      | Unique identifier for this tool invocation.            |
| `name`         | string          | Yes      | Tool name (MUST match an entry in `ext_agent_tools`).  |
| `result`       | object \| null  | Yes      | Tool output. `null` when `error` is non-null.          |
| `tokens_used`  | integer         | No       | Tokens consumed by this tool call (if applicable).     |
| `latency_ms`   | integer         | No       | Wall-clock time for the tool execution in milliseconds.|
| `error`        | object \| null  | Yes      | Error details. `null` on success.                      |

When a tool invocation fails, the `error` field MUST contain:

| Field     | Type   | Required | Description                             |
|-----------|--------|----------|-----------------------------------------|
| `code`    | string | Yes      | Error code (e.g., `AGENT_TOOL_EXECUTION_FAILED`). |
| `message` | string | Yes      | Human-readable error description.       |

Implementations MUST record both successful and failed tool results in
`ext_agent_tool_results`.

**Rationale for MUST record failures**: Failed tool calls consume tokens and time. Omitting
them from the results would make token accounting inaccurate and prevent replay-based
debugging.

---

## 6. Error Handling

This section defines error codes specific to the AI Agent extension. These error codes
are used in the job's error field when the job transitions to `retryable` or `discarded`.

Implementations MUST use the error codes defined in this section for the corresponding
failure conditions. Implementations MUST NOT invent alternative codes for conditions
covered by this section.

**Rationale for MUST use defined codes**: Consistent error codes enable cross-implementation
monitoring, alerting, and retry logic. If each implementation invents its own codes,
consumers cannot write portable error handling.

### 6.1 Error Code Table

| Code                              | HTTP Status | Retryable | Description                                                  |
|-----------------------------------|-------------|-----------|--------------------------------------------------------------|
| `AGENT_TOKEN_BUDGET_EXCEEDED`     | 429         | No        | Token budget depleted before the agent task completed.       |
| `AGENT_MAX_DELEGATION_DEPTH`      | 400         | No        | Delegation chain exceeded the maximum allowed depth.         |
| `AGENT_MODEL_UNAVAILABLE`         | 503         | Yes       | All models (primary + fallbacks) are unavailable.            |
| `AGENT_TOOL_NOT_FOUND`            | 400         | No        | Agent invoked a tool not in the declared tool list.          |
| `AGENT_TOOL_EXECUTION_FAILED`     | 502         | Yes       | A tool invocation raised an error during execution.          |
| `AGENT_OUTPUT_SCHEMA_VIOLATION`   | 422         | Yes       | Agent output does not conform to the declared output schema. |
| `AGENT_CONTEXT_RETRIEVAL_FAILED`  | 502         | Yes       | A RAG context source was unavailable or returned an error.   |
| `AGENT_CONSENSUS_FAILED`          | 409         | No        | Multi-agent voting did not reach the required threshold.     |
| `AGENT_INVALID_PARAMETER`         | 400         | No        | An extension field value is outside its valid range.         |
| `AGENT_TOOL_TIMEOUT`              | 504         | Yes       | A tool invocation exceeded `ext_agent_tool_timeout_ms`.      |

### 6.2 Error Response Format

When an agent task fails, the error MUST be reported using the standard OJS error envelope
with the addition of agent-specific metadata:

```json
{
  "code": "AGENT_TOKEN_BUDGET_EXCEEDED",
  "message": "Token budget of 50000 exhausted after 49823 tokens with task incomplete",
  "details": {
    "ext_agent_tokens_used": 49823,
    "ext_agent_token_budget": 50000,
    "ext_agent_model_used": "gpt-4o",
    "ext_agent_llm_calls": 7,
    "ext_agent_tool_calls": 3
  }
}
```

The `details` field SHOULD include relevant extension fields that help diagnose the failure.
Implementations SHOULD include at minimum the fields that are directly related to the error
condition.

### 6.3 Retryable vs. Non-Retryable Errors

Errors marked as retryable in Section 6.1 indicate transient conditions that MAY resolve
on a subsequent attempt. Non-retryable errors indicate permanent conditions that will not
change without human intervention (e.g., correcting the tool list or increasing the budget).

When a retryable agent error occurs, the standard OJS retry policy applies. The
implementation SHOULD transition the job to `retryable` and allow the retry policy to
determine the next action.

When a non-retryable agent error occurs, the implementation MUST transition the job to
`discarded` (or `dead_letter` if configured by the retry policy's `on_exhaustion` field).
The implementation MUST NOT retry the job regardless of remaining attempts.

**Rationale for MUST NOT retry non-retryable**: Retrying a job that exceeded its token
budget without increasing the budget will produce the same failure. Retrying a job that
hit the delegation depth limit will hit it again immediately. These retries waste resources
and delay the visibility of the real problem.

---

## 7. Conformance Requirements

This section defines the conformance levels for implementations of the AI Agent Task
Orchestration Extension.

### 7.1 Conformance Levels

An implementation MAY claim conformance to this extension at one of three levels:

| Level    | Description                                                        |
|----------|--------------------------------------------------------------------|
| **Base** | Core agent task fields, token budget enforcement, delegation limits.|
| **Standard** | Base + model fallback, output schema validation, tool validation. |
| **Full** | Standard + RAG pipeline, multi-agent coordination, consensus.     |

### 7.2 Base Conformance (MUST)

An implementation claiming Base conformance MUST support the following:

1. **Token budget enforcement**: The implementation MUST enforce `ext_agent_token_budget`
   as described in Section 3.1. Token budget MUST be checked before each LLM call and
   decremented atomically after each call.

2. **Delegation depth limits**: The implementation MUST enforce
   `ext_agent_max_delegation_depth` as described in Section 3.3. The implementation MUST
   reject delegation attempts that would exceed the limit.

3. **Field preservation**: The implementation MUST preserve all `ext_agent_*` fields on the
   job envelope, even those it does not actively process.

4. **Error codes**: The implementation MUST use the error codes `AGENT_TOKEN_BUDGET_EXCEEDED`,
   `AGENT_MAX_DELEGATION_DEPTH`, and `AGENT_INVALID_PARAMETER` as defined in Section 6.

5. **System-managed fields**: The implementation MUST manage `ext_agent_tokens_used` and
   `ext_agent_delegation_depth` as system-managed fields. Client-provided values for these
   fields MUST be ignored on enqueue.

### 7.3 Standard Conformance (SHOULD)

An implementation claiming Standard conformance SHOULD support the following in addition
to all Base requirements:

1. **Model fallback**: The implementation SHOULD attempt `ext_agent_fallback_models` in
   order when the primary model is unavailable, as described in Section 3.2.

2. **Output schema validation**: The implementation SHOULD validate agent output against
   `ext_agent_output_schema` before completing the job.

3. **Tool validation**: The implementation SHOULD validate tool invocations against the
   declared `ext_agent_tools` list. Tool definitions SHOULD be validated at enqueue time.

4. **Tool result recording**: The implementation SHOULD record tool results in
   `ext_agent_tool_results` as described in Section 5.

5. **Token usage metadata**: The implementation SHOULD include token usage metadata in the
   job result envelope.

### 7.4 Full Conformance (MAY)

An implementation claiming Full conformance MAY support the following in addition to all
Standard requirements:

1. **RAG pipeline**: The implementation MAY support `ext_agent_context_sources`,
   `ext_agent_context_window`, and `ext_agent_retrieval_strategy` as described in
   Section 2.5.

2. **Multi-agent coordination**: The implementation MAY support `ext_agent_role`,
   `ext_agent_team_id`, `ext_agent_consensus_required`, and `ext_agent_voting_threshold`
   as described in Section 2.6.

3. **Consensus voting**: The implementation MAY implement consensus voting with configurable
   thresholds as described in Section 3.5.

### 7.5 Conformance Test Matrix

| Requirement                    | Base | Standard | Full |
|--------------------------------|------|----------|------|
| Token budget enforcement       | MUST | MUST     | MUST |
| Delegation depth limits        | MUST | MUST     | MUST |
| Field preservation             | MUST | MUST     | MUST |
| Error codes (base set)         | MUST | MUST     | MUST |
| System-managed fields          | MUST | MUST     | MUST |
| Model fallback                 | —    | SHOULD   | MUST |
| Output schema validation       | —    | SHOULD   | MUST |
| Tool invocation validation     | —    | SHOULD   | MUST |
| Tool result recording          | —    | SHOULD   | MUST |
| Token usage metadata           | —    | SHOULD   | MUST |
| RAG pipeline support           | —    | —        | MAY  |
| Multi-agent coordination       | —    | —        | MAY  |
| Consensus voting               | —    | —        | MAY  |

---

## 8. Examples

All examples in this section are normative. Job IDs use UUIDv7 format. Timestamps use
RFC 3339 format in UTC.

### 8.1 Simple LLM Completion Job

A minimal agent task that performs a single LLM inference call with no tools.

```json
{
  "id": "019539a4-b6c7-7000-8000-000000000001",
  "type": "agent.summarize",
  "args": ["Summarize recent developments in quantum computing"],
  "created_at": "2026-02-23T10:00:00Z",
  "options": {
    "queue": "ai-agents",
    "timeout_ms": 60000
  },
  "ext_agent_model": "gpt-4o",
  "ext_agent_fallback_models": ["claude-sonnet-4", "gpt-4o-mini"],
  "ext_agent_provider": "openai",
  "ext_agent_temperature": 0.7,
  "ext_agent_max_tokens": 4096,
  "ext_agent_token_budget": 8000,
  "ext_agent_output_format": "markdown"
}
```

### 8.2 Tool-Calling Agent with Delegation

An agent that uses tools and delegates a sub-task to a child agent.

```json
{
  "id": "019539a4-b6c7-7000-8000-000000000010",
  "type": "agent.research",
  "args": ["Research and compile a report on climate policy changes in 2026"],
  "created_at": "2026-02-23T10:05:00Z",
  "options": {
    "queue": "ai-agents",
    "timeout_ms": 300000
  },
  "ext_agent_model": "gpt-4o",
  "ext_agent_fallback_models": ["claude-sonnet-4"],
  "ext_agent_provider": "openai",
  "ext_agent_temperature": 0.3,
  "ext_agent_max_tokens": 8192,
  "ext_agent_token_budget": 100000,
  "ext_agent_delegation_depth": 0,
  "ext_agent_max_delegation_depth": 3,
  "ext_agent_tools": [
    {
      "name": "web_search",
      "description": "Search the web for current information",
      "parameters": {
        "type": "object",
        "properties": {
          "query": { "type": "string", "description": "Search query" }
        },
        "required": ["query"]
      }
    },
    {
      "name": "delegate_analysis",
      "description": "Delegate detailed analysis of a topic to a specialist agent",
      "parameters": {
        "type": "object",
        "properties": {
          "topic": { "type": "string", "description": "Topic to analyze" },
          "depth": { "type": "string", "enum": ["shallow", "deep"], "description": "Analysis depth" }
        },
        "required": ["topic"]
      }
    }
  ],
  "ext_agent_tool_choice": "auto",
  "ext_agent_output_schema": {
    "type": "object",
    "properties": {
      "title": { "type": "string" },
      "sections": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "heading": { "type": "string" },
            "content": { "type": "string" },
            "sources": { "type": "array", "items": { "type": "string" } }
          },
          "required": ["heading", "content"]
        }
      }
    },
    "required": ["title", "sections"]
  },
  "ext_agent_output_format": "json"
}
```

The delegated child job would be enqueued as:

```json
{
  "id": "019539a4-b6c7-7000-8000-000000000011",
  "type": "agent.analyze",
  "args": ["Analyze the Paris Agreement amendments proposed in 2026"],
  "created_at": "2026-02-23T10:05:30Z",
  "options": {
    "queue": "ai-agents",
    "timeout_ms": 120000
  },
  "ext_agent_model": "gpt-4o",
  "ext_agent_provider": "openai",
  "ext_agent_temperature": 0.2,
  "ext_agent_max_tokens": 4096,
  "ext_agent_token_budget": 30000,
  "ext_agent_parent_id": "019539a4-b6c7-7000-8000-000000000010",
  "ext_agent_delegation_depth": 1,
  "ext_agent_max_delegation_depth": 3
}
```

### 8.3 RAG Pipeline Job

An agent task that retrieves context from external sources before LLM inference.

```json
{
  "id": "019539a4-b6c7-7000-8000-000000000020",
  "type": "agent.qa",
  "args": ["What is our company's policy on remote work for contractors?"],
  "created_at": "2026-02-23T10:10:00Z",
  "options": {
    "queue": "ai-agents-rag",
    "timeout_ms": 60000
  },
  "ext_agent_model": "gpt-4o",
  "ext_agent_provider": "openai",
  "ext_agent_temperature": 0.1,
  "ext_agent_max_tokens": 2048,
  "ext_agent_token_budget": 15000,
  "ext_agent_context_sources": [
    {
      "type": "vector_db",
      "name": "company-policies",
      "endpoint": "https://pinecone.example.com",
      "collection": "hr-policies-2026",
      "top_k": 5
    },
    {
      "type": "document_store",
      "name": "employee-handbook",
      "endpoint": "https://elastic.internal:9200",
      "collection": "handbook-v3"
    }
  ],
  "ext_agent_context_window": 4000,
  "ext_agent_retrieval_strategy": "hybrid",
  "ext_agent_output_schema": {
    "type": "object",
    "properties": {
      "answer": { "type": "string" },
      "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
      "source_documents": {
        "type": "array",
        "items": { "type": "string" }
      }
    },
    "required": ["answer", "confidence"]
  },
  "ext_agent_output_format": "json"
}
```

### 8.4 Multi-Agent Coordination

A team of agents collaborating on a code review task with consensus voting.

```json
{
  "id": "019539a4-b6c7-7000-8000-000000000030",
  "type": "agent.code_review",
  "args": ["Review PR #142: Add rate limiting to /api/v2/jobs endpoint"],
  "created_at": "2026-02-23T10:15:00Z",
  "options": {
    "queue": "ai-agents-review",
    "timeout_ms": 180000
  },
  "ext_agent_model": "claude-sonnet-4",
  "ext_agent_provider": "anthropic",
  "ext_agent_temperature": 0.2,
  "ext_agent_max_tokens": 4096,
  "ext_agent_token_budget": 25000,
  "ext_agent_role": "security_reviewer",
  "ext_agent_team_id": "019539a4-b6c7-7000-8000-team00000001",
  "ext_agent_consensus_required": true,
  "ext_agent_voting_threshold": 0.67,
  "ext_agent_output_schema": {
    "type": "object",
    "properties": {
      "verdict": { "type": "string", "enum": ["approve", "request_changes", "comment"] },
      "findings": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "severity": { "type": "string", "enum": ["critical", "warning", "info"] },
            "file": { "type": "string" },
            "line": { "type": "integer" },
            "message": { "type": "string" }
          },
          "required": ["severity", "message"]
        }
      }
    },
    "required": ["verdict", "findings"]
  },
  "ext_agent_output_format": "json"
}
```

Other agents in the same team would share `ext_agent_team_id` but have different roles
(e.g., `"performance_reviewer"`, `"style_reviewer"`).

### 8.5 Error Case: Token Budget Exceeded (Negative Example)

*This example is informative, not normative.*

An agent task that exhausts its token budget before completing. The job transitions to
`discarded` with the following error:

```json
{
  "id": "019539a4-b6c7-7000-8000-000000000040",
  "type": "agent.research",
  "state": "discarded",
  "args": ["Write a comprehensive history of artificial intelligence"],
  "created_at": "2026-02-23T11:00:00Z",
  "completed_at": "2026-02-23T11:02:15Z",
  "options": {
    "queue": "ai-agents",
    "timeout_ms": 300000
  },
  "ext_agent_model": "gpt-4o",
  "ext_agent_token_budget": 5000,
  "ext_agent_tokens_used": 4892,
  "ext_agent_model_used": "gpt-4o",
  "error": {
    "code": "AGENT_TOKEN_BUDGET_EXCEEDED",
    "message": "Token budget of 5000 exhausted after 4892 tokens; estimated next call requires 1500 tokens",
    "details": {
      "ext_agent_tokens_used": 4892,
      "ext_agent_token_budget": 5000,
      "ext_agent_model_used": "gpt-4o",
      "ext_agent_llm_calls": 3,
      "ext_agent_tool_calls": 2
    }
  }
}
```

**Analysis**: The budget of 5000 tokens was insufficient for a comprehensive history task.
The implementation correctly refused the fourth LLM call because the estimated token
requirement (1500) plus tokens already used (4892) would exceed the budget (5000). The
error is non-retryable because retrying with the same budget will produce the same failure.
The correct remediation is to re-enqueue with a larger `ext_agent_token_budget`.

### 8.6 Error Case: Max Delegation Depth (Negative Example)

*This example is informative, not normative.*

An agent attempts to delegate at the maximum depth and is rejected:

```json
{
  "id": "019539a4-b6c7-7000-8000-000000000050",
  "type": "agent.delegate_subtask",
  "state": "discarded",
  "args": ["Verify the sources cited in the analysis"],
  "created_at": "2026-02-23T11:05:00Z",
  "completed_at": "2026-02-23T11:05:00Z",
  "options": {
    "queue": "ai-agents",
    "timeout_ms": 60000
  },
  "ext_agent_model": "gpt-4o-mini",
  "ext_agent_token_budget": 10000,
  "ext_agent_parent_id": "019539a4-b6c7-7000-8000-000000000049",
  "ext_agent_delegation_depth": 5,
  "ext_agent_max_delegation_depth": 5,
  "error": {
    "code": "AGENT_MAX_DELEGATION_DEPTH",
    "message": "Delegation depth 5 equals max delegation depth 5; cannot create child agent",
    "details": {
      "ext_agent_delegation_depth": 5,
      "ext_agent_max_delegation_depth": 5,
      "ext_agent_parent_id": "019539a4-b6c7-7000-8000-000000000049"
    }
  }
}
```

**Analysis**: The agent at depth 5 attempted to delegate, which would create a child at
depth 6. Since `ext_agent_max_delegation_depth` is 5, the implementation correctly
rejected the delegation. This error is non-retryable. The correct remediation is either
to increase `ext_agent_max_delegation_depth` or to restructure the agent workflow to
require fewer delegation levels.

---

## 9. Security Considerations

AI agent tasks introduce security risks that do not exist in traditional background jobs.
This section defines security requirements and recommendations.

### 9.1 Prompt Injection Prevention

Implementations MUST sanitize tool results before feeding them back into the LLM context.
Tool results may contain adversarial content designed to manipulate the agent's behavior
(indirect prompt injection).

**Rationale for MUST sanitize**: A tool result from a web search or database query may
contain text crafted by an attacker to override the agent's instructions. Without
sanitization, the agent may ignore its original task, exfiltrate data, or produce harmful
output. Sanitization SHOULD include at minimum:

- Stripping or escaping control characters and known prompt injection patterns.
- Clearly delimiting tool results from system/user prompts using structured message
  formatting (e.g., separate `tool` role messages rather than string concatenation).
- Truncating tool results that exceed `ext_agent_context_window` to prevent context
  overflow attacks.

### 9.2 API Key Isolation

Each agent task SHOULD use scoped API keys with the minimum permissions required for the
task. Implementations SHOULD NOT share a single global API key across all agent tasks.

**Rationale**: A compromised agent task (e.g., through prompt injection) with a global
API key could access resources beyond its scope. Scoped keys limit the blast radius.

Implementations MUST NOT include API keys in the job envelope. API keys MUST be resolved
at execution time from a secure credential store.

**Rationale for MUST NOT include in envelope**: Job envelopes are stored in queues,
logged, and may be inspected by monitoring tools. Including API keys in the envelope
would expose credentials to any system with queue read access.

### 9.3 Cost Controls

Token budgets (Section 2.1) serve as the primary cost control mechanism. Implementations
MUST enforce token budgets server-side.

**Rationale for MUST enforce server-side**: Client-side budget enforcement can be bypassed
by a misbehaving client or ignored by a direct API caller. Server-side enforcement is the
only reliable mechanism.

Implementations SHOULD provide configurable per-queue and per-team budget limits in
addition to per-job limits. This enables operators to set organization-level cost ceilings
that individual jobs cannot exceed.

### 9.4 Data Exfiltration Prevention

Tools declared in `ext_agent_tools` MUST NOT be permitted to access data outside the
scope declared by the job's context. Implementations SHOULD enforce network-level
isolation for tool executions (e.g., restricting outbound connections to declared
endpoints).

**Rationale for MUST NOT access out-of-scope data**: An agent with unrestricted tool
access could be tricked (via prompt injection) into reading sensitive data from internal
systems and encoding it in its output. Tool access control is a defense-in-depth measure
complementing prompt injection prevention.

### 9.5 Audit Logging

All tool invocations SHOULD be logged with sufficient detail for post-incident analysis.
The log SHOULD include at minimum:

| Field            | Description                                        |
|------------------|----------------------------------------------------|
| `job_id`         | The agent task's job ID.                           |
| `tool_name`      | The name of the tool invoked.                      |
| `tool_call_id`   | The unique tool call identifier.                   |
| `timestamp`      | RFC 3339 timestamp of the invocation.              |
| `latency_ms`     | Execution time of the tool call.                   |
| `tokens_used`    | Tokens consumed by the tool call (if applicable).  |
| `success`        | Boolean indicating success or failure.             |
| `error_code`     | Error code if the invocation failed.               |

Implementations SHOULD retain audit logs for a configurable period. The default retention
period SHOULD be at least 30 days.

Delegation events SHOULD also be logged, including the parent job ID, child job ID, and
delegation depth.

---

## 10. Prior Art

This section surveys existing AI agent orchestration systems and explains how OJS differs.

### 10.1 LangChain / LangGraph

LangChain provides Python and JavaScript libraries for building LLM-powered applications
with tool use and agent loops. LangGraph extends this with a state-machine graph
abstraction. Both systems are tightly coupled to their runtime and represent agent state
as in-memory Python/JavaScript objects. OJS differs by encoding agent configuration in a
transport-neutral, language-agnostic job envelope that any OJS-conformant backend can
process.

### 10.2 CrewAI

CrewAI defines agents with roles, goals, and backstories that collaborate on tasks. Agent
definitions are Python classes bound to the CrewAI runtime. OJS adopts the role concept
(`ext_agent_role`) and team concept (`ext_agent_team_id`) but represents them as
serializable fields rather than runtime objects, enabling cross-language agent teams.

### 10.3 AutoGen (Microsoft)

AutoGen models multi-agent conversations as message threads between agent personas. State
is maintained in memory and does not survive process restarts. OJS encodes the relevant
state (delegation chain, token budget, tool results) in the durable job envelope,
providing persistence and recoverability by default.

### 10.4 OpenAI Assistants API

The Assistants API provides server-side agent state management with tool use, file
retrieval, and conversation threads. However, it is vendor-locked to OpenAI. OJS provides
a vendor-neutral envelope that can target any LLM provider through the
`ext_agent_provider` and `ext_agent_model` fields.

### 10.5 Anthropic Tool Use

Anthropic's tool use protocol defines a JSON format for tool definitions and results that
is compatible with the OJS tool schema (Section 4). OJS builds on this compatibility by
adding orchestration concerns (budgets, delegation, fallback) that the Anthropic API does
not address.

### 10.6 Key Differentiators

| Concern              | LangChain | CrewAI | AutoGen | OpenAI API | OJS AI Agents    |
|----------------------|-----------|--------|---------|------------|------------------|
| Transport-neutral    | No        | No     | No      | No         | **Yes**          |
| Language-agnostic    | No        | No     | No      | Partial    | **Yes**          |
| Vendor-neutral       | Partial   | No     | Partial | No         | **Yes**          |
| Durable state        | No        | No     | No      | Yes        | **Yes**          |
| Retry integration    | No        | No     | No      | No         | **Yes**          |
| Workflow composition | Partial   | No     | No      | No         | **Yes**          |
| Token budget control | No        | No     | No      | Partial    | **Yes (enforce)** |

---

## 11. Extension Interactions

This section defines how the AI Agent extension interacts with other OJS specifications.

### 11.1 Interaction with OJS Retry Policy

Model fallback (Section 3.2) is an internal mechanism of agent execution. Model fallback
attempts MUST NOT count as job-level retries as defined by the OJS Retry Policy
Specification. A single job execution may attempt multiple models; this entire sequence
is one job attempt.

When an agent task fails with a retryable error (e.g., `AGENT_MODEL_UNAVAILABLE` after
all fallback models are exhausted), the standard OJS retry policy applies. The retry
policy's `initial_interval`, `backoff_coefficient`, and `max_attempts` govern the
inter-attempt behavior.

Non-retryable agent errors (e.g., `AGENT_TOKEN_BUDGET_EXCEEDED`) SHOULD be added to the
retry policy's `non_retryable_errors` list to prevent wasted retry attempts.

### 11.2 Interaction with OJS Workflows

Agent delegation chains (Section 2.3) are distinct from OJS workflow chains. A delegation
chain is an agent-internal mechanism where one agent spawns a sub-agent; a workflow chain
is a user-defined sequence of independent jobs.

Agent tasks MAY participate in OJS workflows. An agent task MAY be a step in a workflow
chain, a job in a workflow group, or a job in a workflow batch. The agent extension fields
are orthogonal to workflow fields -- both can coexist on the same job envelope.

When an agent task is part of a workflow chain, the workflow's data passing semantics apply:
the result of the previous step is available via `JobContext.parent_results`. This result
MAY be used to populate the agent's prompt or tool inputs.

### 11.3 Interaction with OJS Middleware

Middleware chains (enqueue and execution) can inspect and modify agent extension fields.
This enables cross-cutting concerns such as:

- **Token budget enforcement middleware**: An enqueue middleware that validates
  `ext_agent_token_budget` against organizational limits before the job enters the queue.
- **Model routing middleware**: An enqueue middleware that overrides `ext_agent_model`
  based on queue load, cost optimization, or A/B testing policies.
- **Audit middleware**: An execution middleware that logs all tool invocations and
  delegation events.
- **Cost tracking middleware**: An execution middleware that aggregates
  `ext_agent_tokens_used` across agent tasks for billing purposes.

Middleware MUST NOT modify `ext_agent_tokens_used` or `ext_agent_delegation_depth` except
through the mechanisms defined in this specification (Section 3.1 and Section 3.3).

**Rationale for MUST NOT modify system fields**: These fields are system-managed counters
with atomicity requirements. Middleware that arbitrarily modifies them would break budget
enforcement and depth tracking invariants.

### 11.4 Interaction with OJS Encryption Extension

Agent prompts and outputs MAY contain sensitive data (PII, proprietary information,
confidential queries). When the OJS encryption extension is active, implementations
SHOULD encrypt:

- The `args` field (which typically contains the agent's prompt).
- The job result (which contains the agent's output).
- The `ext_agent_tool_results` field (which may contain sensitive retrieval results).

The `ext_agent_output_schema` and `ext_agent_tools` fields SHOULD NOT be encrypted, as
they are structural metadata needed for routing and validation.

---

*End of specification.*
