# Open Job Spec: Security Considerations

| Field        | Value                                          |
|-------------|------------------------------------------------|
| **Title**   | OJS Security Considerations                    |
| **Version** | 1.0.0-rc.1                                     |
| **Date**    | 2026-02-15                                     |
| **Status**  | Release Candidate 1                            |
| **Layer**   | Cross-Cutting Concern                          |
| **URI**     | `urn:ojs:spec:security`                        |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Notational Conventions](#2-notational-conventions)
3. [Terminology](#3-terminology)
4. [Threat Model](#4-threat-model)
5. [Transport Security](#5-transport-security)
6. [Authentication](#6-authentication)
7. [Authorization](#7-authorization)
8. [Input Validation and Sanitization](#8-input-validation-and-sanitization)
9. [Payload Security](#9-payload-security)
10. [Denial of Service Protection](#10-denial-of-service-protection)
11. [Audit Logging](#11-audit-logging)
12. [Secrets Management](#12-secrets-management)
13. [Conformance Requirements](#13-conformance-requirements)
14. [Prior Art](#14-prior-art)
15. [Examples](#15-examples)

---

## 1. Introduction

Background job processing systems occupy a privileged position in application architectures. They execute arbitrary workloads, handle sensitive data in job arguments, and operate with elevated permissions to access databases, external APIs, and internal services. A compromised job system can exfiltrate data, escalate privileges, or disrupt business-critical workflows.

Despite this, most job processing systems treat security as an afterthought — delegating authentication, authorization, and transport security entirely to the deployment environment with no guidance or normative requirements. This leaves operators to reinvent security patterns for every deployment, often with gaps.

This specification defines security requirements and guidance for OJS implementations. It covers transport security, authentication, authorization, input validation, payload protection, denial-of-service mitigation, audit logging, and secrets management. The goal is to ensure that conformant OJS deployments meet a baseline security posture suitable for production environments handling sensitive workloads.

### 1.1 Scope

This specification defines:

- A threat model for OJS deployments identifying trust boundaries and attack surfaces.
- Normative requirements for transport security, authentication, and authorization.
- Input validation rules for all externally provided data.
- Audit logging requirements for security-relevant events.
- Guidance for secrets management and payload protection.

This specification does **not** define:

- Specific cryptographic implementations (see [ojs-encryption.md](./ojs-encryption.md) for payload encryption).
- Network architecture or firewall rules (deployment concern).
- Application-level security within job handlers (application concern).

---

## 2. Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) [[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)] [[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)] when, and only when, they appear in ALL CAPITALS, as shown here.

Every MUST requirement includes a rationale explaining why the requirement is mandatory.

---

## 3. Terminology

| Term                | Definition                                                                                          |
|---------------------|-----------------------------------------------------------------------------------------------------|
| principal           | An authenticated identity (user, service, or worker) interacting with the OJS backend.              |
| credential          | A secret value used to prove a principal's identity (API key, token, certificate).                   |
| threat actor        | An entity attempting to exploit vulnerabilities in the system, whether external or internal.         |
| trust boundary      | A logical border where the level of trust changes between components.                               |
| data plane          | The path through which jobs flow: enqueue, dispatch, execute, acknowledge.                          |
| control plane       | The path through which administrative operations flow: configuration, monitoring, management.       |
| tenant              | A logical isolation unit in a multi-tenant deployment (see [ojs-multi-tenancy.md](./ojs-multi-tenancy.md)). |
| mTLS                | Mutual TLS — both client and server present certificates for authentication.                        |
| least privilege     | The principle of granting only the minimum permissions required for a task.                          |
| credential rotation | The process of replacing active credentials with new ones, ideally without downtime.                |

---

## 4. Threat Model

### 4.1 Trust Boundaries

An OJS deployment has four trust boundaries where security controls MUST be enforced. Rationale: each boundary represents a point where an untrusted or partially trusted component communicates with a more privileged component.

```
┌─────────────┐    TB-1     ┌─────────────┐    TB-2     ┌─────────────┐
│  Producer    │────────────▶│   Backend   │────────────▶│   Worker    │
│ (untrusted)  │             │  (trusted)  │◀────────────│ (semi-trust)│
└─────────────┘             └─────────────┘    TB-3     └─────────────┘
                                   ▲
                              TB-4 │
                            ┌──────┴──────┐
                            │   Admin /   │
                            │  Operator   │
                            └─────────────┘
```

| Boundary | From → To            | Trust Level | Key Risks                                              |
|----------|----------------------|-------------|--------------------------------------------------------|
| TB-1     | Producer → Backend   | Untrusted   | Malicious job injection, payload manipulation, DoS      |
| TB-2     | Backend → Worker     | Semi-trusted| Job tampering in transit, unauthorized job dispatch     |
| TB-3     | Worker → Backend     | Semi-trusted| Spoofed acknowledgments, false heartbeats, data exfil   |
| TB-4     | Admin → Backend      | Privileged  | Credential theft, unauthorized bulk operations          |

### 4.2 Cross-Tenant Threats

In multi-tenant deployments, an additional class of threats arises:

- **Tenant data leakage**: One tenant's job arguments visible to another tenant's workers.
- **Tenant impersonation**: A producer submitting jobs on behalf of another tenant.
- **Resource exhaustion**: One tenant consuming all processing capacity (see [ojs-multi-tenancy.md](./ojs-multi-tenancy.md) for noisy neighbor mitigation).

### 4.3 Threat Table

| Threat                      | Description                                                        | Mitigation                                           | Spec Reference  |
|-----------------------------|--------------------------------------------------------------------|------------------------------------------------------|-----------------|
| Eavesdropping               | Attacker intercepts job payloads in transit                        | TLS on all connections                               | §5              |
| Credential theft            | Stolen API keys or tokens used to submit malicious jobs            | Token rotation, short-lived tokens                   | §6, §12         |
| Unauthorized enqueue        | Unauthenticated producer submits jobs                              | Mandatory authentication on enqueue                  | §6              |
| Privilege escalation        | Producer gains worker or admin privileges                          | Role-based authorization, least privilege             | §7              |
| Job injection               | Malicious job type or arguments bypass validation                  | Input validation, type allowlists                    | §8              |
| Payload data leakage        | Sensitive args exposed in logs or dashboards                       | Payload encryption, log redaction                    | §9, §11         |
| Denial of service           | Flood of enqueue requests overwhelms the backend                   | Rate limiting, backpressure                          | §10             |
| Worker impersonation        | Rogue process claims to be an authorized worker                    | Worker authentication, mTLS                          | §6.2            |
| Tenant isolation violation  | Cross-tenant data access in shared deployments                     | Tenant-scoped authorization                          | §7.4            |
| Audit evasion               | Attacker modifies or disables audit logs                           | Append-only logging, log integrity                   | §11             |

---

## 5. Transport Security

### 5.1 TLS Requirements

Implementations MUST require TLS for all client-to-backend and worker-to-backend connections in production deployments. Rationale: without transport encryption, job payloads (which frequently contain PII, credentials, and business data) are transmitted in plaintext and vulnerable to eavesdropping and tampering.

Implementations MUST support TLS 1.2 as the minimum protocol version. Rationale: TLS 1.0 and 1.1 have known vulnerabilities (BEAST, POODLE) and are deprecated by [RFC 8996](https://www.rfc-editor.org/rfc/rfc8996).

Implementations SHOULD support TLS 1.3 and SHOULD prefer it when both endpoints support it. Rationale: TLS 1.3 removes insecure cipher suites, reduces handshake latency, and provides forward secrecy by default.

### 5.2 Certificate Validation

Implementations MUST validate server certificates against a trusted certificate authority (CA) by default. Rationale: without certificate validation, connections are vulnerable to man-in-the-middle attacks.

Implementations MUST NOT disable certificate validation in production configurations. Implementations MAY allow disabling certificate validation for local development when explicitly configured (e.g., `tls_verify: false`), but MUST log a warning when this is active.

### 5.3 Mutual TLS (mTLS)

Implementations SHOULD support mTLS for worker-to-backend communication. Rationale: mTLS provides strong worker identity verification without relying on shared secrets, and prevents unauthorized processes from connecting as workers.

When mTLS is enabled, the backend MUST verify the client certificate against a configured CA or certificate allowlist. The backend MUST reject connections with expired, revoked, or untrusted client certificates.

### 5.4 Cipher Suite Requirements

Implementations MUST NOT negotiate cipher suites using:

- RC4, DES, or 3DES (broken or weak ciphers).
- NULL encryption (no encryption).
- Export-grade ciphers (intentionally weakened).
- Static RSA key exchange (no forward secrecy).

Rationale: these cipher suites have known weaknesses that undermine the security guarantees of TLS.

---

## 6. Authentication

### 6.1 Producer Authentication

Implementations MUST require authentication for all enqueue operations. Rationale: unauthenticated enqueue allows any network-adjacent attacker to inject arbitrary jobs into the system.

Implementations MUST support at least one of the following authentication mechanisms:

| Mechanism                    | Description                                                       | Recommended For              |
|------------------------------|-------------------------------------------------------------------|------------------------------|
| API key                      | Long-lived secret sent via `Authorization: Bearer <key>` header   | Internal services            |
| JWT (JSON Web Token)         | Short-lived signed token with claims                              | Microservices, SSO           |
| OAuth 2.0 client credentials | Token obtained via client_id/client_secret exchange               | Third-party integrations     |

API keys MUST be at least 256 bits of entropy. Rationale: shorter keys are vulnerable to brute-force attacks.

JWT tokens MUST be validated for signature, expiry (`exp` claim), and issuer (`iss` claim) on every request. Rationale: accepting expired or unsigned tokens defeats the purpose of token-based authentication.

### 6.2 Worker Authentication

Implementations MUST require authentication for worker connections (FETCH, ACK, HEARTBEAT operations). Rationale: an unauthenticated worker endpoint allows rogue processes to dequeue and process jobs, potentially exfiltrating sensitive data.

Implementations MUST support at least one of the following:

- **Shared secret**: A pre-shared token presented during worker registration.
- **mTLS**: Worker identity established via client certificate (see §5.3).
- **Token-based**: A short-lived token obtained via an authentication handshake.

Worker credentials MUST be distinct from producer credentials. Rationale: if a producer credential is compromised, the attacker should not automatically gain the ability to dequeue and process jobs.

### 6.3 Admin API Authentication

Implementations MUST require separate authentication for administrative operations (queue management, job cancellation, bulk operations, configuration changes). Rationale: administrative operations have a higher blast radius than data-plane operations and require stronger access controls.

Admin credentials MUST be distinct from both producer and worker credentials. Rationale: separation of credentials limits the impact of any single credential compromise.

Implementations SHOULD support multi-factor authentication (MFA) for admin API access. Rationale: admin actions (e.g., purging queues, cancelling all jobs) are destructive and warrant additional authentication factors.

### 6.4 Token Rotation and Expiry

Long-lived credentials (API keys, shared secrets) MUST support rotation without service interruption. Implementations MUST accept both the current and previous credential during a configurable grace period. Rationale: credential rotation is a critical operational requirement; systems that require downtime for rotation discourage regular rotation.

JWT and OAuth 2.0 tokens SHOULD have a maximum lifetime of 1 hour. Rationale: short-lived tokens limit the window of exploitation if a token is compromised.

---

## 7. Authorization

### 7.1 Queue-Level Access Control

Implementations MUST support restricting which principals can enqueue to which queues. Rationale: without queue-level access control, any authenticated producer can enqueue jobs to any queue, including internal system queues.

Queue access policies MUST be configurable without code changes (e.g., via configuration file or Admin API). Rationale: access control changes should not require redeployment.

### 7.2 Operation-Level Permissions

Implementations MUST enforce operation-level permissions. The following operations MUST be individually authorizable:

| Operation    | Description                                        |
|--------------|----------------------------------------------------|
| `enqueue`    | Submit a new job to a queue                        |
| `dequeue`    | Fetch a job for processing (worker)                |
| `cancel`     | Cancel a pending or active job                     |
| `inspect`    | Read job details, status, and arguments            |
| `admin`      | Manage queues, configuration, and bulk operations  |

Rationale: coarse-grained authorization (all-or-nothing) violates the principle of least privilege and increases the blast radius of compromised credentials.

### 7.3 Role-Based Access Model

Implementations SHOULD define the following standard roles:

| Role       | Permitted Operations                           | Description                                    |
|------------|------------------------------------------------|------------------------------------------------|
| producer   | `enqueue`                                      | Can submit jobs to authorized queues           |
| worker     | `dequeue`                                      | Can fetch and process jobs from assigned queues |
| operator   | `enqueue`, `cancel`, `inspect`                 | Can manage individual jobs and view status      |
| admin      | `enqueue`, `cancel`, `inspect`, `admin`        | Full access to all operations                  |

Custom roles beyond these four MAY be defined by implementations.

### 7.4 Multi-Tenant Authorization

In multi-tenant deployments, authorization MUST be scoped to the authenticated tenant. A principal authenticated as tenant A MUST NOT be able to:

- Enqueue jobs that will be processed by tenant B's workers.
- Dequeue or inspect jobs belonging to tenant B.
- Cancel or modify jobs belonging to tenant B.

Rationale: tenant isolation is a fundamental security requirement in multi-tenant systems; violations can result in data breaches and regulatory non-compliance.

### 7.5 Permission Matrix

The following matrix defines the minimum authorization model:

| Operation / Role | Producer | Worker | Operator | Admin |
|------------------|----------|--------|----------|-------|
| Enqueue          | ✅       | ❌     | ✅       | ✅    |
| Dequeue (FETCH)  | ❌       | ✅     | ❌       | ✅    |
| ACK / NACK       | ❌       | ✅     | ❌       | ✅    |
| Cancel job       | ❌       | ❌     | ✅       | ✅    |
| Inspect job      | ❌       | ❌     | ✅       | ✅    |
| List queues      | ❌       | ❌     | ✅       | ✅    |
| Purge queue      | ❌       | ❌     | ❌       | ✅    |
| Manage config    | ❌       | ❌     | ❌       | ✅    |
| Manage users     | ❌       | ❌     | ❌       | ✅    |

Implementations MUST enforce at least this permission model. Implementations MAY provide more granular controls.

---

## 8. Input Validation and Sanitization

### 8.1 Job Type Validation

Implementations MUST validate the `type` field against a configurable allowlist of registered job types. Rationale: unrestricted job types allow attackers to trigger arbitrary handler code or cause handler-not-found errors that pollute dead-letter queues.

The allowlist SHOULD be maintained via configuration or the Admin API. Jobs with unregistered types MUST be rejected with a `422 Unprocessable Entity` response.

### 8.2 Args Validation

Implementations MUST enforce a maximum payload size for the `args` field. The default limit SHOULD be 1 MiB. Rationale: unbounded payloads can exhaust backend memory and storage.

Implementations MUST validate that `args` is valid JSON (when using the JSON format). Malformed JSON MUST be rejected at the API boundary.

Implementations SHOULD support schema validation for `args` (e.g., JSON Schema) when configured for a job type. Rationale: schema validation prevents injection of unexpected fields that could exploit downstream handler logic.

Implementations MUST NOT evaluate or execute `args` content as code at any point in the job lifecycle. Rationale: treating job arguments as executable code enables remote code execution attacks.

### 8.3 Metadata Validation

Implementations MUST validate the `meta` field to prevent header injection. Specifically:

- Meta keys MUST match the pattern `^[a-zA-Z0-9_.-]{1,128}$`. Rationale: unrestricted key names can be used to inject HTTP headers or exploit downstream systems that use meta keys in header construction.
- Meta values MUST NOT contain newline characters (`\r`, `\n`). Rationale: newlines in header values enable HTTP response splitting attacks.
- The total size of all meta key-value pairs MUST NOT exceed 64 KiB. Rationale: unbounded metadata can be used for DoS.

### 8.4 Queue Name Validation

Implementations MUST validate queue names against the pattern `^[a-zA-Z0-9_.-]{1,255}$`. Rationale: unrestricted queue names can be used for path traversal attacks in backends that map queues to filesystem paths, or for injection attacks in backends that use queue names in SQL queries.

Queue names MUST be case-sensitive. Queue names MUST NOT begin with the prefix `_ojs_` (reserved for internal system queues).

### 8.5 Unknown Attribute Rejection

Implementations MUST reject job envelopes containing attributes not defined in the OJS specification or registered extensions. Rationale: accepting unknown attributes risks forward-compatibility issues and can mask injection attempts.

When unknown attributes are detected, the backend MUST return a `422 Unprocessable Entity` response with a clear error message listing the unexpected attributes.

---

## 9. Payload Security

### 9.1 Encryption at Rest

For sensitive payloads, implementations SHOULD use the codec architecture defined in [ojs-encryption.md](./ojs-encryption.md) to encrypt `args` and `meta` before they reach the backend. Rationale: encryption at rest protects sensitive data from unauthorized access via database dumps, backups, or compromised operator accounts.

### 9.2 Sensitive Data Handling

Producers SHOULD avoid placing highly sensitive data (passwords, credit card numbers, SSNs) directly in job `args`. Instead, producers SHOULD store sensitive data in a secure vault and pass a reference (e.g., a vault path or token) in `args`.

When sensitive data must be included in `args`, producers MUST use the encryption codec (see [ojs-encryption.md](./ojs-encryption.md)).

### 9.3 Data Classification

Implementations SHOULD support a `data_classification` field in `meta` to indicate the sensitivity level of job payloads:

| Classification | Description                                           | Handling Requirements                     |
|----------------|-------------------------------------------------------|-------------------------------------------|
| `public`       | Non-sensitive data                                    | Standard handling                         |
| `internal`     | Internal business data                                | Restrict dashboard visibility             |
| `confidential` | PII, financial data                                   | Encrypt at rest, redact from logs         |
| `restricted`   | Highly regulated data (PCI, HIPAA)                    | Encrypt at rest and in transit, audit all access |

### 9.4 Logging Considerations

Implementations MUST NOT log the full `args` or `meta` fields at INFO level or above in production. Rationale: job arguments frequently contain PII, credentials, and business-sensitive data; logging them creates an additional data leakage vector.

Implementations MAY log a truncated or redacted summary (e.g., `"args": "<redacted, 2.3 KiB>"`) for debugging purposes.

Implementations MUST NOT include credentials, tokens, or encryption keys in any log output at any level.

---

## 10. Denial of Service Protection

### 10.1 Rate Limiting

Implementations MUST support rate limiting on enqueue operations. See [ojs-rate-limiting.md](./ojs-rate-limiting.md) for the full rate limiting specification. Rationale: without rate limiting, a single misbehaving or compromised producer can flood the system with jobs, degrading service for all consumers.

Per-principal rate limits SHOULD be configurable. The default enqueue rate limit SHOULD be no more than 1,000 jobs per second per principal.

### 10.2 Queue Depth Limits

Implementations MUST support configurable queue depth limits. See [ojs-backpressure.md](./ojs-backpressure.md) for the full backpressure specification. Rationale: unbounded queue growth can exhaust backend storage and memory.

When a queue reaches its depth limit, the backend MUST respond according to the configured backpressure strategy (reject, block, or drop oldest).

### 10.3 Payload Size Limits

Implementations MUST enforce maximum payload size limits on all API endpoints:

| Field      | Default Maximum | Configurable |
|------------|-----------------|--------------|
| `args`     | 1 MiB           | Yes          |
| `meta`     | 64 KiB          | Yes          |
| Full body  | 2 MiB           | Yes          |

Rationale: oversized payloads can exhaust memory, saturate network bandwidth, and degrade backend performance.

Requests exceeding the configured limit MUST be rejected with a `413 Payload Too Large` response before the full body is read.

### 10.4 Connection Limits

Implementations MUST support configurable per-client connection limits. Rationale: a single client opening an excessive number of connections can exhaust server resources (file descriptors, memory, threads).

The default per-client connection limit SHOULD be 100. Connections exceeding the limit MUST be rejected with a `429 Too Many Requests` response.

### 10.5 Slowloris Prevention

Implementations MUST enforce request timeouts on all API endpoints, including long-polling FETCH endpoints. Rationale: slow-read attacks (Slowloris) can tie up server resources indefinitely by keeping connections open without completing requests.

- Request header read timeout MUST default to no more than 30 seconds.
- Request body read timeout MUST default to no more than 60 seconds.
- Long-polling FETCH endpoints MUST have a maximum poll duration (SHOULD default to 30 seconds) after which the server returns an empty response.
- Idle connections MUST be closed after a configurable timeout (SHOULD default to 120 seconds).

---

## 11. Audit Logging

### 11.1 Events That MUST Be Logged

Implementations MUST produce audit log entries for the following security-relevant events. Rationale: audit logs are essential for incident investigation, compliance, and detecting unauthorized access.

| Event Category         | Events                                                                     |
|------------------------|----------------------------------------------------------------------------|
| Authentication         | Login success, login failure, token refresh, token revocation              |
| Authorization          | Permission denied, role change, access policy modification                 |
| Job lifecycle          | Job cancelled (by whom), job purged, bulk delete                           |
| Admin actions          | Queue created/deleted, configuration changed, rate limit overridden        |
| Security               | TLS handshake failure, certificate rejected, credential rotation           |

### 11.2 Log Format

Audit log entries MUST be structured (JSON or equivalent). Each entry MUST include:

| Field            | Type     | Description                                        |
|------------------|----------|----------------------------------------------------|
| `timestamp`      | string   | ISO 8601 timestamp with timezone                   |
| `event_type`     | string   | Dot-delimited event identifier                     |
| `principal`      | string   | Authenticated identity that triggered the event    |
| `source_ip`      | string   | Client IP address                                  |
| `correlation_id` | string   | Request correlation ID for tracing                 |
| `outcome`        | string   | `success` or `failure`                             |
| `detail`         | object   | Event-specific data                                |

Rationale: structured logs enable automated analysis, alerting, and SIEM integration.

### 11.3 What NOT to Log

Audit logs MUST NOT contain:

- Credentials (API keys, tokens, passwords, certificates).
- Full job `args` when classified as `confidential` or `restricted`.
- Encryption keys or key material.

Rationale: audit logs are often stored in less-secure systems (log aggregators, SIEM) and may be accessible to a wider audience than the job data itself.

When referencing credentials in audit logs, implementations MUST use a truncated identifier (e.g., `"api_key": "sk_...a1b2"`).

---

## 12. Secrets Management

### 12.1 Backend Credentials

Backend credentials (database connection strings, message broker passwords) MUST NOT be stored in source code or configuration files committed to version control. Rationale: credentials in source code are the most common cause of data breaches.

Implementations MUST support loading credentials from at least one of:

- Environment variables.
- A secrets management service (e.g., HashiCorp Vault, AWS Secrets Manager, Azure Key Vault).
- A file mounted at runtime (e.g., Kubernetes secrets).

### 12.2 Encryption Keys

For implementations supporting the encryption codec ([ojs-encryption.md](./ojs-encryption.md)):

- Encryption keys MUST NOT be stored alongside encrypted data. Rationale: co-located keys and ciphertext provide no security.
- Key rotation MUST be supported without re-encrypting existing jobs. Rationale: re-encryption of large job backlogs is operationally infeasible.
- Implementations SHOULD use envelope encryption (data key encrypted by a master key).

### 12.3 API Keys and Tokens

- API keys MUST be stored hashed (using bcrypt, scrypt, or Argon2) in the backend database. Rationale: if the database is compromised, plaintext API keys would allow immediate unauthorized access.
- API keys MUST NOT be returned in full after initial creation. Rationale: the initial creation response is the only time the full key should be visible.
- Implementations MUST support revoking individual API keys without affecting other keys.

### 12.4 Environment Variable Guidance

When using environment variables for secrets:

- Variable names SHOULD follow the pattern `OJS_SECRET_<PURPOSE>` (e.g., `OJS_SECRET_DB_PASSWORD`, `OJS_SECRET_API_KEY`).
- Implementations MUST NOT log environment variable values.
- Implementations SHOULD warn at startup if secrets appear to be set via command-line arguments (which are visible in process listings).

### 12.5 Secret Rotation Without Downtime

Implementations MUST support zero-downtime secret rotation using one of these strategies:

- **Dual-read**: Accept both old and new credentials during a grace period. The grace period SHOULD be configurable and SHOULD default to 24 hours.
- **Hot-reload**: Watch for credential changes and reload without restart.
- **External rotation**: Delegate rotation to a secrets manager that provides versioned access.

Rationale: systems that require downtime for credential rotation discourage regular rotation, leading to long-lived credentials that increase risk.

---

## 13. Conformance Requirements

### 13.1 Required Capabilities

An implementation declaring conformance with this security specification MUST support:

| ID      | Requirement                                                                                           |
|---------|-------------------------------------------------------------------------------------------------------|
| SEC-001 | TLS 1.2 or higher on all production connections.                                                      |
| SEC-002 | Certificate validation enabled by default; no production bypass.                                      |
| SEC-003 | Authentication required on all enqueue operations.                                                    |
| SEC-004 | Authentication required on all worker operations (FETCH, ACK, HEARTBEAT).                             |
| SEC-005 | Separate authentication for admin API operations.                                                     |
| SEC-006 | Queue-level access control (restrict enqueue per principal).                                          |
| SEC-007 | Operation-level permissions (enqueue, dequeue, cancel, inspect, admin).                               |
| SEC-008 | Job type validation against a configurable allowlist.                                                 |
| SEC-009 | Maximum payload size enforcement on all API endpoints.                                                |
| SEC-010 | Queue name validation against `^[a-zA-Z0-9_.-]{1,255}$`.                                            |
| SEC-011 | Meta key validation against `^[a-zA-Z0-9_.-]{1,128}$`; no newlines in values.                       |
| SEC-012 | Rejection of unknown attributes in job envelopes.                                                     |
| SEC-013 | Args and meta fields not logged in full at INFO level or above.                                       |
| SEC-014 | Rate limiting on enqueue operations.                                                                  |
| SEC-015 | Configurable queue depth limits.                                                                      |
| SEC-016 | Per-client connection limits.                                                                         |
| SEC-017 | Request timeouts on all API endpoints including long-polling.                                         |
| SEC-018 | Structured audit logging of authentication failures and permission denials.                            |
| SEC-019 | Credentials not stored in source code; loaded from environment, secrets manager, or mounted files.    |
| SEC-020 | API keys stored hashed in the backend database.                                                       |
| SEC-021 | Zero-downtime credential rotation support.                                                            |
| SEC-022 | Tenant-scoped authorization in multi-tenant deployments.                                              |

### 13.2 Recommended Capabilities

| ID       | Requirement                                                                                          |
|----------|------------------------------------------------------------------------------------------------------|
| SEC-R001 | TLS 1.3 preferred when supported by both endpoints.                                                  |
| SEC-R002 | mTLS for worker-to-backend communication.                                                            |
| SEC-R003 | MFA for admin API access.                                                                            |
| SEC-R004 | JSON Schema validation for job `args` per job type.                                                  |
| SEC-R005 | Data classification support via `meta.data_classification`.                                          |
| SEC-R006 | Payload encryption via the codec architecture (ojs-encryption.md).                                   |
| SEC-R007 | Envelope encryption for key management.                                                              |

---

## 14. Prior Art

| System / Standard        | Security Approach                                                                                    |
|--------------------------|------------------------------------------------------------------------------------------------------|
| **OAuth 2.0** ([RFC 6749](https://www.rfc-editor.org/rfc/rfc6749)) | Industry-standard token-based authorization framework. OJS adopts OAuth 2.0 client credentials flow as a supported authentication mechanism and follows OAuth 2.0's separation of access tokens from refresh tokens. |
| **CloudEvents** ([Security spec](https://github.com/cloudevents/spec/blob/main/cloudevents/extensions/security.md)) | Defines a `security` extension attribute for carrying authentication context in event payloads. OJS follows CloudEvents' approach of separating transport security from payload security. |
| **RabbitMQ** ([Access Control](https://www.rabbitmq.com/docs/access-control)) | Provides vhost-level isolation, per-user permissions (configure, write, read) on exchanges and queues, and topic-level authorization. OJS's queue-level access control and role model are influenced by RabbitMQ's granular permission system. |
| **Temporal** ([Security model](https://docs.temporal.io/security)) | Namespace-level isolation, mTLS for all inter-component communication, codec server for client-side encryption. OJS adopts Temporal's mTLS recommendation for worker connections and its codec server concept for payload encryption. |
| **AWS SQS** ([IAM policies](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-authentication-and-access-control.html)) | IAM-based per-queue, per-action authorization policies. OJS's permission matrix is modeled after SQS's action-level IAM policies (`sqs:SendMessage`, `sqs:ReceiveMessage`, `sqs:DeleteMessage`). |
| **OWASP** ([API Security Top 10](https://owasp.org/API-Security/)) | Comprehensive API security guidelines covering broken authentication, excessive data exposure, rate limiting, and injection. OJS's input validation and rate limiting requirements align with OWASP API Security Top 10 recommendations. |

---

## 15. Examples

### 15.1 Authenticated Job Submission

A producer submitting a job with JWT authentication:

**Request:**

```http
POST /ojs/v1/jobs HTTP/1.1
Host: ojs.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJhdXRoLmV4YW1wbGUuY29tIiwic3ViIjoic3ZjLW9yZGVycyIsInJvbGUiOiJwcm9kdWNlciIsInF1ZXVlcyI6WyJvcmRlcnMiLCJub3RpZmljYXRpb25zIl0sImV4cCI6MTczOTYyODgwMH0.signature
Content-Type: application/json
X-Request-ID: req_a1b2c3d4
X-OJS-Tenant-ID: tenant_acme
```

```json
{
  "type": "order.process",
  "queue": "orders",
  "args": [
    {
      "order_id": "ord_7890",
      "customer_ref": "vault://secrets/customers/cust_456"
    }
  ],
  "meta": {
    "data_classification": "confidential",
    "source_service": "order-api"
  }
}
```

**Response (201 Created):**

```json
{
  "id": "job_01HQ3K5P7X2Y",
  "type": "order.process",
  "queue": "orders",
  "state": "available",
  "created_at": "2026-02-15T10:30:00Z"
}
```

### 15.2 Permission Denied Response

A producer attempting to enqueue to a queue it does not have access to:

**Request:**

```http
POST /ojs/v1/jobs HTTP/1.1
Host: ojs.example.com
Authorization: Bearer eyJhbGci...producer_token
Content-Type: application/json
```

```json
{
  "type": "admin.purge_cache",
  "queue": "_ojs_internal",
  "args": [{}]
}
```

**Response (403 Forbidden):**

```json
{
  "error": {
    "code": "permission_denied",
    "message": "Principal 'svc-orders' does not have 'enqueue' permission on queue '_ojs_internal'.",
    "detail": {
      "principal": "svc-orders",
      "operation": "enqueue",
      "queue": "_ojs_internal",
      "required_role": "admin"
    }
  }
}
```

### 15.3 Audit Log Entry

An audit log entry for a failed authentication attempt:

```json
{
  "timestamp": "2026-02-15T10:31:42.003Z",
  "event_type": "auth.login_failure",
  "principal": "unknown",
  "source_ip": "198.51.100.42",
  "correlation_id": "req_x9y8z7w6",
  "outcome": "failure",
  "detail": {
    "mechanism": "api_key",
    "reason": "invalid_key",
    "key_prefix": "sk_...f3g4",
    "endpoint": "POST /ojs/v1/jobs",
    "user_agent": "ojs-sdk-python/1.2.0"
  }
}
```

An audit log entry for an admin bulk-cancel operation:

```json
{
  "timestamp": "2026-02-15T14:22:10.847Z",
  "event_type": "admin.bulk_cancel",
  "principal": "admin@example.com",
  "source_ip": "10.0.1.50",
  "correlation_id": "req_m3n4o5p6",
  "outcome": "success",
  "detail": {
    "queue": "notifications",
    "filter": {"state": "available", "type": "email.send"},
    "jobs_cancelled": 1247,
    "reason": "Provider outage — cancelling backlog per incident INC-2026-0042"
  }
}
```
