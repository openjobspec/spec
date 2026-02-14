# Open Job Spec: Framework Adapter Interface

> **⚠️ EXPERIMENTAL**: This extension is under active development. The specification
> may change in breaking ways between versions. Implementations and SDKs that adopt
> this extension should expect migration work when the spec evolves. Feedback is
> encouraged via the OJS RFC process.

| Field        | Value                                                    |
|-------------|----------------------------------------------------------|
| **Title**   | OJS Framework Adapter Specification                      |
| **Version** | 0.1.0                                                    |
| **Date**    | 2026-02-13                                               |
| **Status**  | Experimental                                             |
| **Tier**    | Experimental Extension                                   |
| **URI**     | `urn:ojs:ext:experimental:framework-adapters`            |
| **Requires**| OJS Core Specification (Layer 1)                         |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [The Transactional Enqueue Problem](#4-the-transactional-enqueue-problem)
5. [Adapter Interface](#5-adapter-interface)
6. [Transactional Enqueue](#6-transactional-enqueue)
   - 6.1 [Database-Backed Backends](#61-database-backed-backends)
   - 6.2 [External Backends (Outbox Pattern)](#62-external-backends-outbox-pattern)
7. [Framework Integration Patterns](#7-framework-integration-patterns)
   - 7.1 [Request Context](#71-request-context)
   - 7.2 [Dependency Injection](#72-dependency-injection)
   - 7.3 [Lifecycle Hooks](#73-lifecycle-hooks)
8. [Language-Specific Guidance](#8-language-specific-guidance)
9. [Conformance Requirements](#9-conformance-requirements)
10. [Prior Art](#10-prior-art)
11. [Examples](#11-examples)
12. [Resolved Design Decisions](#12-resolved-design-decisions)

---

## 1. Introduction

The single most impactful framework integration pattern is **transactional enqueue**: ensuring jobs are only enqueued if the database transaction that created them commits successfully. This eliminates an entire class of distributed systems bugs:

- **Orphaned jobs**: A job is enqueued, but the transaction that created the business data rolls back. The worker processes a job for data that doesn't exist.
- **Duplicate processing**: A job is enqueued, the transaction commits, but the enqueue confirmation is lost. The application retries, creating duplicate jobs.
- **Inconsistent state**: The database has committed but the job hasn't been enqueued yet (or vice versa), creating a window of inconsistency.

Systems with native transactional enqueue include Oban (inherent -- jobs are in the same Postgres database), Rails 7.2+ (`enqueue_after_transaction_commit`, default in Rails 8.2), and Laravel (`afterCommit()`). Systems requiring external patterns include Celery (manual `transaction.on_commit`), BullMQ (outbox pattern), and Sidekiq (recently added `transactional_push!`).

This specification defines a framework adapter interface that OJS SDKs MAY implement to integrate with web frameworks, providing transactional enqueue, request context propagation, and lifecycle management.

### 1.1 Scope

This specification defines:

- The adapter interface that frameworks implement.
- Transactional enqueue semantics for both database-backed and external backends.
- The transactional outbox pattern for external backends (Redis, SQS, Kafka).
- Framework integration patterns (request context, DI, lifecycle hooks).
- Language-specific guidance for common frameworks.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term                    | Definition                                                                                    |
|-------------------------|-----------------------------------------------------------------------------------------------|
| framework adapter       | A thin integration layer between an OJS SDK and a web framework.                              |
| transactional enqueue   | Enqueueing a job atomically within a database transaction.                                    |
| outbox pattern          | Storing jobs in a local database table within the transaction, then relaying to the backend.   |
| request context         | Per-request data (user ID, trace context, tenant ID) propagated to job metadata.              |

---

## 4. The Transactional Enqueue Problem

Consider a user signup flow:

```python
# WITHOUT transactional enqueue
def signup(request):
    user = User.create(email=request.email)    # INSERT into database
    ojs.enqueue("email.welcome", [user.id])    # HTTP POST to OJS backend
    return Response(201)
```

Three failure modes:

1. **Database commits, enqueue fails**: User exists but never gets a welcome email. Silent data loss.
2. **Enqueue succeeds, database rolls back**: OJS has a job for a user that doesn't exist. Worker fails with "user not found."
3. **Both succeed, response fails**: Client retries, creating a duplicate user and duplicate job.

With transactional enqueue:

```python
# WITH transactional enqueue
def signup(request):
    with transaction():
        user = User.create(email=request.email)
        ojs.enqueue_after_commit("email.welcome", [user.id])
    return Response(201)
    # Job is only sent to OJS if and when the transaction commits
```

---

## 5. Adapter Interface

### 5.1 Core Methods

Framework adapters MUST implement these methods:

| Method                    | Description                                                        |
|---------------------------|--------------------------------------------------------------------|
| `enqueue(type, args, opts)` | Enqueue a job immediately (standard behavior).                   |
| `enqueue_after_commit(type, args, opts)` | Enqueue after the current transaction commits.     |
| `enqueue_bulk(jobs)`      | Enqueue multiple jobs in one operation.                            |

### 5.2 Adapter Configuration

```json
{
  "adapter": {
    "ojs_url": "http://localhost:8080",
    "backend_type": "external",
    "outbox": {
      "enabled": true,
      "table_name": "ojs_outbox",
      "poll_interval": "PT1S",
      "batch_size": 100
    }
  }
}
```

---

## 6. Transactional Enqueue

### 6.1 Database-Backed Backends

When the OJS backend uses the same database as the application (e.g., both use Postgres), transactional enqueue is native:

```sql
BEGIN;
  INSERT INTO users (email) VALUES ('user@example.com');
  INSERT INTO ojs_jobs (type, args, queue) VALUES ('email.welcome', '[1]', 'email');
COMMIT;
-- Both the user and the job are committed atomically
```

For database-backed backends, the adapter SHOULD:

1. Detect that the OJS backend shares the application database.
2. Insert jobs directly into the OJS jobs table within the application's transaction.
3. Trigger the backend's notification mechanism (e.g., `NOTIFY` for Postgres) after commit.

### 6.2 External Backends (Outbox Pattern)

When the OJS backend uses a different storage system (Redis, SQS, Kafka), transactional enqueue requires the **outbox pattern**:

```
┌──────────────────────────────────┐
│ Application Database             │
│                                  │
│ BEGIN                            │
│   INSERT INTO users (...)        │
│   INSERT INTO ojs_outbox (...)   │  ← Stage job in local table
│ COMMIT                           │
└──────────┬───────────────────────┘
           │
           │ Outbox Relay (polls ojs_outbox)
           ▼
┌──────────────────────────────────┐
│ OJS Backend (Redis/SQS/Kafka)    │
│                                  │
│   POST /ojs/v1/jobs              │  ← Relay enqueues to backend
│                                  │
└──────────────────────────────────┘
```

### 6.3 Outbox Table Schema

```sql
CREATE TABLE ojs_outbox (
    id          BIGSERIAL PRIMARY KEY,
    job_type    TEXT NOT NULL,
    job_args    JSONB NOT NULL,
    job_options JSONB NOT NULL DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at     TIMESTAMPTZ,
    error       TEXT
);

CREATE INDEX idx_ojs_outbox_pending ON ojs_outbox (status, created_at)
    WHERE status = 'pending';
```

### 6.4 Outbox Relay

The outbox relay is a background process (or thread) that:

1. Polls `ojs_outbox` for `pending` rows (ordered by `created_at`).
2. Sends each job to the OJS backend via `POST /ojs/v1/jobs`.
3. On success: updates `status = 'sent'` and sets `sent_at`.
4. On failure: updates `status = 'failed'` and records the error. Retries on next poll.
5. Periodically prunes old `sent` rows (configurable retention, default 24 hours).

The relay SHOULD use batch enqueue (`POST /ojs/v1/jobs/batch`) when multiple outbox rows are pending, for efficiency.

### 6.5 At-Least-Once Delivery

The outbox pattern provides **at-least-once** delivery. If the relay crashes after sending to the backend but before updating the outbox row, the job will be sent again on restart. OJS backends MUST handle duplicate enqueues gracefully (idempotent by job ID, or via unique job deduplication).

---

## 7. Framework Integration Patterns

### 7.1 Request Context

Framework adapters SHOULD automatically inject request context into job metadata:

| Context Field         | Meta Key                | Source                              |
|-----------------------|-------------------------|-------------------------------------|
| Current user ID       | `ojs.context.user_id`  | Authentication middleware           |
| Request ID            | `ojs.context.request_id`| `X-Request-ID` header              |
| Trace context         | `traceparent`           | W3C Trace Context header            |
| Tenant ID             | `tenant_id`             | Authentication or `X-OJS-Tenant`    |
| Locale                | `ojs.context.locale`   | `Accept-Language` header            |

This enables:

- **Audit trails**: Which user triggered which job.
- **Distributed tracing**: Jobs carry the trace context from the originating request.
- **Tenant routing**: Multi-tenant jobs automatically inherit the request's tenant.

### 7.2 Dependency Injection

Framework adapters SHOULD integrate with the framework's dependency injection system:

- Register the OJS client as a singleton service.
- Register the OJS worker as a managed service with lifecycle hooks.
- Provide typed configuration binding (read OJS config from the framework's config system).

### 7.3 Lifecycle Hooks

Framework adapters SHOULD hook into the framework's lifecycle:

| Framework Event       | OJS Action                                                |
|-----------------------|-----------------------------------------------------------|
| Application start     | Initialize OJS client, start outbox relay if configured.  |
| Application stop      | Flush outbox, stop relay, stop worker gracefully.         |
| Request start         | Create request-scoped OJS context.                        |
| Request end           | Flush any pending `enqueue_after_commit` jobs.            |

---

## 8. Language-Specific Guidance

### 8.1 Ruby on Rails

```ruby
# config/initializers/ojs.rb
OJS.configure do |config|
  config.url = ENV['OJS_URL']
  config.adapter = :active_record  # Uses transactional outbox
  config.outbox_table = 'ojs_outbox'
end

# app/controllers/users_controller.rb
class UsersController < ApplicationController
  def create
    ActiveRecord::Base.transaction do
      @user = User.create!(user_params)
      OJS.enqueue_after_commit('email.welcome', [@user.id])
    end
  end
end
```

### 8.2 Django (Python)

```python
# settings.py
OJS_CONFIG = {
    'url': os.environ['OJS_URL'],
    'outbox': { 'enabled': True, 'table': 'ojs_outbox' },
}

# views.py
from django.db import transaction
from openjobspec.django import ojs

def signup(request):
    with transaction.atomic():
        user = User.objects.create(email=request.POST['email'])
        ojs.enqueue_after_commit('email.welcome', [user.id])
    return JsonResponse({'id': user.id}, status=201)
```

### 8.3 Express.js (Node.js)

```javascript
// Middleware that creates request-scoped OJS context
app.use(ojsMiddleware({ url: process.env.OJS_URL }));

app.post('/signup', async (req, res) => {
  await db.transaction(async (trx) => {
    const user = await trx('users').insert({ email: req.body.email });
    req.ojs.enqueueAfterCommit('email.welcome', [user.id]);
  });
  // Job is sent to OJS after transaction commits
  res.status(201).json({ id: user.id });
});
```

### 8.4 Go (net/http or chi)

```go
// Middleware
func OJSMiddleware(client *ojs.Client) func(http.Handler) http.Handler {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            ctx := ojs.WithRequestContext(r.Context(), client)
            next.ServeHTTP(w, r.WithContext(ctx))
        })
    }
}

// Handler
func SignupHandler(w http.ResponseWriter, r *http.Request) {
    tx, _ := db.Begin(r.Context())
    defer tx.Rollback()

    user := createUser(tx, r)
    ojs.EnqueueAfterCommit(r.Context(), tx, "email.welcome", ojs.Args{user.ID})

    tx.Commit() // Job is enqueued after commit
}
```

---

## 9. Conformance Requirements

An SDK declaring support for the framework-adapters extension MUST support:

| ID           | Requirement                                                                 |
|--------------|-----------------------------------------------------------------------------|
| FA-001       | `enqueue_after_commit` method that defers enqueue until transaction commits.|
| FA-002       | Jobs NOT sent if transaction rolls back.                                    |
| FA-003       | At-least-once delivery guarantee for outbox pattern.                        |

Recommended:

| ID           | Requirement                                                                 |
|--------------|-----------------------------------------------------------------------------|
| FA-R001      | Automatic request context injection (user ID, trace context).               |
| FA-R002      | Outbox relay with batch enqueue support.                                    |
| FA-R003      | Framework lifecycle integration (start/stop hooks).                         |

---

## 10. Prior Art

| System/Framework     | Transactional Enqueue Approach                                                        |
|----------------------|---------------------------------------------------------------------------------------|
| **Oban**             | Native -- jobs stored in same Postgres database as application data.                  |
| **Rails 7.2+**       | `enqueue_after_transaction_commit` (default in Rails 8.2). ActiveJob integration.     |
| **Laravel**          | `afterCommit()` on dispatchable jobs.                                                 |
| **Sidekiq**          | `transactional_push!` (recent addition). Client-side transaction tracking.            |
| **Celery**           | Manual `transaction.on_commit(lambda: task.delay())`. No built-in support.            |
| **Temporal**         | Recommends signal-based patterns. No native transactional enqueue.                    |
| **Postgres outbox**  | Debezium-based CDC for outbox relay. Industry standard for microservices.             |

The outbox pattern is a well-established microservices pattern. OJS standardizes the table schema and relay behavior so that each framework adapter doesn't reinvent it.

---

## 11. Examples

### 11.1 E-Commerce Order Flow

```python
async def place_order(request):
    async with db.transaction() as tx:
        order = await tx.execute(
            "INSERT INTO orders (user_id, total) VALUES ($1, $2) RETURNING id",
            request.user_id, request.total
        )

        for item in request.items:
            await tx.execute(
                "INSERT INTO order_items (order_id, product_id, qty) VALUES ($1, $2, $3)",
                order.id, item.product_id, item.quantity
            )

        # All jobs are staged in the outbox within the same transaction
        ojs.enqueue_after_commit("order.confirm_email", [order.id])
        ojs.enqueue_after_commit("order.reserve_inventory", [order.id])
        ojs.enqueue_after_commit("order.charge_payment", [order.id])

    # Transaction committed → outbox relay sends all 3 jobs to OJS
    return Response({"order_id": order.id}, status=201)
```

If the payment charge or any database insert fails, the entire transaction rolls back -- including the outbox entries. No orphaned jobs.

---

## 12. Resolved Design Decisions

The following design decisions were resolved during the experimental phase:

### 12.1 Outbox Relay Deployment Model

**Question:** Should the outbox relay be built into the SDK or run as a separate process?

**Decision:** The SDK MUST support both modes. Built-in relay (runs in the application process) MUST be the default for simplicity. Separate relay process SHOULD be supported for production deployments requiring independent scaling.

**Rationale:** Built-in relay provides zero-configuration getting started; separate relay serves high-throughput production needs. Both Temporal and Debezium support this dual model.

### 12.2 Outbox and Job Priority Interaction

**Question:** How should the outbox interact with job priority?

**Decision:** Outbox jobs MUST be relayed in insertion order (FIFO). Priority is applied by the backend when the job is enqueued from the outbox, not during relay.

**Rationale:** The outbox is a transport mechanism, not a scheduling mechanism. Applying priority during relay would require complex sorting logic in the outbox table.

### 12.3 Framework Adapter Discovery

**Question:** Should there be a standard for framework adapter discovery?

**Decision:** Framework adapters SHOULD follow a naming convention: `ojs-adapter-{framework}` (e.g., `ojs-adapter-express`, `ojs-adapter-rails`, `ojs-adapter-django`). Adapters are NOT part of the core SDK; they are separate packages that depend on the SDK.

**Rationale:** Separate packages avoid bloating the core SDK with framework-specific dependencies. Naming convention enables discoverability.

### 12.4 `enqueue_after_commit` with Nested Transactions

**Question:** How should `enqueue_after_commit` work with nested transactions / savepoints?

**Decision:** `enqueue_after_commit` MUST execute after the outermost transaction commits. Savepoints (nested transactions) MUST NOT trigger relay. If the outermost transaction rolls back, all pending jobs from inner savepoints MUST be discarded.

**Rationale:** Only the outermost commit represents a durable state change. Triggering on savepoints could relay jobs for data that is subsequently rolled back.

---

## Appendix A: Changelog

| Date       | Change                          |
|------------|---------------------------------|
| 2026-02-13 | Initial experimental release.   |
