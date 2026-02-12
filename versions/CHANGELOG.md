# Changelog

All notable changes to the Open Job Spec specification will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0-rc.1] - 2025-06-01

### Added
- Core specification (ojs-core.md): Job envelope with 5 required + 8 optional + 8 system-managed attributes
- 8-state lifecycle state machine: scheduled, available, pending, active, completed, retryable, cancelled, discarded
- JSON wire format (ojs-json-format.md): Required baseline encoding with content type application/openjobspec+json
- HTTP protocol binding (ojs-http-binding.md): Required baseline protocol with REST endpoints
- gRPC protocol binding (ojs-grpc-binding.md): Optional high-performance protocol with streaming
- Retry policy specification (ojs-retry.md): Structured retry policies following Temporal's format
- Unique jobs specification (ojs-unique-jobs.md): Multi-dimensional deduplication
- Workflow primitives (ojs-workflows.md): Chain, group, and batch compositions
- Cron specification (ojs-cron.md): Periodic/recurring job scheduling
- Event vocabulary (ojs-events.md): Standard lifecycle events and metrics
- Middleware specification (ojs-middleware.md): Enqueue and execution middleware chains
- Worker protocol (ojs-worker-protocol.md): Three-state worker lifecycle (running, quiet, terminate)
- Conformance levels (ojs-conformance.md): 5 levels (Core through Advanced) with test suite format
- RFC process and template (CONTRIBUTING.md, rfcs/RFC-0000-template.md)

### Changed (from v0.2 draft)
- Renamed `payload` (object) to `args` (array) for clean separation (inspired by Sidekiq)
- Expanded state machine from 7 states to 8 (added `pending` from River, split `failed`/`dead` into `retryable`/`discarded`)
- Adopted Temporal's structured retry policy format instead of simple backoff enum
- Limited workflow primitives to chain/group/batch (deferred DAGs to future version)
- Added middleware as first-class MUST requirement (inspired by Sidekiq)
- Added three-tier architecture (Core → Wire Format → Protocol Binding) inspired by CloudEvents
- Added `specversion` as required attribute
- Switched from `payload` (object) to `args` (array)
- Added worker lifecycle protocol with heartbeat and visibility timeout

## [0.2.0] - 2025-02-12

### Added
- Initial draft specification
- 5 conformance levels (Core through Advanced)
- REST/HTTP, gRPC, WebSocket, and native protocol definitions
- Job lifecycle with 8 states
- Retry policies, unique jobs, workflows, cron support
- Observability (events, metrics, distributed tracing)
- Payload schema validation
- Governance and RFC process
- Reference implementation roadmap
