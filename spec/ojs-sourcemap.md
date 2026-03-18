# Open Job Spec: Source Map Extension

| Field        | Value                              |
|--------------|------------------------------------|
| **Title**   | OJS Source Map                     |
| **Version** | 0.1.0                              |
| **Date**    | 2026-04-17                         |
| **Status**  | Stage-0 RFC                        |
| **Maturity** | Experimental                       |
| **Layer**   | Extension                          |
| **URI**     | `urn:ojs:ext:sourcemap`            |
| **Requires**| OJS Core Specification (Layer 1)   |
| **Related** | OJS Execution History (consumed by Studio M6) |

---

## 1. Introduction

The Source Map extension binds a job invocation to the exact handler
source code that processed it: a content-addressable identifier (Git SHA
or container image digest), the file/function within that artifact, and
optionally line ranges for inline lambdas. Combined with the Execution
History extension (`urn:ojs:ext:execution-history`), it enables OJS
Studio (M6) to drop a developer's IDE breakpoint on the precise
`(commit × file × line)` that ran a failing job, even when the binary
shipped weeks ago and the working tree has moved on.

The 60-second wow moment: replay a production failure inside a local
debugger with the original source checked out automatically.

This RFC is **Stage 0** — the envelope shape is normative for early
prototypes; everything else (resolver protocol, Studio API) will land in
follow-up Stage-1 RFCs after design-partner feedback.

## 2. Notational Conventions

The keywords MUST, SHOULD, MAY are interpreted per RFC 2119/8174.

## 3. Envelope Field

A producer or worker MAY attach a `ext_sourcemap` object to a job
envelope. When present it MUST be a JSON object matching this schema:

```json
{
  "ext_sourcemap": {
    "vcs": "git",
    "repo": "https://github.com/example/jobs",
    "rev": "9b4f0c8c2aa6f1d3e8c4a1b6f2e9d8c7a3b2c1d0",
    "path": "src/jobs/email_worker.py",
    "symbol": "send_welcome_email",
    "lines": [42, 88],
    "image": null,
    "lang": "python",
    "tool": "ojs-py-sdk@1.7.3",
    "build_id": null
  }
}
```

### 3.1 Field semantics

| Field      | Type             | Required | Notes |
|------------|------------------|----------|-------|
| `vcs`      | string           | MUST     | One of `git`, `hg`, `oci`, `none`. |
| `repo`     | string (URL)     | SHOULD   | Canonical clone URL or registry URL. |
| `rev`      | string           | MUST     | Full SHA (no abbreviations); for `oci`, an `algorithm:hex` digest per OCI image-spec §6. |
| `path`     | string           | MUST     | Repository-root-relative POSIX path. |
| `symbol`   | string           | SHOULD   | Function/method/class identifier. |
| `lines`    | [int, int]       | MAY      | Inclusive 1-based line range. |
| `image`    | string or null   | MAY      | Container image reference if the worker ran inside one. |
| `lang`     | string           | SHOULD   | Lowercase language tag (`go`, `python`, `node`, `java`, `rust`, `ruby`, `dotnet`, `php`, `wasm`). |
| `tool`     | string           | SHOULD   | SDK identifier and version that emitted the map. |
| `build_id` | string or null   | MAY      | LLVM/ELF build-id or compiler-emitted unique id when source is compiled from a non-VCS artifact. |

Producers MUST omit the field rather than emit empty/placeholder values.
Backends MUST treat `ext_sourcemap` as opaque — they MAY index it but
MUST NOT mutate it.

### 3.2 SDK responsibilities

An SDK SHOULD populate `ext_sourcemap` automatically for handler
registration calls when it can determine the values cheaply:

- `vcs=git` + `rev`: read from the build environment
  (`GITHUB_SHA`, `CI_COMMIT_SHA`, or `git rev-parse HEAD` at startup).
- `path` + `symbol`: capture from the language's reflection facility
  at handler-registration time (Python `inspect`, Go `runtime.FuncForPC`,
  Node `Error.stack` parsing, JVM stack-walker, etc.).
- `image`: read `/proc/self/cgroup` or platform env (`KUBERNETES_*`,
  `ECS_CONTAINER_METADATA_URI`).

When automation cannot determine a field, the SDK SHOULD omit it.

### 3.3 Validation

- `rev` for `git`/`hg` MUST match `^[0-9a-f]{40}$` (SHA-1) or
  `^[0-9a-f]{64}$` (SHA-256).
- `rev` for `oci` MUST match `^[a-z0-9]+(?:[+._-][a-z0-9]+)*:[a-fA-F0-9]+$`.
- `path` MUST NOT contain `..` segments or absolute prefixes.
- `lines[0] <= lines[1]` and both > 0 if present.

A backend that performs envelope validation MUST reject envelopes whose
`ext_sourcemap` violates these constraints with HTTP 400 and an error
code `ext_sourcemap_invalid`.

## 4. Resolver Protocol (informative)

A *source resolver* is any service that, given an `ext_sourcemap`
object, returns the original source bytes. The normative resolver
contract will land in a Stage-1 RFC; the rough shape:

```
GET /v1/source?vcs=git&rev=<sha>&path=<path>
Accept: text/plain; charset=utf-8

200 OK
Content-Type: text/plain; charset=utf-8
ETag: "<sha256-of-bytes>"

<file bytes>
```

Studio (M6) ships a reference resolver that talks to GitHub, GitLab,
Bitbucket, and a generic OCI image-extract path. Self-hosted users can
plug in their own.

## 5. Privacy & Security

- `ext_sourcemap` reveals repository names and (transitively) source
  code paths. Backends with multi-tenant indexes MUST NOT expose the
  field across tenants.
- `repo` MAY contain credentials in URL form (`https://user:token@…`).
  SDKs MUST strip user-info before emitting.
- Source resolvers SHOULD authenticate callers and SHOULD redact
  files matched by the consumer's `.gitattributes` `export-ignore` or
  equivalent policy file.
- Source bytes are not job data; they are not subject to GDPR
  data-subject access requests in the OJS data plane. Resolvers MAY
  apply their own redaction policies.

## 6. Compatibility

- This extension is purely additive. Backends, SDKs, and tools that
  do not implement it SHOULD round-trip the field unchanged through
  storage and APIs.
- The field name is namespaced (`ext_sourcemap`); collisions are
  vendor-error and not the concern of this spec.

## 7. Open Questions

1. Should `lines` be a list of ranges to support handlers spread
   across decorators, mixins, or generated wrappers?
2. Do we want a binary-only mode (`vcs=none`, `build_id` set, no
   `repo`) for closed-source handlers, and what does the resolver
   return then — a disassembly?
3. Should the resolver protocol carry a content-addressable cache
   layer (CAS) so cold debuggers don't pull entire repos?

These will be answered in the Stage-1 RFC.

## 8. References

- OCI Image Format Specification §6 (Digests):
  https://github.com/opencontainers/image-spec/blob/main/descriptor.md#digests
- Source-Map v3 specification (TC39 stage 4):
  https://tc39.es/source-map/
- LLVM build-id documentation:
  https://llvm.org/docs/AdvancedBuilds.html
- OJS Execution History extension: `spec/spec/ojs-execution-history.md`
