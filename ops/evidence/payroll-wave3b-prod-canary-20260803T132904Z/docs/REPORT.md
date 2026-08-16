# Payroll Wave 3-B — production synthetic qualification

**Stamp:** `20260803T132904Z`  
**Evidence:** `ops/evidence/payroll-wave3b-prod-canary-20260803T132904Z/`  
**Scope:** Payslip documents (native preview + external mirror)  
**Mode:** production WATHEFNI · **SYNTHETIC_ONLY** · markers **PYW3/PYW1/W3B** · phones **965541***  

---

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Wave 3 payslips | **GO** |
| Freeze Wave 3 | **GO** |
| Wave 1 + 2A + 2A-C + 2B freezes retained | **YES** |
| Bank / WPS / PIFSS / EOS / journals / payments / AI | **NO-GO** |
| Next payroll wave | **NO-GO / not started** |

---

## Migration / ACK

```
wave3_version 1.0.0
wave2b_version 1.0.0
wave2a_version 1.0.0
wave1_version 1.0.0
honesty_ok {'payment_processing': 'disabled', 'payslips_as_money': False, 'native_payslips_authoritative': False, 'external_payslips_authority': 'external', 'ai_calculations': False, 'synthetic_only': True}
connected_db wathefni
payslip_tables ['payroll_payslip_documents', 'payroll_payslip_events', 'payroll_payslip_lines']
wave1_2a_2b_tables_ok
MIGRATE_OK payroll_payslip_wave3_prod
ACK_PRODUCTION_PAYROLL_W3B=YES
```

ACK flags:
```
PAYROLL_WAVE3 1
SYNTHETIC_ONLY True
enabled True
company True
markers ('PYW3', 'PYW3-SYNTH|', 'PYW2B', 'PYW2B-SYNTH|', 'PYW2A', 'PYW2ACB', 'PYW1', 'PYW1-SYNTH|', 'W2BB', 'W3B')
prefixes ('965541', '965540', '965539')
honesty {'payment_processing': 'disabled', 'payslips_as_money': False, 'native_payslips_authoritative': False, 'external_payslips_authority': 'external', 'ai_calculations': False, 'bank_files': False, 'synthetic_only': True}
flags_ok_synthetic=true
ACK_OK
```

---

## Production flags (after deploy)

```
=== SHAs after ===
dad1653d287a42533e826b83bc37c6053568eb737df54a69bbade8154b4a1418  /opt/wathefni/orchestrator/payroll_payslip_wave3.py
37dd6393958131176ab93a70616a6ef992ce30a65ab3f5339270bc0fb8a5a4e1  /opt/wathefni/orchestrator/app.py
2470298b86bd6a282cfe87c03ffbf11f41f1e53fd82c75854e754d0f79fbc62e  /opt/wathefni/orchestrator/payroll_native_preview_wave2b.py
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
WATHEFNI_PAYROLL_WAVE3=1
WATHEFNI_PAYROLL_WAVE3_COMPANIES=WATHEFNI
WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_KEY_MARKERS=PYW3,PYW3-SYNTH|,PYW2B,PYW2B-SYNTH|,PYW2A,PYW2ACB,PYW1,PYW1-SYNTH|,W2BB,W3B
WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_ONLY=1
WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_PHONE_PREFIXES=965541,965540,965539
```

Required:
- `WATHEFNI_PAYROLL_WAVE3=1`
- `WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_ONLY=1`
- native payslips non-authoritative · external authority retained
- `payment_processing=disabled` · `payslips_as_money=false`
- Wave 1 + 2A + 2B flags remain enabled

---

## Backup / rollback

- Backup: `/opt/wathefni/backups/production-pre-payroll-wave3b-20260803T132904Z`
- Rollback executed + verified: **YES**
- Wave 1 + 2A + 2B posture retained; Wave 3 drop-in cleared
- Redeploy + second canary completed

---

## Synthetic canary counts

| Pass | Passed | Failed | Residual |
|---|---:|---:|---:|
| Before rollback | 51 | 0 | |
| After redeploy | 51 | 0 | 0 |

Proofs: native preview payslip, external imported payslip, scope/permissions, EN/AR download, mobile UX, replace/revoke/history, idempotency, residual cleanup.

---

## EN/AR + mobile

| Check | Result |
|---|---|
| Local UX smoke | PASS |
| Prod UX smoke | PASS |

---

## Sibling freezes

| Suite | Result |
|---|---|
| Employees 360 (local) | 57/0 |
| Onboarding (local) | 54/0 |
| Attendance (local) | 26/0 |
| Leave (local) | 35/0 |
| Shifts (local) | 96/0 |
| Production freezes + Wave 1/2A/2B/3 honesty | PASS |

---

## Blockers

- None for Wave 3 freeze scope.

Bank/WPS, PIFSS remittance, EOS, journals, payments, AI calculations, and the next payroll wave remain **NO-GO**.
