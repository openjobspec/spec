# OJS Serverless Integration Specification

**Open Job Spec v1.0.0-rc.1 — Experimental Extension**

| Field       | Value                  |
|-------------|------------------------|
| Version     | 0.1.0                  |
| Date        | 2026-02-19             |
| Status      | Experimental           |
| Maturity    | Experimental           |
| Layer       | 3 (Protocol Binding)   |
| Level       | Extension              |

---

## 1. Overview

Serverless functions (AWS Lambda, Google Cloud Functions, Azure Functions) represent a natural execution model for background job processing: event-triggered, auto-scaling, pay-per-use compute. This extension defines how OJS jobs can be delivered to and processed by serverless functions, complementing the existing poll-based worker model with push-based delivery.

### 1.1 Relationship to Other Specifications

- **ojs-core.md**: Serverless workers process standard OJS jobs. The job envelope, lifecycle, and state machine are unchanged.
- **ojs-http-binding.md**: The push delivery endpoint reuses the HTTP binding's content types and error format.
- **ojs-webhooks.md**: Push delivery builds on webhook patterns (HMAC signing, retry semantics, idempotency).
- **ojs-sqs-backend**: The SQS backend is a natural fit for Lambda integration via SQS event source mapping.

### 1.2 Terminology

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

---

## 2. Delivery Modes

OJS supports two delivery models for job processing:

| Mode | Mechanism | Use Case |
|------|-----------|----------|
| **Pull** (default) | Worker calls `POST /workers/fetch` | Long-running workers, stateful processing |
| **Push** (this extension) | Server invokes function endpoint | Serverless, event-driven, auto-scaling |

### 2.1 Push Delivery Registration

A serverless function registers as a push endpoint for specific job types:

```json
{
  "endpoint": "https://abc123.lambda-url.us-east-1.on.aws/",
  "job_types": ["email.send", "report.generate"],
  "queues": ["default"],
  "config": {
    "max_concurrency": 100,
    "timeout_ms": 30000,
    "signing_secret": "whsec_..."
  }
}
```

### 2.2 Push Delivery Request

When a job becomes available and matches a registered push endpoint, the server MUST deliver it via HTTP POST:

```http
POST / HTTP/1.1
Content-Type: application/json
X-OJS-Signature: sha256=...
X-OJS-Delivery-ID: del_01234567-89ab-7cde-8000-000000000001
X-OJS-Job-ID: 01234567-89ab-7cde-8000-000000000001

{
  "job": {
    "specversion": "1.0",
    "id": "01234567-89ab-7cde-8000-000000000001",
    "type": "email.send",
    "queue": "default",
    "args": [{"to": "user@example.com"}],
    "attempt": 1
  },
  "worker_id": "push_worker_01234567",
  "delivery_id": "del_01234567-89ab-7cde-8000-000000000001"
}
```

### 2.3 Push Delivery Response

The function MUST respond with a JSON body indicating success or failure:

**Success (ACK):**
```json
{
  "status": "completed",
  "result": {"message_id": "msg_123"}
}
```

**Failure (NACK):**
```json
{
  "status": "failed",
  "error": {
    "code": "handler_error",
    "message": "SMTP connection refused",
    "retryable": true
  }
}
```

**Status codes:**
- `200` with `"status": "completed"` → ACK (job completed)
- `200` with `"status": "failed"` → NACK (job failed, may retry)
- `4xx` → NACK with `retryable: false`
- `5xx` → NACK with `retryable: true`
- Timeout → NACK with `retryable: true`

---

## 3. AWS Lambda Integration

### 3.1 SQS Event Source Mapping

The recommended pattern for AWS Lambda is SQS event source mapping, which provides native integration without custom push delivery:

```
OJS Backend (SQS) → SQS Queue → Lambda (event source mapping) → ACK/NACK callback
```

### 3.2 Lambda Handler Wrapper

The OJS SDK provides a Lambda handler wrapper that maps the SQS event to an OJS JobContext:

```go
package main

import (
    "context"
    "github.com/aws/aws-lambda-go/lambda"
    "github.com/openjobspec/ojs-go-sdk/serverless"
)

func main() {
    handler := serverless.NewLambdaHandler(
        serverless.WithOJSURL("https://ojs.example.com"),
    )

    handler.Register("email.send", func(ctx context.Context, job serverless.Job) error {
        // Process the job
        return nil
    })

    lambda.Start(handler.HandleSQS)
}
```

### 3.3 SAM Template

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  OJSWorkerFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: bootstrap
      Runtime: provided.al2023
      MemorySize: 256
      Timeout: 30
      Events:
        OJSQueue:
          Type: SQS
          Properties:
            Queue: !GetAtt OJSQueue.Arn
            BatchSize: 10
            MaximumBatchingWindowInSeconds: 5
      Environment:
        Variables:
          OJS_URL: !Ref OJSServerURL

  OJSQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: ojs-default
      VisibilityTimeout: 60
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt OJSDeadLetterQueue.Arn
        maxReceiveCount: 3

  OJSDeadLetterQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: ojs-default-dlq
```

---

## 4. Serverless Meta Fields

Jobs targeting serverless workers MAY include resource hints in the `meta` field:

```json
{
  "type": "ml.inference",
  "args": [{"model": "gpt-4"}],
  "meta": {
    "serverless": {
      "memory_mb": 1024,
      "timeout_s": 300,
      "runtime": "provided.al2023",
      "function_arn": "arn:aws:lambda:us-east-1:123456789012:function:ojs-worker"
    }
  }
}
```

These fields are advisory — the backend MAY use them for routing or ignore them.

---

## 5. Conformance Requirements

### 5.1 Push Delivery (Optional)

An OJS backend that implements push delivery:

1. MUST sign all push requests using HMAC-SHA256 (as per ojs-webhooks.md).
2. MUST set the job state to `active` before invoking the push endpoint.
3. MUST respect the configured timeout and NACK on timeout.
4. MUST NOT deliver the same job to multiple push endpoints simultaneously.
5. SHOULD implement exponential backoff for push delivery retries.
6. SHOULD respect `max_concurrency` limits per push endpoint.

### 5.2 SQS Lambda Integration

An OJS SQS backend that supports Lambda integration:

1. MUST use SQS event source mapping for job delivery.
2. MUST ACK/NACK jobs based on Lambda invocation result.
3. SHOULD use batch processing for efficiency.
4. MAY support FIFO queues for ordered processing.

---

## 6. Prior Art

| System | Serverless Support |
|--------|-------------------|
| **Inngest** | Native serverless-first (push delivery, step functions) |
| **Temporal** | Cloud-hosted workers, no native Lambda |
| **AWS Step Functions** | Native Lambda integration, but proprietary |
| **BullMQ** | No native serverless support |
| **Celery** | No native serverless support |

OJS differentiates by providing a standard push delivery protocol that works across cloud providers, not just AWS.
