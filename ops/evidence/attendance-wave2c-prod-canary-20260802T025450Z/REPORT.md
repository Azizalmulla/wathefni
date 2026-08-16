# Attendance Wave 2C — Production synthetic BioTime connector canary

**Stamp:** `20260802T025450Z`  
**Local evidence:** `ops/evidence/attendance-wave2c-prod-canary-20260802T025450Z/`  
**Remote:** `/opt/wathefni/production-evidence/attendance-wave2c-prod-canary/20260802T025450Z/`  
**Backup:** `/opt/wathefni/backups/production-pre-attendance-wave2c-20260802T025450Z/`

## Scope kept

- Lab BioTime fixture only (127.0.0.1:19199) — **no real customer device**
- Real clocking disabled; `WATHEFNI_ATTENDANCE_IMPORT=off`
- Synthetic-only authority (`ATTW1C,ATTW2C` markers; phone prefix `965524`)
- QR/GPS/kiosk/POS UI not built/enabled
- Employees 360 / Onboarding freezes green

## Pre-deploy

| Item | Value |
|---|---|
| `app.py` | `e4b8643f…741c63c3` |
| Pre `attendance_authority_wave1.py` | `b556f349…88df5c9` |
| Capture modules | absent |
| WATHEFNI attendance rows | 42 demo |
| Authority punches | 0 |
| Flags | 1C synthetic-only still on |

Backup + `ROLLBACK.sh` written; fingerprint CSV captured.

## Deploy SHAs (final)

| File | SHA256 |
|---|---|
| `app.py` | `e4b8643f9d8b2551b6fbc23604bb97ab6089260d1f15336faf6c372c741c63c3` |
| `attendance_authority_wave1.py` | `f285bc1da763878d3fc429d26ae43eda3a44432c69aa262476a6a4072c8f487d` |
| `attendance_capture_contract.py` | `26d17a986ce2d1d1fd2a388ecf7b9671386588642985dd18ed4be052acb4cde3` |
| `attendance_capture_biotime.py` | `d02a9630f61ea0cb83d81fec6f631369273d33f2729fbfaac6bf449a6989bda6` |
| `attendance_capture_agent.py` | `d5f6cede392e1a01131bb3d6da1e1302138bf514d045733a325bf7504946d0b5` |
| `attendance_capture_csv.py` | `e5803ff1321b356d6f6c1c11078615f9164d35cf3218a28154d5074641fc5cbe` |
| `attendance_capture_pipeline.py` | `049d8d1b4ed6879b135254c5b55112454e991d9a443cbedacb4ff13ba48ea812` |

### Flags

```
WATHEFNI_ATTENDANCE_AUTHORITY=on
WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES=WATHEFNI
WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY=on
WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_KEY_MARKERS=ATTW1C,ATTW2C,W1C-SYNTH|,W2C-SYNTH|
WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965524
WATHEFNI_ATTENDANCE_AUTHORITY_STORE=postgres
WATHEFNI_ATTENDANCE_IMPORT=off
WATHEFNI_DB_POOL_MAX=8
WATHEFNI_CAPTURE_CREDENTIAL_KEY=[REDACTED]  # via EnvironmentFile
```

### Secrets hygiene

- Capture Fernet key provisioned at `/root/.openclaw/secrets/attendance-capture.env` mode `600`
- Initial deploy stdout briefly exposed the key → **key rotated immediately**; evidence redacted to `[REDACTED]`
- Canary asserts secrets absent from evidence JSON

## Canary — PASS 54/0

### Synthetic IDs

| Field | Value |
|---|---|
| employee_key | `WATHEFNI-ATTW2C-312feae3` |
| phone | `965524312fea` |
| device_user_id | `9312` |
| terminal_sn | `LAB-W2C-312FEA` |
| connector_id | `w2c-lab-312feae3` |
| checkpoint | `biotime:2302` |
| quarantine_id | `49f04e4f-3661-4902-bc8e-f23bdc5f6430` |
| projection_id | `8aad537f-ae64-4896-8b44-f7f114f95c8d` |
| snapshot_id | `41ee89c4-9de8-4bca-ae01-4b9b68d658c3` |

### Proofs

- Lab fixture synthetic-only gate PASS  
- Normal + overnight BioTime → projections 480  
- Card/face/biometric **type** metadata; no payloads retained  
- Privacy hard-fail on `fingerprint_image` + `template`  
- Duplicate pulls idempotent; checkpoint resume `biotime:2301/2302`  
- Agent offline queue + reconnect delivery; sealed creds; restart empty outbox  
- Invalid creds fail + rotation recovers; health error_count≥1  
- Unknown user quarantine → mapped replay  
- CSV duplicate across files; XLSX; SFTP digest resume  
- Payroll snapshot worked_minutes=480; approved correction; reimport does not alter snapshot  
- Cross-tenant isolation; cleanup left punches/projections 0  
- Demo 42 fingerprint unchanged; four reals present  

## Backup / rollback

Executed `ROLLBACK.sh`: capture modules removed; wave1 SHA restored to pre-2C; 1C dropin restored → then **redeployed** 2C dark canary. Freezes re-verified green.

## Freezes

- E360 **57/0**  
- Onboarding **54/0**

## Separate verdicts

See `VERDICT.txt`.
