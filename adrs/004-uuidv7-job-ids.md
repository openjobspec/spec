# ADR-004: UUIDv7 for Job IDs

## Status

Accepted

## Context

Job identifiers must be:
1. **Globally unique** — no collisions across backends, regions, or time
2. **Sortable by creation time** — for efficient indexing, pagination, and "oldest first" queries
3. **Generated client-side** — so producers can reference job IDs before the backend acknowledges creation
4. **Compact** — reasonable storage and wire size

Options considered:

| Format | Unique | Time-sortable | Client-generated | Size |
|--------|--------|---------------|------------------|------|
| Auto-increment (DB sequence) | Per-DB only | ✅ | ❌ | 4-8 bytes |
| UUIDv4 | ✅ | ❌ | ✅ | 16 bytes |
| ULID | ✅ | ✅ | ✅ | 16 bytes |
| UUIDv7 | ✅ | ✅ | ✅ | 16 bytes |
| Snowflake ID | ✅ | ✅ | ✅ (needs config) | 8 bytes |

**UUIDv4** is the most widely used but not time-sortable, causing B-tree index fragmentation in PostgreSQL and poor range-scan performance.

**ULID** is time-sortable and widely adopted but uses a non-standard encoding (Crockford Base32) and is not part of the UUID standard, limiting library support.

**UUIDv7** (RFC 9562, published May 2024) provides time-sortable UUIDs as part of the official UUID standard. It encodes a Unix timestamp in the high bits, providing millisecond-precision ordering while maintaining the standard UUID format (128-bit, hyphenated hex string).

**Snowflake IDs** are compact but require machine ID configuration, making them unsuitable for a protocol where any client can generate IDs.

## Decision

All job IDs in OJS MUST be UUIDv7 as defined in RFC 9562.

- Backends MUST accept UUIDv7 values in the `id` field
- SDKs MUST generate UUIDv7 values when creating jobs client-side
- Backends MAY generate UUIDv7 values server-side if the client omits the `id` field
- Job IDs are represented as standard hyphenated lowercase hex strings: `01912b6c-5a30-7e91-b123-456789abcdef`

## Consequences

### Easier
- **Database performance**: Time-ordered inserts avoid B-tree fragmentation in PostgreSQL, MySQL, and SQLite — up to 3x faster inserts under load compared to UUIDv4
- **Natural ordering**: `ORDER BY id` returns jobs in creation order without a separate `created_at` index
- **Client-side generation**: Producers can create job IDs before enqueuing, enabling idempotent retries and pre-referencing in workflows
- **Standard compliance**: RFC 9562 ensures long-term library support across all languages
- **Extraction of creation time**: The embedded timestamp can be extracted for debugging without querying additional fields

### Harder
- **Library availability**: UUIDv7 libraries are newer than UUIDv4 — some languages require specific library choices (though support is now widespread as of 2025)
- **Clock skew**: UUIDv7 ordering assumes synchronized clocks; clock skew between producers can cause minor ordering inconsistencies (mitigated by the random suffix bits)
- **Migration**: Existing systems using UUIDv4 or integer IDs must convert or maintain dual-ID schemes
