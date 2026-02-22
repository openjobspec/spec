# ADR-007: Client-Side Encryption Architecture

## Status

Accepted

## Context

Job payloads frequently contain sensitive data — personally identifiable information (PII), payment details, authentication tokens, and other confidential fields. As job systems scale across organizational boundaries and cloud providers, the question of who can access plaintext job arguments becomes critical for compliance and trust.

The spec needed to decide between two fundamental encryption strategies: server-side encryption, where the backend encrypts data at rest and decrypts it for workers, and client-side encryption, where the SDK encrypts job arguments before they ever leave the producer process. Server-side encryption is simpler to implement — the backend manages keys and encryption transparently — but it creates a single point of trust. The backend (and anyone with access to it) can read all job data.

Client-side encryption eliminates this trust requirement entirely: the backend only ever sees opaque ciphertext. However, it introduces significant complexity. Every SDK must implement encryption codecs, key management must be handled client-side, and any server-side feature that inspects job arguments (filtering, deduplication on args, dashboard previews) becomes impossible without additional infrastructure.

Several production systems have validated the client-side approach. Temporal's Payload Codec architecture demonstrates that a codec pipeline — where data passes through a chain of encode/decode transformations — can cleanly separate encryption from business logic while remaining composable with other transformations like compression.

## Decision

We adopt client-side encryption via a codec architecture, inspired by Temporal's Payload Codec pattern. SDKs apply encryption codecs before enqueuing jobs; the backend stores and transmits opaque ciphertext without any knowledge of the plaintext content.

The codec architecture is a pipeline: producers encode job arguments through an ordered chain of codecs (e.g., compress → encrypt), and consumers decode in reverse order (decrypt → decompress). Each codec is a simple encode/decode interface, making them composable and testable independently.

For operational visibility, a separate Codec Server (an HTTP service that performs encode/decode on behalf of authorized callers) enables dashboards and admin tools to decrypt job arguments for display without giving the backend itself access to encryption keys. The Codec Server is authenticated independently, allowing organizations to control who can view plaintext job data.

## Consequences

### Easier

- **Zero-trust backend**: The backend never sees plaintext job data, eliminating an entire class of data breach vectors
- **Regulatory compliance**: Satisfies data residency and encryption-at-rest requirements (GDPR, HIPAA, PCI-DSS) without backend cooperation
- **Codec composability**: Encryption, compression, and custom transformations compose naturally in a pipeline
- **Key rotation**: Client-side key management enables per-tenant or per-job-type key rotation without backend changes

### Harder

- **SDK implementation burden**: Every SDK must implement the codec pipeline and at least one encryption codec to support this feature
- **Deduplication on encrypted fields**: Identical plaintext arguments produce different ciphertext (with proper IV/nonce usage), making content-based deduplication impossible on encrypted args
- **Server-side filtering**: Backends cannot filter or route jobs based on encrypted argument values without a Codec Server roundtrip
- **Debugging complexity**: Troubleshooting job failures requires access to a Codec Server or local decryption keys to inspect arguments

