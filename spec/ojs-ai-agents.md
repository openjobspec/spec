# Open Job Spec -- AI Agent Task Orchestration Extension

| Field        | Value                                    |
|-------------|------------------------------------------|
| **Title**   | OJS AI Agent Task Orchestration Extension |
| **Version** | 1.0.0-rc.1                               |
| **Status**  | Draft                                    |
| **Date**    | 2026-02-23                               |
| **Layer**   | Extension                                |

---

## 1. Introduction

This extension defines how AI agent workloads -- including LLM inference, tool-calling
chains, multi-agent delegation, and RAG pipelines -- are represented and orchestrated
within the OJS job envelope.

AI agent tasks have unique requirements: model selection and fallback, token budget
tracking, structured output schemas, tool-call dependency chains, and agent-to-agent
delegation. This extension provides a standardized way to express these requirements
using the `ext_agent_*` field namespace.

## 2. Extension Fields

All fields use the `ext_agent_` prefix per the OJS extension naming convention.

### 2.1 Agent Task Metadata

| Field                       | Type     | Required | Description                                           |
|-----------------------------|----------|----------|-------------------------------------------------------|
| `ext_agent_model`           | string   | No       | Preferred model identifier (e.g., `gpt-4o`, `claude-3.5-sonnet`) |
| `ext_agent_fallback_models` | string[] | No       | Ordered list of fallback models if primary is unavailable |
| `ext_agent_provider`        | string   | No       | Provider identifier (e.g., `openai`, `anthropic`, `local`) |
| `ext_agent_temperature`     | number   | No       | Sampling temperature (0.0 -- 2.0)                     |
| `ext_agent_max_tokens`      | integer  | No       | Maximum tokens for the response                       |
| `ext_agent_token_budget`    | integer  | No       | Total token budget for the entire agent task chain     |
| `ext_agent_tokens_used`     | integer  | No       | Tokens consumed so far (system-managed)               |

### 2.2 Tool Calling

| Field                       | Type     | Required | Description                                           |
|-----------------------------|----------|----------|-------------------------------------------------------|
| `ext_agent_tools`           | object[] | No       | Available tools for this agent task                   |
| `ext_agent_tool_choice`     | string   | No       | Tool selection mode: `auto`, `required`, `none`       |
| `ext_agent_tool_results`    | object[] | No       | Results from tool invocations (system-managed)        |

### 2.3 Agent Delegation

| Field                           | Type     | Required | Description                                       |
|---------------------------------|----------|----------|---------------------------------------------------|
| `ext_agent_parent_id`           | string   | No       | Job ID of the parent agent that delegated this task |
| `ext_agent_delegation_depth`    | integer  | No       | Current depth in the delegation chain (max 10)    |
| `ext_agent_max_delegation_depth`| integer  | No       | Maximum allowed delegation depth                  |

### 2.4 Structured Output

| Field                         | Type   | Required | Description                                         |
|-------------------------------|--------|----------|-----------------------------------------------------|
| `ext_agent_output_schema`     | object | No       | JSON Schema for the expected structured output      |
| `ext_agent_output_format`     | string | No       | Output format: `json`, `text`, `markdown`           |

## 3. Agent Task Lifecycle

Agent tasks follow the standard OJS 8-state lifecycle with additional semantics:

1. **Token budget exhaustion**: If `ext_agent_tokens_used` exceeds `ext_agent_token_budget`,
   the job SHOULD transition to `retryable` with error code `AGENT_TOKEN_BUDGET_EXCEEDED`.
2. **Model fallback**: If the primary model is unavailable, implementations SHOULD
   attempt `ext_agent_fallback_models` in order before failing.
3. **Delegation depth**: If `ext_agent_delegation_depth` exceeds
   `ext_agent_max_delegation_depth`, the job MUST fail with `AGENT_MAX_DELEGATION_DEPTH`.

## 4. Tool Definition Schema

```json
{
  "name": "web_search",
  "description": "Search the web for information",
  "parameters": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "description": "Search query" }
    },
    "required": ["query"]
  }
}
```

## 5. Example

```json
{
  "type": "agent.research",
  "args": ["Summarize recent developments in quantum computing"],
  "options": {
    "queue": "ai-agents",
    "timeout_ms": 120000
  },
  "ext_agent_model": "gpt-4o",
  "ext_agent_fallback_models": ["claude-3.5-sonnet", "gpt-4o-mini"],
  "ext_agent_provider": "openai",
  "ext_agent_temperature": 0.7,
  "ext_agent_max_tokens": 4096,
  "ext_agent_token_budget": 50000,
  "ext_agent_tools": [
    {
      "name": "web_search",
      "description": "Search the web",
      "parameters": {
        "type": "object",
        "properties": {
          "query": { "type": "string" }
        },
        "required": ["query"]
      }
    }
  ],
  "ext_agent_tool_choice": "auto",
  "ext_agent_output_schema": {
    "type": "object",
    "properties": {
      "summary": { "type": "string" },
      "sources": { "type": "array", "items": { "type": "string" } }
    },
    "required": ["summary"]
  },
  "ext_agent_output_format": "json"
}
```

## 6. Security Considerations

- Token budgets MUST be enforced server-side to prevent cost overruns.
- Delegation depth MUST be bounded to prevent infinite agent loops.
- Tool definitions SHOULD be validated against an allowlist.
- Agent task results containing PII SHOULD respect the OJS encryption extension.
