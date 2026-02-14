# ADR-003: Args (Array) Over Payload (Object)

## Status

Accepted

## Context

Job processing systems use one of two patterns for passing data to job handlers:

1. **Payload (Object)**: A single JSON object with named keys — `{ "user_id": 123, "action": "notify" }`
2. **Args (Array)**: An ordered JSON array of positional arguments — `[123, "notify"]`

Systems using the payload pattern: BullMQ (`data` object), Celery (`kwargs` dict), most HTTP-based task queues.
Systems using the args pattern: Sidekiq (`args` array), Resque (`args` array), Faktory (`args` array).

Key considerations:

- **Function signature mapping**: Most programming languages define job handlers as functions with positional parameters. `args` maps directly to function parameters: `handle(userId, action)` ← `[123, "notify"]`. Payload requires destructuring or a wrapper.
- **Serialization simplicity**: Arrays have deterministic ordering, making it trivial to define canonical forms for deduplication and unique job fingerprinting.
- **Backward compatibility**: When adding optional parameters, args can be extended by appending (preserving existing positions), while payload keys are inherently unordered.
- **Language ergonomics**: In strongly-typed languages (Go, Java, Rust), mapping an object to function parameters requires reflection or code generation. An array maps naturally to a tuple/varargs.

## Decision

OJS uses `args` (a JSON array) as the job argument field, not `payload` (a JSON object).

```json
{
  "type": "email.send",
  "args": [123, "welcome", {"priority": "high"}]
}
```

The `args` array:
- MUST be a JSON array
- MAY contain any valid JSON values (strings, numbers, objects, arrays, booleans, null)
- Is positional — order matters and maps to handler function parameters
- Is used for unique job fingerprinting when combined with `type` and `queue`

For complex arguments, a single object can be the sole element: `args: [{"user_id": 123, "action": "notify"}]`.

## Consequences

### Easier
- **SDK implementation**: Handler registration maps naturally to function signatures in all languages
- **Unique job keys**: Deterministic serialization of arrays enables reliable fingerprinting without key-sorting objects
- **Cross-language consistency**: All SDKs destructure args identically regardless of language idioms
- **Migration from Sidekiq/Resque/Faktory**: Direct compatibility with the largest Ruby/polyglot job ecosystems

### Harder
- **Self-documenting payloads**: Objects with named keys are more readable than positional arrays — `{"to": "user@example.com"}` vs `["user@example.com"]`
- **Migration from BullMQ/Celery**: Teams using object payloads must refactor to array positions
- **Refactoring risk**: Changing argument order is a breaking change (unlike renaming object keys)
