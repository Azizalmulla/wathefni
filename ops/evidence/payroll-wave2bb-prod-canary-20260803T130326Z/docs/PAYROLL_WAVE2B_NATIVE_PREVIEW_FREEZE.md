# Payroll Wave 2B — Native Preview Engine Freeze

**Gate:** `PROD_SYNTHETIC_PAYROLL_WAVE2B_GO`  
**Evidence:** `ops/evidence/payroll-wave2bb-prod-canary-20260803T130326Z/`  
**Staging evidence:** `ops/evidence/payroll-wave2b-20260803T125550Z/`  
**Freeze:** **GO** for Wave 2B native payroll preview (synthetic-only production posture)

## Frozen posture

- Deterministic preview engine only (`payroll_preview_policy@1.0.0`); **no AI calculations**
- Previews are **non-authoritative**; `payment_processing=disabled`
- Production flags: `WATHEFNI_PAYROLL_WAVE2B=1`, `SYNTHETIC_ONLY=1`, markers `PYW2B`/`PYW1`/`W2BB`, phones `965541*`/`965539*`
- New tables only (`payroll_preview_*`); Wave 1 / Wave 2A / Wave 2A-C DDL and external flows untouched
- No bank files, WPS, remittance, journals, payslips, or payment execution

## Proven on production synthetic

- Migrate/ACK `ACK_PRODUCTION_PAYROLL_W2BB=YES`
- Canary ×2 (before rollback + after redeploy): **65/65** each, residual **0**
- Full-month salary; mid-month join/exit calendar-day proration
- Approved unpaid-leave deductions; fixed allowance/deduction; one-time adjustments
- Missing / overlapping contract fail-closed
- Idempotent calculation; recalculation supersedes prior successful runs only
- KWD 3dp `ROUND_HALF_UP`; fingerprints + audit events
- Counsel-gated blocked as `review_only`: PIFSS, OT premiums, sick-leave fractions, EOS, public-holiday/rest-day pay
- External mode blocks native preview; real employees refused under `SYNTHETIC_ONLY`
- Rollback verified; Wave 1 + Wave 2A retained; Wave 2B drop-in cleared then redeployed
- Sibling freezes green (E360 / Onboarding / Attendance / Leave / Shifts)

## Explicit NO-GO (outside this freeze)

- Payslips or any payment execution
- Authoritative G2N, PIFSS remittance, EOS, bank/WPS, journals
- AI calculations
- Real-employee payroll authority / money movement
- Next payroll wave (not started)

## Rollback

Backup + `ROLLBACK.sh` under `/opt/wathefni/backups/production-pre-payroll-wave2bb-*`  
(Removes Wave 2B drop-in + restores pre-2B-B `app.py`; Wave 1 + Wave 2A drop-ins retained. Preview schema tables remain additive.)
