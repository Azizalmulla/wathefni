# Attendance final — production promotion & freeze

**Stamp:** `20260802T131146Z`  
**Evidence:** `ops/evidence/attendance-final-20260802T131146Z/`  
**Remote:** `/opt/wathefni/production-evidence/attendance-final/20260802T131146Z/`  
**Company:** WATHEFNI only  

---

## Verdicts (separate)

| Gate | Verdict |
|---|---|
| **HR production Attendance use** | **GO** — Wave 4B daily board, exceptions/corrections, disputes, dual approval + separate apply, payroll exclusion/lock UX, connector health (synthetic) live on production dashboard |
| **Manager production Attendance use** | **GO (scoped)** — manager scope + self-correction denial proven in Wave 4B / final canary; no broad manager enablement beyond existing scoped ops |
| **Real employee clocking** | **NO-GO / disabled** |
| **Real device ingestion** | **NO-GO** — `WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off` |
| **Attendance-to-Payroll authority** | **GO for approved synthetic eligibility snapshots only** — **NO-GO** for real payroll money impact (timesheet fingerprint unchanged) |
| **Overall Attendance completion** | **GO for controlled WATHEFNI HR/manager UX + synthetic ops** — formally **frozen**. Not a broad clocking/device/QR/GPS/kiosk rollout |

---

## Production SHAs (after promote)

| Artifact | SHA256 |
|---|---|
| `PostHire-D8YjEnpm.js` | `2f4cfd5303727e59839a180d7bac2d4a227b01703c25e3c102e0546e547ae5f6` |
| `attendance_ops_wave3.py` | `5be5770f27de36d2933a6f37e85d72bd2677887097fc8cec4e6fe53d63bbce1f` |
| `attendance_authority_wave1.py` | `5e9c2780499a59c9799e0e4d8f194f33c9b4647e461094d50e4e3cfe61657f02` |

Pre-promote PostHire (rollback target): `PostHire-BrW2GlcR.js` = `0f13238daf5431b087da549c57abf17e3eb890453302af21ce409c7d64c349aa`

Bundle markers verified: Attendance operations / عمليات الحضور / Connector health / Day detail / Approved — ready to apply.

---

## Production flags (live)

```
WATHEFNI_ATTENDANCE_AUTHORITY=on
WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES=WATHEFNI
WATHEFNI_ATTENDANCE_AUTHORITY_STORE=postgres
WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY=on
WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_KEY_MARKERS=ATTW1C,ATTW2C,ATTW2E,ATTW2G,ATTW3,ATTW4B,W1C-SYNTH|,W2C-SYNTH|,W2E-SYNTH|,W2G-SYNTH|,W3-SYNTH|
WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965524
WATHEFNI_ATTENDANCE_OPS=on
WATHEFNI_ATTENDANCE_OPS_COMPANIES=WATHEFNI
WATHEFNI_ATTENDANCE_OPS_STORE=postgres
WATHEFNI_ATTENDANCE_OPS_SYNTHETIC_ONLY=on
WATHEFNI_ATTENDANCE_OPS_DUAL_APPROVAL_KINDS=absence,early_leave
WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
WATHEFNI_ATTENDANCE_IMPORT=off
WATHEFNI_ATTENDANCE_CAPTURE_OPS=on
WATHEFNI_ATTENDANCE_CAPTURE_OPS_COMPANIES=WATHEFNI
WATHEFNI_ATTENDANCE_CAPTURE_STORE=postgres
```

Freeze drop-in (wins over older wave drop-ins):  
`/etc/systemd/system/wathefni-orchestrator.service.d/zzz-attendance-final-freeze.conf`

Schema snapshot: `remote/schema/attendance-tables.txt`

---

## Backup & rollback proof

| Item | Path / result |
|---|---|
| Backup | `/opt/wathefni/backups/production-pre-attendance-final-20260802T131146Z` |
| ROLLBACK.sh | present + executable |
| Preflight counts | 42 attendance rows / 42 demo_seed / 4 real employees |
| Fingerprint CSV | `attendance-records-fingerprint.csv` in backup |
| Executed rollback | restored `PostHire-BrW2GlcR.js` (`ROLLBACK_OK`) |
| Redeploy | restored `PostHire-D8YjEnpm.js` (`DEPLOY_OK` + `ROLLBACK_REDEPLOY_OK`) |

Evidence: `tests/rollback-redeploy.out`, `remote/verify/rollback.out`, `remote/backup/`

---

## Preflight freezes

| Suite | Result |
|---|---|
| Local Employees 360 freeze | 57 passed, 0 failed |
| Local Onboarding freeze | 54 passed, 0 failed |
| Staging E360 + Onboarding freezes | `STAGING_FREEZES_OK` |
| Local Wave 4B prove | 40/40 |
| Attendance freeze smoke | 26 passed, 0 failed |

---

## Production synthetic canary

**Run:** `remote/canary-rerun/` (authoritative; first canary aborted on cleanup bug, fixed and re-run)  
**Tag:** `98AA2996` · **work_date:** `2026-08-02` · **Result:** **33 passed, 0 failed**

Proved:

- Normal / overnight / multi-session (via Wave 4B seed+prove)
- Paid/unpaid breaks, missing in/out, late, early leave, absence
- Correction request, reject, dual approve, separate apply
- Dispute + reopen; stale conflict; manager self-denial; scope denial
- Payroll lock + exclusion reasons; exact API/UI total reconciliation
- Connector offline / lag / recovered + mapping remediation reject
- Capture ingest remains disabled in overview
- Cleanup: 42 demo rows unchanged; four reals fingerprint unchanged; payroll timesheets unchanged; no ATTW4B projection/exception residue
- Employees 360 + Onboarding freeze regressions green on production

---

## Authenticated UI evidence

8 authenticated screenshots (EN/AR × desktop/mobile) with **12** synthetic daily-board rows (tag `7700A6A9`), then cleaned to 42/42:

- `screenshots/daily-board-en-desktop.png`
- `screenshots/daily-board-en-mobile.png`
- `screenshots/daily-board-ar-desktop.png`
- `screenshots/daily-board-ar-mobile.png`
- `screenshots/ops-en-desktop.png` / `ops-en-mobile.png`
- `screenshots/ops-ar-desktop.png` / `ops-ar-mobile.png`

`manifest.json`: `authenticated=true`, `ingest_enabled=false`, `attw4b_rows=12`  
Cleanup: `SCREENSHOTS_CLEANUP_OK` → `{rows:42, demo:42}`

Note: day-detail / connector-health dedicated crops were not always click-captured; connector remediation was proven in the HTTP canary. Full-page board+ops shots are the UI evidence set.

---

## Cleanup proof

- Canary cleanup JSON: `remote/canary-rerun/cleanup.json`
- Screenshot seed cleanup deleted ATTW4B punches/projections/cases + capture lab site/device/connector for UI prefix
- Final posture assert: `attw4b_left=0`, rows=42, demo=42, four=4
- Immutable Wave 2F `attendance_capture_audit_events` are intentionally not deleted (append-only); no demo/payroll/real-employee mutation

---

## Remaining controlled-rollout limits

Still **off / forbidden** without a new owner-approved wave:

1. Real punch ingest (`CAPTURE_INGEST`)
2. Real biometric / device connectivity
3. Employee clocking (app), QR, GPS, kiosk
4. Broad multi-company Attendance enablement beyond WATHEFNI
5. Real payroll money posting from attendance
6. Weakening punch immutability, approve≠apply, dual approval, manager self-denial, payroll locks, tenant isolation, or secret redaction
7. Changes to frozen Employees 360 or Onboarding to unblock Attendance

---

## Freeze gates added

- Authority doc: `ops/ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md` (also `/opt/wathefni/ops/`)
- Cursor rule: `.cursor/rules/attendance-freeze.mdc`
- Regression smoke: `wathefni-orchestrator/smoke-test-attendance-freeze-regression.py`

**Attendance is formally frozen** at this controlled WATHEFNI production posture.
