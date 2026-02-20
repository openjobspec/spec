# Open Job Spec: Encryption and Codec Specification

> **⚠️ EXPERIMENTAL**: This extension is under active development. The specification
> may change in breaking ways between versions. Implementations and SDKs that adopt
> this extension should expect migration work when the spec evolves. Feedback is
> encouraged via the OJS RFC process.

| Field        | Value                                                    |
|-------------|----------------------------------------------------------|
| **Title**   | OJS Encryption and Codec Specification                   |
| **Version** | 0.1.0                                                    |
| **Date**    | 2026-02-19                                               |
| **Status**  | Experimental                                             |
| **Maturity** | Experimental                                             |
| **Tier**    | Experimental Extension                                   |
| **URI**     | `urn:ojs:ext:experimental:encryption`                    |
| **Requires**| OJS Core Specification (Layer 1)                         |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Design Principles](#4-design-principles)
5. [Codec Architecture](#5-codec-architecture)
6. [Encryption Codec](#6-encryption-codec)
7. [Compression Codec](#7-compression-codec)
8. [Codec Chaining](#8-codec-chaining)
9. [Codec Server](#9-codec-server)
10. [Key Management](#10-key-management)
11. [HTTP Binding](#11-http-binding)
12. [Conformance Requirements](#12-conformance-requirements)
13. [Prior Art](#13-prior-art)
14. [Examples](#14-examples)
15. [Resolved Design Decisions](#15-resolved-design-decisions)

---

## 1. Introduction

Enterprise compliance requirements (GDPR, HIPAA, PCI-DSS, SOC 2) often mandate that sensitive data (personal information, financial data, health records) be encrypted at rest. When job arguments contain such data, the OJS backend stores them in plaintext -- visible to operators, dashboards, logs, and anyone with backend access.

Temporal's Codec Server approach is the gold standard for this problem: a custom PayloadCodec encrypts job arguments client-side before they reach the server, so the server never sees plaintext. A separate HTTPS Codec Server with JWT-based authentication enables dashboards to decrypt payloads for authorized users.

This specification defines a codec architecture that supports encryption, compression, and custom transformations of job payloads. The codec operates at the SDK level, transforming `args` and `meta` before they are sent to the backend and after they are received.

### 1.1 Scope

This specification defines:

- A codec interface for transforming job payloads (args and meta).
- An encryption codec for AES-256-GCM encryption of sensitive data.
- A compression codec for reducing payload size.
- Codec chaining for composing multiple transformations.
- A Codec Server protocol for dashboard/UI integration.
- Key management guidance.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term            | Definition                                                                                     |
|-----------------|------------------------------------------------------------------------------------------------|
| codec           | A component that encodes (transforms) data before storage and decodes it after retrieval.      |
| payload codec   | A codec that operates on job `args` and optionally `meta` fields.                              |
| encryption codec| A payload codec that encrypts data using symmetric encryption.                                 |
| compression codec| A payload codec that compresses data to reduce size.                                          |
| codec chain     | An ordered sequence of codecs applied in order during encoding and reverse order during decoding.|
| codec server    | An HTTP service that provides codec operations for dashboards and tools.                       |
| plaintext       | Unencoded data.                                                                                |
| ciphertext      | Encrypted data.                                                                                |

---

## 4. Design Principles

1. **Client-side transformation.** Codecs execute in the SDK, not the backend. The backend never sees plaintext when encryption is enabled. This is the fundamental security property.

2. **Backend-transparent.** The backend stores encoded data as opaque strings. No backend changes are required to support codecs. This means any OJS backend works with any codec.

3. **Composable via chaining.** Multiple codecs can be chained: e.g., compress then encrypt. The chain applies in order during encoding and reverse order during decoding.

4. **Dashboard integration via Codec Server.** Dashboards cannot decrypt data directly (they don't have keys). A separate Codec Server mediates, enabling authorized dashboard access to plaintext.

---

## 5. Codec Architecture

### 5.1 Codec Interface

A codec implements two operations:

```
encode(payload: Payload) → Payload
decode(payload: Payload) → Payload
```

Where `Payload` is:

```json
{
  "data": "<base64-encoded bytes>",
  "metadata": {
    "encoding": "binary/encrypted",
    "encryption_key_id": "key-2026-02"
  }
}
```

### 5.2 Encoded Job Envelope

When a codec is active, the job's `args` field contains an encoded payload instead of the original array:

```json
{
  "type": "payment.process",
  "args": [
    {
      "ojs_encoded": true,
      "encoding": "binary/encrypted+zstd",
      "data": "AQAAABR...base64...=="
    }
  ],
  "meta": {
    "ojs.codec.encodings": ["zstd/plain", "binary/encrypted"],
    "ojs.codec.key_id": "key-2026-02"
  }
}
```

The `ojs_encoded: true` marker tells the SDK that the args need decoding before passing to the handler.

### 5.3 Codec Metadata in `meta`

When codecs are applied, the SDK MUST store codec metadata in the `meta` field:

| Meta Field                 | Description                                               |
|----------------------------|-----------------------------------------------------------|
| `ojs.codec.encodings`     | Array of encoding names applied, in order.                |
| `ojs.codec.key_id`        | Encryption key identifier (if encryption codec is used).  |

---

## 6. Encryption Codec

### 6.1 Algorithm

The encryption codec MUST use **AES-256-GCM** (Galois/Counter Mode) for authenticated encryption.

| Parameter          | Value                                              |
|--------------------|----------------------------------------------------|
| Algorithm          | AES-256-GCM                                        |
| Key size           | 256 bits (32 bytes)                                |
| Nonce size         | 96 bits (12 bytes), randomly generated per job     |
| Tag size           | 128 bits (16 bytes)                                |

**Rationale**: AES-256-GCM is the industry standard for authenticated encryption. It provides both confidentiality and integrity. It is supported by every major language's crypto library. The 96-bit nonce with random generation provides negligible collision probability for up to 2^32 encryptions per key.

### 6.2 Encrypted Payload Format

```
[1 byte: version] [12 bytes: nonce] [N bytes: ciphertext] [16 bytes: GCM tag]
```

- **Version byte**: `0x01` for AES-256-GCM. Enables future algorithm changes.
- **Nonce**: Randomly generated per encryption. MUST NOT be reused with the same key.
- **Ciphertext**: The encrypted `args` JSON, serialized as UTF-8 bytes.
- **GCM tag**: Authentication tag. Decryption MUST fail if the tag does not verify.

### 6.3 What Gets Encrypted

By default, the encryption codec encrypts the `args` field only. The following fields are NOT encrypted (they are needed for routing and management):

| Field        | Encrypted? | Rationale                                       |
|--------------|------------|--------------------------------------------------|
| `type`       | No         | Needed for routing to the correct handler.       |
| `queue`      | No         | Needed for queue assignment.                     |
| `args`       | **Yes**    | Contains business data (PII, financial, etc.).   |
| `meta`       | Partial    | Codec metadata fields are not encrypted. User-defined meta fields MAY be encrypted. |
| `id`         | No         | Needed for job correlation and deduplication.    |
| `priority`   | No         | Needed for scheduling.                           |
| `scheduled_at`| No        | Needed for scheduling.                           |

### 6.4 Selective Encryption

Implementations MAY support encrypting only specific fields within `args` rather than the entire array. This enables backends to search/filter on non-sensitive fields while keeping sensitive fields encrypted.

---

## 7. Compression Codec

### 7.1 Supported Algorithms

| Algorithm | Encoding Name    | Use Case                                       |
|-----------|------------------|-------------------------------------------------|
| zstd      | `zstd/plain`     | Best ratio + speed balance. RECOMMENDED.        |
| gzip      | `gzip/plain`     | Widely available. Good for interop.             |
| snappy    | `snappy/plain`   | Fastest. Lower ratio.                           |

### 7.2 When to Compress

Compression is most effective for jobs with large `args` payloads (> 1 KB). For small payloads, compression overhead may increase size. SDKs SHOULD skip compression when the compressed output is larger than the input.

---

## 8. Codec Chaining

Codecs are applied in chain order during encoding and reverse order during decoding:

```
Encoding: plaintext → compress → encrypt → stored
Decoding: stored → decrypt → decompress → plaintext
```

The `ojs.codec.encodings` meta field records the chain for decoding:

```json
{
  "ojs.codec.encodings": ["zstd/plain", "binary/encrypted"]
}
```

This reads as: "first compressed with zstd, then encrypted."

---

## 9. Codec Server

### 9.1 Purpose

The Codec Server is a standalone HTTP service that provides encode/decode operations for tools that don't have direct access to encryption keys (dashboards, admin CLIs, debugging tools).

### 9.2 Codec Server API

```
POST /codec/encode
POST /codec/decode
```

**Request** (decode):

```json
{
  "payloads": [
    {
      "data": "AQAAABR...base64...==",
      "metadata": {
        "encoding": "binary/encrypted",
        "encryption_key_id": "key-2026-02"
      }
    }
  ]
}
```

**Response**:

```json
{
  "payloads": [
    {
      "data": "eyJjdXN0b21lcl9pZCI6ICJjdXN0XzEyMyJ9",
      "metadata": {
        "encoding": "json/plain"
      }
    }
  ]
}
```

### 9.3 Authentication

The Codec Server MUST require authentication. RECOMMENDED: JWT-based bearer token authentication:

```http
POST /codec/decode HTTP/1.1
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Content-Type: application/json
```

The Codec Server SHOULD validate that the requesting user has permission to view the decoded data. This enables per-user or per-role access control over sensitive job data.

### 9.4 Dashboard Integration

Dashboards query the Codec Server to display decoded job arguments:

```
Dashboard → [GET /ojs/v1/admin/jobs/{id}] → Backend (returns encrypted args)
         → [POST /codec/decode] → Codec Server (returns plaintext args)
         → Displays plaintext to authorized user
```

---

## 10. Key Management

### 10.1 Key Rotation

Encryption keys SHOULD be rotated periodically. When keys are rotated:

1. New jobs are encrypted with the new key.
2. Old jobs remain readable because the `ojs.codec.key_id` identifies which key was used.
3. The old key MUST be retained until all jobs encrypted with it have been processed or pruned.

### 10.2 Key Storage

This specification does not mandate a specific key storage mechanism. Implementations SHOULD support:

- Environment variables (simplest, for development).
- Secret management services (AWS Secrets Manager, HashiCorp Vault, GCP Secret Manager).
- Key Management Services (AWS KMS, GCP KMS, Azure Key Vault) for key wrapping.

---

## 11. HTTP Binding

### 11.1 Codec Server Registration

Backends MAY support registering a Codec Server URL in the manifest:

```json
{
  "extensions": {
    "experimental": [
      {
        "name": "encryption",
        "uri": "urn:ojs:ext:experimental:encryption",
        "version": "0.1.0"
      }
    ]
  },
  "codec_server_url": "https://codec.internal.example.com"
}
```

---

## 12. Conformance Requirements

An SDK declaring support for the encryption extension MUST support:

| ID           | Requirement                                                                |
|--------------|----------------------------------------------------------------------------|
| ENC-001      | Codec interface with encode/decode operations.                             |
| ENC-002      | AES-256-GCM encryption codec with random nonce per job.                    |
| ENC-003      | Codec metadata stored in `meta.ojs.codec.encodings` and `meta.ojs.codec.key_id`. |
| ENC-004      | Transparent decode before handler invocation.                              |
| ENC-005      | `ojs_encoded: true` marker in encoded args.                               |

---

## 13. Prior Art

| System           | Encryption Approach                                                                       |
|------------------|-------------------------------------------------------------------------------------------|
| **Temporal**     | PayloadCodec interface with Codec Server. Client-side encryption/compression. Server never sees plaintext. |
| **Sidekiq Enterprise** | `Sidekiq::Enterprise::Crypto` for encrypting job args at rest.                      |
| **River Pro**    | Encrypted jobs feature.                                                                   |
| **AWS SQS**      | Server-side encryption via KMS. Client-side encryption via SQS Extended Client Library.  |
| **Kafka**        | Client-side serialization/encryption. Schema Registry for codec management.              |

Temporal's Codec Server model is the primary inspiration. OJS adapts it with a simpler protocol (JSON over HTTP) and explicit support for codec chaining.

---

## 14. Examples

### 14.1 Encrypting Job Args (Go)

```go
key := []byte("32-byte-encryption-key-here!!!!!")
codec := ojs.NewEncryptionCodec(key, "key-2026-02")

client, _ := ojs.NewClient("http://localhost:8080",
    ojs.WithCodec(codec),
)

// Args are encrypted before sending to the backend
job, _ := client.Enqueue(ctx, "payment.process",
    ojs.Args{"card_number": "4111111111111111", "amount": 9999},
)
// Backend sees encrypted blob, not card number
```

### 14.2 Compression + Encryption Chain (JavaScript)

```javascript
import { OJSClient, ZstdCodec, EncryptionCodec, CodecChain } from '@openjobspec/client';

const codec = new CodecChain([
  new ZstdCodec(),                    // Compress first
  new EncryptionCodec(key, 'key-2026-02'), // Then encrypt
]);

const client = new OJSClient({
  url: 'http://localhost:8080',
  codec,
});
```

---

## 15. Resolved Design Decisions

The following design decisions were resolved during the experimental phase:

### 15.1 Server-Side Encryption

**Question:** Should the backend support server-side encryption as an alternative?

**Decision:** No. OJS specifies client-side encryption only. Server-side encryption is a backend implementation detail outside the spec scope.

**Rationale:** Client-side encryption provides zero-trust security. Backend-specific server-side encryption (e.g., Redis TDE, PostgreSQL pgcrypto) MAY be used as defense-in-depth but is not standardized by OJS.

### 15.2 Key Exchange Standard

**Question:** Should there be a standard for key exchange between SDK and Codec Server?

**Decision:** Out of scope for v1.0. Key distribution MUST be handled by the deployment environment (e.g., Vault, AWS KMS, environment variables). The OJS spec defines the codec interface, not key management infrastructure.

**Rationale:** Key management is deployment-specific and well-served by existing tools (HashiCorp Vault, AWS KMS, Azure Key Vault).

### 15.3 Encrypted Jobs and Unique Job Deduplication

**Question:** How should encrypted jobs interact with unique job deduplication?

**Decision:** Unique key computation MUST occur BEFORE encryption in the middleware chain. The SDK's enqueue middleware ordering MUST be: validate → compute unique key → encrypt → enqueue. This is documented in ojs-extension-interactions.md.

**Rationale:** This preserves deduplication capability while still encrypting the payload at rest.

### 15.4 Partial Encryption via JSON Paths

**Question:** Should partial encryption support specific JSON paths?

**Decision:** Yes, as an optional feature. The encryption codec MAY support a `paths` configuration specifying which JSON paths to encrypt (e.g., `["args[0].card_number", "args[0].ssn"]`). Unspecified paths remain in plaintext. This is OPTIONAL and implementations MAY choose to support only full-payload encryption.

**Rationale:** Partial encryption enables server-side filtering on non-sensitive fields while protecting PII, a common production requirement.

---

## Appendix A: Changelog

| Date       | Change                          |
|------------|---------------------------------|
| 2026-02-13 | Initial experimental release.   |

