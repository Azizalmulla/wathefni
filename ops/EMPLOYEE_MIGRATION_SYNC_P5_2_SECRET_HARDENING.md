# Employee Migration & Sync P5.2 — Connector Secret Hardening

Contract: `employee_migration_sync_p5_2_secret_hardening` @ `5.2.0`  
Keeps P5.1 scheduler, SFTP, sync pipeline, UI, and P1–P5 authority unchanged.

## Required behavior

- Connector credentials/private keys encrypted at rest via `encrypt_sensitive_text` / Fernet (`WATHEFNI_MAILBOX_SECRET_KEY`)
- Missing or invalid encryption key → **fail closed** on create/update (503 `connector_encryption_*`)
- Never persist submitted credentials if seal fails
- Never silently fall back to plainhex / plaintext
- Sync/scheduler encountering insecure or unreadable secrets → failed `sync_run`, no apply, connection flagged `credentials_require_reentry:*`
- API/UI continue to redact secrets; audits log alg/key_version/reason codes only

## Remediation

`audit_and_remediate_insecure_secrets`:

1. Scan `employee_migration_connection_secrets` for plainhex/plaintext
2. If encryption key available → reseal to Fernet (one-time plainhex read for migration only)
3. Else → delete secret, `status=error`, `schedule_enabled=false`, require admin re-entry

## Boundaries

No full cron expansion · no vendor APIs · no P6 · no Auth Wave 2 Phase 6
