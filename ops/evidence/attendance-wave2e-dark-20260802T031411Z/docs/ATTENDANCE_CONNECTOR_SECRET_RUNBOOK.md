# Attendance Connector Secret Handling Runbook (Wave 2D)

**Audience:** operators deploying BioTime / CSV capture agents  
**Scope:** local / staging / controlled pilot prep. Never put credentials in argv, curl bodies printed to logs, evidence packs, or chat.

## Secret-handling contract

1. Load secrets only from a mode-`600` EnvironmentFile (e.g. `/root/.openclaw/secrets/attendance-capture.env`) or sealed Fernet vault.
2. Never pass `--password`, `--token`, `--api-secret`, or raw key values on the command line.
3. Redact with `attendance_capture_secrets.redact_text` / `safe_error` before any `tee`, journal, or evidence write.
4. Run `scan_paths` on deployment logs and the evidence pack; `qualify_or_block` must PASS or qualification is blocked.
5. On suspected exposure: rotate immediately → revoke connector → reconnect with new secrets → re-qualify.

## Deploy pattern (secret-safe)

```bash
# Write EnvironmentFile (mode 600) — values never echoed
install -m 600 /dev/null /root/.openclaw/secrets/attendance-capture.env
# Use a sealed editor or write_environment_file() — do not cat the file into logs

# systemd unit uses:
# EnvironmentFile=-/root/.openclaw/secrets/attendance-capture.env
systemctl restart wathefni-attendance-capture-agent
```

Forbidden:

- `ssh … "export BIOTIME_PASSWORD=…; python …"`  (ellipsis only — never paste real values)
- `curl -u user:pass … | tee deploy.log`
- Packaging `*.env` into evidence directories

## Credential rotate

1. Generate new BioTime / connector credential on the customer middleware.
2. Call registry `rotate_credentials(connector_id, new_secrets, expected_row_version=…)`.
3. Agent `reconnect_after_rotate` — confirm `has_password` / `has_token` flags only (no secret return).
4. Confirm health returns online; lag recovers.
5. Archive previous sealed blob only in vault history; wipe on revoke.

## Connector revoke

1. `revoke(connector_id, expected_row_version=…, reason=…)`.
2. Sealed credentials are wiped from registry memory/store.
3. Agent must refuse reconnect (`connector_revoked`).
4. Health dashboard status = `revoked`.
5. Open remediation items for offline/lag remain payroll-excluded until closed.

## Leak scan gate

```bash
python -c "
from attendance_capture_secrets import scan_paths, qualify_or_block
import json, sys
r = scan_paths(['ops/evidence/<stamp>/'])
q = qualify_or_block(r)
print(json.dumps(q, indent=2))
sys.exit(0 if q['ok'] else 1)
"
```

Simulated exposure in a log file must produce `blocked: true` and fail qualification.

## Incident: key printed to deploy stdout (Wave 2C lesson)

1. Rotate Fernet / BioTime credentials immediately.
2. Redact historical evidence (`[REDACTED]`).
3. Fix deploy script to redact before `tee`.
4. Re-run leak scan; do not qualify until clean.
