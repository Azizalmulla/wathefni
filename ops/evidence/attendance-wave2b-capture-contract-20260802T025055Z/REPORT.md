# Attendance Wave 2B — Canonical capture, BioTime connector, CSV fallback

**Stamp:** local `20260802T025055Z` · staging evidence `20260802T025320Z`  
**Mode:** Local + staging qualification only. No production deploy. No real device. No real clocking. No QR/GPS/kiosk UI. Frozen modules unchanged.

## Result

| Suite | Result |
|---|---|
| Local qualify | **PASS 44/0** (includes E360 + Onboarding freezes) |
| Staging capture qualify | **PASS 43/0** (freezes skipped in-process; run separately) |
| Staging E360 freeze | **57/0** |
| Staging Onboarding freeze | **54/0** |

## Modules delivered

| File | Role |
|---|---|
| `attendance_capture_contract.py` | Canonical punch, capture_method, privacy sanitizer, mapping/quarantine, health model |
| `attendance_capture_biotime.py` | BioTime REST pull `/iclock/api/transactions/` → canonical |
| `attendance_capture_csv.py` | CSV/XLSX/SFTP fallback → same contract |
| `attendance_capture_agent.py` | Outbound on-prem agent: sqlite outbox, checkpoint, Fernet credentials, health |
| `attendance_capture_pipeline.py` | Sanitize → map → Wave 1 `ingest_punch` |
| `smoke-test-attendance-capture-wave2b.py` | Qualification suite |

Wave 1 `PUNCH_SOURCES` extended with connector sources (`biotime`, `csv`, `sftp`, `file_import`, `capture`) so accepted events land on the immutable punch ledger.

## Canonical punch schema

Required: `company_code`, `source`, `source_event_id`, `device_user_id`, `punched_at`, `direction`  
Capture method: `biometric|face|rfid|card|pin|qr|gps|kiosk|pos|file_import|manual_correction|unknown`  
Optional: `employee_key`, `device_id`, `connector_id`, `connector_version`, `work_date_hint`, `raw_ref`, `metadata`  

**No ZKTeco-specific fields** on the envelope. Vendor scalars only via allowlisted `raw_ref`.

## BioTime API mapping

| BioTime field | Canonical |
|---|---|
| `id` | `source_event_id = biotime:{id}` |
| `emp_code` | `device_user_id` |
| `punch_time` | `punched_at` (Asia/Kuwait if naive) |
| `punch_state` | `direction` (0→in, 1→out, 2→break_start, 3→break_end; configurable) |
| `verify_type` | `capture_method` type only (1→biometric, 2/4→card, 15→face, …) |
| `terminal_sn` | `device_id` |

Forbidden vendor keys/blobs hard-fail before ingest (images, templates, pictureURL, long hex templates). Content hashes (`*_sha256`) are not treated as templates.

## On-prem agent

- Poll BioTime on LAN → encrypt credentials (Fernet) → durable sqlite outbox + checkpoint  
- Outbound upload callback to Wathefni ingest  
- Restart resumes checkpoint; undelivered outbox replays  
- Health: status, last_sync, lag, errors, checkpoint, version  

## CSV/SFTP workflow

- Parse CSV/XLSX → same canonical punch  
- Idempotency: `csv:{file_sha256}:{row_sha256}` (identical content across filenames collapses)  
- SFTP drop folder watcher; `processed_files` prevents re-import of same digest  
- Safe “reversal”: re-upload is idempotent; punches append-only; payroll snapshots unchanged  

## Pipeline

`vendor event → privacy sanitizer → canonical punch → mapping (or quarantine) → Attendance Authority ingest_punch → projection → approve_day → payroll snapshot`

Unknown `device_user_id` never auto-creates employees; quarantine then map-and-replay.

## Privacy threat model (tests)

| Control | Evidence |
|---|---|
| Reject fingerprint_image / template / face_image | PASS privacy hard-fail biotime + csv |
| Event metadata only (card/face/biometric type) | PASS capture methods without payloads |
| No biometric in raw_ref | PASS |

## Connector health model

`ConnectorHealth`: connector_id, version, company_code, status (`ok|degraded|error|offline`), last_sync_at, last_success_at, lag_seconds, events_in_window, error_count, last_error, checkpoint, auth_expires_at.

## Proven scenarios

BioTime normal + overnight · RFID/card + face/fingerprint **type** metadata · duplicate pulls · pagination + checkpoint resume · agent offline queue + reconnect · invalid creds + rotation · unknown user quarantine + mapping replay · CSV duplicate across files · XLSX · SFTP file resume · privacy hard-fail · authority projection 480 · payroll snapshot exact · locked snapshot unchanged under reimport · tenant isolation · freezes green.

## GO / NO-GO — WATHEFNI-only synthetic BioTime production canary

**CONDITIONAL GO** for a **synthetic-only** production canary, subject to:

1. Production still `SYNTHETIC_ONLY=on` + ATTW1C/ATTW2B markers (no real employees)  
2. Agent pointed at a **fixture or lab BioTime**, not a live customer device  
3. Separate Wave 2C deploy pack + backup/rollback (not done in 2B)  
4. Real customer device connection remains **NO-GO**  
5. Real clocking / import / QR / GPS / kiosk remain **OFF**

Capture readiness for real WATHEFNI employees: **NO-GO**.

## Non-goals confirmed

No deploy · no real device · no real clocking · no QR/GPS/kiosk UI · no frozen-module changes · BioTime remains biometric authority; Wathefni stores events only.
