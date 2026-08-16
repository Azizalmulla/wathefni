# Payroll Wave 4-B — production synthetic qualification

**Stamp:** `20260803T135930Z`  
**Evidence:** `ops/evidence/payroll-wave4b-prod-canary-20260803T135930Z/`  
**Scope:** Close + finance export foundation (journal drafts + bank-export contract validation)  
**Mode:** production WATHEFNI · **SYNTHETIC_ONLY** · markers **PYW4/PYW1/W4B** · phones **965541***  

---

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Wave 4 close/export | **GO** |
| Freeze Wave 4 | **GO** |
| Wave 1 + 2A + 2B + 3 freezes retained | **YES** |
| Real bank / WPS / AS’HAL / PIFSS / EOS / payments / AI | **NO-GO** |
| Next payroll wave | **NO-GO / not started** |

---

## Migration / ACK

```
wave4_version 1.0.0
wave3_version 1.0.0
wave2b_version 1.0.0
wave2a_version 1.0.0
wave1_version 1.0.0
honesty_ok {'payment_processing': 'disabled', 'posts_payment': False, 'journal_drafts': True, 'journals': False, 'bank_export_contract': True, 'bank_files': False, 'native_results_authoritative': False, 'external_payroll_authority': 'external', 'ai_calculations': False, 'synthetic_only': True}
connected_db wathefni
wave4_tables ['payroll_account_mappings', 'payroll_bank_export_drafts', 'payroll_close_dual_control', 'payroll_close_run_events', 'payroll_close_runs', 'payroll_finance_exports', 'payroll_journal_drafts', 'payroll_journal_lines']
wave1_2a_2b_3_tables_ok
MIGRATE_OK payroll_close_export_wave4_prod
ACK_PRODUCTION_PAYROLL_W4B=YES
```

ACK flags:
```
PAYROLL_WAVE4 1
SYNTHETIC_ONLY True
enabled True
company True
markers ('PYW4', 'PYW4-SYNTH|', 'PYW3', 'PYW3-SYNTH|', 'PYW2B', 'PYW2B-SYNTH|', 'PYW2A', 'PYW2ACB', 'PYW1', 'PYW1-SYNTH|', 'W2BB', 'W3B', 'W4B', 'W4')
prefixes ('965541', '965540', '965539')
honesty {'payment_processing': 'disabled', 'posts_payment': False, 'journal_drafts': True, 'journals': False, 'bank_export_contract': True, 'bank_files': False, 'bank_connection': False, 'wps': False, 'ashal': False, 'native_results_authoritative': False, 'external_payroll_authority': 'external', 'ai_calculations': False, 'pifss': False, 'eos': False, 'synthetic_only': True}
flags_ok_synthetic=true
ACK_OK
```

---

## Production flags (after deploy)

```
=== SHAs after ===
69cb36ccf0ebc40dd61032b6b05fbd557a040564e5b42752e96b4bba76dcde13  /opt/wathefni/orchestrator/payroll_close_export_wave4.py
03603f36d86b99d95f3f23d78410fba35d58b0c07158750c61c64867878c99a9  /opt/wathefni/orchestrator/app.py
dad1653d287a42533e826b83bc37c6053568eb737df54a69bbade8154b4a1418  /opt/wathefni/orchestrator/payroll_payslip_wave3.py
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
WATHEFNI_PAYROLL_WAVE4=1
WATHEFNI_PAYROLL_WAVE4_COMPANIES=WATHEFNI
WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_KEY_MARKERS=PYW4,PYW4-SYNTH|,PYW3,PYW3-SYNTH|,PYW2B,PYW2B-SYNTH|,PYW2A,PYW2ACB,PYW1,PYW1-SYNTH|,W2BB,W3B,W4B,W4
WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_ONLY=1
WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_PHONE_PREFIXES=965541,965540,965539
```

Required:
- `WATHEFNI_PAYROLL_WAVE4=1`
- `WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_ONLY=1`
- native non-authoritative · external authority retained
- `payment_processing=disabled` · journal drafts only · bank-export contract validation only
- Wave 1 + 2A + 2B + 3 flags remain enabled

---

## Backup / rollback

- Backup: `/opt/wathefni/backups/production-pre-payroll-wave4b-20260803T135930Z`
- Rollback executed + verified: **YES**
- Wave 1 + 2A + 2B + 3 posture retained; Wave 4 drop-in cleared
- Redeploy + second canary completed

---

## Synthetic canary counts

| Pass | Passed | Failed | Residual |
|---|---:|---:|---:|
| Before rollback | 92 | 0 | |
| After redeploy | 92 | 0 | 0 |

Proofs: review→approve→close, immutable snapshots, SOD, dual-approval reopen, balanced journals, fail-closed mappings, export idempotency + fingerprint drift, residual cleanup.

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
| Production freezes + Wave 1/2A/2B/3/4 honesty | PASS |

---

## Blockers

- None for Wave 4 freeze scope.

Real bank integrations, WPS/AS’HAL, PIFSS, EOS, payments, AI, and the next payroll wave remain **NO-GO**.
