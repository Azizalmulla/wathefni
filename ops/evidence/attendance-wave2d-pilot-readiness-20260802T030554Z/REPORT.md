# Attendance Wave 2D — Real-device pilot readiness & exception operations

**Stamp:** `20260802T030554Z`  
**Mode:** Local + staging qualification only. No production deploy. No real customer device. No real punch ingest. No QR/GPS/kiosk UI. Frozen modules unchanged.

## Result

| Suite | Result |
|---|---|
| Local qualify | **PASS 53/0** (includes E360 + Onboarding freezes) |
| Staging qualify | **PASS 52/0** (freezes skipped in-process — staging skew; local freezes are the freeze proof) |
| Evidence leak scan (local pack) | **PASS** |
| Evidence leak scan (staging pack) | **PASS** |

## Modules delivered

| File | Role |
|---|---|
| `attendance_capture_secrets.py` | Secret-handling contract, argv safety, EnvironmentFile writer, leak scan, qualify gate |
| `attendance_capture_registry.py` | Customer/site/device/connector registration, ownership, rotate/revoke/reconnect |
| `attendance_capture_remediation.py` | HR exception queue, mapping approve/reject/replay, payroll exclusion, optimistic concurrency |
| `attendance_capture_health.py` | Connector health dashboard contract (online/offline/lag/failures/quarantine) |
| `attendance_capture_compat.py` | Read-only BioTime compatibility probe (`ingest=false`) |
| `smoke-test-attendance-capture-wave2d.py` | Qualification suite |
| `ops/ATTENDANCE_CONNECTOR_SECRET_RUNBOOK.md` | Rotate / revoke / leak incident runbook |
| `ops/ATTENDANCE_PILOT_INSTALLATION_CHECKLIST.md` | Network, firewall, BioTime, timezone, fields, security, exceptions |
| `ops/qualify-attendance-wave2d-staging.sh` | Local + staging qualify (secret-safe copy) |

## Secret-handling contract

- Never pass passwords/tokens/keys on argv or plaintext curl in deploy scripts  
- Load only from mode-`600` EnvironmentFile or sealed Fernet vault  
- Redact before tee/log/evidence write; finding excerpts are redacted  
- `scan_paths` + `qualify_or_block` must PASS or qualification is blocked  
- On exposure: rotate → revoke → reconnect → re-qualify  

**Proven:** argv flag blocked · EnvironmentFile `600` · clean pack PASS · simulated `BIOTIME_PASSWORD=…` exposure DETECTED + BLOCKS qualify · `safe_error` redacts · finding excerpts never echo secrets.

## Connector registration model

`site → device(terminal_sn) → connector(secrets sealed)` with:

- Cross-tenant device/connector registration **denied**  
- Same `terminal_sn` owned by another tenant **fail-closed**  
- `verify_device_ownership` wrong-tenant → `wrong_tenant_device`  
- Activate / rotate / revoke with `row_version` optimistic concurrency  
- `reconnect_after_rotate` returns presence flags only (`secrets=[REDACTED]`)  
- Revoked connectors refuse reconnect  

## HR exception workflow

Exception kinds: `unknown_employee`, `unknown_device`, `missing_check_in`, `missing_check_out`, `ambiguous_punch_order`, `duplicate_conflict`, `connector_lag`, `connector_offline`.

- Unknown mappings quarantine (no payroll) → remediation → **approve then replay** into Wave 1 authority  
- Missing / ambiguous remain `payroll_excluded` while open/rejected  
- Reject + enqueue actions are idempotent  
- Manager self-action denied · manager scope denied · cross-tenant denied  
- Audit trail + `row_version` on every decision  

## Health dashboard contract

`attendance_connector_health_wave2d_v1` fields: connector_id, company_code, site_id, status (`online|offline|degraded|revoked`), last_sync_at, lag_seconds, failure_count, last_error, quarantined_events, open_remediation, checkpoint, connector_version, alerts.

Alerts proven: offline, lag critical, recovery clears offline/lag, revoked.

## Pilot installation checklist

See `ops/ATTENDANCE_PILOT_INSTALLATION_CHECKLIST.md` (also copied under evidence `docs/`). Covers network/firewall, BioTime version, timezone, required event fields, security, exception ops, Wave 1 authority path, freeze regressions, single-device allowlist sign-off.

## Read-only compatibility

`run_readonly_compat` authenticates, samples transaction fields, maps to canonical for privacy checks, **never sets ingest=true**, never writes authority.

## Proven scenarios (Wave 2D)

Secrets never in deploy/app evidence after redact · simulated leak blocks qualify · rotate/revoke/reconnect · wrong-tenant registration fail-closed · unknown → remediation → approve/replay · missing/ambiguous payroll excluded · offline/lag alerts + recovery · idempotent remediation · manager/self/cross-tenant denial · accepted punches via Wave 1 authority · E360 + Onboarding freezes (local).

## Remaining blockers (before one allowlisted real-device pilot)

1. Customer-signed pilot checklist incomplete (network, BioTime version, single `terminal_sn` allowlist)  
2. Supplier/site read-only compat against **their** BioTime (not lab fixture) still pending  
3. Staging freeze scripts skewed vs local (does not block 2D core; refresh staging freeze helpers before prod pilot)  
4. No production Wave 2D deploy / agent unit EnvironmentFile rollout yet  
5. Real punch ingest flag still off — requires a separate allowlisted pilot wave with rollback owner  
6. HR UI for remediation queue not built (API/contract only in this wave)

## GO / NO-GO — one allowlisted real-device pilot

**NO-GO** for connecting a real customer attendance device or ingesting real punches.

**CONDITIONAL GO** only after: checklist sign-off · customer read-only compat PASS · leak scan green on pilot deploy evidence · rotate/revoke drill on that connector · single terminal allowlist named · separate pilot enablement wave.

Wave 2D operational/security readiness for **staging qualification of the exception + secret path**: **PASS**.

## Non-goals confirmed

No real device · no real punch ingest · no QR/GPS/kiosk UI · no frozen-module changes · no production deploy of 2D.
