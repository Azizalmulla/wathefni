# Employee Payslips P0 — Qualification Report

**Verdict: PASS**  
**Stamp:** `20260807T203541Z`  
**Company:** WATHEFNI canary  
**Smoke:** 85 PASS / 0 FAIL

## Authority model

Employee-visible **iff** `status=active AND employee_visibility=released`.

| Facing state | Rule |
|---|---|
| not_released | active + not_released |
| released | active + released |
| replaced | status=replaced |
| revoked | status=revoked |

Period `open|locked|closed` never implies visibility. Generate never auto-releases. Release is deliberate + idempotent. Replace starts not_released (must re-release). Unrelease withdraws app visibility. Revoke removes employee visibility; history retained.

## Evidence path

`ops/evidence/employee-payslips-p0-20260807T203541Z/`

- `results.json` / `smoke.log`
- `docs/EMPLOYEE_PAYSLIPS_P0.md`
- `sources/smoke-test-employee-payslips-p0.py`
- Dashboard: `PostHire-C4jIRIa-.js`
- Rollback: `/opt/wathefni/backups/production-pre-employee-payslips-p0-20260807T202829Z/ROLLBACK.sh`

## Deployed

| Surface | Detail |
|---|---|
| Backend | release columns + `/app/payslips*` + HR release/unrelease + `payslip_ready` notify |
| Dashboard | PayslipWorkspace employee-visibility column + Release/Withdraw |
| Mobile OTA | canary group `7fb336c2-7454-4537-a11f-e36457c61571` · runtime 0.1.0 · no native build |

## Prove matrix (PASS)

- Draft/unreleased invisible (API + list)
- Explicit HR release → owner-only visibility
- Peer detail/download 404
- Duplicate release idempotent
- Replace → prior replaced; new needs re-release; history ≥2
- Unrelease / revoke → unavailable
- Payroll module off → feature contract disabled
- EN/AR honesty + catalog `Payslip ready` / `كشف الراتب جاهز`
- Notify deep_link `/payslips`

## Official download blockers

1. Official PDF generation + signed storage  
2. Authoritative money for native (or external-only release)  
3. Real `payment_date` field  
4. Production non-synthetic payroll authority (Wave 3 still synthetic-only)

Download today = statement summary `.txt` with honesty banner (`official_document=false`). No invented payment date.

## Next

Do **not** start Auth Wave 2 Phase 6 or wider P1 Employee App roadmap from this wave.
