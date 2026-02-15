# Contributing to Open Job Spec

Welcome, and thank you for your interest in contributing to the Open Job Spec (OJS) project. Whether you are reporting a bug in the spec text, proposing a new extension, building a reference implementation, or writing conformance tests, your contribution matters and we are glad you are here.

## Ways to Contribute

### Reporting Issues

If you find an ambiguity, contradiction, or error in the specification:

1. Search [existing issues](https://github.com/openjobspec/spec/issues) to avoid duplicates.
2. Open a new issue with the label `spec-bug` or `clarification`.
3. Include the document name, section number, and a clear description of the problem.
4. Where possible, suggest corrected wording.

### Proposing Changes via the RFC Process

All non-trivial changes to OJS go through a formal RFC process. See [RFC Process](#rfc-process) below for full details. In short: open an RFC, get community feedback, iterate, and land it once consensus is reached.

### Implementing the Spec

Building an OJS-compliant library in a new language or for a new backend is one of the most valuable contributions you can make. To get started:

1. Read the [Core Specification](spec/ojs-core.md) and the [JSON Wire Format](spec/ojs-json-format.md) end to end.
2. Pick a conformance level to target (start with Level 0).
3. Use the [ojs-conformance](https://github.com/openjobspec/ojs-conformance) test suite to validate your implementation.
4. Open an issue to let us know you are working on it -- we can provide guidance and early feedback.

### Writing Conformance Tests

The conformance test suite is the source of truth for whether an implementation is spec-compliant. If you find a spec requirement that lacks test coverage:

1. Open an issue in [ojs-conformance](https://github.com/openjobspec/ojs-conformance) describing the gap.
2. Submit a PR with test cases that exercise the requirement. Each test MUST reference the spec document and section it validates.

## RFC Process

OJS uses a staged RFC process modeled after the [GraphQL RFC process](https://github.com/graphql/graphql-spec/blob/main/CONTRIBUTING.md), with explicit time floors at each stage to ensure thorough review. All RFCs are tracked in the [`rfcs/`](../rfcs/) directory.

### Stage 0 -- Strawman

**Goal:** Identify a real problem and sketch a rough direction.

- Open a pull request using the [RFC template](../rfcs/RFC-0000-template.md).
- The PR MUST include a clear problem statement with motivating use cases.
- A rough solution sketch is encouraged but not required.
- **Minimum discussion period: 2 weeks** from the date the PR is opened.
- Anyone can champion a Stage 0 RFC.

### Stage 1 -- Proposal

**Goal:** Present a detailed, concrete solution.

- A **champion** MUST be assigned. The champion is responsible for driving the RFC through the remaining stages.
- The RFC MUST include:
  - Detailed solution design with data model changes, attribute definitions, and type information.
  - Draft spec text written in the style of the existing specification documents.
  - A discussion of alternatives considered and why they were rejected.
- **Minimum review period: 4 weeks** from promotion to Stage 1.

### Stage 2 -- Draft

**Goal:** Prove the design works in practice.

- The working group MUST reach rough consensus that the design is sound.
- The champion MUST provide a **reference implementation pull request** in at least one language.
- **Conformance tests** covering the new behavior MUST be written and submitted.
- **Critical requirement:** Before promotion to Stage 3, the proposal MUST have **working prototypes in at least two programming languages**. This rule, inspired by [OpenTelemetry's OTEP process](https://github.com/open-telemetry/oteps), ensures that the design is truly language-agnostic and not biased toward one ecosystem.
- **Minimum stabilization period: 8 weeks** from promotion to Stage 2.

### Stage 3 -- Accepted

**Goal:** Finalize and merge.

- Editorial review MUST be complete. All RFC 2119 keywords MUST be audited for correctness.
- The spec text is merged into the working draft of the relevant specification document.
- The RFC PR is merged into `rfcs/` with its final number assigned.
- The feature is included in the next spec release.

### RFC Numbering

RFCs are numbered sequentially: `RFC-0001`, `RFC-0002`, etc. Use `RFC-0000-template.md` as your starting point. The final number is assigned when the RFC reaches Stage 3.

## Protocol Extension Registration

Adding a new protocol binding (beyond HTTP and gRPC) requires a dedicated RFC that meets additional requirements:

1. **Full method mapping.** The RFC MUST include a complete mapping of every logical interface method defined in the core spec (enqueue, dequeue, ack, nack, heartbeat, etc.) to the protocol's native primitives.

2. **Error handling.** The RFC MUST define how OJS error codes map to the protocol's native error/status code system. Every error condition in the core spec MUST have a defined mapping.

3. **Working implementation.** At least one working implementation of the binding MUST exist and be linked from the RFC before it can advance to Stage 2.

4. **Performance characteristics.** The RFC MUST include benchmark data comparing the new binding's throughput and latency against the HTTP binding baseline for a standard workload (enqueue 10,000 jobs, dequeue and ack 10,000 jobs). Absolute numbers are less important than understanding the relative tradeoffs.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). By participating, you agree to uphold its standards. Please report unacceptable behavior to [conduct@openjobspec.org](mailto:conduct@openjobspec.org).

## Style Guide for Spec Text

All specification documents MUST follow these conventions to ensure consistency and precision:

### RFC 2119 Keywords

- Use the keywords **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** as defined in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt).
- These keywords MUST appear in **uppercase** when used with their RFC 2119 meaning.
- Every **MUST** requirement MUST be accompanied by a brief rationale explaining *why* the requirement exists. This helps implementers understand the intent and prevents cargo-culting.

  Example:
  > The `id` attribute MUST be a non-empty string. *Rationale: An empty identifier would make idempotency checks and log correlation impossible.*

### Data Structures

- Every data structure introduced in the spec MUST include at least one complete example in JSON format.
- Examples SHOULD use realistic values, not placeholder text like `"foo"` or `"bar"`.

### Types

- Be explicit about types. Say `string (UUIDv7 format)`, not just `string`.
- Specify constraints: minimum/maximum lengths, allowed character sets, valid ranges.
- When referencing time, always specify the format (e.g., `string (RFC 3339 timestamp in UTC)`).

### General Writing

- Use the present tense and active voice.
- Keep sentences short. One requirement per sentence.
- Define terms on first use and maintain a glossary if the document introduces more than five terms.

## Licensing

By submitting a contribution to this project, you agree that your contribution is licensed under the [Apache License, Version 2.0](../LICENSE). You represent that you have the right to license your contribution under this license.

---

Thank you for helping make background job processing better for everyone. If you have questions that are not answered here, open a [discussion](https://github.com/openjobspec/spec/discussions) and we will be happy to help.
