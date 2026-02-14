# Security Policy

## Reporting a Vulnerability

The Open Job Spec team takes security seriously. We appreciate your efforts to responsibly disclose any security issues you find.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please report security vulnerabilities by emailing:

📧 **[security@openjobspec.org](mailto:security@openjobspec.org)**

Include the following in your report:

- A description of the vulnerability
- Steps to reproduce the issue
- The specification document(s) affected
- The potential impact (e.g., data exposure, authentication bypass)
- Any suggested mitigation or fix

## Response Timeline

| Action | Timeline |
|--------|----------|
| Acknowledgment of report | Within 48 hours |
| Initial assessment | Within 5 business days |
| Resolution or mitigation plan | Within 30 days |
| Public disclosure (coordinated) | After fix is available |

## Scope

This security policy covers:

- The OJS specification documents (this repository)
- Reference implementation repositories under the `openjobspec` GitHub organization
- The [openjobspec.org](https://openjobspec.org) website

For security issues in third-party OJS implementations, please contact the respective maintainers directly.

## Security Considerations in the Specification

The OJS specification includes a dedicated security document: [ojs-security.md](spec/ojs-security.md). This covers threat modeling, transport security, authentication, authorization, input validation, and audit logging requirements for all OJS implementations.

## Recognition

We gratefully acknowledge security researchers who help improve OJS. With your permission, we will credit you in the security advisory and CHANGELOG.
