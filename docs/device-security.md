# Device Security, Authentication & Data Boundary

## 1. Cryptographic Device Identity

Every device participating in AI Supervisor sync is assigned a cryptographic identity:
- `device_id`: Public string identifier (`dev_<12 hex chars>`).
- `device_token`: Secret credential (`tok_<64 hex chars>`).
- `device_token_hash`: Salted SHA-256 hash stored on the sync server and SQLite table.

The server never stores the raw `device_token`. Authentication verifies `hash_device_token(provided_token) == stored_token_hash`.

---

## 2. Instant Revocation Model

If a developer loses a laptop or wishes to decommission an old workstation:
1. The developer triggers device revocation from the Control Room or API (`POST /api/sync/devices/{id}/revoke`).
2. The device status transitions immediately to `REVOKED`.
3. All subsequent push or pull operations by that device fail with `403 Forbidden` (`DeviceRevokedError`).
4. Other devices remain completely unaffected.

---

## 3. Zero-Secret Data Boundary

AI Supervisor guarantees that no API credentials, private keys, passwords, or machine-specific absolute paths ever leave the workstation.

### Recursive Payload Sanitizer
Every record payload is processed through `sync.sanitizer.sanitize_payload()`:
- **API Keys**: OpenAI, Anthropic, GitHub, AWS, and generic `sk-*` tokens are redacted into `[REDACTED_CREDENTIAL]`.
- **Private Keys**: OpenSSH, RSA, DSA, EC, PGP blocks are redacted into `[REDACTED_SECRET]`.
- **Passwords & Dotenv**: Keys containing `password`, `secret`, `credential`, `env_var` are scrubbed into `[REDACTED_CREDENTIAL]`.
- **Host Absolute Paths**: Windows drive paths (`C:\Users\...\file.py`) and Unix root paths (`/home/.../file.py`) are sanitized into project-relative identifiers (`[local_path:/file.py]`).

### Strict Assertion Test
The codebase enforces `assert_payload_is_clean(payload)`. Any payload containing unscrubbed credentials immediately raises `PayloadSanitizationError` before transmission.
