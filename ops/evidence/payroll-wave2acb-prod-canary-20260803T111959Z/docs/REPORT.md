# Payroll Wave 2A-C-B — production synthetic qualification

**Stamp:** `20260803T111959Z`  
**Evidence:** `ops/evidence/payroll-wave2acb-prod-canary-20260803T111959Z/`  
**Scope:** External payroll operations workflow (UI + APIs + ops helpers)  
**Mode:** production WATHEFNI · **SYNTHETIC_ONLY** · markers **PYW1-W2ACB** / **965540***  

---

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Wave 2A-C ops workflow | **GO** |
| Freeze Wave 2A-C | **GO** |
| Wave 1 + Wave 2A freezes retained | **YES** |
| Real vendor / money / bank / native G2N | **NO-GO** |
| Wave 2B native calculations | **NO-GO / not started** |

---

## Migration / ACK

```
wave2a_version 1.0.0
wave1_version 1.0.0
ops_helpers_ok
honesty_ok {'payment_processing': 'disabled', 'money_authority': 'external', 'vendor_claimed': False, 'adapter_kind': 'synthetic_csv_sftp'}
connected_db wathefni
adapter_tables ['payroll_adapter_events', 'payroll_adapter_export_runs', 'payroll_adapter_import_lines', 'payroll_adapter_import_runs', 'payroll_adapter_quarantine', 'payroll_adapter_reconciliations']
wave1_contract_cols_ok ['contract_id', 'row_version', 'status']
routes_present ['/dashboard/posthire/payroll/external', '/dashboard/posthire/payroll/external/events', '/dashboard/posthire/payroll/external/exports', '/dashboard/posthire/payroll/external/quarantine', '/dashboard/posthire/payroll/external/readiness']
MIGRATE_OK payroll_external_ops_wave2ac_prod
ACK_PRODUCTION_PAYROLL_W2ACB=YES
```

ACK flags:
```
PAYROLL_WAVE2A 1
SYNTHETIC_ONLY True
enabled True
company True
markers ('PYW2ACB', 'PYW2ACB-SYNTH|', 'PYW2AB', 'PYW2AB-SYNTH|', 'PYW2A', 'PYW2A-SYNTH|', 'PYW1', 'PYW1-SYNTH|')
prefixes ('965540', '965539')
honesty {'payment_processing': 'disabled', 'money_authority': 'external', 'wathefni_money_authority': False, 'posts_payment': False, 'vendor_claimed': False, 'bank_files': False, 'native_gross_to_net': False, 'wave1_contracts_unchanged': True, 'synthetic_only': True}
flags_ok_synthetic=true
ACK_OK
```

---

## Production flags (after deploy)

```
=== SHAs after ===
f44118ded8ca1276013e4b25e6125580608522f9878037021bb0bab8fda6e035  /opt/wathefni/orchestrator/app.py
4540e93c8a01c3b95642f35ab0483498198b0f085f9789a4e73f5914bdc67773  /opt/wathefni/orchestrator/payroll_external_adapter_wave2a.py
7a49696446deb6e469a8a4b23e615932b8c849d28f521cbcb3ccc9c49ffd0207  /opt/wathefni/orchestrator/payroll_authority_wave1.py
=== flags after ===
WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
WATHEFNI_PAYROLL_WAVE1=1
WATHEFNI_PAYROLL_WAVE1_COMPANIES=WATHEFNI
WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_KEY_MARKERS=PYW1,PYW1-SYNTH|
WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY=1
WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_PHONE_PREFIXES=965539
WATHEFNI_PAYROLL_WAVE2A=1
WATHEFNI_PAYROLL_WAVE2A_COMPANIES=WATHEFNI
WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_KEY_MARKERS=PYW2ACB,PYW2ACB-SYNTH|,PYW2AB,PYW2AB-SYNTH|,PYW2A,PYW2A-SYNTH|,PYW1,PYW1-SYNTH|
WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1
WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_PHONE_PREFIXES=965540,965539
```

Required:
- `WATHEFNI_PAYROLL_WAVE2A=1`
- `WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1`
- markers include `PYW2ACB` (+ Wave 2A/Wave 1 markers)
- `money_authority=external` · `payment_processing=disabled` · `vendor_claimed=false`
- Wave 1 flags remain enabled

Dashboard build: `DASHBOARD_BUILD_OK`

---

## Backup / rollback

- Backup: `/opt/wathefni/backups/production-pre-payroll-wave2acb-20260803T111959Z`
- Rollback executed + verified: **YES**
- Wave 1 + Wave 2A posture retained after Wave 2A-C-B rollback
- Redeploy + second canary completed

---

## Synthetic canary counts

| Pass | Passed | Failed | Residual |
|---|---:|---:|---:|
| Before rollback | 50 | 0 | |
| After redeploy | 50 | 0 | 0 |

Proofs: readiness, assemble/export, upload/replace, quarantine, reconciliation, fingerprint drift, history/events, manager empty scope, permissions/routes, residual cleanup.

---

## EN/AR + mobile

| Check | Result |
|---|---|
| Local UX smoke | PASS |
| Prod UX + dist | PASS (DIST_COPY_OK) |

---

## Sibling freezes

| Suite | Result |
|---|---|
| Employees 360 (local) | 57 passed / 0 failed |
| Onboarding (local) | 54 passed / 0 failed |
| Attendance (local) | 26 passed / 0 failed |
| Leave (local) | 35 passed / 0 failed |
| Shifts (local) | 96 passed / 0 failed |
| Production freezes + Wave 2A honesty | PASS |

---

## Blockers

- None for Wave 2A-C freeze scope.

Real vendor connection, bank files, PIFSS/WPS/EOS/journals, and Wave 2B native calculations remain **NO-GO**.
