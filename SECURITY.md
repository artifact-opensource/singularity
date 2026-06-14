# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Singularity, please report it responsibly.

**Email:** ali.shakil@artifactvirtual.com  
**Subject:** `[SECURITY] Singularity — <brief description>`

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will acknowledge receipt within 48 hours and provide a timeline for resolution.

## Security Model

### Approval Gates
All mutation operations (executive spawns, POA deployments, production actions) require explicit human approval. Monitoring and auditing are autonomous; changes are gated.

### Credential Management
- Environment variables for all secrets (never hardcoded)
- `.env` files excluded from version control
- Secrets vault with Fernet encryption for at-rest storage
- Config examples contain only placeholder values

### Tool Execution
- Sandboxed executor with timeout enforcement
- Output size limits to prevent resource exhaustion
- Per-role tool permission scoping
- No arbitrary code execution without explicit tool definitions

### LLM Provider Security
- No credentials transmitted to LLM providers beyond API authentication
- Provider chain operates with circuit breakers to prevent cascade failures
- Local/qorvex mode available via Ollama (zero external dependencies)

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |
