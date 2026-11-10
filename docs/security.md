# Security

## Authentication and admin protection

No default password exists. scripts/setup_admin.py uses a hidden prompt and Argon2 password hashing. Sessions use cryptographically random bearer tokens; only SHA-256 digests are stored server-side. Sessions expire, are revocable, and use HttpOnly SameSite=Strict cookies scoped to /api/admin. Admin mutation endpoints require a per-session CSRF token. Login has a bounded in-process client-address attempt counter; use ingress rate limiting in production. Enable secure cookies with HTTPS.

All admin configuration and analytics endpoints depend on authorization. Public model summaries omit local paths. Normal translator UI does not import or display admin navigation. Client-side route separation is not the authorization boundary; the backend enforces access.

## Provider secrets

Fernet encrypts stored keys using ENCRYPTION_KEY. Keys are never returned after saving and are not included in logs. API responses show only a saved-secret indicator; no key suffix is exposed. A blank key edit preserves the old value. Encryption key must be stored separately from the database and backed up through secret management. .env is ignored by Git and excluded from containers.

External provider base URLs must use HTTPS with an exact server-managed hostname allowlist, default TLS port, and no embedded credentials/query/fragment. Redirects are disabled. Only trusted, administrator-controlled public providers should be allowlisted; DNS ownership and network egress restrictions remain operator responsibilities. Provider endpoints must not be untrusted user-controlled URLs. Remote model code execution is disabled; administrators still need to trust model repositories and weight formats.

## Input and inference limits

Pydantic forbids unknown configuration fields and validates enums, lengths, language mappings, and routing references. Public translation has a configurable character limit and a strict 128-token model limit. No silent truncation occurs. Whitespace-only text is rejected. Audio MIME and streamed bytes are validated, and the decoder verifies actual audio frames under a sample-count duration budget. Temporary files are deleted after processing. Configure ingress body/time limits as a second boundary.

The manager serializes model access and tokenization. Public inference has a four-request in-process admission cap. Before internet exposure, add rate limits, user quotas or authentication, and host resource limits to protect against sustained compute abuse.

## Privacy and logging

Server analytics store no original text, translations, audio, API keys, or auth tokens. Safe fixed error messages are used instead of raw exceptions. Translation text can be sent to external providers selected by administrators; Edge TTS always sends translated text externally. A future privacy preference would need to route only through local speech/translation implementations.

Local history stores up to 40 translations in this browser profile and can be cleared. Other users of a shared browser can access it. Disabling history prevents new persistence; users should clear existing browser history when removing sensitive data. Audio replay regenerates output and does not archive uploaded audio.

Production access logs should avoid sensitive query parameters. No credentials belong in URLs. Retain operational analytics only as long as necessary, and establish a database pruning policy before large-scale deployment.

## Release considerations

Use TLS, exact CORS origins, non-root backend containers, persistent secret management, database backups, dependency vulnerability review, and a trusted administrator boundary. Test authentication, CSRF, secret redaction, malformed uploads, and inference limits during releases. This implementation is not a completed external security audit.

