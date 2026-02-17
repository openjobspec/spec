# Open Job Spec: Payload Limits Specification

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Payload Limits Specification               |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-19                                     |
| **Status**  | Release Candidate 1                            |
| **Maturity** | Experimental                                   |
| **Tier**    | Official Extension                             |
| **URI**     | `urn:ojs:ext:payload-limits`                   |
| **Requires**| OJS Core Specification (Layer 1)               |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Size Limits](#4-size-limits)
5. [External Payload References](#5-external-payload-references)
6. [Content Negotiation for Large Payloads](#6-content-negotiation-for-large-payloads)
7. [Chunking](#7-chunking)
8. [Backend Capability Declaration](#8-backend-capability-declaration)
9. [Error Handling](#9-error-handling)
10. [Conformance Requirements](#10-conformance-requirements)
11. [Prior Art](#11-prior-art)
12. [Examples](#12-examples)

---

## 1. Introduction

Job payloads vary dramatically in size — from a few bytes for a simple notification to hundreds of megabytes for media processing pipelines. Without clear limits, producers risk silent truncation, serialization timeouts, or out-of-memory failures in the backend.

Payload limits matter across every layer of a job system:

- **Memory**: Backends hold jobs in memory during enqueue, dispatch, and processing. Unbounded payloads can exhaust heap space and trigger OOM kills.
- **Network**: Large payloads increase enqueue latency, consume bandwidth, and amplify the cost of retries.
- **Storage**: Persistent backends (databases, Redis, message brokers) have their own storage constraints. Exceeding them causes silent data loss or write failures.
- **Serialization performance**: JSON serialization and deserialization cost grows linearly with payload size. A 100 MB payload serialized on every retry attempt creates significant CPU overhead.

This specification defines size limits for OJS job envelopes, a standard pattern for offloading large payloads to external storage, content negotiation for compressed payloads, and error handling when limits are exceeded.

### 1.1 Scope

This specification defines:

- Maximum sizes for job envelopes, metadata, queue names, and job types.
- An external reference pattern for payloads that exceed inline limits.
- Content negotiation and compression guidance for large payloads.
- Chunking semantics (and when NOT to use them).
- Backend capability declaration for payload size limits.
- Error responses when payload limits are exceeded.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term                  | Definition                                                                                      |
|-----------------------|-------------------------------------------------------------------------------------------------|
| payload               | The data carried by a job, primarily the `args` array and `meta` object.                        |
| inline payload        | A payload embedded directly within the job envelope as JSON values.                             |
| external payload      | A payload stored outside the job envelope in an external storage system (S3, GCS, filesystem).  |
| payload reference     | A JSON object within `args` that points to an external payload via a URI.                       |
| chunking              | Splitting a large payload into ordered segments for incremental transfer and reassembly.        |
| content negotiation   | The process by which a producer and backend agree on payload encoding (e.g., compression).      |

---

## 4. Size Limits

### 4.1 Job Envelope Total Size

The job envelope is the complete serialized JSON document submitted to the backend, including `type`, `args`, `meta`, and all other fields.

- Backends MUST support job envelopes of at least **1 MB** (1,048,576 bytes).
- Backends SHOULD support job envelopes of up to **10 MB** (10,485,760 bytes).
- Backends MAY support larger envelopes, but MUST document the maximum in their capability manifest.

Size is measured as the byte length of the UTF-8 encoded JSON document after serialization, before any transport-level compression.

### 4.2 Individual `args` Elements

There is no individual size limit for elements within the `args` array. The total envelope size limit applies. A single large argument is permitted as long as the complete envelope stays within the backend's declared maximum.

### 4.3 `meta` Field

The `meta` object MUST NOT exceed **64 KB** (65,536 bytes) when serialized as UTF-8 JSON.

**Rationale**: Metadata is indexed, logged, and displayed in dashboards. Unbounded metadata inflates indexes, slows queries, and clutters operational tooling. 64 KB is sufficient for rich metadata while preventing abuse.

### 4.4 Queue Name

Queue names MUST NOT exceed **255 bytes** when encoded as UTF-8.

### 4.5 Job Type

Job type identifiers MUST NOT exceed **255 bytes** when encoded as UTF-8.

### 4.6 Backend-Declared Limits

A backend MUST declare its maximum supported payload size in its capability manifest (see [Section 8](#8-backend-capability-declaration)).

Backends MAY support configurable per-queue payload limits. When a per-queue limit is configured, it MUST be less than or equal to the backend's global maximum.

---

## 5. External Payload References

For payloads that exceed inline size limits — or where large data should not transit through the job backend — producers SHOULD use external payload references.

### 5.1 Reference Format

An external payload reference is a JSON object containing the reserved key `__ojs_ref` with a URI pointing to the external storage location:

```json
{
  "__ojs_ref": "s3://bucket/path/to/payload.json",
  "size": 52428800,
  "checksum": "sha256:abc123def456..."
}
```

| Field        | Type    | Required | Description                                                    |
|-------------|---------|----------|----------------------------------------------------------------|
| `__ojs_ref` | string  | Yes      | URI of the external payload. Supported schemes: `s3://`, `gs://`, `file://`, `https://`. |
| `size`      | integer | No       | Size of the external payload in bytes.                         |
| `checksum`  | string  | No       | Integrity checksum in `algorithm:hex` format (e.g., `sha256:abc123...`). |

### 5.2 Usage in `args`

External references are placed within the `args` array as regular elements:

```json
{
  "type": "video.transcode",
  "args": [
    {
      "__ojs_ref": "s3://media-bucket/uploads/video-raw.mp4",
      "size": 524288000,
      "checksum": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    },
    {"output_format": "mp4", "resolution": "1080p"}
  ]
}
```

### 5.3 Resolution Responsibilities

- **Backends MUST NOT attempt to resolve external references.** The backend stores the job envelope as-is, including the reference objects.
- **SDKs SHOULD provide transparent resolution** of external references when delivering jobs to workers. The SDK downloads the referenced payload and replaces the reference object with the actual data before invoking the worker function.
- **Workers MAY resolve references themselves** if the SDK does not provide transparent resolution.

### 5.4 Integrity Verification

When a `checksum` field is present, the resolving party (SDK or worker) MUST verify the checksum after downloading the external payload. If the checksum does not match, the job MUST be failed with a `PayloadChecksumMismatch` error.

Supported checksum algorithms: `sha256` (REQUIRED), `sha384`, `sha512` (OPTIONAL).

---

## 6. Content Negotiation for Large Payloads

### 6.1 Compression

For payloads that are large but still within inline limits, producers MAY compress the payload before submission. Compression follows the codec chain architecture defined in [ojs-encryption.md](ojs-encryption.md).

Backends SHOULD support the following compression codecs:

| Codec   | Content-Encoding | Notes                                      |
|---------|------------------|--------------------------------------------|
| gzip    | `gzip`           | Widely supported, good compression ratio.  |
| zstd    | `zstd`           | Better compression ratio and speed than gzip. RECOMMENDED for new implementations. |

### 6.2 HTTP Binding

When submitting compressed payloads via the HTTP binding, producers MUST set the `Content-Encoding` header:

```http
POST /ojs/v1/jobs HTTP/1.1
Content-Type: application/openjobspec+json
Content-Encoding: zstd

<zstd-compressed job envelope>
```

The backend MUST decompress the payload before applying size limit validation. Size limits apply to the **decompressed** payload.

### 6.3 Negotiation

Producers SHOULD check the backend's capability manifest for supported compression codecs before sending compressed payloads. If the backend does not advertise support for a codec, the producer MUST send the payload uncompressed.

---

## 7. Chunking

### 7.1 Overview

Chunking splits a large payload into ordered segments for incremental transfer. Each chunk is a separate message that the receiver reassembles into the complete payload.

### 7.2 Applicability

Chunking is **NOT RECOMMENDED** for most job systems. External payload references (Section 5) are the preferred approach for large data. Chunking adds complexity in ordering, reassembly, and failure handling that is rarely justified.

Chunking MAY be appropriate for:

- Streaming pipelines where data is produced incrementally.
- Environments where external storage is unavailable.
- Backend transports with hard per-message size limits that cannot be increased.

### 7.3 Chunk Format

If a backend supports chunking, each chunk MUST include:

| Field            | Type    | Description                                          |
|-----------------|---------|------------------------------------------------------|
| `chunk_id`      | string  | Unique identifier for the chunked payload group.     |
| `chunk_index`   | integer | Zero-based index of this chunk in the sequence.      |
| `chunk_total`   | integer | Total number of chunks in the payload.               |
| `chunk_data`    | string  | Base64-encoded chunk content.                        |

### 7.4 Reassembly

The receiver MUST reassemble chunks in `chunk_index` order. The receiver MUST NOT begin processing until all chunks have been received. If any chunk is missing after a configurable timeout, the entire chunked payload MUST be discarded and an error reported.

---

## 8. Backend Capability Declaration

### 8.1 Manifest Fields

Backends MUST advertise payload limits in their capability manifest:

```json
{
  "extensions": {
    "payload_limits": {
      "max_envelope_bytes": 10485760,
      "max_meta_bytes": 65536,
      "max_queue_name_bytes": 255,
      "max_job_type_bytes": 255,
      "supported_compression": ["gzip", "zstd"],
      "external_references": true,
      "chunking": false,
      "per_queue_limits": true
    }
  }
}
```

| Field                     | Type     | Description                                              |
|--------------------------|----------|----------------------------------------------------------|
| `max_envelope_bytes`     | integer  | Maximum job envelope size in bytes.                      |
| `max_meta_bytes`         | integer  | Maximum `meta` field size in bytes.                      |
| `max_queue_name_bytes`   | integer  | Maximum queue name length in bytes.                      |
| `max_job_type_bytes`     | integer  | Maximum job type length in bytes.                        |
| `supported_compression`  | string[] | List of supported compression codecs.                    |
| `external_references`    | boolean  | Whether the backend passes through `__ojs_ref` objects.  |
| `chunking`               | boolean  | Whether the backend supports chunked payloads.           |
| `per_queue_limits`       | boolean  | Whether per-queue payload limits are configurable.       |

### 8.2 SDK Negotiation

SDKs SHOULD query the backend's capability manifest on initialization and cache the result. When a producer enqueues a job, the SDK SHOULD validate the payload against the declared limits **before** sending it to the backend. This avoids unnecessary network round-trips for payloads that will be rejected.

---

## 9. Error Handling

### 9.1 PayloadTooLarge Error

When a job envelope exceeds the backend's maximum payload size, the backend MUST reject the request.

**HTTP Binding**: Return HTTP **413 Payload Too Large**.

```http
HTTP/1.1 413 Payload Too Large
Content-Type: application/json

{
  "error": "PayloadTooLarge",
  "message": "Job envelope size 15728640 bytes exceeds maximum of 10485760 bytes.",
  "details": {
    "actual_bytes": 15728640,
    "max_bytes": 10485760,
    "field": "envelope"
  }
}
```

### 9.2 MetadataTooLarge Error

When the `meta` field exceeds the 64 KB limit:

```http
HTTP/1.1 413 Payload Too Large
Content-Type: application/json

{
  "error": "MetadataTooLarge",
  "message": "Meta field size 131072 bytes exceeds maximum of 65536 bytes.",
  "details": {
    "actual_bytes": 131072,
    "max_bytes": 65536,
    "field": "meta"
  }
}
```

### 9.3 Error Codes Summary

| Error Code               | HTTP Status | Trigger                                        |
|--------------------------|-------------|------------------------------------------------|
| `PayloadTooLarge`        | 413         | Job envelope exceeds `max_envelope_bytes`.     |
| `MetadataTooLarge`       | 413         | `meta` field exceeds `max_meta_bytes`.         |
| `QueueNameTooLong`       | 400         | Queue name exceeds `max_queue_name_bytes`.     |
| `JobTypeTooLong`         | 400         | Job type exceeds `max_job_type_bytes`.         |
| `PayloadChecksumMismatch`| 422         | External reference checksum verification failed.|
| `UnsupportedCompression` | 415         | Payload uses an unsupported compression codec. |

---

## 10. Conformance Requirements

An implementation declaring support for the payload-limits extension MUST support:

| ID     | Requirement                                                                              | Level    |
|--------|------------------------------------------------------------------------------------------|----------|
| PL-001 | Support job envelopes of at least 1 MB.                                                  | MUST     |
| PL-002 | Enforce `meta` field size limit of 64 KB.                                                | MUST     |
| PL-003 | Enforce queue name limit of 255 bytes.                                                   | MUST     |
| PL-004 | Enforce job type limit of 255 bytes.                                                     | MUST     |
| PL-005 | Declare maximum payload size in capability manifest.                                     | MUST     |
| PL-006 | Return HTTP 413 when job envelope exceeds declared maximum.                              | MUST     |
| PL-007 | Pass through `__ojs_ref` objects without resolving them.                                 | MUST     |
| PL-008 | Support job envelopes of up to 10 MB.                                                    | SHOULD   |
| PL-009 | Support gzip and zstd compressed payloads.                                               | SHOULD   |
| PL-010 | Apply size limits to decompressed payload, not compressed wire format.                   | MUST     |
| PL-011 | SDK validates payload size against manifest before sending.                               | SHOULD   |
| PL-012 | SDK provides transparent resolution of external references.                               | SHOULD   |
| PL-013 | Verify `checksum` on external references when present.                                   | MUST     |
| PL-014 | Support configurable per-queue payload limits.                                           | MAY      |

---

## 11. Prior Art

### 11.1 AWS SQS

Amazon SQS imposes a **256 KB** message size limit. For larger payloads, the [Extended Client Library](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-s3-messages.html) transparently stores the payload in S3 and replaces the message body with an S3 pointer. This is the direct inspiration for the `__ojs_ref` pattern in Section 5.

### 11.2 Sidekiq

Sidekiq (Ruby) stores job arguments in Redis. The community guidance is to keep job arguments small (IDs and scalar values) and fetch large data inside the worker. Sidekiq does not enforce a hard payload limit but warns when arguments exceed 100 KB because Redis `HSET` performance degrades with large values.

### 11.3 Celery

Celery (Python) supports multiple result backends (Redis, RabbitMQ, database). Each has different size constraints. RabbitMQ has a configurable `max_message_size` (default: 128 MB). Redis has no per-value limit but is constrained by available memory. Celery recommends passing file paths or URLs rather than embedding large data in task arguments.

### 11.4 Apache Kafka

Kafka's `message.max.bytes` defaults to **1 MB** per message, configurable at the broker and topic level. Producers receive a `MessageSizeTooLarge` error when the limit is exceeded. This broker-declared, client-validated pattern informed the capability manifest approach in Section 8.

### 11.5 gRPC

gRPC enforces a default maximum message size of **4 MB** (`grpc.max_receive_message_length`). Both client and server can override this limit independently. If a message exceeds the receiver's limit, a `RESOURCE_EXHAUSTED` status code is returned.

---

## 12. Examples

### 12.1 Normal Inline Payload

A typical job with inline arguments well within limits:

```json
{
  "type": "email.send",
  "queue": "notifications",
  "args": [
    {
      "to": "user@example.com",
      "subject": "Welcome!",
      "body": "Thank you for signing up."
    }
  ],
  "meta": {
    "tenant_id": "acme-corp",
    "correlation_id": "req-abc-123"
  }
}
```

### 12.2 External Reference for Large Payload

A video transcoding job where the input file is referenced externally:

```json
{
  "type": "video.transcode",
  "queue": "media-processing",
  "args": [
    {
      "__ojs_ref": "s3://media-bucket/uploads/2026/02/raw-footage.mp4",
      "size": 1073741824,
      "checksum": "sha256:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
    },
    {
      "output_format": "mp4",
      "resolution": "1080p",
      "codec": "h264"
    }
  ],
  "meta": {
    "user_id": "user-456",
    "upload_id": "upload-789"
  }
}
```

### 12.3 Error Response: Payload Too Large

```json
{
  "error": "PayloadTooLarge",
  "message": "Job envelope size 15728640 bytes exceeds maximum of 10485760 bytes.",
  "details": {
    "actual_bytes": 15728640,
    "max_bytes": 10485760,
    "field": "envelope"
  }
}
```

### 12.4 Backend Capability Manifest (Payload Limits Section)

```json
{
  "extensions": {
    "payload_limits": {
      "max_envelope_bytes": 10485760,
      "max_meta_bytes": 65536,
      "max_queue_name_bytes": 255,
      "max_job_type_bytes": 255,
      "supported_compression": ["gzip", "zstd"],
      "external_references": true,
      "chunking": false,
      "per_queue_limits": true
    }
  }
}
```
