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

### 3.4 Cold Start Considerations

Serverless functions experience cold starts when a new execution environment is initialized. This latency has direct implications for job delivery timeouts and reliability.

1. Backends SHOULD track cold-start vs warm-start execution times separately.

   *Rationale:* Distinguishing cold-start latency from handler execution time allows operators to set accurate timeout thresholds and identify performance regressions in handler code vs infrastructure initialization.

2. Push delivery timeouts SHOULD account for cold-start latency. The RECOMMENDED approach is to add 10 seconds to the configured timeout for the first invocation of a function instance.

   *Rationale:* Lambda cold starts can add 1–10s of latency depending on runtime, package size, and VPC configuration. Premature timeouts during cold starts cause false NACK responses, leading to unnecessary retries and duplicated work.

3. SDKs SHOULD support connection pool pre-warming in the function init phase.

   *Rationale:* Establishing HTTP connections to the OJS server during the init phase (outside the billed execution window on most providers) reduces first-request latency and avoids timeout pressure during actual job processing.

4. Backends MAY include a `cold_start` boolean field in push delivery observability metadata:

   ```json
   {
     "delivery_id": "del_01234567-89ab-7cde-8000-000000000001",
     "cold_start": true,
     "init_duration_ms": 2340,
     "handler_duration_ms": 150
   }
   ```

5. When a push delivery times out and the backend suspects a cold start (e.g., first invocation or invocation after idle period), the backend SHOULD extend the job's visibility timeout before NACKing, rather than immediately releasing the job for redelivery.

   *Rationale:* The function may still be executing after a cold-start-induced timeout. Immediately releasing the job risks duplicate processing if the original invocation eventually completes.

---

## 4. Google Cloud Functions Integration

### 4.1 Pub/Sub Event Source

The recommended pattern for Google Cloud Functions uses Pub/Sub as the event source, providing native integration with automatic scaling and at-least-once delivery:

```
OJS Backend → Cloud Pub/Sub Topic → Cloud Function (event trigger) → ACK/NACK callback
```

The OJS backend publishes job payloads to a Pub/Sub topic. A Cloud Function subscribed to the topic receives each job as a CloudEvent. After processing, the function calls back to the OJS server to ACK or NACK the job.

**Requirements:**

1. The backend MUST publish the full OJS job envelope as the Pub/Sub message data, JSON-encoded.
2. The backend MUST include the `X-OJS-Job-ID` and `X-OJS-Delivery-ID` as Pub/Sub message attributes.
3. The Pub/Sub subscription SHOULD use the `exactly_once_delivery` option when available.
4. The acknowledgement deadline SHOULD be set to at least the function's configured timeout plus 10 seconds (to account for cold starts).

   *Rationale:* If the Pub/Sub acknowledgement deadline is shorter than the function execution time, Pub/Sub will redeliver the message while the function is still processing, causing duplicate invocations.

### 4.2 Cloud Function Handler Wrapper

The OJS SDK provides a Cloud Function handler wrapper that maps the Pub/Sub CloudEvent to an OJS JobContext:

```go
package handler

import (
    "context"
    "fmt"

    "github.com/GoogleCloudPlatform/functions-framework-go/functions"
    "github.com/openjobspec/ojs-go-sdk/serverless"
)

func init() {
    handler := serverless.NewGCPHandler(
        serverless.WithOJSURL("https://ojs.example.com"),
    )

    handler.Register("email.send", processEmail)
    handler.Register("report.generate", generateReport)

    functions.CloudEvent("OJSWorker", handler.HandleCloudEvent)
}

func processEmail(ctx context.Context, job serverless.Job) error {
    to := job.Args[0]["to"].(string)
    fmt.Printf("Sending email to %s\n", to)
    // Process the job
    return nil
}

func generateReport(ctx context.Context, job serverless.Job) error {
    // Process the job
    return nil
}
```

**Handler wrapper responsibilities:**

1. The handler wrapper MUST deserialize the CloudEvent data into an OJS job envelope.
2. The handler wrapper MUST call the registered handler function based on the job type.
3. On handler success, the wrapper MUST send an ACK callback to the OJS server (`POST /jobs/{id}/ack`).
4. On handler error, the wrapper MUST send a NACK callback with the error details.
5. The handler wrapper SHOULD set up connection pooling during the `init()` phase.

### 4.3 Deployment (gcloud CLI)

**Command-line deployment:**

```bash
gcloud functions deploy ojs-worker \
  --gen2 \
  --runtime=go122 \
  --region=us-central1 \
  --source=. \
  --entry-point=OJSWorker \
  --trigger-topic=ojs-default \
  --memory=256Mi \
  --timeout=60s \
  --set-env-vars=OJS_URL=https://ojs.example.com \
  --min-instances=1 \
  --max-instances=100
```

> Setting `--min-instances=1` keeps at least one warm instance to reduce cold-start latency for the first job after an idle period.

**YAML configuration (`function.yaml`):**

```yaml
apiVersion: cloud.google.com/v1
kind: Function
metadata:
  name: ojs-worker
spec:
  generation: 2nd
  runtime: go122
  entryPoint: OJSWorker
  region: us-central1
  memory: 256Mi
  timeout: 60s
  minInstances: 1
  maxInstances: 100
  trigger:
    eventType: google.cloud.pubsub.topic.v1.messagePublished
    resource: projects/my-project/topics/ojs-default
  environmentVariables:
    OJS_URL: https://ojs.example.com
```

---

## 5. Azure Functions Integration

### 5.1 Service Bus Event Source

The recommended pattern for Azure Functions uses Azure Service Bus as the event source:

```
OJS Backend → Azure Service Bus Queue → Azure Function (trigger) → ACK/NACK callback
```

The OJS backend enqueues job payloads to a Service Bus queue. An Azure Function with a Service Bus trigger receives each job message. After processing, the function calls back to the OJS server to ACK or NACK the job.

**Requirements:**

1. The backend MUST publish the full OJS job envelope as the Service Bus message body, JSON-encoded.
2. The backend MUST set `X-OJS-Job-ID` and `X-OJS-Delivery-ID` as Service Bus application properties.
3. The Service Bus queue SHOULD use sessions when ordered processing is required (equivalent to FIFO).
4. The lock duration SHOULD be set to at least the function's configured timeout plus 15 seconds.

   *Rationale:* Azure Service Bus message locks have a maximum duration of 5 minutes. For longer-running jobs, the function MUST renew the lock periodically. The extra 15 seconds accounts for cold starts and lock renewal overhead.

5. The backend SHOULD use the `dead_letter_queue` option for messages that exceed the maximum delivery count.

### 5.2 Azure Function Handler

The OJS SDK provides an Azure Function handler for C# that maps the Service Bus message to an OJS job:

```csharp
using Microsoft.Azure.Functions.Worker;
using Microsoft.Extensions.Logging;
using Azure.Messaging.ServiceBus;
using OpenJobSpec.Serverless;

public class OJSWorkerFunction
{
    private readonly ILogger<OJSWorkerFunction> _logger;
    private readonly OJSServerlessHandler _handler;

    public OJSWorkerFunction(ILogger<OJSWorkerFunction> logger)
    {
        _logger = logger;
        _handler = new OJSServerlessHandler(
            Environment.GetEnvironmentVariable("OJS_URL")
        );
    }

    [Function("OJSWorker")]
    public async Task Run(
        [ServiceBusTrigger("ojs-default", Connection = "ServiceBusConnection")]
        ServiceBusReceivedMessage message,
        FunctionContext context)
    {
        await _handler.ProcessAsync(message, async (job) =>
        {
            _logger.LogInformation("Processing job {JobId} of type {JobType}",
                job.Id, job.Type);

            switch (job.Type)
            {
                case "email.send":
                    await SendEmailAsync(job);
                    break;
                case "report.generate":
                    await GenerateReportAsync(job);
                    break;
                default:
                    throw new InvalidOperationException(
                        $"Unknown job type: {job.Type}");
            }
        });
    }

    private async Task SendEmailAsync(OJSJob job) { /* ... */ }
    private async Task GenerateReportAsync(OJSJob job) { /* ... */ }
}
```

**Handler wrapper responsibilities:**

1. The handler wrapper MUST deserialize the Service Bus message body into an OJS job envelope.
2. On handler success, the wrapper MUST send an ACK callback to the OJS server.
3. On handler error, the wrapper MUST send a NACK callback and allow Service Bus to handle retries (via message abandonment).
4. The handler wrapper SHOULD read delivery metadata from Service Bus application properties.

### 5.3 Bicep Template

```bicep
param location string = resourceGroup().location
param ojsUrl string

resource serviceBusNamespace 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: 'ojs-servicebus'
  location: location
  sku: {
    name: 'Standard'
  }
}

resource ojsQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'ojs-default'
  properties: {
    lockDuration: 'PT1M'
    maxDeliveryCount: 5
    deadLetteringOnMessageExpiration: true
    defaultMessageTimeToLive: 'P1D'
  }
}

resource ojsDeadLetterQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'ojs-default-dlq'
  properties: {
    maxDeliveryCount: 1
    defaultMessageTimeToLive: 'P7D'
  }
}

resource hostingPlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: 'ojs-worker-plan'
  location: location
  sku: {
    name: 'Y1'
    tier: 'Dynamic'
  }
}

resource functionApp 'Microsoft.Web/sites@2023-01-01' = {
  name: 'ojs-worker-func'
  location: location
  kind: 'functionapp'
  properties: {
    serverFarmId: hostingPlan.id
    siteConfig: {
      appSettings: [
        {
          name: 'OJS_URL'
          value: ojsUrl
        }
        {
          name: 'ServiceBusConnection'
          value: serviceBusNamespace.listKeys().primaryConnectionString
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'dotnet-isolated'
        }
      ]
    }
  }
}
```

---

## 6. Serverless Meta Fields

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

Backends that support multi-cloud deployment (see Section 9) MAY additionally accept cloud-specific resource hints:

```json
{
  "type": "image.resize",
  "args": [{"url": "https://example.com/photo.jpg", "width": 800}],
  "meta": {
    "serverless": {
      "memory_mb": 512,
      "timeout_s": 60,
      "provider": "gcp",
      "gcp": {
        "region": "us-central1",
        "function_name": "ojs-image-worker"
      }
    }
  }
}
```

---

## 7. Error Handling

Serverless environments introduce failure modes that differ from traditional long-running workers. This section defines how backends MUST classify and respond to these failures.

### 7.1 Error Classification Matrix

| Scenario | HTTP Status | OJS Action | Retryable |
|----------|-------------|------------|-----------|
| Function completes successfully | 200 | ACK | N/A |
| Function returns error | 200 (`status: "failed"`) | NACK | Per `retryable` field |
| Function timeout | N/A | NACK | Yes |
| Function cold-start timeout | N/A | NACK + extend visibility | Yes |
| Function crashes (OOM, stack overflow) | 5xx | NACK | Yes |
| Function not found (deleted/misconfigured) | 404 | NACK | No (disable endpoint) |
| Rate limited by cloud provider | 429 | NACK + backoff | Yes |
| Network error to function endpoint | N/A | NACK | Yes |
| Invalid response from function | N/A | NACK | Yes |
| Authentication failure | 401/403 | NACK | No (alert) |

### 7.2 Error Handling Requirements

1. Backends MUST distinguish between **function errors** (errors returned by the handler code) and **delivery errors** (errors in the transport layer between the backend and the function).

   *Rationale:* Function errors indicate a problem with the job or handler logic, while delivery errors indicate infrastructure issues. Different retry strategies are appropriate for each category.

2. Backends MUST NOT retry when receiving HTTP 404 (function not found). The backend SHOULD disable the push endpoint and emit an alert or event.

   *Rationale:* A 404 indicates the function has been deleted or misconfigured. Retrying will never succeed and wastes resources. Operators must be notified to reconfigure the endpoint.

3. Backends MUST NOT retry when receiving HTTP 401 or 403 (authentication/authorization failure). The backend SHOULD disable the push endpoint and emit an alert.

   *Rationale:* Authentication failures indicate credential rotation or permission changes. Retrying with the same credentials will never succeed.

4. When receiving HTTP 429 (rate limited), backends MUST implement backoff. The backend SHOULD respect the `Retry-After` header if present. If no `Retry-After` header is provided, the RECOMMENDED initial backoff is 1 second with exponential increase up to 60 seconds.

   *Rationale:* Cloud providers enforce rate limits to protect shared infrastructure. Ignoring rate limit signals can lead to extended throttling or account-level restrictions.

5. Backends SHOULD implement a **circuit breaker pattern**: after N consecutive delivery failures to the same endpoint (RECOMMENDED: 5), the backend SHOULD temporarily disable push delivery for that endpoint and fall back to pull mode.

   *Rationale:* Serverless functions can be deleted, misconfigured, or rate-limited by the cloud provider. Without proper error classification, the backend may waste resources retrying unrecoverable failures. The circuit breaker prevents cascade failures and allows time for operators to resolve the issue.

6. The circuit breaker SHOULD automatically attempt to re-enable push delivery after a cooldown period (RECOMMENDED: 60 seconds), using a half-open state that sends a single test delivery.

7. Backends SHOULD record error classification in delivery attempt metadata for observability:

   ```json
   {
     "delivery_id": "del_01234567-89ab-7cde-8000-000000000001",
     "attempt": 3,
     "error_class": "delivery_error",
     "error_type": "timeout",
     "retryable": true,
     "cold_start_suspected": true,
     "circuit_breaker_state": "closed"
   }
   ```

### 7.3 Dead Letter Handling

1. When a job exceeds the maximum number of delivery attempts, the backend MUST move the job to the `discarded` state.
2. Backends SHOULD publish a dead-letter event containing the job envelope, delivery history, and the final error.
3. Backends MAY support a dead-letter queue or topic for failed deliveries, separate from the primary job queue.

   *Rationale:* Dead-letter handling ensures that permanently failing jobs do not block the queue and provides operators with the information needed to diagnose and recover from failures.

---

## 8. Idempotency

Serverless functions may be invoked multiple times for the same job due to retry logic, at-least-once delivery guarantees, or timeout-induced redelivery. This section defines requirements for idempotent processing.

### 8.1 Delivery ID Requirements

1. Push delivery MUST include a unique `X-OJS-Delivery-ID` header (and corresponding `delivery_id` field in the request body) for every delivery attempt.

2. Each retry of the same job MUST generate a new `X-OJS-Delivery-ID`. The delivery ID identifies a specific delivery attempt, not the job itself.

   *Rationale:* A unique delivery ID per attempt enables functions to distinguish between retries and duplicate deliveries. Using the job ID alone is insufficient because the same job may be legitimately retried after a failure.

3. Functions SHOULD use the delivery ID as an idempotency key to prevent duplicate processing. The RECOMMENDED approach is to check a persistent store (e.g., database, cache) for the delivery ID before processing:

   ```go
   func handleJob(ctx context.Context, job serverless.Job) error {
       deliveryID := job.DeliveryID

       // Check if this delivery was already processed
       if alreadyProcessed(ctx, deliveryID) {
           return nil // Idempotent: skip duplicate
       }

       // Process the job
       err := process(ctx, job)
       if err != nil {
           return err
       }

       // Mark delivery as processed
       markProcessed(ctx, deliveryID)
       return nil
   }
   ```

### 8.2 Late Response Handling

1. Backends MUST NOT consider a timed-out delivery as permanently failed if a late ACK response arrives with the correct delivery ID. If the job is still in `active` state when the late ACK arrives, the backend MUST accept it.

   *Rationale:* Cloud functions may complete execution after the backend has timed out the delivery. If the backend has already NACKed and the job has been redelivered, the late ACK for the original delivery ID should be ignored (the job is now associated with a new delivery). But if the job is still active (e.g., waiting for retry), the late ACK should be honored.

2. Backends MUST ignore late NACK responses for delivery IDs that no longer correspond to the current active delivery of a job.

3. The RECOMMENDED approach for backends is to maintain a mapping of `delivery_id → job_id` with a TTL equal to twice the configured push delivery timeout.

### 8.3 Idempotency Window

1. Functions SHOULD maintain idempotency state for at least the duration of the job's maximum retry window (i.e., `max_attempts × timeout` plus backoff intervals).

2. Backends SHOULD include an `X-OJS-Idempotency-Window` header in push deliveries indicating the RECOMMENDED duration (in seconds) for which the function should retain the delivery ID.

   *Rationale:* This allows functions to size their idempotency stores appropriately and garbage-collect old delivery IDs.

---

## 9. Multi-Cloud Deployment

The push delivery model enables deploying OJS workers across multiple cloud providers simultaneously. This section defines patterns and routing rules for multi-cloud configurations.

### 9.1 Multi-Cloud Architecture

```
                    ┌──────────────────────┐
                    │     OJS Backend       │
                    │  (routing + dispatch) │
                    └──────┬───────┬───────┬┘
                           │       │       │
              ┌────────────┘       │       └────────────┐
              ▼                    ▼                     ▼
    ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
    │   AWS Lambda    │  │  GCP Cloud Fn   │  │  Azure Function │
    │  (email.send)   │  │ (image.resize)  │  │ (report.gen)    │
    └─────────────────┘  └─────────────────┘  └─────────────────┘
```

### 9.2 Routing Rules

1. Backends MAY route jobs to specific cloud providers based on job type, queue, or metadata.

2. Routing configuration SHOULD support the following strategies:

   - **Job-type routing**: Route specific job types to specific providers (e.g., `email.send → AWS Lambda`, `image.resize → GCP Cloud Functions`).
   - **Queue-based routing**: Route all jobs in a queue to a specific provider (e.g., `priority → AWS Lambda`, `batch → Azure Functions`).
   - **Metadata routing**: Route based on `meta.serverless.provider` field (see Section 6).
   - **Fallback routing**: Define a default provider when no specific rule matches.

3. Backends SHOULD support weighted routing for load distribution across providers:

   *Rationale:* Weighted routing enables gradual migration between providers, cost optimization (routing to the cheapest provider for non-latency-sensitive jobs), and resilience (distributing load to avoid single-provider outages).

### 9.3 Multi-Cloud Configuration Example

```json
{
  "push_endpoints": [
    {
      "id": "aws-email-worker",
      "provider": "aws_lambda",
      "endpoint": "arn:aws:lambda:us-east-1:123456789012:function:ojs-email",
      "job_types": ["email.send", "email.bulk"],
      "config": {
        "max_concurrency": 100,
        "timeout_ms": 30000,
        "signing_secret": "whsec_aws_..."
      }
    },
    {
      "id": "gcp-image-worker",
      "provider": "gcp_cloud_function",
      "endpoint": "https://us-central1-myproject.cloudfunctions.net/ojs-image",
      "job_types": ["image.resize", "image.thumbnail"],
      "config": {
        "max_concurrency": 50,
        "timeout_ms": 60000,
        "signing_secret": "whsec_gcp_..."
      }
    },
    {
      "id": "azure-report-worker",
      "provider": "azure_function",
      "endpoint": "https://ojs-worker-func.azurewebsites.net/api/OJSWorker",
      "job_types": ["report.generate", "report.export"],
      "config": {
        "max_concurrency": 25,
        "timeout_ms": 300000,
        "signing_secret": "whsec_azure_..."
      }
    }
  ],
  "routing": {
    "default_endpoint": "aws-email-worker",
    "rules": [
      {
        "match": {"job_type": "image.*"},
        "endpoint": "gcp-image-worker"
      },
      {
        "match": {"job_type": "report.*"},
        "endpoint": "azure-report-worker"
      },
      {
        "match": {"queue": "priority"},
        "endpoint": "aws-email-worker",
        "weight": 80
      },
      {
        "match": {"queue": "priority"},
        "endpoint": "gcp-image-worker",
        "weight": 20
      }
    ]
  }
}
```

### 9.4 Multi-Cloud Requirements

1. Backends that support multi-cloud routing MUST apply the same HMAC signing, timeout, and error handling rules to all providers uniformly.

2. Backends SHOULD maintain per-provider circuit breaker state (see Section 7). A circuit breaker trip on one provider MUST NOT affect delivery to other providers.

   *Rationale:* Provider-level isolation ensures that an outage or misconfiguration on one cloud provider does not cascade to the entire system.

3. Backends SHOULD emit per-provider observability metrics (delivery latency, error rate, circuit breaker state) to enable cost and performance comparison.

4. When a provider-specific endpoint is unavailable and no fallback is configured, the backend MUST fall back to pull mode for affected job types.

---

## 10. Conformance Requirements

### 10.1 Push Delivery (Optional)

An OJS backend that implements push delivery:

1. MUST sign all push requests using HMAC-SHA256 (as per ojs-webhooks.md).
2. MUST set the job state to `active` before invoking the push endpoint.
3. MUST respect the configured timeout and NACK on timeout.
4. MUST NOT deliver the same job to multiple push endpoints simultaneously.
5. SHOULD implement exponential backoff for push delivery retries.
6. SHOULD respect `max_concurrency` limits per push endpoint.
7. MUST include `X-OJS-Delivery-ID` header on all push deliveries (see Section 8).
8. MUST distinguish between function errors and delivery errors (see Section 7).
9. SHOULD implement circuit breaker pattern for endpoint health management (see Section 7).

### 10.2 SQS Lambda Integration

An OJS SQS backend that supports Lambda integration:

1. MUST use SQS event source mapping for job delivery.
2. MUST ACK/NACK jobs based on Lambda invocation result.
3. SHOULD use batch processing for efficiency.
4. MAY support FIFO queues for ordered processing.

### 10.3 Pub/Sub Cloud Functions Integration

An OJS backend that supports Google Cloud Functions integration:

1. MUST publish the full OJS job envelope as the Pub/Sub message data.
2. MUST include job ID and delivery ID as Pub/Sub message attributes.
3. SHOULD set the acknowledgement deadline to exceed the function timeout.
4. MAY support ordering keys for ordered processing within a partition.

### 10.4 Service Bus Azure Functions Integration

An OJS backend that supports Azure Functions integration:

1. MUST publish the full OJS job envelope as the Service Bus message body.
2. MUST set job ID and delivery ID as Service Bus application properties.
3. SHOULD configure lock duration to exceed the function timeout.
4. MAY support Service Bus sessions for ordered processing.

### 10.5 Multi-Cloud (Optional)

An OJS backend that supports multi-cloud push delivery:

1. MUST apply uniform signing and error handling across all providers.
2. MUST maintain per-provider circuit breaker state.
3. SHOULD support job-type and queue-based routing rules.
4. MAY support weighted routing for load distribution.

---

## 11. Prior Art

| System | Serverless Support |
|--------|-------------------|
| **Inngest** | Native serverless-first (push delivery, step functions) |
| **Temporal** | Cloud-hosted workers, no native Lambda |
| **AWS Step Functions** | Native Lambda integration, but proprietary |
| **Google Cloud Tasks** | Native Cloud Functions integration, but GCP-only |
| **Azure Durable Functions** | Native Azure Functions orchestration, but Azure-only |
| **BullMQ** | No native serverless support |
| **Celery** | No native serverless support |

OJS differentiates by providing a standard push delivery protocol that works across cloud providers, not just AWS. The multi-cloud routing model (Section 9) enables organizations to leverage the strengths of each provider — cost optimization, regional availability, runtime support — without vendor lock-in at the job processing layer.
