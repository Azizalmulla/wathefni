# Payroll Wave 2A-D-B — production synthetic qualification

**Stamp:** `20260803T182513Z`  
**Evidence:** `ops/evidence/payroll-wave2adb-prod-canary-20260803T182513Z/`  
**Scope:** External Run Operability (setup, checklist, package honesty, rollback concurrency, pickers, quarantine ack, CSV/EN/AR/mobile)  
**Mode:** production WATHEFNI · **SYNTHETIC_ONLY** · markers **PYW2ADB** / **965540***  

---

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Wave 2A-D operability | **GO** |
| Freeze Wave 2A-D | **GO** |
| Wave 1 + Wave 2A + 2A-C freezes retained | **YES** |
| Real vendor / money / bank / native G2N | **NO-GO** |
| Attendance/leave/shifts package expansion | **NO-GO** |
| Next Payroll / differentiation wave | **NO-GO / not started** |

---

## Migration / ACK

```
wave2a_version 1.0.0
wave2ad_operability 1.0.0
wave1_version 1.0.0
operability_helpers_ok
honesty_ok
connected_db wathefni
quarantine_ack_columns_ok ['acknowledged_at', 'acknowledged_by_phone', 'acknowledgement_reason']
bootstrap_setup_ok
MIGRATE_OK
ACK_PRODUCTION_PAYROLL_W2ADB=YES
```

ACK flags:
```
PAYROLL_WAVE2A 1
SYNTHETIC_ONLY True
markers ('PYW2ADB', 'PYW2ADB-SYNTH|', 'PYW2ACB', 'PYW2ACB-SYNTH|', 'PYW2AB', 'PYW2AB-SYNTH|', 'PYW2A', 'PYW2A-SYNTH|', 'PYW1', 'PYW1-SYNTH|')
honesty {'payment_processing': 'disabled', 'money_authority': 'external', 'wathefni_money_authority': False, 'posts_payment': False, 'vendor_claimed': False, 'bank_files': False, 'ai': False, 'wave1_contracts_unchanged': True, 'wave2a_adapter_contracts_unchanged': True, 'payroll_wave2ad_operability_version': '1.0.0'}
package_attendance_leave_shifts False
flags_ok_synthetic=true
ACK_OK
```

---

## Production flags (after deploy)

```
=== SHAs after ===
1797f463b4563f1cd055a68d5019ea6ea2f1939fcee2ceb577203ae012b8f0ce  /opt/wathefni/orchestrator/app.py
4aba1abdb23229a65532ed497a8abee3042ecb9141e42d92f634fa2fdbd51fcf  /opt/wathefni/orchestrator/payroll_external_adapter_wave2a.py
7a49696446deb6e469a8a4b23e615932b8c849d28f521cbcb3ccc9c49ffd0207  /opt/wathefni/orchestrator/payroll_authority_wave1.py
=== flags after ===
WATHEFNI_ACTION_INBOX_EXCLUDE_PAYROLL=1
WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
WATHEFNI_PAYROLL_FINAL_SCOPE=waves_1_through_5
WATHEFNI_PAYROLL_FINAL_SYNTHETIC=1
WATHEFNI_PAYROLL_FINAL_SYNTHETIC_ONLY=1
WATHEFNI_PAYROLL_WAVE1=1
WATHEFNI_PAYROLL_WAVE1_COMPANIES=WATHEFNI
WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_KEY_MARKERS=PYW1,PYW1-SYNTH|
WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY=1
WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_PHONE_PREFIXES=965539
WATHEFNI_PAYROLL_WAVE2A=1
WATHEFNI_PAYROLL_WAVE2A_COMPANIES=WATHEFNI
WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_KEY_MARKERS=PYW2ADB,PYW2ADB-SYNTH|,PYW2ACB,PYW2ACB-SYNTH|,PYW2AB,PYW2AB-SYNTH|,PYW2A,PYW2A-SYNTH|,PYW1,PYW1-SYNTH|
WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1
WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_PHONE_PREFIXES=965540,965539
WATHEFNI_PAYROLL_WAVE2B=1
WATHEFNI_PAYROLL_WAVE2B_COMPANIES=WATHEFNI
WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_KEY_MARKERS=PYW2B,PYW2B-SYNTH|,PYW1,PYW1-SYNTH|,W2BB
WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_ONLY=1
WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_PHONE_PREFIXES=965541,965539
WATHEFNI_PAYROLL_WAVE3=1
WATHEFNI_PAYROLL_WAVE3_COMPANIES=WATHEFNI
WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_KEY_MARKERS=PYW3,PYW3-SYNTH|,PYW2B,PYW2B-SYNTH|,PYW2A,PYW2ACB,PYW1,PYW1-SYNTH|,W2BB,W3B
WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_ONLY=1
WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_PHONE_PREFIXES=965541,965540,965539
WATHEFNI_PAYROLL_WAVE4=1
WATHEFNI_PAYROLL_WAVE4_COMPANIES=WATHEFNI
WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_KEY_MARKERS=PYW4,PYW4-SYNTH|,PYW3,PYW3-SYNTH|,PYW2B,PYW2B-SYNTH|,PYW2A,PYW2ACB,PYW1,PYW1-SYNTH|,W2BB,W3B,W4B,W4
WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_ONLY=1
WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_PHONE_PREFIXES=965541,965540,965539
WATHEFNI_PAYROLL_WAVE5=1
WATHEFNI_PAYROLL_WAVE5_COMPANIES=WATHEFNI
WATHEFNI_PAYROLL_WAVE5_SYNTHETIC_KEY_MARKERS=PYW5,PYW5-SYNTH|,PYW4,PYW4-SYNTH|,PYW3,PYW3-SYNTH|,PYW2B,PYW2B-SYNTH|,PYW2A,PYW2ACB,PYW1,PYW1-SYNTH|,W2BB,W3B,W4B,W4,W5B,W5
WATHEFNI_PAYROLL_WAVE5_SYNTHETIC_ONLY=1
WATHEFNI_PAYROLL_WAVE5_SYNTHETIC_PHONE_PREFIXES=965541,965540,965539
```

Required:
- `WATHEFNI_PAYROLL_WAVE2A=1`
- `WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1`
- markers include `PYW2ADB`
- `money_authority=external` · `payment_processing=disabled` · `vendor_claimed=false`
- Wave 1 flags remain enabled
- attendance/leave/shifts **not** packaged

Dashboard build: `DASHBOARD_BUILD_OK`

---

## Backup / rollback

- Backup: `/opt/wathefni/backups/production-pre-payroll-wave2adb-20260803T182513Z`
- Rollback executed + verified: **YES**
- Wave 1 + Wave 2A posture retained after Wave 2A-D-B rollback
- Redeploy + second canary completed

---

## Synthetic canary counts

| Pass | Passed | Failed | Residual |
|---|---:|---:|---:|
| Before rollback | 84 | 0 | |
| After redeploy | 84 | 0 | 0 |

Proofs: setup status, guided checklist surface, package-content honesty, tab separation (UI), run pickers (UI), quarantine acknowledgement, CSV guidance (UI), rollback concurrency, EN/AR + mobile, residual cleanup.

---

## EN/AR + mobile

| Check | Result |
|---|---|
| Local UX smoke | PASS |
| Prod UX / dist | PASS · DIST_OPERABILITY_COPY_OK |

---

## Sibling freezes

| Suite | Result |
|---|---|
| Employees 360 (local) | 57/0 |
| Onboarding (local) | 54/0 |
| Attendance (local) | 26/0 |
| Leave (local) | 35/0 |
| Shifts (local) | 96/0 |
| Production freezes + Wave 2A-D honesty | PASS |

---

## Blockers

- None for Wave 2A-D freeze scope.

Real vendor connection, bank files, PIFSS/WPS/EOS/journals, package expansion, and further Payroll waves remain **NO-GO**.
