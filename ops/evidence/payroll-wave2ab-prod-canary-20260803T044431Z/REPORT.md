# Payroll Wave 2A-B — production synthetic qualification

**Stamp:** `20260803T044431Z`  
**Evidence:** `ops/evidence/payroll-wave2ab-prod-canary-20260803T044431Z/`  
**Module:** `payroll_external_adapter_wave2a.py` **v1.0.0**  
**Mode:** production WATHEFNI · **SYNTHETIC_ONLY** · markers **PYW1-W2AB** / **965540***  

---

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Wave 2A external adapter | **GO** |
| Freeze Wave 2A foundation | **GO** |
| Real vendor / money / bank / native G2N | **NO-GO** |
| Wave 2B native calculations | **NO-GO / not started** |

---

## Migration / ACK

```
wave2a_version 1.0.0
wave1_version 1.0.0
honesty_ok {'payment_processing': 'disabled', 'money_authority': 'external', 'vendor_claimed': False, 'adapter_kind': 'synthetic_csv_sftp'}
connected_db wathefni
adapter_tables ['payroll_adapter_events', 'payroll_adapter_export_runs', 'payroll_adapter_import_lines', 'payroll_adapter_import_runs', 'payroll_adapter_quarantine', 'payroll_adapter_reconciliations']
wave1_contract_cols_ok ['contract_id', 'row_version', 'status']
MIGRATE_OK payroll_external_adapter_wave2a_prod
ACK_PRODUCTION_PAYROLL_W2AB=YES
```

ACK flags:
```
PAYROLL_WAVE2A 1
SYNTHETIC_ONLY True
enabled True
company True
markers ('PYW2AB', 'PYW2AB-SYNTH|', 'PYW2A', 'PYW2A-SYNTH|', 'PYW1', 'PYW1-SYNTH|')
prefixes ('965540', '965539')
honesty {'payment_processing': 'disabled', 'money_authority': 'external', 'wathefni_money_authority': False, 'posts_payment': False, 'vendor_claimed': False, 'bank_files': False, 'native_gross_to_net': False, 'wave1_contracts_unchanged': True, 'synthetic_only': True}
flags_ok_synthetic=true
ACK_OK
```

---

## Production flags (after deploy)

```
=== SHAs after ===
629e36e5cbfb5eb26d7458bc48ef782b9f17c2043ffd9efa9d4a293ff3c2326c  /opt/wathefni/orchestrator/payroll_external_adapter_wave2a.py
7a49696446deb6e469a8a4b23e615932b8c849d28f521cbcb3ccc9c49ffd0207  /opt/wathefni/orchestrator/payroll_authority_wave1.py
=== flags after ===
WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
WATHEFNI_PAYROLL_WAVE1=1
WATHEFNI_PAYROLL_WAVE1_COMPANIES=WATHEFNI
WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_KEY_MARKERS=PYW1,PYW1-SYNTH|
WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY=1
WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_PHONE_PREFIXES=965539
WATHEFNI_PAYROLL_WAVE2A=1
WATHEFNI_PAYROLL_WAVE2A_COMPANIES=WATHEFNI
WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_KEY_MARKERS=PYW2AB,PYW2AB-SYNTH|,PYW2A,PYW2A-SYNTH|,PYW1,PYW1-SYNTH|
WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1
WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_PHONE_PREFIXES=965540,965539
```

Required:
- `WATHEFNI_PAYROLL_WAVE2A=1`
- `WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1`
- `money_authority=external` · `payment_processing=disabled` · `vendor_claimed=false`
- Wave 1 flags remain enabled (foundation freeze)

---

## Backup / rollback

- Backup: `/opt/wathefni/backups/production-pre-payroll-wave2ab-20260803T044431Z`
- Rollback executed + verified: **YES**
- Wave 1 posture retained after Wave 2A-B rollback
- Redeploy + second canary completed

---

## Synthetic canary counts

| Pass | Passed | Failed | Residual |
|---|---:|---:|---:|
| Before rollback | 32 | 0 | |
| After redeploy | 32 | 0 | 0 |

Proofs covered: clean export/import, idempotency, unmatched quarantine, fingerprint drift, reconciliation diffs, malformed quarantine, export rollback, residual cleanup.

---

## Sibling freezes

| Suite | Result |
|---|---|
| Employees 360 (local) | 57/0 |
| Onboarding (local) | 54/0 |
| Attendance (local) | 26/0 |
| Leave (local) | 35/0 |
| Shifts (local) | 96/0 |
| Production freezes | PASS |

---

## Blockers

- None for Wave 2A freeze scope.

Real vendor connection, bank files, PIFSS/WPS/EOS/journals, and Wave 2B native calculations remain **NO-GO**.
