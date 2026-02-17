# RFC-0007: Serverless Runtime Adapters

- **Stage**: 0 (Strawman)
- **Champion**: TBD
- **Created**: 2025-07-25
- **Last Updated**: 2025-07-25
- **Target Spec Version**: 0.3.0

## Summary

This RFC proposes a standardized adapter interface for executing OJS jobs on serverless runtimes including AWS Lambda, CloudFlare Workers, Vercel Edge Functions, Google Cloud Functions, and Azure Functions. It defines the execution model, state management patterns, cold start handling, timeout semantics, and a portable configuration format so that OJS workers can run on any supported serverless platform without code changes.

## Motivation

Serverless functions are the dominant deployment model for event-driven workloads. Many teams want to process OJS jobs using serverless functions to benefit from automatic scaling, pay-per-use pricing, and zero infrastructure management. However, the OJS worker model assumes long-running processes:

1. **Poll-based fetching is incompatible**: OJS workers poll the backend for new jobs. Serverless functions are triggered by events, not polling loops. A Lambda function cannot run a persistent poll loop without wasteful idle charges.

2. **Graceful shutdown semantics differ**: OJS workers handle `SIGTERM` to drain in-flight jobs. Serverless runtimes use platform-specific shutdown signals with tight timeout windows (e.g., Lambda gives 500ms for cleanup after timeout).

3. **Cold start impacts**: Loading large handler codebases, initializing database connections, and registering middleware on every invocation is wasteful. OJS provides no guidance on what to initialize once (outside the handler) versus per-invocation.

4. **No concurrency model**: OJS workers control concurrency by limiting parallel fetches. Serverless platforms control concurrency externally (reserved concurrency, max instances). The interaction between these two concurrency models is undefined.

5. **State management**: OJS workers maintain in-memory state (middleware chains, connection pools, configuration). Serverless functions are ephemeral. There is no pattern for managing stateful resources across invocations.

The v0.3 roadmap identifies "Serverless adapters — AWS Lambda, CloudFlare Workers, Vercel Edge Functions" as a future direction. This RFC defines a portable adapter interface that works across platforms.

### Use Cases

1. **Event-driven processing**: An e-commerce platform processes order fulfillment jobs on AWS Lambda. Jobs are triggered by an SQS queue fronting the OJS backend. Lambda scales automatically from 0 to 1000 concurrent executions during peak hours.

2. **Edge computing**: A content delivery service runs image optimization jobs on CloudFlare Workers. Jobs are executed at the edge location closest to the user, reducing latency for real-time image transformations.

3. **Cost optimization**: A startup processes background jobs on Google Cloud Functions with pay-per-invocation pricing. During off-hours, they pay nothing. During spikes, they scale to thousands of concurrent executions without provisioning servers.

4. **Hybrid deployment**: A company runs latency-sensitive inference jobs on dedicated GPU workers and low-priority email jobs on AWS Lambda. Both worker types consume from the same OJS backend.

## Prior Art

### Sidekiq (Ruby)

Sidekiq has no official serverless adapter. Community solutions like `sidekiq-aws-lambda` exist but are not widely adopted. They typically wrap the Sidekiq processor in a Lambda handler that processes a batch of jobs per invocation.

**Lesson**: Retrofitting a long-running worker model onto serverless is awkward. OJS should design the adapter interface from first principles.

### BullMQ (TypeScript)

BullMQ supports a "sandboxed processor" that runs each job in a separate child process. This is conceptually similar to serverless execution (isolated, stateless). However, BullMQ does not support actual serverless runtimes.

**Lesson**: Process-level isolation is a useful intermediate step. The adapter should support both in-process and isolated execution models.

### Temporal (Go/TypeScript)

Temporal does not support serverless workers. Activities (the equivalent of job handlers) must run in long-running worker processes. The Temporal team has discussed serverless support but considers it architecturally challenging due to workflow history replay requirements.

**Lesson**: Stateful workflow execution is hard to serverless-ify. OJS's stateless job handlers (each job is independent) are a better fit for serverless.

### AWS Lambda Event Source Mappings

Lambda supports event source mappings for SQS, Kinesis, and DynamoDB Streams. The mapping polls the source and invokes Lambda with batches of records. Lambda manages concurrency, retries, and dead-letter routing.

**Lesson**: Event source mappings are the proven pattern for connecting job queues to serverless functions. OJS should define a similar integration pattern.

### CloudFlare Queues

CloudFlare Queues natively integrate with Workers. A queue consumer is defined as a `queue()` handler in the Worker. Messages are delivered in batches with configurable batch size and wait time.

**Lesson**: Platform-native queue integration is the smoothest developer experience. OJS adapters should feel native to each platform.

## Detailed Design

### 1. Adapter Architecture

```
                    ┌─────────────────────────┐
                    │      OJS Backend         │
                    │  (Redis / Postgres)      │
                    └──────────┬──────────────┘
                               │
                    ┌──────────┴──────────────┐
                    │     Trigger Bridge       │
                    │  (per-platform adapter)  │
                    │                          │
                    │  - Polls OJS backend     │
                    │  - Maps jobs to events   │
                    │  - Handles ack/nack      │
                    └──────────┬──────────────┘
                               │
         ┌─────────────────────┼────────────────────┐
         │                     │                     │
   ┌─────┴─────┐       ┌──────┴──────┐      ┌──────┴──────┐
   │ AWS Lambda │       │ CloudFlare  │      │   Vercel    │
   │  Handler   │       │   Worker    │      │    Edge     │
   └───────────┘       └─────────────┘      └─────────────┘
```

The adapter has two components:

1. **Trigger Bridge**: A lightweight process (or platform-native integration) that fetches jobs from the OJS backend and delivers them to serverless functions. The bridge handles polling, batching, and ack/nack lifecycle.

2. **Runtime Adapter**: A language-specific library that wraps the serverless function handler, providing the OJS handler interface (`(ctx, job) => result`) and managing per-invocation setup.

### 2. Execution Model

#### Invocation Lifecycle

```
Platform Event
    │
    ├─1. Cold Start (first invocation only)
    │   ├── Load handler module
    │   ├── Initialize middleware chain
    │   └── Establish connection pool (if warm)
    │
    ├─2. Handler Invocation
    │   ├── Parse job from event payload
    │   ├── Execute middleware chain
    │   ├── Execute job handler
    │   └── Return result or error
    │
    ├─3. Response
    │   ├── Success → Trigger bridge sends ACK
    │   ├── Failure → Trigger bridge sends NACK
    │   └── Timeout → Platform kills function → Bridge detects timeout → NACK
    │
    └─4. Warm Instance (reused for next invocation)
        └── Connection pools, cached config preserved
```

#### Cold Start Optimization

The adapter MUST separate initialization code from per-invocation code:

```typescript
// TypeScript — AWS Lambda adapter
import { createLambdaAdapter } from "@ojs/lambda-adapter";

// Runs ONCE on cold start (outside handler)
const adapter = createLambdaAdapter({
  handlers: {
    "email.send": async (ctx, job) => {
      await sendEmail(job.args[0], job.args[1]);
    },
    "report.generate": async (ctx, job) => {
      await generateReport(job.args[0]);
    },
  },
  middleware: [loggingMiddleware, metricsMiddleware],
});

// Runs PER INVOCATION
export const handler = adapter.handler;
```

```python
# Python — AWS Lambda adapter
from ojs.adapters.lambda_adapter import create_lambda_adapter

# Runs ONCE on cold start
adapter = create_lambda_adapter(
    handlers={
        "email.send": lambda ctx, job: send_email(job.args[0], job.args[1]),
        "report.generate": lambda ctx, job: generate_report(job.args[0]),
    },
    middleware=[logging_middleware, metrics_middleware],
)

# Runs PER INVOCATION
def handler(event, context):
    return adapter.handle(event, context)
```

```go
// Go — AWS Lambda adapter
package main

import (
    "github.com/openjobspec/ojs-go-sdk/adapters/lambda"
)

// Runs ONCE on cold start
var adapter = lambda.NewAdapter(lambda.Config{
    Handlers: map[string]ojs.HandlerFunc{
        "email.send":       emailSendHandler,
        "report.generate":  reportGenerateHandler,
    },
    Middleware: []ojs.Middleware{loggingMiddleware, metricsMiddleware},
})

// Runs PER INVOCATION
func main() {
    lambda.Start(adapter.Handler)
}
```

### 3. Platform-Specific Trigger Bridges

#### AWS Lambda + SQS

The recommended integration uses SQS as the trigger bridge:

```
OJS Backend → Trigger Bridge (polls OJS, pushes to SQS) → SQS → Lambda
```

Configuration:

```json
{
  "adapter": "aws-lambda",
  "trigger": "sqs",
  "config": {
    "ojs_url": "https://ojs.example.com",
    "sqs_queue_url": "https://sqs.us-east-1.amazonaws.com/123456789/ojs-jobs",
    "batch_size": 10,
    "visibility_timeout_seconds": 300,
    "poll_interval_seconds": 1,
    "queues": ["email", "notifications"],
    "concurrency": 100
  }
}
```

Lambda event source mapping:

```yaml
# serverless.yml / SAM template
functions:
  ojsWorker:
    handler: handler.handler
    events:
      - sqs:
          arn: !GetAtt OjsJobQueue.Arn
          batchSize: 10
          maximumBatchingWindow: 5
```

#### CloudFlare Workers + Queues

CloudFlare Workers natively support queue consumers:

```typescript
// CloudFlare Worker adapter
import { createWorkersAdapter } from "@ojs/cloudflare-adapter";

const adapter = createWorkersAdapter({
  handlers: {
    "image.optimize": async (ctx, job) => {
      // Runs at the edge
      return await optimizeImage(job.args[0]);
    },
  },
});

export default {
  async queue(batch: MessageBatch, env: Env): Promise<void> {
    await adapter.processBatch(batch, env);
  },
};
```

#### Vercel Edge Functions

```typescript
// Vercel Edge Function adapter
import { createVercelAdapter } from "@ojs/vercel-adapter";

const adapter = createVercelAdapter({
  handlers: {
    "og.generate": async (ctx, job) => {
      return await generateOgImage(job.args[0]);
    },
  },
});

// Edge function invoked via Vercel Cron or webhook
export default adapter.handler;
export const config = { runtime: "edge" };
```

### 4. Timeout Handling

Serverless runtimes impose execution time limits. The adapter MUST handle timeouts gracefully:

| Platform | Max Timeout | Default Timeout | OJS Behavior |
|----------|-------------|-----------------|--------------|
| AWS Lambda | 15 minutes | 3 seconds | NACK with `timeout` reason |
| CloudFlare Workers | 30 seconds (standard), 15 minutes (Cron) | 30 seconds | NACK with `timeout` reason |
| Vercel Edge | 25 seconds (hobby), 300 seconds (pro) | 10 seconds | NACK with `timeout` reason |
| Google Cloud Functions | 9 minutes (1st gen), 60 minutes (2nd gen) | 60 seconds | NACK with `timeout` reason |
| Azure Functions | 10 minutes (consumption), unlimited (premium) | 5 minutes | NACK with `timeout` reason |

The adapter MUST set a safety margin (default: 5 seconds before platform timeout) to allow for cleanup:

```
Platform timeout: 300s
Safety margin:      5s
Effective timeout: 295s

At t=295s: Adapter cancels handler context
At t=295s-300s: Adapter sends NACK to OJS backend
At t=300s: Platform kills function
```

### 5. State Management

#### Connection Pooling

Serverless functions reuse warm instances. The adapter SHOULD maintain connection pools across invocations:

```typescript
// Connection pool survives across warm invocations
const adapter = createLambdaAdapter({
  ojsUrl: "https://ojs.example.com",
  connectionPool: {
    maxConnections: 5,
    idleTimeoutMs: 60_000,
  },
});
```

#### Configuration Caching

The adapter SHOULD cache configuration (handler registry, middleware chain) at the module level to avoid re-initialization on warm starts.

#### No Persistent State

Adapters MUST NOT rely on persistent local state between invocations. *Rationale: Serverless platforms may route subsequent invocations to different instances, and warm instances may be recycled at any time.*

### 6. Concurrency Model

| Concern | Long-Running Worker | Serverless Adapter |
|---------|--------------------|--------------------|
| Concurrency control | SDK-side (`concurrency` config) | Platform-side (reserved concurrency) |
| Scaling | Manual (add workers) | Automatic (platform scales instances) |
| Batch processing | Fetch N jobs at once | Platform delivers batch |
| Backpressure | Stop polling | Platform throttles invocations |

The adapter MUST delegate concurrency control to the platform. *Rationale: Serverless platforms have sophisticated concurrency management that is more efficient than SDK-side control.*

### 7. Adapter Configuration Format

A portable configuration format enables platform switching:

```json
{
  "ojs": {
    "url": "https://ojs.example.com",
    "queues": ["email", "notifications", "reports"],
    "auth": {
      "type": "bearer",
      "token_env": "OJS_API_TOKEN"
    }
  },
  "adapter": {
    "platform": "aws-lambda",
    "timeout_safety_margin_seconds": 5,
    "batch_size": 10,
    "retry_on_timeout": true
  },
  "handlers": {
    "email.send": "./handlers/email.js",
    "report.generate": "./handlers/report.js"
  }
}
```

## Examples

### AWS Lambda: Complete Email Processing Setup

```typescript
// handler.ts
import { createLambdaAdapter } from "@ojs/lambda-adapter";
import { SESClient, SendEmailCommand } from "@aws-sdk/client-ses";

const ses = new SESClient({ region: "us-east-1" });

const adapter = createLambdaAdapter({
  ojsUrl: process.env.OJS_URL!,
  handlers: {
    "email.send": async (ctx, job) => {
      const [to, subject, body] = job.args as [string, string, string];
      await ses.send(new SendEmailCommand({
        Source: "noreply@example.com",
        Destination: { ToAddresses: [to] },
        Message: {
          Subject: { Data: subject },
          Body: { Text: { Data: body } },
        },
      }));
    },
  },
  middleware: [
    async (ctx, job, next) => {
      const start = Date.now();
      await next(ctx, job);
      console.log(`Job ${job.id} completed in ${Date.now() - start}ms`);
    },
  ],
});

export const handler = adapter.handler;
```

### CloudFlare Workers: Edge Image Processing

```typescript
// worker.ts
import { createWorkersAdapter } from "@ojs/cloudflare-adapter";

const adapter = createWorkersAdapter({
  handlers: {
    "image.resize": async (ctx, job) => {
      const [imageUrl, width, height] = job.args as [string, number, number];
      const response = await fetch(imageUrl);
      const image = await response.arrayBuffer();
      // Use CloudFlare Image Resizing
      return { resized: true, width, height };
    },
  },
});

export default {
  async queue(batch: MessageBatch, env: Env) {
    await adapter.processBatch(batch, env);
  },
};
```

### Go: Google Cloud Functions

```go
package function

import (
    "context"
    "github.com/openjobspec/ojs-go-sdk/adapters/gcf"
)

var adapter = gcf.NewAdapter(gcf.Config{
    OJSURL: os.Getenv("OJS_URL"),
    Handlers: map[string]ojs.HandlerFunc{
        "data.transform": func(ctx context.Context, job ojs.Job) error {
            // Process data transformation
            return nil
        },
    },
})

func ProcessJob(ctx context.Context, e gcf.Event) error {
    return adapter.Handle(ctx, e)
}
```

## Conformance Impact

Serverless adapters are an OPTIONAL extension. They do not affect conformance levels 0–4.

New requirements introduced:

- **MUST**: Adapters MUST send NACK to the OJS backend when a function execution times out. *Rationale: Unacknowledged jobs would remain in `active` state until the heartbeat timeout, delaying retry.*
- **MUST**: Adapters MUST separate cold-start initialization from per-invocation handler code. *Rationale: Re-initializing on every invocation wastes compute and increases latency.*
- **MUST**: Adapters MUST NOT rely on persistent local state between invocations. *Rationale: Serverless instances are ephemeral; state assumptions lead to data loss.*
- **SHOULD**: Adapters SHOULD maintain connection pools across warm invocations. *Rationale: TCP/TLS handshake overhead is significant for short-lived functions.*
- **SHOULD**: Adapters SHOULD implement a timeout safety margin of at least 5 seconds. *Rationale: The safety margin allows the adapter to cleanly NACK before the platform kills the function.*
- **MAY**: Adapters MAY support batch processing (multiple jobs per invocation). *Rationale: Batch invocation reduces per-job overhead and is supported by most platforms.*

## Backward Compatibility

This proposal is fully backward compatible. Serverless adapters are new packages in each SDK. They consume from the same OJS backend APIs as long-running workers. No changes to the backend, wire format, or existing SDK interfaces are required. Jobs enqueued by any client are consumable by both long-running workers and serverless adapters.

## Implementation Requirements

Per the OJS RFC process, proposals at Stage 2+ MUST include working prototypes in at least two languages:

- [ ] TypeScript: AWS Lambda adapter in `ojs-js-sdk/src/adapters/lambda/`
- [ ] Go: AWS Lambda adapter in `ojs-go-sdk/adapters/lambda/`
- [ ] TypeScript: CloudFlare Workers adapter in `ojs-js-sdk/src/adapters/cloudflare/`

## Alternatives Considered

### Direct HTTP Invocation (No Trigger Bridge)

Having the OJS backend directly invoke serverless functions via HTTP was considered. This was rejected because:

- It requires the backend to know about serverless platform APIs (Lambda InvokeFunction, etc.)
- It couples the backend to specific cloud providers
- It bypasses platform-native scaling and retry mechanisms

### WebSocket-Based Worker in Serverless

Running a WebSocket-based OJS worker inside a serverless function was considered. This was rejected because:

- Most serverless platforms do not support persistent WebSocket connections in functions
- WebSocket connections consume resources even when idle, defeating pay-per-use benefits
- The event-driven trigger model is a better fit for serverless

### Generic Webhook Adapter

A single webhook adapter that works with any serverless platform was considered. This was rejected because:

- Each platform has different event formats, timeout semantics, and scaling behavior
- Platform-specific adapters can optimize for each runtime (e.g., CloudFlare KV for state, Lambda Layers for dependencies)
- A generic adapter would be the lowest common denominator, missing platform-specific optimizations

### OJS Backend as Serverless Function

Running the OJS backend itself as a serverless function was considered. This was rejected because:

- Backends require persistent state (Redis/Postgres connections) that is incompatible with ephemeral execution
- Backends need to run background processes (job scheduling, heartbeat monitoring) that cannot run in request-scoped functions
- This RFC focuses on the worker side, where serverless is a natural fit

## Open Questions

1. **Trigger bridge deployment**: Should the trigger bridge be a standalone binary, a cloud-native integration (e.g., EventBridge Pipe), or embedded in the OJS backend? Each has different operational trade-offs.

2. **Multi-platform testing**: How should the conformance suite test serverless adapters? Local emulators (SAM local, Miniflare) can simulate platforms but may miss production-specific behavior.

3. **Cost modeling**: Should the adapter expose cost estimation based on invocation count and duration? This would help operators compare serverless vs. long-running worker costs.

4. **Partial batch failure**: When processing a batch of jobs, what happens if some succeed and others fail? Should the adapter ack/nack individually, or fail the entire batch? Platform behavior varies (Lambda supports partial batch failure reporting).

5. **Platform abstraction depth**: How much should the adapter abstract platform differences? Too much abstraction hides platform-specific features; too little creates a leaky abstraction.
