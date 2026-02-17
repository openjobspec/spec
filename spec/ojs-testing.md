# Open Job Spec: Testing Specification

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Testing Specification                      |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-19                                     |
| **Status**  | Release Candidate                              |
| **Maturity** | Experimental                                   |
| **Tier**    | Official Extension                             |
| **URI**     | `urn:ojs:ext:testing`                          |
| **Requires**| OJS Core Specification (Layer 1)               |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Design Principles](#4-design-principles)
5. [Testing Modes](#5-testing-modes)
   - 5.1 [Fake Mode](#51-fake-mode)
   - 5.2 [Inline Mode](#52-inline-mode)
   - 5.3 [Real Mode](#53-real-mode)
6. [Standard Assertion Helpers](#6-standard-assertion-helpers)
   - 6.1 [Enqueue Assertions](#61-enqueue-assertions)
   - 6.2 [Execution Assertions](#62-execution-assertions)
   - 6.3 [State Assertions](#63-state-assertions)
   - 6.4 [Workflow Assertions](#64-workflow-assertions)
7. [Test Utilities](#7-test-utilities)
   - 7.1 [Queue Drain](#71-queue-drain)
   - 7.2 [Time Control](#72-time-control)
   - 7.3 [Failure Injection](#73-failure-injection)
8. [Behavioral Differences Between Modes](#8-behavioral-differences-between-modes)
9. [SDK Implementation Requirements](#9-sdk-implementation-requirements)
10. [Language-Specific Conventions](#10-language-specific-conventions)
11. [Conformance Requirements](#11-conformance-requirements)
12. [Prior Art](#12-prior-art)
13. [Examples](#13-examples)

---

## 1. Introduction

Testing utilities are the feature developers interact with most frequently. Developers spend more time writing and running tests than writing production code. The quality of testing support directly impacts developer satisfaction and adoption velocity.

Every mature job processing system provides testing utilities, and the quality of these utilities varies dramatically:

- **Sidekiq** offers three modes: `fake!` (in-memory), `inline!` (synchronous), and `disable!` (real Redis). The fake mode is used by virtually every Sidekiq application.
- **Oban** provides `assert_enqueued`, `refute_enqueued`, `perform_job`, and `drain_queue` -- widely regarded as best-in-class testing ergonomics.
- **Celery** has `task_always_eager` mode but with documented behavioral discrepancies that surprise developers.
- **BullMQ** lacks built-in testing utilities entirely, forcing teams to write custom mocks.

OJS standardizes a testing interface that every SDK SHOULD implement. This creates consistent testing ergonomics across all languages and eliminates the need for per-SDK custom mocking patterns.

### 1.1 Scope

This specification defines:

- Three testing modes (fake, inline, real) and their behavioral guarantees.
- A standard set of assertion helpers for verifying enqueue, execution, and state transitions.
- Test utility functions for draining queues, controlling time, and injecting failures.
- Behavioral differences between modes and their implications for test design.
- SDK implementation requirements and language-specific conventions.

This specification does **not** define:

- Integration testing against specific backends (see ojs-conformance.md).
- Load testing or performance benchmarking methodology.
- Test framework integrations (Jest, pytest, RSpec, etc.) -- SDKs adapt the OJS testing interface to each framework.

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

---

## 3. Terminology

| Term            | Definition                                                                                     |
|-----------------|------------------------------------------------------------------------------------------------|
| fake mode       | A testing mode where jobs are stored in-memory without touching any backend. No HTTP calls.    |
| inline mode     | A testing mode where jobs execute synchronously in the calling thread/process.                  |
| real mode       | A testing mode where jobs are processed by a real OJS backend. Full integration testing.       |
| assertion helper| A function that verifies expectations about enqueued, executed, or completed jobs.              |
| drain           | The act of synchronously processing all available jobs in a queue until it is empty.           |
| test context    | An isolated testing scope that tracks enqueued and executed jobs for assertion purposes.       |

---

## 4. Design Principles

1. **Tests should not require infrastructure.** The default testing mode (fake) MUST NOT require a running OJS backend, Redis, Postgres, or any external service. This enables fast, reliable unit tests.

2. **Testing ergonomics are the product.** Assertion helpers MUST read like natural language. `assert_enqueued("email.send", args: {to: "user@example.com"})` should be immediately understandable to someone who has never used OJS.

3. **Modes are explicit, not automatic.** The testing mode MUST be set explicitly by the developer, not inferred from environment variables or runtime detection. Celery's `task_always_eager` is a cautionary tale: its implicit behavior leads to tests that pass locally but fail in CI.

4. **Isolation between tests.** Each test MUST start with a clean state. Assertion helpers MUST operate on the current test's jobs, not jobs from previous tests.

5. **Behavioral parity where possible.** Fake mode SHOULD match real mode behavior for state transitions, validation, and error handling. Where behavior diverges, the divergence MUST be documented.

---

## 5. Testing Modes

### 5.1 Fake Mode

**Purpose**: Fast unit tests that verify enqueueing logic without any backend interaction.

**Behavior**:

- The OJS client stores jobs in an in-memory list instead of sending HTTP requests to a backend.
- No network calls are made.
- Jobs are stored with their full envelope (type, args, options, queue, meta).
- Jobs are NOT executed -- they are only recorded for assertion.
- State transitions follow the same validation rules as a real backend (invalid transitions are rejected).
- The `id` field is generated (UUIDv7) exactly as in production.
- Middleware chains execute normally (enqueue middleware runs; execution middleware does not, since jobs don't execute).

SDKs implementing fake mode MUST provide:

| Operation           | Behavior in Fake Mode                                     |
|---------------------|------------------------------------------------------------|
| `enqueue()`         | Stores job in memory. Returns a Job object with generated ID. |
| `enqueueBatch()`    | Stores all jobs in memory. Returns Job objects.             |
| `cancel()`          | Marks the job as cancelled if it exists in the fake store.  |
| `getJob()`          | Returns the job from the fake store or null.                |
| `workflow()`        | Stores the workflow definition. Does NOT execute steps.     |

**Rationale**: Fake mode is the highest-value testing feature. It enables test suites that run in milliseconds with zero external dependencies, covering the most common testing need: "did my code enqueue the right job with the right arguments?"

### 5.2 Inline Mode

**Purpose**: Integration-style tests that verify both enqueueing AND handler execution in a single synchronous call.

**Behavior**:

- When `enqueue()` is called, the job is immediately executed synchronously in the calling thread.
- The registered handler for the job type is invoked.
- Execution middleware runs (both enqueue and execution chains).
- The return value of the handler becomes the job result.
- Exceptions propagate to the caller (NOT caught and retried).
- Retry logic does NOT apply -- a failure fails the test immediately.
- State transitions are: `available` → `active` → `completed` (on success) or `available` → `active` → error thrown (on failure).

SDKs implementing inline mode MUST clearly document these behavioral differences from production:

| Aspect          | Production                          | Inline Mode                                |
|-----------------|-------------------------------------|--------------------------------------------|
| Execution       | Asynchronous, by a worker           | Synchronous, in the calling thread         |
| Concurrency     | Multiple jobs run concurrently      | One job at a time, blocking                |
| Retries         | Failed jobs are retried per policy  | Failures propagate immediately             |
| Ordering        | FIFO within priority                | Immediate (no queue)                       |
| Scheduling      | Jobs run at `scheduled_at`          | Jobs run immediately (delay ignored)       |
| Visibility timeout | Worker reservation               | Not applicable                             |

**Rationale**: Inline mode is useful for testing the full enqueue-to-completion path without infrastructure. However, its behavioral divergence from production makes it unsuitable as the only testing mode. Celery's `task_always_eager` documentation warns that "many tests will use eager mode to run the whole task body in one test." OJS makes the limitations explicit to prevent this trap.

### 5.3 Real Mode

**Purpose**: End-to-end tests against a running OJS backend. Full behavioral fidelity.

**Behavior**:

- All operations go through the real HTTP (or gRPC) protocol to a real backend.
- Jobs are processed by real workers (which may be started in the test process or externally).
- Retries, scheduling, visibility timeouts, and all other production behaviors apply.
- Tests may need to wait for asynchronous operations to complete.

SDKs implementing real mode SHOULD provide:

- A way to start an embedded worker within the test process.
- Polling helpers that wait for a job to reach a specific state with configurable timeout.
- Cleanup utilities that purge test data after each test.

**Rationale**: Real mode is essential for integration and acceptance tests but too slow and infrastructure-dependent for unit tests. It is the gold standard for behavioral correctness.

---

## 6. Standard Assertion Helpers

All assertion helpers operate on the current test context (the jobs enqueued during the current test, not globally). SDKs MUST provide at minimum the helpers in Section 6.1. Sections 6.2-6.4 are RECOMMENDED.

### 6.1 Enqueue Assertions

#### `assert_enqueued(type, options?)`

Asserts that at least one job of the given type was enqueued, optionally matching additional criteria.

**Parameters**:

| Parameter      | Type   | Required | Description                                                        |
|----------------|--------|----------|--------------------------------------------------------------------|
| `type`         | string | Yes      | The job type to match.                                             |
| `options.args` | any    | No       | Expected args (deep equality).                                     |
| `options.queue`| string | No       | Expected queue name.                                               |
| `options.meta` | object | No       | Expected subset of meta fields (partial match).                    |
| `options.count`| integer| No       | Expected number of matching jobs. Default: at least 1.             |

**Behavior**: Searches all enqueued jobs in the current test context. Passes if at least one job matches all specified criteria (or exactly `count` jobs match when specified). Fails with a descriptive message listing the enqueued jobs that did NOT match and why.

#### `refute_enqueued(type, options?)`

Asserts that NO job of the given type was enqueued matching the criteria. The inverse of `assert_enqueued`.

#### `all_enqueued(filter?)`

Returns all jobs enqueued in the current test context, optionally filtered by type, queue, or args. This is not an assertion -- it returns data for custom assertions.

#### `clear_all()`

Clears all enqueued jobs from the current test context. Useful for setup/teardown.

### 6.2 Execution Assertions

These helpers are available in inline mode and real mode.

#### `assert_performed(type, options?)`

Asserts that at least one job of the given type was executed (not just enqueued). Same parameters as `assert_enqueued`.

#### `refute_performed(type, options?)`

Asserts that no job of the given type was executed.

#### `assert_completed(type, options?)`

Asserts that at least one job of the given type reached the `completed` state. Available only in modes where jobs actually execute (inline or real).

#### `assert_failed(type, options?)`

Asserts that at least one job of the given type failed (reached `retryable` or `discarded` state).

### 6.3 State Assertions

#### `assert_job_state(job_id, expected_state)`

Asserts that a specific job (by ID) is in the expected state. Useful for testing state machine transitions.

### 6.4 Workflow Assertions

#### `assert_workflow_created(type, options?)`

Asserts that a workflow of the given type was created. Options allow matching on step count, step types, or workflow name.

---

## 7. Test Utilities

### 7.1 Queue Drain

#### `drain(queue?, options?)`

Synchronously processes all available jobs in a queue (or all queues if none specified). Returns when no more jobs are available.

**Parameters**:

| Parameter          | Type    | Required | Description                                                 |
|--------------------|---------|----------|-------------------------------------------------------------|
| `queue`            | string  | No       | Queue to drain. Default: all queues.                        |
| `options.max_jobs` | integer | No       | Maximum number of jobs to process. Default: unlimited.      |
| `options.timeout`  | duration| No       | Maximum time to drain. Default: 30 seconds.                 |
| `options.with_scheduled` | boolean | No | Whether to also process scheduled jobs. Default: false.    |

**Behavior in fake mode**: Invokes the registered handler for each enqueued job, in FIFO order. After draining, all processed jobs are marked as `completed` or `failed` based on handler outcome.

**Behavior in inline mode**: No-op (jobs are already executed at enqueue time).

**Behavior in real mode**: Polls the backend until the queue is empty or timeout is reached.

**Rationale**: Drain is the bridge between fake mode (which doesn't execute) and inline mode (which executes eagerly). It allows tests to control exactly when jobs are processed, enabling patterns like "enqueue three jobs, assert all are enqueued, then drain and assert results."

### 7.2 Time Control

#### `freeze_time(timestamp)`

Sets the test clock to a fixed timestamp. Affects `scheduled_at` evaluation, `expires_at` checks, and retry backoff calculations.

#### `advance_time(duration)`

Advances the test clock by the specified duration. Scheduled jobs that are now past their `scheduled_at` become available.

**Rationale**: Time control is essential for testing scheduled jobs and retry backoff without waiting for real time to pass. Sidekiq's testing guide recommends `Timecop` or `travel_to` for this purpose; OJS standardizes the interface.

### 7.3 Failure Injection

#### `fail_next(type, error)`

Configures the next execution of a job of the given type to fail with the specified error. Useful for testing retry behavior and error handling.

```javascript
testing.failNext('email.send', new Error('SMTP connection refused'));
await testing.drain();
assert_failed('email.send');
```

#### `fail_all(type, error)`

Configures ALL executions of a job of the given type to fail.

---

## 8. Behavioral Differences Between Modes

This table summarizes which OJS features behave correctly in each testing mode. SDKs MUST document these differences.

| Feature                    | Fake Mode | Inline Mode | Real Mode |
|----------------------------|-----------|-------------|-----------|
| Job envelope validation    | ✅         | ✅           | ✅         |
| State machine transitions  | ✅         | ✅           | ✅         |
| Enqueue middleware         | ✅         | ✅           | ✅         |
| Execution middleware       | ❌         | ✅           | ✅         |
| Handler execution          | ❌ (use drain) | ✅       | ✅         |
| Retry on failure           | ❌         | ❌           | ✅         |
| Scheduled job timing       | ❌ (use time control) | ❌ | ✅     |
| Visibility timeout         | ❌         | ❌           | ✅         |
| Concurrency limits         | ❌         | ❌           | ✅         |
| Rate limiting              | ❌         | ❌           | ✅         |
| Unique job deduplication   | ✅ (in-memory) | ✅ (in-memory) | ✅  |
| Workflow orchestration     | ❌         | Partial      | ✅         |
| Event emission             | ✅ (in-memory) | ✅ (in-memory) | ✅  |

---

## 9. SDK Implementation Requirements

### 9.1 Required Interface

Every OJS SDK SHOULD provide a testing module with the following interface (in language-idiomatic form):

1. **Mode activation**: A function or configuration to switch to fake, inline, or real mode.
2. **Test context management**: A way to create isolated test contexts (typically per-test setup/teardown).
3. **Enqueue assertions**: `assert_enqueued` and `refute_enqueued` at minimum.
4. **Clear utility**: `clear_all` to reset state between tests.

### 9.2 Recommended Interface

SDKs SHOULD additionally provide:

5. **Drain utility**: For processing enqueued jobs in fake mode.
6. **Execution assertions**: `assert_performed`, `assert_completed`, `assert_failed`.
7. **Time control**: `freeze_time`, `advance_time`.
8. **Failure injection**: `fail_next`, `fail_all`.

### 9.3 Test Isolation

SDKs MUST ensure that test contexts are isolated:

- Jobs enqueued in test A MUST NOT be visible to assertions in test B.
- Parallel test execution MUST be supported (each test gets its own context).
- The global client state MUST be restorable after testing (e.g., `testing.restore()` switches back to real mode).

**Rationale**: Test isolation failures are a notorious source of flaky tests. Sidekiq's testing guide explicitly warns about shared state between tests. By making isolation a MUST requirement, OJS prevents an entire class of testing bugs.

---

## 10. Language-Specific Conventions

### 10.1 JavaScript / TypeScript

```typescript
import { testing } from '@openjobspec/client';

beforeEach(() => {
  testing.fake();   // Switch to fake mode
});

afterEach(() => {
  testing.restore(); // Restore real mode, clear state
});

test('sends welcome email on signup', async () => {
  await signupUser({ email: 'user@example.com' });

  testing.assertEnqueued('email.send', {
    args: [{ to: 'user@example.com', template: 'welcome' }],
    queue: 'email',
  });
});

test('processes email job correctly', async () => {
  testing.inline(); // Switch to inline mode

  await client.enqueue('email.send', [{ to: 'user@example.com' }]);

  testing.assertPerformed('email.send');
  testing.assertCompleted('email.send');
});
```

### 10.2 Go

```go
func TestSignup(t *testing.T) {
    ctx := ojs.Testing.Fake(t) // Creates isolated test context

    signupUser(ctx, "user@example.com")

    ojs.Testing.AssertEnqueued(t, "email.send", ojs.MatchArgs(
        map[string]any{"to": "user@example.com"},
    ))
}

func TestEmailProcessing(t *testing.T) {
    ctx := ojs.Testing.Inline(t)

    client.Enqueue(ctx, "email.send", ojs.Args{"to": "user@example.com"})

    ojs.Testing.AssertCompleted(t, "email.send")
}

func TestDrain(t *testing.T) {
    ctx := ojs.Testing.Fake(t)

    client.Enqueue(ctx, "email.send", ojs.Args{"to": "a@example.com"})
    client.Enqueue(ctx, "email.send", ojs.Args{"to": "b@example.com"})

    ojs.Testing.AssertEnqueued(t, "email.send", ojs.MatchCount(2))

    ojs.Testing.Drain(ctx)

    ojs.Testing.AssertCompleted(t, "email.send", ojs.MatchCount(2))
}
```

### 10.3 Python

```python
import pytest
from openjobspec.testing import fake_mode, assert_enqueued, drain

@pytest.fixture(autouse=True)
def ojs_testing():
    with fake_mode():
        yield

async def test_sends_welcome_email():
    await signup_user(email="user@example.com")

    assert_enqueued("email.send", args=[{"to": "user@example.com"}])

async def test_drain_and_complete():
    await client.enqueue("email.send", [{"to": "user@example.com"}])

    drain()

    assert_completed("email.send")
```

### 10.4 Ruby

```ruby
RSpec.describe UserSignup do
  include OJS::Testing

  before { ojs_fake! }
  after  { ojs_restore! }

  it "sends welcome email on signup" do
    signup_user(email: "user@example.com")

    assert_enqueued "email.send",
      args: [{ to: "user@example.com", template: "welcome" }],
      queue: "email"
  end

  it "does not send email for inactive users" do
    signup_user(email: "user@example.com", active: false)

    refute_enqueued "email.send"
  end
end
```

---

## 11. Conformance Requirements

An SDK declaring support for the testing extension MUST support:

| ID           | Requirement                                                                 |
|--------------|-----------------------------------------------------------------------------|
| TST-001      | Fake mode with in-memory job storage, no backend required.                  |
| TST-002      | `assert_enqueued` with type and optional args/queue/meta matching.          |
| TST-003      | `refute_enqueued` as the inverse of `assert_enqueued`.                      |
| TST-004      | `clear_all` to reset test state.                                            |
| TST-005      | Test isolation: parallel tests do not share state.                          |
| TST-006      | Mode restoration: switching back to real client after testing.              |

Recommended:

| ID           | Requirement                                                                 |
|--------------|-----------------------------------------------------------------------------|
| TST-R001     | Inline mode with synchronous handler execution.                             |
| TST-R002     | `drain()` for processing jobs in fake mode.                                 |
| TST-R003     | `assert_performed` and `assert_completed`.                                  |
| TST-R004     | Time control utilities (`freeze_time`, `advance_time`).                     |
| TST-R005     | Failure injection (`fail_next`, `fail_all`).                                |

---

## 12. Prior Art

| System           | Testing Approach                                                                          |
|------------------|-------------------------------------------------------------------------------------------|
| **Sidekiq**      | Three modes: `fake!`, `inline!`, `disable!`. Fake mode stores jobs in `Sidekiq::Queues`. `drain` processes all jobs. |
| **Oban**         | `assert_enqueued`, `refute_enqueued`, `perform_job`, `drain_queue`. Built into the library. Best-in-class ergonomics. |
| **Celery**       | `task_always_eager` for synchronous execution. Documented behavioral caveats. Limited assertion helpers. |
| **BullMQ**       | No built-in testing utilities. Community relies on custom mocks and sandboxed processors. |
| **Faktory**      | No built-in testing mode. Tests require a running Faktory server.                         |
| **ActiveJob (Rails)** | `assert_enqueued_with`, `assert_performed_jobs`, `perform_enqueued_jobs`. Test adapter pattern. |

OJS synthesizes the best ideas: Sidekiq's three-mode model, Oban's assertion ergonomics, and ActiveJob's test adapter pattern. The key addition is standardization across all languages -- the testing interface is the same whether using the Go, JavaScript, Python, or Ruby SDK.

---

## 13. Examples

### 13.1 Testing Retry Behavior

```typescript
import { testing } from '@openjobspec/client';

test('retries on transient failure then succeeds', async () => {
  testing.fake();

  // Fail the first attempt, succeed on second
  testing.failNext('payment.process', new Error('timeout'));

  await client.enqueue('payment.process', [{ order_id: 'ord_123' }]);
  testing.drain();

  const jobs = testing.allEnqueued({ type: 'payment.process' });
  expect(jobs).toHaveLength(1);
  expect(jobs[0].attempt).toBe(2);
});
```

### 13.2 Testing Scheduled Jobs with Time Control

```typescript
test('sends reminder after 24 hours', async () => {
  testing.fake();
  testing.freezeTime('2026-02-13T10:00:00Z');

  await client.enqueue('reminder.send', [{ user_id: 'u_123' }], {
    delay: 'PT24H',
  });

  // Job is enqueued but not yet available
  testing.assertEnqueued('reminder.send');

  // Advance time by 24 hours
  testing.advanceTime('PT24H');
  testing.drain({ withScheduled: true });

  testing.assertCompleted('reminder.send');
});
```

### 13.3 Testing Workflow Steps

```typescript
test('data pipeline processes in order', async () => {
  testing.fake();

  await client.workflow(
    chain(
      { type: 'data.fetch', args: [{ url: 'https://api.example.com' }] },
      { type: 'data.transform', args: [{ format: 'csv' }] },
      { type: 'data.load', args: [{ dest: 'warehouse' }] },
    )
  );

  testing.assertWorkflowCreated('chain', { stepCount: 3 });
  testing.assertEnqueued('data.fetch');
});
```

---

## Appendix A: Changelog

| Date       | Change                        |
|------------|-------------------------------|
| 2026-02-13 | Initial release candidate.    |
