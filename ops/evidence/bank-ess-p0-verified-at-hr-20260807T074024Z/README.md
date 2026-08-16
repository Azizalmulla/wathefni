# Bank ESS P0 — verified at HR approval (WATHEFNI canary)

**Verdict:** **PASS**  
**Stamp:** `20260807T074024Z`  
**P1 / OCR:** not started  
**Auth Wave 2 Phase 6:** not started  

## Product rule shipped

| Layer | Written by |
|---|---|
| Proposed | Employee submit (sealed) |
| Verified | **HR approval** (`decide` at `pending_hr`) |
| Payroll-effective | **Payroll Apply only** |

Verified remains distinct from payroll-effective. Employee/OCR never write verified or effective rows.

## What changed

### Backend
- `employee_bank_ess.py` — submission states (`pending_hr` / `pending_payroll` / `approved` / `applied`); employee next_step copy (no “Apply”); `has_verified_bank` from verified only; verified display never falls back to effective; KW IBAN always enforced; `needs_review` replaceable; withdraw/onboarding sync; restore superseded verified
- `employee_selfservice_wave5.py` — HR approve → `record_verified(..., stage=hr, supersede_previous=True)`; Apply → effective only (+ legacy verified backfill); withdraw revokes verified + syncs checklist; `needs_review` withdrawable
- `app.py` — bank create response includes `replaced`

### Mobile
- BankView + EN/AR copy for truthful states; separate payroll-effective card
- Profile + Settings permanent Bank entry when feature eligible

### Dashboard
- Bank review state labels/tones + HR approve notice (“verified… not payroll-effective yet”)

### Contract / tests
- `ops/BANK_ESS_AND_ONBOARDING_COMPLETION_CONTRACT.md`
- `ops-smoke-bank-ess-onboarding-qual-matrix.py` (P0 assertions)

## Migrations / data repair

**None.** Soft-revoke / history semantics preserved. No backfill of historical `verified_by_stage=payroll` rows required for canary (Aziz keeps existing verified+effective fingerprint).

## Prove

| Check | Result |
|---|---|
| Qual matrix Bank ESS | **47/47 PASS** |
| Qual matrix onboarding completion | **31/31 PASS** |
| HR approve → verified not effective | PASS |
| Apply → effective | PASS |
| Withdraw → checklist not stuck processing | PASS |
| needs_review replace recovery | PASS |
| KW IBAN enforced at submit | PASS |
| EN next_step has no “Apply” after HR approve | PASS |
| AR next_step | PASS |
| Aziz effective fingerprint unchanged | `0f349ce848ab5e4b` PASS |
| Dashboard needles | PASS |
| Mobile OTA canary | **PASS** group `d73cd3c7-703e-4d66-a865-90d90b925125` |

## Evidence paths

- Local: `ops/evidence/bank-ess-p0-verified-at-hr-20260807T074024Z/`
- Remote: `/opt/wathefni/production-evidence/bank-ess-p0/20260807T074024Z/`
- Backup: `/opt/wathefni/backups/production-pre-bank-ess-p0-20260807T074024Z/`

## Rollback

Restore backed-up `employee_bank_ess.py`, `employee_selfservice_wave5.py`, `app.py` from the backup path; restore prior dashboard www; republish prior OTA if needed; `systemctl restart wathefni-orchestrator`. Allowlists/flags were not rewritten.
