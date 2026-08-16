# Payroll Wave 2B-B — production synthetic qualification

**Stamp:** `20260803T130326Z`  
**Evidence:** `ops/evidence/payroll-wave2bb-prod-canary-20260803T130326Z/`  
**Scope:** Native payroll preview engine (deterministic, non-authoritative)  
**Mode:** production WATHEFNI · **SYNTHETIC_ONLY** · markers **PYW2B/PYW1/W2BB** · phones **965541***  

---

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Wave 2B native preview | **GO** |
| Freeze Wave 2B | **GO** |
| Wave 1 + Wave 2A + Wave 2A-C freezes retained | **YES** |
| Payslips / money / bank / PIFSS / EOS / journals / AI | **NO-GO** |
| Next payroll wave | **NO-GO / not started** |

---

## Migration / ACK

```
wave2b_version 1.0.0
policy payroll_preview_policy@1.0.0
wave1_version 1.0.0
wave2a_version 1.0.0
honesty_ok {'payment_processing': 'disabled', 'authoritative': False, 'preview_only': True, 'ai_calculations': False, 'external_flows_unchanged': True, 'synthetic_only': True}
connected_db wathefni
preview_tables ['payroll_preview_adjustments', 'payroll_preview_employee_results', 'payroll_preview_events', 'payroll_preview_lines', 'payroll_preview_policies', 'payroll_preview_runs']
wave1_wave2a_tables_ok
MIGRATE_OK payroll_native_preview_wave2b_prod
ACK_PRODUCTION_PAYROLL_W2BB=YES
```

ACK flags:
```
PAYROLL_WAVE2B 1
SYNTHETIC_ONLY True
enabled True
company True
markers ('PYW2B', 'PYW2B-SYNTH|', 'PYW1', 'PYW1-SYNTH|', 'W2BB')
prefixes ('965541', '965539')
honesty {'payment_processing': 'disabled', 'authoritative': False, 'preview_only': True, 'ai_calculations': False, 'external_flows_unchanged': True, 'bank_files': False, 'pifss': False, 'synthetic_only': True}
flags_ok_synthetic=true
ACK_OK
```

---

## Production flags (after deploy)

```
=== SHAs after ===
2470298b86bd6a282cfe87c03ffbf11f41f1e53fd82c75854e754d0f79fbc62e  /opt/wathefni/orchestrator/payroll_native_preview_wave2b.py
f8c2b134088f647bd44483df7e013400425fefbdbcb122aae2e46cc3b611f1fc  /opt/wathefni/orchestrator/app.py
7a49696446deb6e469a8a4b23e615932b8c849d28f521cbcb3ccc9c49ffd0207  /opt/wathefni/orchestrator/payroll_authority_wave1.py
4540e93c8a01c3b95642f35ab0483498198b0f085f9789a4e73f5914bdc67773  /opt/wathefni/orchestrator/payroll_external_adapter_wave2a.py
=== flags after ===
WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
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
WATHEFNI_PAYROLL_WAVE2B=1
WATHEFNI_PAYROLL_WAVE2B_COMPANIES=WATHEFNI
WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_KEY_MARKERS=PYW2B,PYW2B-SYNTH|,PYW1,PYW1-SYNTH|,W2BB
WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_ONLY=1
WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_PHONE_PREFIXES=965541,965539
```

Required:
- `WATHEFNI_PAYROLL_WAVE2B=1`
- `WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_ONLY=1`
- markers include `PYW2B` / `PYW1` / `W2BB`
- `authoritative=false` · `payment_processing=disabled` · `preview_only=true` · `ai_calculations=false`
- Wave 1 + Wave 2A flags remain enabled

---

## Backup / rollback

- Backup: `/opt/wathefni/backups/production-pre-payroll-wave2bb-20260803T130326Z`
- Rollback executed + verified: **YES**
- Wave 1 + Wave 2A posture retained; Wave 2B drop-in cleared
- Redeploy + second canary completed

---

## Synthetic canary counts

| Pass | Passed | Failed | Residual |
|---|---:|---:|---:|
| Before rollback | 65 | 0 | |
| After redeploy | 65 | 0 | 0 |

Proofs: full-month, join/exit proration, unpaid leave, fixed components, missing/overlap denial, idempotency, recalculation, KWD 3dp, counsel-gated blocked, rollback, residual cleanup.

---

## Sibling freezes

| Suite | Result |
|---|---|
| Employees 360 (local) | 57/0 |
| Onboarding (local) | 54/0 |
| Attendance (local) | 26/0 |
| Leave (local) | 35/0 |
| Shifts (local) | 96/0 |
| Production freezes + Wave 1/2A/2B honesty | PASS |

---

## Blockers

- None for Wave 2B freeze scope.

Payslips, bank/WPS, PIFSS remittance, EOS, journals, payments, AI calculations, and the next payroll wave remain **NO-GO**.
